# -*- coding: utf-8 -*-
"""Xuất file thống kê đã gắn đánh giá (định dạng skill gpu-util-vtnet) — dùng chung cho CLI & API.

Đầu vào là file thống kê GỐC (.xlsx) + bảng server_stats đã tính. Đầu ra:
  * sheet 'Thống kê chi tiết': cột "Đánh giá..." (tìm theo header; chưa có thì thêm cuối) + 6 cột phụ
  * sheet 'Đánh giá tải VTNet' (đầu file): tổng thể vùng×đầu mối, mẫu hình, so sánh kỳ trước,
    lỗ hổng ánh xạ, danh sách VTNet đã thu hồi
Mọi sheet/công thức khác giữ nguyên; đặt fullCalcOnLoad để Excel tự tính lại khi mở.
"""
from __future__ import annotations

from typing import Optional

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .parsing import is_ipv4, links_dict, norm_ip, norm_text
from .rules import DEFAULT_PARAMS, PATTERN_LABEL_VI, VTNET_LOW_LOAD_T, ZONE_LABEL_VI, RuleParams

FILL = {"danger": "F4CCCC", "warning": "FCE5CD", "safe": "D9EAD3", "na": "EFEFEF"}
ASSESS_HEADER = "Đánh giá, nhận xét, cảnh báo, dựa trên Ultilization từ VTNet"
EXTRA_HEADERS = ["Vùng (VTNet)", "gpu_util TB %", "gpu_memory TB %", "Đỉnh util %",
                 "Số ngày có số liệu", f"Cờ THẤP TẢI VTNet (<{VTNET_LOW_LOAD_T:.0f}%)"]
SUMMARY_SHEET = "Đánh giá tải VTNet"


def _extra_headers(vt: float) -> list:
    return EXTRA_HEADERS[:-1] + [f"Cờ THẤP TẢI VTNet (<{vt:.0f}%)"]


def _fill(hex6):
    return PatternFill("solid", fgColor=hex6)


def _find_col(ws, prefix: str) -> Optional[int]:
    for c in range(1, ws.max_column + 1):
        if norm_text(ws.cell(1, c).value).casefold().startswith(prefix):
            return c
    return None


def write_assessed_inventory(inventory_path, out_path, stats: pd.DataFrame, inv: pd.DataFrame,
                             threshold: float, start, end,
                             reclaimed: Optional[pd.DataFrame] = None,
                             movement: Optional[tuple[str, pd.DataFrame]] = None,
                             ip_links: Optional[dict] = None, params: RuleParams = DEFAULT_PARAMS) -> dict:
    """stats: kết quả metrics.server_stats (cột ip). inv: kết quả parsing.read_inventory.
    movement: (nhãn kỳ trước, metrics.compare_periods(...)).
    ip_links: {inventory_ip: vtnet_ip} hoặc DataFrame từ parsing.load_ip_links."""
    st = stats.set_index("ip")
    links = links_dict(ip_links)
    rec_ips = set(reclaimed["ip"]) if reclaimed is not None and len(reclaimed) else set()

    wb = openpyxl.load_workbook(inventory_path)
    ws = wb[inv.attrs.get("sheet", "Thống kê chi tiết")]
    ip_col = _find_col(ws, "ip")
    a_col = _find_col(ws, "đánh giá") or (ws.max_column + 1)
    extra_headers = _extra_headers(params.vtnet_low_load_t)
    for i, h in enumerate([ASSESS_HEADER] + extra_headers):
        c = ws.cell(1, a_col + i, h)
        c.font = Font(name="Arial", bold=True)
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    for i, w in enumerate([60, 16, 12, 14, 11, 12, 14]):
        ws.column_dimensions[get_column_letter(a_col + i)].width = w

    matched = set()
    for r in range(2, ws.max_row + 1):
        inv_ip = norm_ip(ws.cell(r, ip_col).value)
        if not is_ipv4(inv_ip):
            continue
        ip = links.get(inv_ip, inv_ip)
        if ip in st.index:
            x = st.loc[ip]
            matched.add(ip)
            text = x["assessment"] + (f" [Số liệu VTNet theo IP liên kết {ip}]" if ip != inv_ip else "")
            vals = [text, ZONE_LABEL_VI[x["zone"]], round(x["gpu_avg"], 1), round(x["mem_avg"], 1),
                    round(x["gpu_peak"], 1), f"{int(x['days'])}/{int(x['days_in_range'])}",
                    "CÓ" if x["vtnet_low_load"] else None]
            for i, v in enumerate(vals):
                ws.cell(r, a_col + i, v)
            ws.cell(r, a_col + 1).fill = _fill(FILL[x["zone"]])
        else:
            gone = inv_ip in rec_ips
            ws.cell(r, a_col, "VTNet ĐÃ THU HỒI (sheet 'DS đã thu') – cập nhật lại file thống kê." if gone else
                    "VTNet chưa báo tải cho IP này – xác nhận: chưa gắn monitor / đã trả / đổi IP / non-GPU?")
            ws.cell(r, a_col + 1, "Đã thu hồi" if gone else "Chưa có dữ liệu VTNet")
            ws.cell(r, a_col + 1).fill = _fill(FILL["na"])
            for i in range(2, len(extra_headers) + 1):
                ws.cell(r, a_col + i, None)

    inv_eff = inv.assign(ip=inv["ip"].map(lambda v: links.get(v, v)))
    _summary(wb, stats, inv_eff, matched, rec_ips, reclaimed, threshold,
             pd.Timestamp(start), pd.Timestamp(end), movement, params.vtnet_low_load_t)
    wb.calculation.fullCalcOnLoad = True
    wb.save(out_path)
    return {"matched": len(matched)}


