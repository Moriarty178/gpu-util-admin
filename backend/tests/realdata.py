"""Đường dẫn dữ liệu thật trong samples/ (gitignored) + marker skip theo đúng file còn thiếu."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

import gpu_core as g

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def sample(*names: str) -> Path:
    """File thật đầu tiên tồn tại (chấp nhận vài cách đặt tên)."""
    return next((SAMPLES / n for n in names if (SAMPLES / n).exists()), SAMPLES / names[0])


T10 = sample("HSSD_GPU_Thang_10_2026_-_VTT.xlsx", "HSSD_GPU_Thang_10_2026_VTT.xlsx")
T7 = sample("HSSD GPU Thang 7 2026 - VTT.xlsx", "HSSD_GPU_Daily_VTT_thang7.xlsx")
T8 = sample("HSSD GPU Thang 8 2026 - VTT.xlsx")
T9 = sample("HSSD GPU Thang 9 2026 - VTT.xlsx")
# Thống kê toàn bộ server VTT (1 file, người dùng chốt 03/11/2026): 134 dòng / 129 IP hợp lệ — khớp golden T7 (skill v1).
INV7 = sample("Thong_ke_toan_bo_server_TTCN_VTT.xlsx", "Thong_ke_toan_bo_server_TTCN_VTT_thang7.xlsx")
# Bản 137 dòng dùng khi lập golden "thống kê T10" (CONTEXT §7) — chưa có → các test đó tự skip.
INV10 = sample("Thong_ke_toan_bo_server_TTCN_VTT_ban137.xlsx")


def needs(*files: Path) -> pytest.MarkDecorator:
    missing = [f.name for f in files if not f.exists()]
    return pytest.mark.skipif(bool(missing), reason=f"thiếu dữ liệu thật trong samples/: {', '.join(missing)}")


def has_sheet(path: Path, sheet: str) -> bool:
    """Kiểm tra sheet có trong file — độc lập với parser (để không che lỗi parser)."""
    names = openpyxl.load_workbook(path, read_only=True).sheetnames
    return any(g.norm_text(n).casefold() == sheet.casefold() for n in names)
