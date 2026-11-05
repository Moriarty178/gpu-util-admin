"""Xuất Excel định dạng skill (PLAN §7 `/alerts/export.xlsx`): gpu_core.export.write_assessed_inventory trên
file thống kê GỐC của snapshot hiện hành + liên kết IP + danh sách thu hồi → cùng kết quả với CLI skill.

Phạm vi 1 đầu mối (G2-M2): chỉ đánh giá + tổng hợp server của đầu mối, rồi XÓA khỏi file các dòng thống kê của người khác
và mọi sheet khác của file gốc (vd 'GPU QHDC' — số liệu toàn bộ) → file xuất không lộ dữ liệu ngoài phạm vi.

Sửa tay danh mục (PLAN §14.11): ô admin sửa khác file được ghi đè bằng giá trị sửa tay (nền vàng nhạt + ghi chú "theo file: …")
và thêm cột "Trạng thái thu hồi" cuối sheet thống kê chi tiết — chỉ trình bày, không tính gì (gpu_core / skill giữ nguyên)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

import gpu_core as g
from app.errors import ServiceError
from app.repo import batch_repo, inventory_repo
from app.scope import Scope
from app.services.analytics_service import Bundle, apply_scope
from app.services.import_service import resolve_file
from app.services.inventory_service import RECLAIM_LABEL
from gpu_core.export import SUMMARY_SHEET, _find_col, write_assessed_inventory  # cùng cách tìm cột IP
from gpu_core.parsing import _inv_key, is_ipv4, norm_ip  # cùng cách nhận header với read_inventory


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
    # đầu mối… theo sửa tay của admin (PLAN §14.11) — phạm vi & tổng hợp theo đầu mối khớp với web; ô gốc giữ nguyên
    inv = inventory_repo.apply_overrides(inv, inventory_repo.overrides_frame(s))
    inv.attrs["sheet"] = sheet
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
        _apply_edits(out, sheet, inv)
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


RECLAIM_HEADER = "Trạng thái thu hồi"
EDITED_FILL = PatternFill("solid", fgColor="FFF2CC")  # vàng nhạt: ô sửa tay trên web


def _apply_edits(path: Path, sheet: str, inv: pd.DataFrame) -> None:
    """Ghi giá trị sửa tay (chỉ ô khác file) + cột "Trạng thái thu hồi" vào sheet thống kê chi tiết của file xuất.
    `inv`: read_inventory đã qua inventory_repo.apply_overrides (cột `edited`, `reclaim_status`; ip = IP thống kê)."""
    by_ip = {r["ip"]: r for r in inv.to_dict("records")}
    wb = openpyxl.load_workbook(path)
    ws = wb[sheet]
    ip_col = _find_col(ws, "ip")
    if ip_col is None:
        return
    cols: dict[str, int] = {}
    for c in range(1, ws.max_column + 1):
        key = _inv_key(ws.cell(1, c).value)
        if key and key not in cols:
            cols[key] = c
    r_col = ws.max_column + 1
    h = ws.cell(1, r_col, RECLAIM_HEADER)
    h.font = Font(name="Arial", bold=True)
    h.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    ws.column_dimensions[get_column_letter(r_col)].width = 18
    for r in range(2, ws.max_row + 1):
        ip = norm_ip(ws.cell(r, ip_col).value)
        row = by_ip.get(ip) if is_ipv4(ip) else None
        if row is None:
            continue
        ws.cell(r, r_col, RECLAIM_LABEL[row["reclaim_status"]])
        for field, file_value in (row["edited"] or {}).items():
            col = cols.get(field)
            if col is None:
                continue
            cell = ws.cell(r, col, row[field])
            cell.fill = EDITED_FILL
            cell.comment = Comment(f"Sửa tay trên web — theo file: {file_value or '(trống)'}", "GPU Util")
    wb.calculation.fullCalcOnLoad = True  # giữ như gpu_core.export: Excel tự tính lại công thức khi mở
    wb.save(path)