def _summary(wb, st, inv, matched, rec_ips, reclaimed, T, s, e, movement, vt=VTNET_LOW_LOAD_T):
    if SUMMARY_SHEET in wb.sheetnames:
        del wb[SUMMARY_SHEET]
    ws = wb.create_sheet(SUMMARY_SHEET, 0)
    B, N = Font(name="Arial", bold=True, size=12), Font(name="Arial", size=11)
    row = [1]

    def W(c, v, f=None, fill=None):
        cell = ws.cell(row[0], c, v)
        cell.font = f or N
        if fill:
            cell.fill = _fill(fill)

    def nl(k=1):
        row[0] += k

    W(1, f"ĐÁNH GIÁ TẢI GPU VTNet — {s:%d/%m/%Y} → {e:%d/%m/%Y} (TTCN-VTT)", Font(name="Arial", bold=True, size=14)); nl()
    W(1, f"Luật vùng (T={T:g}%): util≤T & mem≤T = Nguy hiểm | đúng 1 metric ≤T = Cảnh báo | cả 2 >T = An toàn. "
         f"Cờ THẤP TẢI VTNet: util<{vt:g}% & mem<{vt:g}%."); nl()
    W(1, "Lưu ý: VTNet xét CPU+RAM+GPU khi thu hồi; file chỉ có GPU → đây là xấp xỉ theo GPU.",
      Font(name="Arial", italic=True, color="CC0000")); nl(2)

    m = st[st["ip"].isin(matched)].merge(inv[["ip", "owner"]].drop_duplicates("ip"), on="ip")
    owners = sorted(m["owner"].dropna().unique())
    W(1, f"1) TỔNG THỂ — vùng × đầu mối ({len(m)} server map được)", B); nl()
    W(1, "Vùng", B)
    for j, o in enumerate(owners):
        W(2 + j, o, B)
    W(2 + len(owners), "Tổng", B); nl()
    for z in ["safe", "warning", "danger"]:
        W(1, ZONE_LABEL_VI[z], fill=FILL[z])
        for j, o in enumerate(owners):
            W(2 + j, int(((m["zone"] == z) & (m["owner"] == o)).sum()))
        W(2 + len(owners), int((m["zone"] == z).sum()), B); nl()
    nl()
    W(1, "2) BÓC TÁCH KỸ THUẬT (server map được)", B); nl()
    for p in ["memory_bound", "compute_bound", "idle", "bursty_idle", "high_load", "healthy"]:
        W(1, PATTERN_LABEL_VI[p]); W(3, int((m["pattern"] == p).sum()), B); nl()
    W(1, f"Dưới ngưỡng THẤP TẢI VTNet (<{vt:g}% cả 2) – toàn bộ server VTNet đo")
    W(3, int(st["vtnet_low_load"].sum()), B); nl(2)

    if movement:
        label, cmp = movement
        W(1, f"3) SO SÁNH VỚI KỲ TRƯỚC ({label})", B); nl()
        for mv, lab, color in [("worsened", "⚠ Xấu đi", "CC0000"), ("improved", "✔ Cải thiện", "38761D")]:
            rows = cmp[cmp["movement"] == mv]
            W(1, f"{lab} ({len(rows)} server):", Font(name="Arial", bold=True, color=color)); nl()
            for _, x in rows.iterrows():
                W(1, f"   {x['ip']}: {ZONE_LABEL_VI.get(x['zone_prev'])} → {ZONE_LABEL_VI.get(x['zone_cur'])}"); nl()
        nl()
    else:
        W(1, "3) SO SÁNH KỲ TRƯỚC: chưa có dữ liệu kỳ trước.", Font(name="Arial", italic=True)); nl(2)

    vt_only = sorted(set(st["ip"]) - set(inv["ip"]))
    inv_only = sorted(set(inv["ip"]) - set(st["ip"]))
    W(1, "4) LỖ HỔNG ÁNH XẠ", B); nl()
    W(1, f"• {len(inv_only)} IP trong thống kê nhưng VTNet không báo tải "
         f"(trong đó {len(set(inv_only) & rec_ips)} đã bị VTNet thu hồi)"); nl()
    W(1, f"• {len(vt_only)} IP VTNet có tải nhưng thiếu trong thống kê:"); nl()
    W(1, "IP", B); W(2, "util TB%", B); W(3, "VRAM TB%", B); W(4, "gpu_type", B); nl()
    for _, x in st[st["ip"].isin(vt_only)].iterrows():
        W(1, x["ip"]); W(2, round(x["gpu_avg"], 1)); W(3, round(x["mem_avg"], 1)); W(4, x["gpu_type"]); nl()
    if reclaimed is not None and len(reclaimed):
        nl(); W(1, f"5) DANH SÁCH VTNet ĐÃ THU HỒI ({len(reclaimed)} server, sheet 'DS đã thu')", B); nl()
        W(1, "IP", B); W(2, "GPU", B); W(3, "Thụ hưởng QHDC", B); W(4, "Owner DCIM", B); nl()
        for _, x in reclaimed.iterrows():
            W(1, x["ip"]); W(2, x["gpu_type"]); W(3, x["beneficiary"]); W(4, x["owner_dcim"]); nl()
    for c, w in {1: 72, 2: 14, 3: 16, 4: 20}.items():
        ws.column_dimensions[get_column_letter(c)].width = w
