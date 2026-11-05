"""Nhập dữ liệu theo lô (PLAN §5).

    upload ──► staged ──xác nhận──► committed ──hoàn tác──► rolled_back
                 ├─ đọc/kiểm tra lỗi ─► failed
                 └─ hủy (hoặc chờ > 24h) ─► discarded

Mẫu tải append-only: lô staged chưa ảnh hưởng số liệu; util_effective (VIEW) tự lấy lô committed mới nhất.
Mọi việc đọc file & chuẩn hóa đi qua gpu_core. File gốc luôn lưu ở data/uploads/<sha256>.xlsx.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import openpyxl
import pandas as pd
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import gpu_core as g
from app.config import ROOT_DIR, Settings
from app.db.models import ImportBatch
from app.errors import ServiceError
from app.repo import batch_repo, inventory_repo, settings_repo, util_repo
from app.repo.convert import jsonable, py
from app.scope import CurrentUser
from app.services import import_checks as checks
from app.services import inventory_service
from app.services.analytics_service import rule_params
from gpu_core.parsing import INVENTORY_SHEET, RAW_SHEET_NAMES, norm_key

log = logging.getLogger(__name__)

KIND_VTNET = "vtnet_util"
KIND_INVENTORY = "inventory"
KIND_VI = {KIND_VTNET: "File tải VTNet", KIND_INVENTORY: "File thống kê server"}
STATUS_VI = {
    "staged": "chờ xác nhận",
    "committed": "đã nhập",
    "rolled_back": "đã hoàn tác",
    "failed": "lỗi",
    "discarded": "đã hủy",
}
STALE_STAGED = timedelta(hours=24)
INVENTORY_COLUMNS = [
    "stt", "server_class", "config", "cpu", "ram", "disk", "hba", "gpu_spec", "gpu_count", "gpu_model",
    "serial", "owner", "model", "input_load", "service", "managed_by", "cluster",
]  # fmt: skip


class StagingError(Exception):
    """Lỗi nội dung file khi tạo lô → lô ghi trạng thái failed."""


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ------------------------------------------------------------------ file


def _store_file(upload_dir: Path, sha256: str, data: bytes) -> Path:
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{sha256}.xlsx"
    if not dest.exists():
        tmp = dest.with_suffix(".part")
        tmp.write_bytes(data)
        os.replace(tmp, dest)
    return dest


def _stored_path(path: Path) -> str:
    """Lưu đường dẫn tương đối gốc repo nếu được (vd data/uploads/<sha>.xlsx) — dễ chuyển máy/GĐ2."""
    try:
        return path.resolve().relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def resolve_file(batch: ImportBatch) -> Path:
    p = Path(batch.file_path)
    return p if p.is_absolute() else ROOT_DIR / p


def detect_kind(path: Path) -> tuple[str | None, list[str]]:
    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        sheets = list(wb.sheetnames)
    finally:
        wb.close()
    keys = {norm_key(n) for n in sheets}
    if keys & set(RAW_SHEET_NAMES):
        return KIND_VTNET, sheets
    if norm_key(INVENTORY_SHEET) in keys:
        return KIND_INVENTORY, sheets
    return None, sheets


# ------------------------------------------------------------------ staging


def stage_upload(
    s: Session, *, settings: Settings, user: CurrentUser, file_name: str, data: bytes, now: datetime | None = None
) -> ImportBatch:
    now = now or utcnow()
    name = Path(file_name.replace("\\", "/")).name or "upload.xlsx"
    if not name.lower().endswith(".xlsx"):
        raise ServiceError(422, "Chỉ nhận file Excel .xlsx.")
    if not data:
        raise ServiceError(422, "File rỗng.")
    sha256 = hashlib.sha256(data).hexdigest()
    path = _store_file(settings.upload_path, sha256, data)
    try:
        kind, sheets = detect_kind(path)
    except Exception as exc:  # zip hỏng, không phải xlsx…
        raise ServiceError(422, "Không đọc được file như Excel .xlsx (file hỏng hoặc sai định dạng).") from exc
    if kind is None:
        raise ServiceError(
            422,
            "Không nhận diện được loại file: cần sheet 'server_raw' hoặc 'VTT_GPU_Server_RAW' (file tải VTNet), "
            f"hoặc '{INVENTORY_SHEET}' (file thống kê). File có các sheet: {sheets}",
        )
    dup = batch_repo.find_committed(s, kind, sha256)
    if dup is not None:
        when = f", xác nhận ngày {dup.committed_at:%d/%m/%Y}" if dup.committed_at else ""
        raise ServiceError(409, f"File đã được nhập (lô #{dup.id}{when}).")

    def new_batch(status: str) -> ImportBatch:
        return ImportBatch(
            kind=kind,
            file_name=name,
            file_sha256=sha256,
            file_path=_stored_path(path),
            status=status,
            summary={},
            validation={},
            uploaded_by=user.username,
            uploaded_at=now,
        )

    batch = new_batch("staged")
    s.add(batch)
    try:
        s.flush()
        if kind == KIND_VTNET:
            _stage_vtnet(s, batch, path)
        else:
            _stage_inventory(s, batch, path, sheets)
        s.commit()
    except (StagingError, ValueError) as exc:
        _record_failure(s, new_batch("failed"), str(exc))
    except Exception as exc:
        log.exception("Lỗi khi tạo lô từ %s", name)
        _record_failure(s, new_batch("failed"), f"Lỗi không mong đợi khi đọc file: {exc.__class__.__name__}")
    log.info("Lô #%s (%s) %s: %s", batch.id, kind, batch.status, name)
    return batch


def _record_failure(s: Session, failed: ImportBatch, message: str) -> None:
    s.rollback()
    failed.validation = {"error": message}
    s.add(failed)
    s.commit()
    raise ServiceError(422, f"{message} (đã ghi lô #{failed.id} trạng thái lỗi)")


def _stage_vtnet(s: Session, batch: ImportBatch, path: Path) -> None:
    wb = g.read_vtnet_workbook(path)
    raw = wb.raw
    if raw.empty:
        why = "; ".join(wb.warnings) or "sheet không có dòng dữ liệu nào"
        raise StagingError(
            f"Sheet '{wb.sheet_names.get('raw')}' không còn dòng hợp lệ nào — {why}. "
            "Cột gpu/mem phải là số (0–100), date_hour là ngày, host_ip là IPv4."
        )
    start, end = wb.period
    ips = sorted(raw["ip"].unique())

    prev = batch_repo.latest_committed(s, KIND_VTNET)
    prev_ips = util_repo.batch_ips(s, prev.id) if prev else set()
    eff = util_repo.effective_frame(s, start, end, ips)
    both = raw[["ip", "ts", "gpu", "mem"]].merge(
        eff[["ip", "ts", "gpu", "mem"]], on=["ip", "ts"], suffixes=("", "_old")
    )
    changed = ((both["gpu"] - both["gpu_old"]).abs() > 1e-9) | ((both["mem"] - both["mem_old"]).abs() > 1e-9)

    models: dict[str, dict[str, int]] = {}
    for spec in raw.sort_values("ts").groupby("ip")["gpu_type"].last():
        count, model = g.parse_gpu_spec(spec)
        m = models.setdefault(model or "(không rõ)", {"servers": 0, "cards": 0})
        m["servers"] += 1
        m["cards"] += count or 0

    # --- kiểm tra + xem trước tác động (Roadmap §14.1) — cùng T mặc định & tham số luật của cài đặt
    settings = settings_repo.all_values(s)
    t = float(settings.get("default_threshold", g.DEFAULT_THRESHOLD))
    params = rule_params(settings)
    pv = checks.preview(raw, start.date(), end.date(), t, params)
    prev_pv: dict[str, Any] | None = None
    if prev is not None and prev.period_start and prev.period_end:
        prev_raw = util_repo.effective_frame(s, prev.period_start, prev.period_end)
        prev_pv = checks.preview(prev_raw, prev.period_start, prev.period_end, t, params)
        prev_pv.pop("daily", None)
        prev_pv.update(
            n_ips=len(prev_ips), label=prev.period_label, period_start=prev.period_start.isoformat(),
            period_end=prev.period_end.isoformat(), batch_id=prev.id,
        )  # fmt: skip
    overview = None if wb.overview is None else g.validate_overview(raw, wb.overview)
    daily = None if wb.daily is None else g.validate_daily(raw, wb.daily)
    new_ips = sorted(set(ips) - prev_ips) if prev else []
    gone_ips = sorted(prev_ips - set(ips)) if prev else []
    overlap_days = sorted({d.date().isoformat() for d in both["ts"]})
    days = sorted({d.date() for d in raw["ts"].dt.normalize().unique()})
    label = checks.period_label(start.date(), end.date(), days, wb.dominant_month)
    coverage = [(b.period_start, b.period_end) for b in batch_repo.committed_batches(s, KIND_VTNET)
                if b.period_start and b.period_end]  # fmt: skip
    found = checks.run_checks(
        file_name=batch.file_name, wb=wb, raw=raw, start=start, end=end, today=checks.today(),
        prev=prev_pv, new_ips=new_ips, gone_ips=gone_ips, replaced=int(changed.sum()), overlap_days=overlap_days,
        overview=overview, pv=pv, daily=daily, label=label, coverage=coverage,
    )  # fmt: skip

    batch.schema_version = wb.schema
    batch.period_start, batch.period_end = start.date(), end.date()
    batch.period_label = label
    batch.summary = jsonable(
        {
            "schema": wb.schema,
            "rows": len(raw),
            "n_ips": len(ips),
            "days": int(raw["ts"].dt.normalize().nunique()),
            "granularity": "hour" if bool((raw["ts"] != raw["ts"].dt.normalize()).any()) else "day",
            "gpu_models": dict(sorted(models.items())),
            "prev_batch_id": prev.id if prev else None,
            "new_ips": sorted(set(ips) - prev_ips) if prev else [],
            "gone_ips": sorted(prev_ips - set(ips)) if prev else [],
            "overlap_days": sorted({d.date().isoformat() for d in both["ts"]}),
            "overlap_samples": len(both),
            "replaced": int(changed.sum()),
            "reclaimed": None if wb.reclaimed is None else int(wb.reclaimed["ip"].nunique()),
            "preview": pv,
            "previous": prev_pv,
        }
    )
    batch.validation = jsonable(
        {
            "checks": [c.as_dict() for c in found],
            "overview": overview,
            "daily_check": daily,
            "overview_total": None
            if wb.overview_total is None
            else {"gpu": wb.overview_total[0], "mem": wb.overview_total[1]},
            "warnings": wb.warnings,
            "ignored_sheets": wb.ignored_sheets,
            "sheets_used": wb.sheet_names,
        }
    )
    util_repo.insert_samples(s, batch.id, raw)
    if wb.overview is not None:
        util_repo.insert_overview(s, batch.id, wb.overview)
    if wb.reclaimed is not None:
        util_repo.insert_reclaim(s, batch.id, wb.reclaimed)


def _stage_inventory(s: Session, batch: ImportBatch, path: Path, sheets: list[str]) -> None:
    inv = g.read_inventory(path)
    if "owner" not in inv.columns:
        raise StagingError(f"Thiếu cột 'Đầu mối sử dụng' trong sheet '{INVENTORY_SHEET}'.")
    if inv.empty:
        raise StagingError("Không có dòng nào có IP hợp lệ.")
    dup = inv[inv["ip"].duplicated(keep=False)]
    if not dup.empty:
        parts = [
            f"{ip} (dòng Excel {', '.join(str(r) for r in grp['excel_row'])})"
            for ip, grp in dup.groupby("ip", sort=True)
        ]
        raise StagingError(f"IP trùng trong file thống kê — sửa file rồi nhập lại: {'; '.join(parts)}")

    prev = batch_repo.latest_committed(s, KIND_INVENTORY)
    current = inventory_repo.current_ips(s)
    linked = inventory_repo.linked_inventory_ips(s)
    ips = set(inv["ip"])
    extra_cols = [c for c in inv.attrs.get("extra_columns", []) if c in inv.columns]
    if "assessment" in inv.columns:
        extra_cols.append("assessment")

    rows: list[dict[str, Any]] = []
    for r in inv.to_dict("records"):
        row: dict[str, Any] = {"batch_id": batch.id, "ip": r["ip"], "excel_row": int(r["excel_row"])}
        row.update({c: py(r.get(c)) for c in INVENTORY_COLUMNS})
        row["extra"] = jsonable({str(c): r.get(c) for c in extra_cols if py(r.get(c)) is not None})
        rows.append(row)

    conflicts = inventory_service.import_conflicts(s, rows)  # sửa tay trên web khác file mới (PLAN §14.11)
    owners = Counter(str(r["owner"] or "(trống)") for r in rows)
    managed = Counter(str(r["managed_by"] or "(trống)") for r in rows)
    batch.schema_version = "inventory_v1"
    batch.summary = jsonable(
        {
            "rows": len(rows),
            "n_ips": len(ips),
            "by_owner": dict(sorted(owners.items())),
            "managed_by": dict(sorted(managed.items())),
            "prev_batch_id": prev.id if prev else None,
            "added_ips": sorted(ips - current) if prev else [],
            "removed_ips": sorted(current - ips) if prev else [],
            "linked_ips": len(ips & linked),
            "edit_conflicts": conflicts,
        }
    )
    batch.validation = jsonable(
        {
            "warnings": [
                *inv.attrs.get("warnings", []),
                *([inventory_service.conflict_warning(conflicts)] if conflicts else []),
            ],
            "invalid_ip_rows": inv.attrs.get("invalid_ip_rows", []),
            "extra_columns": extra_cols,
            "sheet": inv.attrs.get("sheet"),
            "ignored_sheets": [x for x in sheets if x != inv.attrs.get("sheet")],
        }
    )
    inventory_repo.insert_items(s, rows)


# ------------------------------------------------------------------ chuyển trạng thái


def get_batch(s: Session, batch_id: int) -> ImportBatch:
    b = batch_repo.get(s, batch_id)
    if b is None:
        raise ServiceError(404, f"Không có lô #{batch_id}.")
    return b


def _require(b: ImportBatch, status: str, action: str) -> None:
    if b.status != status:
        raise ServiceError(
            409, f"Không thể {action} lô #{b.id}: lô đang '{STATUS_VI[b.status]}' (cần '{STATUS_VI[status]}')."
        )


def commit_batch(
    s: Session, batch_id: int, user: CurrentUser, now: datetime | None = None, acknowledge: bool = False
) -> ImportBatch:
    """Lỗi chặn → không nhập được (hủy lô, sửa file). Có cảnh báo → cần `acknowledge=True` (người dùng đã xem)."""
    b = get_batch(s, batch_id)
    _require(b, "staged", "xác nhận")
    errors, warnings = checks.blocking(list((b.validation or {}).get("checks", [])))
    if errors:
        raise ServiceError(
            409, f"Lô #{b.id} có lỗi chặn: {'; '.join(c['title'] for c in errors)} — hủy lô, sửa file rồi nhập lại.",
            type_="import_blocked",
        )  # fmt: skip
    if warnings and not acknowledge:
        raise ServiceError(
            409, f"Lô #{b.id} có {len(warnings)} cảnh báo cần xác nhận đã xem: {'; '.join(c['title'] for c in warnings)}.",
            type_="ack_required",
        )  # fmt: skip
    dup = batch_repo.find_committed(s, b.kind, b.file_sha256)
    if dup is not None:
        raise ServiceError(409, f"File này đã được nhập ở lô #{dup.id} — hãy hủy lô #{b.id}.")
    b.status, b.committed_by, b.committed_at = "committed", user.username, now or utcnow()
    try:
        s.commit()
    except IntegrityError as exc:  # 2 lô staged cùng file được xác nhận gần như cùng lúc
        s.rollback()
        raise ServiceError(409, f"File này đã được nhập ở lô khác — hãy hủy lô #{batch_id}.") from exc
    return b


def rollback_batch(s: Session, batch_id: int, user: CurrentUser, now: datetime | None = None) -> ImportBatch:
    b = get_batch(s, batch_id)
    _require(b, "committed", "hoàn tác")
    b.status, b.rolled_back_by, b.rolled_back_at = "rolled_back", user.username, now or utcnow()
    s.commit()
    return b


def discard_batch(s: Session, batch_id: int, user: CurrentUser, note: str | None = None) -> ImportBatch:
    b = get_batch(s, batch_id)
    _require(b, "staged", "hủy")
    b.status = "discarded"
    b.note = note or f"Hủy bởi {user.username}"
    batch_repo.delete_rows(s, b.id)
    s.commit()
    return b


def discard_stale_staged(s: Session, now: datetime | None = None) -> int:
    """Lô chờ xác nhận quá 24h → tự hủy (gọi khi khởi động)."""
    now = now or utcnow()
    stale = list(batch_repo.staged_before(s, now - STALE_STAGED))
    for b in stale:
        b.status, b.note = "discarded", "Tự hủy: chờ xác nhận quá 24 giờ"
        batch_repo.delete_rows(s, b.id)
    s.commit()
    return len(stale)


def effective_samples(s: Session, start: Any, end: Any, ips: list[str] | None = None) -> pd.DataFrame:
    """Mẫu hiệu lực (để kiểm tra / G1-M2 dùng làm đầu vào gpu_core)."""
    return util_repo.effective_frame(s, pd.Timestamp(start), pd.Timestamp(end), ips)
