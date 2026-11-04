"""Kiểm tra + xem trước tác động của 1 lô VTNet trước khi xác nhận nhập (Roadmap §14.1 — "validate, preview khi upload").

Mỗi phát hiện có mức:
  * error   — CHẶN xác nhận (file sai: ngày tương lai, không ngày nào có số liệu…) → sửa file, nhập lại;
  * warning — phải tích "đã xem" mới xác nhận được (API kiểm `acknowledge`);
  * info    — chỉ hiển thị.
Số liệu xem trước (vùng theo T mặc định, TB toàn bộ server, chuỗi ngày, so kỳ trước) tính qua gpu_core — không công thức mới.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

import gpu_core as g

ERROR, WARNING, INFO = "error", "warning", "info"
LEVELS = (ERROR, WARNING, INFO)
MAX_PERIOD_DAYS = 45  # file VTNet là 1 tháng (+ vài ngày tràn) — dài hơn là bất thường
SERVER_DROP = 0.2  # số server giảm > 20% so với kỳ trước
FLEET_SHIFT = 15.0  # TB GPU toàn bộ server lệch > 15 điểm % so với kỳ trước
MISSING_COLUMN_EFFECT = {  # cột chuẩn tùy chọn của server_raw → hệ quả khi thiếu
    "don_vi": "thiếu don_vi → không lọc được dòng của đơn vị khác VTT (VAI…), số VTT có thể bị lẫn",
    "gpu_type": "thiếu gpu_type → không biết loại / số card GPU của server",
}
OVERVIEW_MISSING_NOTE = "Không có sheet VTT_KPI_overview"
_MONTH_RE = re.compile(r"(?:th[aá]ng|thang|\bt)[\s_-]*0?(1[0-2]|[1-9])(?!\d)", re.IGNORECASE)


@dataclass
class Check:
    code: str
    level: str
    title: str
    detail: str | None = None
    items: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"code": self.code, "level": self.level, "title": self.title}
        if self.detail:
            d["detail"] = self.detail
        if self.items:
            d["items"] = self.items[:50]
            d["n_items"] = len(self.items)
        return d


def today() -> date:
    """Hôm nay theo giờ VN (thời điểm mẫu quy ước giờ VN). Test cố định hàm này (conftest) để không phụ thuộc đồng hồ."""
    return (datetime.now(UTC) + timedelta(hours=7)).date()


def month_in_filename(name: str) -> int | None:
    """'HSSD GPU Thang 8 2026 - VTT.xlsx' → 8; 'HSSD_GPU_Thang_10_2026' → 10; 'synthetic_t10' → 10; không thấy → None."""
    m = _MONTH_RE.search(name.rsplit(".", 1)[0].replace("_", " "))
    return int(m.group(1)) if m else None


def _fleet(raw: pd.DataFrame, start: Any, end: Any) -> tuple[float | None, float | None, list[dict[str, Any]]]:
    if raw.empty:
        return None, None, []
    fd = g.fleet_daily(raw, start, end)
    pts = [
        {"date": pd.Timestamp(r.day).date().isoformat(), "gpu": float(r.gpu), "mem": float(r.mem), "n_servers": int(r.n_servers)}
        for r in fd.itertuples(index=False)
    ]  # fmt: skip
    return float(fd["gpu"].mean()), float(fd["mem"].mean()), pts


def _zones(st: pd.DataFrame) -> dict[str, int]:
    return {z: int((st["zone"] == z).sum()) if not st.empty else 0 for z in ("danger", "warning", "safe")}


def preview(raw: pd.DataFrame, start: Any, end: Any, threshold: float, params: g.RuleParams) -> dict[str, Any]:
    if raw.empty:
        st = pd.DataFrame(columns=["ip", "zone", "vtnet_low_load", "thin_data"])
    else:
        st = g.server_stats(raw, start, end, threshold, params=params)
    gpu, mem, pts = _fleet(raw, start, end)
    return {
        "threshold": threshold,
        "n_servers": len(st),
        "zones": _zones(st),
        "vtnet_low_load": int(st["vtnet_low_load"].sum()) if "vtnet_low_load" in st else 0,
        "thin_data": int(st["thin_data"].sum()) if "thin_data" in st else 0,
        "gpu_avg": gpu,
        "mem_avg": mem,
        "daily": pts,
        "thin_ips": sorted(st.loc[st["thin_data"], "ip"]) if "thin_data" in st else [],
    }


def run_checks(
    *,
    file_name: str,
    wb: g.VtnetWorkbook,
    raw: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    today: date,
    prev: dict[str, Any] | None,
    new_ips: list[str],
    gone_ips: list[str],
    replaced: int,
    overlap_days: list[str],
    overview: dict[str, Any] | None,
    pv: dict[str, Any],
    daily: dict[str, Any] | None = None,
) -> list[Check]:
    """`prev` = xem trước của kỳ trước (cùng T) + {n_ips, label}; None nếu chưa có lô VTNet nào."""
    out: list[Check] = []
    ts = raw["ts"]
    # --- lỗi chặn
    future = sorted({d.date().isoformat() for d in ts if d.date() > today})
    if future:
        out.append(Check("future_dates", ERROR, "Có ngày ở tương lai", f"Muộn hơn hôm nay ({today:%d/%m/%Y}).", future))
    if pv["n_servers"] == 0:
        out.append(Check("no_servers", ERROR, "Không tính được tải server nào từ file"))

    # --- cần xác nhận
    missing_cols = [c for c in wb.missing_columns if c in MISSING_COLUMN_EFFECT]
    if missing_cols:
        out.append(Check("missing_columns", WARNING,
                         f"Sheet server_raw thiếu cột chuẩn: {', '.join(missing_cols)}",
                         "; ".join(MISSING_COLUMN_EFFECT[c] for c in missing_cols) + ".",
                         missing_cols))  # fmt: skip
    oor = raw[(raw["gpu"] < 0) | (raw["gpu"] > 100) | (raw["mem"] < 0) | (raw["mem"] > 100)]
    if not oor.empty:
        out.append(Check("out_of_range", WARNING, f"{len(oor)} mẫu có giá trị ngoài 0–100%",
                         "Giữ nguyên khi nhập — sẽ làm lệch trung bình; nên hỏi lại VTNet.",
                         sorted(oor["ip"].unique())))  # fmt: skip
    span = (end - start).days + 1
    if span > MAX_PERIOD_DAYS:
        out.append(Check("period_too_long", WARNING, f"Kỳ dài {span} ngày",
                         f"{start:%d/%m/%Y} → {end:%d/%m/%Y}; file VTNet thường là 1 tháng."))  # fmt: skip
    fm = month_in_filename(file_name)
    dm = int(wb.dominant_month[-2:]) if wb.dominant_month else None
    if fm is not None and dm is not None and fm != dm:
        out.append(Check("filename_month", WARNING, f"Tên file ghi tháng {fm} nhưng dữ liệu chủ yếu là tháng {dm}",
                         "Kiểm tra lại có chọn nhầm file không."))  # fmt: skip
    have = {d.date() for d in ts.dt.normalize().unique()}
    all_days = [start.date() + timedelta(days=i) for i in range(span)]
    missing = [d.isoformat() for d in all_days if d not in have]
    if missing:
        out.append(Check("missing_days", WARNING, f"{len(missing)} ngày trong kỳ không có số liệu nào", None, missing))
    types = raw.groupby("ip")["gpu_type"].nunique()
    multi = sorted(types[types > 1].index)
    if multi:
        out.append(Check("multi_gpu_type", WARNING, f"{len(multi)} server có nhiều loại GPU trong cùng file",
                         "Số card lấy theo bản ghi mới nhất.", multi))  # fmt: skip
    if overview is not None and not overview.get("ok"):
        bad = list(overview.get("mismatched_ips", [])) + list(overview.get("only_overview", []))
        bad += list(overview.get("only_raw", []))
        out.append(Check("overview_mismatch", WARNING, "Trung bình tự tính lệch sheet VTT_KPI_overview của VTNet",
                         "Có thể file bị sửa tay hoặc thiếu dòng.", sorted(set(bad))))  # fmt: skip
    if daily is not None and not daily.get("ok"):
        bad_days = sorted(set(daily.get("mismatched_days", [])) | set(daily.get("only_sheet", [])))
        out.append(Check("daily_mismatch", WARNING, "TB theo ngày tự tính lệch sheet 'HSSD theo ngay VTT' của VTNet",
                         f"{len(bad_days)} ngày lệch (GPU/VRAM > 0,01 điểm %, khác số server, hoặc ngày không có trong "
                         "dữ liệu thô). Có thể file bị sửa tay hoặc thiếu dòng.", bad_days))  # fmt: skip
    if replaced:
        out.append(Check("overlap_replace", WARNING, f"Sẽ thay {replaced} mẫu đã nhập trước đó",
                         "Lô mới thắng lô cũ trên các ngày trùng; hoàn tác được.", overlap_days))  # fmt: skip
    if prev and prev.get("n_ips") and pv["n_servers"] < (1 - SERVER_DROP) * prev["n_ips"]:
        out.append(Check("server_drop", WARNING, f"Số server giảm mạnh: {prev['n_ips']} → {pv['n_servers']}",
                         f"So với kỳ {prev.get('label') or 'trước'}.", gone_ips))  # fmt: skip
    # thiếu overview đã có mục "thông tin" riêng → không bắt xác nhận lại lần nữa
    notes = [w for w in wb.warnings if not (overview is None and w.startswith(OVERVIEW_MISSING_NOTE))]
    if notes:
        out.append(Check("parser_notes", WARNING, "Ghi chú khi đọc file", None, notes))

    # --- thông tin
    if overview is None:
        out.append(Check("overview_missing", INFO, "Không có sheet VTT_KPI_overview — bỏ qua đối soát trung bình"))
    if wb.sheet_names.get("daily") is None:
        out.append(Check("daily_missing", INFO, "Không có sheet 'HSSD theo ngay VTT' — bỏ qua đối soát theo ngày",
                         "File tháng 7/2026 chưa có sheet này; từ tháng 8 VTNet đều gửi kèm."))  # fmt: skip
    if new_ips:
        out.append(Check("new_ips", INFO, f"{len(new_ips)} server mới so với lô trước", None, new_ips))
    if gone_ips and not any(c.code == "server_drop" for c in out):
        out.append(Check("gone_ips", INFO, f"{len(gone_ips)} server không còn so với lô trước", None, gone_ips))
    if pv["thin_ips"]:
        out.append(Check("thin_data", INFO, f"{len(pv['thin_ips'])} server có dữ liệu mỏng", None, pv["thin_ips"]))
    if prev and prev.get("gpu_avg") is not None and pv["gpu_avg"] is not None:
        d = pv["gpu_avg"] - prev["gpu_avg"]
        if abs(d) > FLEET_SHIFT:
            out.append(Check("fleet_shift", INFO, f"TB GPU toàn bộ server đổi {d:+.1f} điểm % so với kỳ trước"))
    if prev and prev.get("period_start") and end.date() < date.fromisoformat(prev["period_start"]):
        out.append(Check("older_period", INFO, "Kỳ của file cũ hơn kỳ đã nhập gần nhất (nhập bù dữ liệu cũ)"))
    order = {lv: i for i, lv in enumerate(LEVELS)}
    return sorted(out, key=lambda c: order[c.level])


def blocking(checks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(lỗi chặn, cần xác nhận) từ validation.checks đã lưu."""
    return [c for c in checks if c.get("level") == ERROR], [c for c in checks if c.get("level") == WARNING]
