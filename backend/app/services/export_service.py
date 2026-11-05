"""Xuất Excel định dạng skill (PLAN §7 `/alerts/export.xlsx`): gpu_core.export.write_assessed_inventory trên
file thống kê GỐC của snapshot hiện hành + liên kết IP + danh sách thu hồi → cùng kết quả với CLI skill.

Phạm vi 1 đầu mối (G2-M2): chỉ đánh giá + tổng hợp server của đầu mối, rồi XÓA khỏi file các dòng thống kê của người khác
và mọi sheet khác của file gốc (vd 'GPU QHDC' — số liệu toàn bộ) → file xuất không lộ dữ liệu ngoài phạm vi."""

from __future__ import annotations

import tempfile
from pathlib import Path

import openpyxl
from sqlalchemy.orm import Session

import gpu_core as g
from app.errors import ServiceError
from app.repo import batch_repo
from app.scope import Scope
from app.services.analytics_service import Bundle, apply_scope
from app.services.import_service import resolve_file
from gpu_core.export import SUMMARY_SHEET, _find_col, write_assessed_inventory  # cùng cách tìm cột IP
from gpu_core.parsing import norm_ip


def export_assessed(s: Session, b: Bundle, scope: Scope) -> tuple[bytes, str]:
    inv_batch = batch_repo.latest_committed(s, "inventory")
    if inv_batch is None:
        raise ServiceError(409, "Chưa nhập file thống kê server — cần file thống kê gốc để xuất Excel.")
    path = resolve_file(inv_batch)
    if not path.is_file():
        raise ServiceError(409, f"Không còn file thống kê gốc của lô #{inv_batch.id} trong data/uploads/.")
    if b.stats.empty:
        raise ServiceError(409, "Không có số liệu VTNet trong khoảng ngày đã chọn.")
    stats = b.stats
    inv = g.read_inventory(path)
    sheet = str(inv.attrs.get("sheet", "Thống kê chi tiết"))
    if scope.kind == "owner":  # chỉ server của đầu mối
        stats = stats[stats["ip"].isin(apply_scope(b.servers, scope)["ip"])]
        inv = inv[inv["owner"] == scope.owner_key].copy()
        inv.attrs["sheet"] = sheet
    links = dict(zip(b.links["inventory_ip"], b.links["vtnet_ip"], strict=True))
    ctx = b.ctx
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "danh_gia.xlsx"
        write_assessed_inventory(
            path,
            out,
            stats,
            inv,
            ctx.threshold,
            ctx.start,
            ctx.end,
            reclaimed=b.reclaimed if not b.reclaimed.empty else None,
            ip_links=links,
            params=ctx.params,
        )
        if scope.kind == "owner":
            _redact(out, sheet, set(inv["ip"]))
        data = out.read_bytes()
    name = f"Danh_gia_tai_GPU_{scope.owner_key}_" if scope.kind == "owner" else "Danh_gia_tai_GPU_"
    metric = "" if ctx.zone_metric == "both" else f"_{ctx.zone_metric}"  # luật 1 chỉ số → ghi vào tên file
    name += f"{ctx.start:%Y%m%d}-{ctx.end:%Y%m%d}_T{ctx.threshold:g}{metric}.xlsx"
    return data, name


def _redact(path: Path, sheet: str, keep_ips: set[str]) -> None:
    """Giữ sheet tổng hợp + sheet thống kê chi tiết (chỉ dòng tiêu đề và dòng có IP trong `keep_ips`)."""
    wb = openpyxl.load_workbook(path)
    for name in list(wb.sheetnames):
        if name not in (SUMMARY_SHEET, sheet):
            del wb[name]
    ws = wb[sheet]
    ip_col = _find_col(ws, "ip")  # không thấy cột IP → xóa hết dòng dữ liệu (an toàn)
    for r in range(ws.max_row, 1, -1):
        ip = norm_ip(ws.cell(r, ip_col).value) if ip_col else ""
        if ip not in keep_ips:
            ws.delete_rows(r)
    wb.save(path)
