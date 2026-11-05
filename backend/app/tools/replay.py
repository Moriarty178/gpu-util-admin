"""Chuyển dữ liệu GĐ1 (SQLite) sang CSDL mới (PostgreSQL GĐ2) bằng cách PHÁT LẠI các lô (PLAN ADR-9).

Không chép bảng mẫu tải: mỗi lô `committed` / `rolled_back` của nguồn được nhập lại từ file gốc `<sha256>.xlsx`
qua đúng luồng nhập của app (stage → commit → [rollback]), giữ nguyên người làm và mốc thời gian gốc → VIEW
`util_effective` / `inventory_current` / `reclaim_current` ở đích giống hệt nguồn. Sau đó chép `ip_link`, `app_setting`
và (GĐ2) `app_user`, `audit_log`, `server_note`, `inventory_override` (sửa tay danh mục) — id do đích tự cấp; tài khoản trùng tên đã có ở đích được giữ nguyên.
Lô `staged` / `failed` / `discarded` không mang dữ liệu hiệu lực → bỏ qua (ghi trong báo cáo).

Chạy (Git Bash, gốc repo): `bash scripts/task.sh replay --target postgresql+psycopg://…` — xem `--help`.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, Table, delete, func, insert, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import Settings, get_settings, resolve_path
from app.db.migrate import is_migrated, upgrade
from app.db.models import AppSetting, AppUser, AuditLog, ImportBatch, InventoryOverride, IpLink, ServerNote
from app.db.seed import seed
from app.db.session import make_engine, resolve_database_url
from app.db.views import inventory_current, reclaim_current, util_effective
from app.errors import ServiceError
from app.scope import CurrentUser
from app.services import import_service as imp

log = logging.getLogger(__name__)

REPLAYED = ("committed", "rolled_back")
NOTE_PREFIX = "Phát lại từ lô #"


class ReplayError(Exception):
    """Không phát lại được (đích đã có dữ liệu, thiếu file gốc, sai sha256…). Thông báo tiếng Việt."""


@dataclass
class ReplayReport:
    id_map: dict[int, int] = field(default_factory=dict)  # lô nguồn → lô đích
    skipped: dict[str, int] = field(default_factory=dict)  # trạng thái → số lô bỏ qua
    links: int = 0
    settings: int = 0
    users: int = 0
    users_kept: list[str] = field(default_factory=list)  # trùng tên với tài khoản đã có ở đích → giữ bản đích
    audit: int = 0
    notes: int = 0
    edits: int = 0

    def lines(self) -> list[str]:
        out = [
            f"Đã phát lại {len(self.id_map)} lô (nguồn → đích): "
            + ", ".join(f"#{a}→#{b}" for a, b in self.id_map.items())
        ]
        if self.skipped:
            out.append("Bỏ qua (không có dữ liệu hiệu lực): " + ", ".join(f"{k}: {v}" for k, v in self.skipped.items()))
        out.append(f"Đã chép {self.links} liên kết IP, {self.settings} cài đặt, {self.users} tài khoản, "
                   f"{self.audit} dòng nhật ký, {self.notes} ghi chú, {self.edits} server sửa tay danh mục.")  # fmt: skip
        if self.users_kept:
            out.append("Giữ tài khoản đã có ở đích (không chép đè): " + ", ".join(self.users_kept))
        return out


def _user(name: str | None) -> CurrentUser:
    return CurrentUser(username=name or "replay", role="admin")


def _source_file(b: ImportBatch, uploads: Path) -> Path:
    """File gốc: ưu tiên `<uploads>/<sha256>.xlsx` (tên cố định theo nội dung), sau đó `file_path` đã lưu."""
    for p in (uploads / f"{b.file_sha256}.xlsx", resolve_path(Path(b.file_path))):
        if p.is_file():
            return p
    raise ReplayError(
        f"Thiếu file gốc của lô #{b.id} ({b.file_name}): không thấy {uploads / (b.file_sha256 + '.xlsx')}"
    )


def replay(source: Engine, target: Engine, *, source_uploads: Path, target_settings: Settings) -> ReplayReport:
    """Phát lại mọi lô của `source` vào `target` (đích phải chưa có lô nào). Tự migrate + seed đích."""
    upgrade(target)
    seed(target)
    report = ReplayReport()
    with Session(source) as src, Session(target) as dst:
        if dst.scalar(select(func.count(ImportBatch.id))):
            raise ReplayError("CSDL đích đã có lô import — chỉ phát lại vào CSDL mới (chưa có dữ liệu).")
        for b in src.scalars(select(ImportBatch).order_by(ImportBatch.id)):
            if b.status not in REPLAYED:
                report.skipped[b.status] = report.skipped.get(b.status, 0) + 1
                continue
            data = _source_file(b, source_uploads).read_bytes()
            if hashlib.sha256(data).hexdigest() != b.file_sha256:
                raise ReplayError(f"File gốc của lô #{b.id} không khớp sha256 đã lưu — dừng, không phát lại.")
            nb = imp.stage_upload(
                dst,
                settings=target_settings,
                user=_user(b.uploaded_by),
                file_name=b.file_name,
                data=data,
                now=b.uploaded_at,
            )
            nb.note = f"{NOTE_PREFIX}{b.id}" + (f" — {b.note}" if b.note else "")
            imp.commit_batch(
                dst, nb.id, _user(b.committed_by), now=b.committed_at, acknowledge=True
            )  # đã duyệt ở nguồn
            if b.status == "rolled_back":
                imp.rollback_batch(dst, nb.id, _user(b.rolled_back_by), now=b.rolled_back_at)
            report.id_map[b.id] = nb.id
            log.info("Lô #%s → #%s (%s, %s)", b.id, nb.id, b.kind, b.status)

        # Liên kết IP & cài đặt: đích = đúng như nguồn (thay bản seed mặc định)
        links = [_row(x, IpLink) for x in src.scalars(select(IpLink))]
        settings = [_row(x, AppSetting) for x in src.scalars(select(AppSetting))]
        dst.execute(delete(IpLink))
        dst.execute(delete(AppSetting))
        if links:
            dst.execute(insert(IpLink), links)
        if settings:
            dst.execute(insert(AppSetting), settings)
        report.links, report.settings = len(links), len(settings)

        # Sửa tay danh mục (PLAN §14.11): chép sau khi phát lại lô (lúc nhập lại file thống kê ở đích chưa có sửa tay)
        edits = [_row(x, InventoryOverride) for x in src.scalars(select(InventoryOverride))]
        if edits:
            dst.execute(insert(InventoryOverride), edits)
        report.edits = len(edits)

        # Tài khoản, nhật ký, ghi chú (GĐ2): không giữ id (đích tự cấp — sequence PG không lệch)
        have = set(dst.scalars(select(AppUser.username)))
        users = []
        for u in src.scalars(select(AppUser).order_by(AppUser.id)):
            if u.username in have:
                report.users_kept.append(u.username)
            else:
                users.append(_row(u, AppUser, skip=("id",)))
        audits = [_row(x, AuditLog, skip=("id",)) for x in src.scalars(select(AuditLog).order_by(AuditLog.id))]
        notes = [_row(x, ServerNote, skip=("id",)) for x in src.scalars(select(ServerNote).order_by(ServerNote.id))]
        for model, rows in ((AppUser, users), (AuditLog, audits), (ServerNote, notes)):
            if rows:
                dst.execute(insert(model), rows)
        report.users, report.audit, report.notes = len(users), len(audits), len(notes)
        dst.commit()
    return report


def _row(obj: Any, model: Any, skip: Sequence[str] = ()) -> dict[str, Any]:
    return {c.key: getattr(obj, c.key) for c in model.__mapper__.column_attrs if c.key not in skip}


# ------------------------------------------------------------------ kiểm sau khi phát lại


def _norm(v: Any) -> Any:
    return round(v, 9) if isinstance(v, float) else v


def _view_rows(s: Session, view: Table, drop: Sequence[str] = ("batch_id",)) -> list[tuple[Any, ...]]:
    cols = [c for c in view.columns if c.name not in drop]
    rows = s.execute(select(*cols)).all()
    return sorted((tuple(_norm(v) for v in r) for r in rows), key=lambda r: repr(r[:2]))  # khóa: (ip, ts) / ip


def _status_counts(s: Session) -> dict[str, int]:
    rows = s.execute(
        select(ImportBatch.kind, ImportBatch.status, func.count()).group_by(ImportBatch.kind, ImportBatch.status)
    )
    return {f"{k}/{st}": n for k, st, n in rows if st in REPLAYED}


def _plain(s: Session, model: Any, keys: Sequence[str]) -> list[tuple[Any, ...]]:
    return sorted(tuple(_norm(getattr(o, k)) for k in keys) for o in s.scalars(select(model)))


USER_KEYS = ["username", "role", "owner_key", "data_scope", "active", "full_name"]
NOTE_KEYS = ["ip", "kind", "text", "valid_until", "created_by", "created_at", "deleted_at"]
AUDIT_KEYS = ["at", "username", "action", "target"]
EDIT_KEYS = [c.key for c in InventoryOverride.__mapper__.column_attrs]


def verify(source: Engine, target: Engine) -> list[str]:
    """So nguồn ↔ đích: số lô theo trạng thái, 3 view hiệu lực (bỏ batch_id vì id lô đổi), liên kết IP, cài đặt.
    Trả danh sách khác biệt (rỗng = khớp)."""
    diffs: list[str] = []
    with Session(source) as a, Session(target) as b:
        src_users = set(a.scalars(select(AppUser.username)))
        checks: list[tuple[str, Any, Any]] = [
            ("số lô theo loại/trạng thái", _status_counts(a), _status_counts(b)),
            ("util_effective", _view_rows(a, util_effective), _view_rows(b, util_effective)),
            ("inventory_current", _view_rows(a, inventory_current), _view_rows(b, inventory_current)),
            ("reclaim_current", _view_rows(a, reclaim_current), _view_rows(b, reclaim_current)),
            (
                "ip_link",
                _plain(a, IpLink, ["inventory_ip", "vtnet_ip", "pair_confirmed", "reason"]),
                _plain(b, IpLink, ["inventory_ip", "vtnet_ip", "pair_confirmed", "reason"]),
            ),
            ("app_setting", _plain(a, AppSetting, ["key", "value"]), _plain(b, AppSetting, ["key", "value"])),
            (
                "app_user",
                _plain(a, AppUser, USER_KEYS),
                [r for r in _plain(b, AppUser, USER_KEYS) if r[0] in src_users],
            ),
            ("server_note", _plain(a, ServerNote, NOTE_KEYS), _plain(b, ServerNote, NOTE_KEYS)),
            ("inventory_override", _plain(a, InventoryOverride, EDIT_KEYS), _plain(b, InventoryOverride, EDIT_KEYS)),
        ]
        # nhật ký: mọi dòng của nguồn phải có ở đích (đích có thể có thêm, vd create-admin trước khi phát lại)
        missing = Counter(_plain(a, AuditLog, AUDIT_KEYS)) - Counter(_plain(b, AuditLog, AUDIT_KEYS))
        if missing:
            diffs.append(f"audit_log: thiếu {sum(missing.values())} dòng của nguồn ở đích")
        for name, x, y in checks:
            if x != y:
                n = f" ({len(x)} vs {len(y)} dòng)" if isinstance(x, list) else ""
                diffs.append(f"{name}: nguồn ≠ đích{n}")
    return diffs


# ------------------------------------------------------------------ CLI


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="replay_batches",
        description="Phát lại các lô GĐ1 (SQLite + data/uploads) sang CSDL mới, rồi kiểm nguồn = đích (PLAN ADR-9).",
    )
    ap.add_argument("--source", default="sqlite:///./data/app.db", help="URL CSDL nguồn (mặc định data/app.db)")
    ap.add_argument("--source-uploads", default="./data/uploads", help="Thư mục file gốc của nguồn")
    ap.add_argument("--target", default=None, help="URL CSDL đích (mặc định DATABASE_URL — trong container api là PG)")
    ap.add_argument("--target-uploads", default=None, help="Thư mục lưu file gốc phía đích (mặc định UPLOAD_DIR)")
    ap.add_argument("--verify-only", action="store_true", help="Chỉ so nguồn ↔ đích, không phát lại")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    base = get_settings()
    target_url: str = args.target or base.database_url
    src_url = resolve_database_url(args.source)
    if src_url == resolve_database_url(target_url):
        print("Nguồn và đích trùng nhau (đặt --target hoặc DATABASE_URL tới CSDL mới).", file=sys.stderr)
        return 2
    if src_url.get_backend_name() == "sqlite" and not Path(src_url.database or "").is_file():
        print(f"Không thấy CSDL nguồn: {src_url.database}", file=sys.stderr)
        return 2
    target_settings = base.model_copy(
        update={
            "database_url": target_url,
            "upload_dir": Path(args.target_uploads) if args.target_uploads else base.upload_dir,
        }
    )
    source, target = make_engine(args.source), make_engine(target_url)
    print(f"Nguồn: {src_url.render_as_string()} → đích: {make_url(target_url).render_as_string()}")
    try:
        if not is_migrated(source):
            print("CSDL nguồn chưa có bảng.", file=sys.stderr)
            return 2
        if not args.verify_only:
            try:
                report = replay(source, target, source_uploads=resolve_path(Path(args.source_uploads)),
                                target_settings=target_settings)  # fmt: skip
            except (ReplayError, ServiceError) as exc:
                print(f"Dừng: {exc}", file=sys.stderr)
                return 1
            print("\n".join(report.lines()))
        diffs = verify(source, target)
        if diffs:
            print("KHÔNG KHỚP:\n  " + "\n  ".join(diffs), file=sys.stderr)
            return 1
        print("Kiểm: nguồn = đích (số lô, util_effective, inventory_current, reclaim_current, ip_link, app_setting, "
              "app_user, server_note, audit_log, inventory_override).")  # fmt: skip
        return 0
    finally:
        source.dispose()
        target.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
