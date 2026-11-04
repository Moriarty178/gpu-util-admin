"""Kiểm tra + xem trước lô VTNet trước khi nhập (Roadmap §14.1): lỗi chặn, cảnh báo cần xác nhận, xem trước tác động.
Mỗi test dựng 1 file tổng hợp có lỗi biết trước (make_synthetic) — không dùng code đang test để sinh kỳ vọng."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from conftest import FIX, make_synthetic
from fastapi.testclient import TestClient
from realdata import T7, T8, T9, T10

from app.services import import_checks
from app.services.import_checks import month_in_filename

OCT = [dt.datetime(2026, 10, d) for d in range(1, 6)]


def up(c: TestClient, path: Path, name: str | None = None) -> dict[str, Any]:
    with path.open("rb") as f:
        r = c.post("/api/v1/imports", files={"file": (name or path.name, f, "application/octet-stream")})
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


def codes(b: dict[str, Any], level: str | None = None) -> list[str]:
    return [x["code"] for x in b["validation"]["checks"] if level is None or x["level"] == level]


def check(b: dict[str, Any], code: str) -> dict[str, Any]:
    return next(x for x in b["validation"]["checks"] if x["code"] == code)


def commit(c: TestClient, b: dict[str, Any], ack: bool | None = None) -> Any:
    kw = {} if ack is None else {"json": {"acknowledge": ack}}
    return c.post(f"/api/v1/imports/{b['id']}/commit", **kw)


@pytest.mark.parametrize(
    "name,month",
    [("HSSD GPU Thang 8 2026 - VTT.xlsx", 8), ("HSSD_GPU_Thang_10_2026_VTT.xlsx", 10), ("synthetic_t10.xlsx", 10),
     ("t11.xlsx", 11), ("HSSD_GPU_Daily_VTT_thang7.xlsx", 7), ("tháng 12.xlsx", 12), ("bao_cao.xlsx", None),
     ("HSSD 2026.xlsx", None)],
)  # fmt: skip
def test_month_in_filename(name: str, month: int | None) -> None:
    assert month_in_filename(name) == month


def test_clean_file_preview_and_no_ack_needed(client: TestClient) -> None:
    b = up(client, FIX / "synthetic_t10.xlsx")
    assert codes(b, "error") == [] and codes(b, "warning") == []
    pv = b["summary"]["preview"]
    assert pv["threshold"] == 40 and pv["n_servers"] == 6 and pv["zones"] == {"danger": 2, "warning": 2, "safe": 2}
    days = [(80 + 50 + 5 + 60 + 2 + 0) / 6] * 4 + [(80 + 50 + 5 + 60 + 2 + 100) / 6]  # TB ngày tính tay
    assert pv["gpu_avg"] == pytest.approx(sum(days) / 5)
    assert [p["date"] for p in pv["daily"]] == [f"2026-10-0{d}" for d in range(1, 6)]
    assert pv["daily"][4]["gpu"] == pytest.approx(days[4]) and pv["daily"][0]["n_servers"] == 6
    assert b["summary"]["previous"] is None
    assert commit(client, b).status_code == 200  # không cảnh báo → không cần acknowledge


def test_warning_requires_acknowledge(client: TestClient) -> None:
    b = up(client, FIX / "synthetic_t10.xlsx", name="HSSD GPU Thang 8 2026 - VTT.xlsx")
    w = check(b, "filename_month")
    assert w["level"] == "warning" and "tháng 8" in w["title"] and "tháng 10" in w["title"]
    r = commit(client, b)
    assert r.status_code == 409 and r.json()["type"] == "ack_required" and "Tên file ghi tháng 8" in r.json()["detail"]
    assert commit(client, b, ack=False).status_code == 409
    assert commit(client, b, ack=True).status_code == 200
    log = client.get("/api/v1/audit", params={"action": "import_committed"}).json()["items"][0]
    assert log["payload"]["acknowledged"] == ["filename_month"]


def test_future_dates_block(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(import_checks, "today", lambda: dt.date(2026, 10, 3))
    b = up(client, FIX / "synthetic_t10.xlsx")
    e = check(b, "future_dates")
    assert e["level"] == "error" and e["items"] == ["2026-10-04", "2026-10-05"]
    r = commit(client, b, ack=True)
    assert r.status_code == 409 and r.json()["type"] == "import_blocked" and "hủy lô" in r.json()["detail"]
    assert client.post(f"/api/v1/imports/{b['id']}/discard").status_code == 200


def test_missing_days_out_of_range_multi_type(client: TestClient, tmp_path: Path) -> None:
    series = {
        "192.0.2.1": ("4×NVIDIA L40S", [80, 120, 80, 80], [85] * 4),  # 120% → ngoài 0–100
        "192.0.2.2": ("2×NVIDIA A30", [50] * 4, [60] * 4),
    }
    days = [OCT[0], OCT[1], OCT[3], OCT[4]]  # thiếu 03/10
    extra = [("192.0.2.2", 50, 60, "4×NVIDIA A30", dt.datetime(2026, 10, 5, 12), "VTT")]  # .2 có 2 loại GPU
    p = tmp_path / "HSSD_GPU_Thang_10_2026.xlsx"
    make_synthetic.make_t10(p, series=series, days=days, extra_rows=extra, reclaimed=False)
    b = up(client, p)
    assert check(b, "missing_days")["items"] == ["2026-10-03"]
    oor = check(b, "out_of_range")
    assert oor["level"] == "warning" and oor["items"] == ["192.0.2.1"] and oor["title"].startswith("1 mẫu")
    assert check(b, "multi_gpu_type")["items"] == ["192.0.2.2"]
    assert "parser_notes" in codes(b, "warning")  # gpu_core ghi chú: giá trị ngoài [0,100], dữ liệu theo giờ


def test_reimport_overview_mismatch_and_server_drop(client: TestClient, tmp_path: Path) -> None:
    assert commit(client, up(client, FIX / "synthetic_t10.xlsx")).status_code == 200
    # 1) sửa 1 giá trị raw (overview giữ nguyên) → lệch overview + thay mẫu đã nhập
    from test_import_api import edited_t10

    b = up(client, edited_t10(tmp_path, "192.0.2.1", 1, 81))
    assert {"overview_mismatch", "overlap_replace"} <= set(codes(b, "warning"))
    assert check(b, "overview_mismatch")["items"] == ["192.0.2.1"]
    assert check(b, "overlap_replace")["title"] == "Sẽ thay 1 mẫu đã nhập trước đó"
    assert b["summary"]["previous"]["zones"] == {"danger": 2, "warning": 2, "safe": 2}
    assert client.post(f"/api/v1/imports/{b['id']}/discard").status_code == 200
    # 2) kỳ sau chỉ còn 2/6 server → giảm mạnh (> 20%)
    nov = tmp_path / "t11.xlsx"
    keep = {k: v for k, v in make_synthetic.SERIES.items() if k in ("192.0.2.1", "192.0.2.2")}
    make_synthetic.make_t10(nov, series=keep, days=[dt.datetime(2026, 11, d) for d in range(1, 6)], reclaimed=False)
    b = up(client, nov)
    drop = check(b, "server_drop")
    assert drop["level"] == "warning" and drop["title"] == "Số server giảm mạnh: 6 → 2"
    assert drop["items"] == ["192.0.2.3", "192.0.2.4", "192.0.2.5", "192.0.2.6"]
    assert "gone_ips" not in codes(b)  # đã gộp vào cảnh báo giảm mạnh
    prev = b["summary"]["previous"]
    assert (prev["n_ips"], prev["label"], prev["period_start"]) == (6, "2026-10", "2026-10-01")


@pytest.mark.parametrize("path", [T7, T8, T9, T10], ids=["T7", "T8", "T9", "T10"])
def test_real_files_have_no_blocking_errors(client: TestClient, path: Path) -> None:
    """File VTNet thật T7–T10: không có lỗi chặn; tên file khớp tháng dữ liệu; số server xem trước = số IP của lô."""
    if not path.exists():
        pytest.skip(f"thiếu dữ liệu thật trong samples/: {path.name}")
    b = up(client, path)
    assert codes(b, "error") == []
    assert "filename_month" not in codes(b) and "period_too_long" not in codes(b)
    assert b["summary"]["preview"]["n_servers"] == b["summary"]["n_ips"]
    assert "missing_columns" not in codes(b) and "daily_mismatch" not in codes(b)
    assert ("daily_missing" in codes(b, "info")) == (path == T7)  # T7 chưa có sheet theo ngày


# ---------------------------------------------------------------- cấu trúc chuẩn (= file HSSD GPU T7–T10 trong samples/)

SYN_MEM = (85 + 60 + 90 + 20 + 3 + 30) / 6  # make_synthetic: mem không đổi theo ngày
SYN_GPU = {d: (80 + 50 + 5 + 60 + 2 + (100 if d == 5 else 0)) / 6 for d in range(1, 6)}


def edited(tmp_path: Path, name: str, fn: Any) -> Path:
    import openpyxl

    wb = openpyxl.load_workbook(FIX / "synthetic_t10.xlsx")
    fn(wb)
    p = tmp_path / f"{name}.xlsx"
    wb.save(p)
    return p


def add_daily(rows: list[tuple[int, float, float, int]]) -> Any:
    def f(wb: Any) -> None:
        ws = wb.create_sheet("HSSD theo ngay VTT")
        ws.append(["HSSD GPU THEO NGÀY - CỦA VTT"])
        ws.append([])
        ws.append(["Ngày", "GPU Core %", "GPU Memory %", "Số server"])
        for d, gpu, mem, n in rows:
            ws.append([dt.datetime(2026, 10, d), gpu, mem, n])

    return f


def drop_col(col: str) -> Any:
    def f(wb: Any) -> None:
        ws = wb["server_raw"]
        ws.delete_cols([c.value for c in ws[1]].index(col) + 1)

    return f


def test_daily_sheet_match_and_mismatch(client: TestClient, tmp_path: Path) -> None:
    good = [(d, SYN_GPU[d], SYN_MEM, 6) for d in range(1, 6)]
    b = up(client, edited(tmp_path, "ok", add_daily(good)))
    assert "daily_mismatch" not in codes(b) and "daily_missing" not in codes(b) and codes(b, "warning") == []
    assert b["validation"]["daily_check"]["ok"] is True and b["validation"]["daily_check"]["n_common"] == 5
    bad = [(d, SYN_GPU[d] + (1 if d == 3 else 0), SYN_MEM, 6) for d in range(1, 6)] + [(6, 10.0, 10.0, 6)]
    b2 = up(client, edited(tmp_path, "bad", add_daily(bad)))
    w = check(b2, "daily_mismatch")
    assert w["level"] == "warning" and w["items"] == ["2026-10-03", "2026-10-06"] and "2 ngày lệch" in w["detail"]
    assert commit(client, b2).json()["type"] == "ack_required"


def test_no_daily_sheet_is_info(client: TestClient) -> None:
    b = up(client, FIX / "synthetic_t10.xlsx")
    assert check(b, "daily_missing")["level"] == "info" and b["validation"]["daily_check"] is None


@pytest.mark.parametrize("col", ["don_vi", "gpu_type"])
def test_missing_standard_column_needs_ack(client: TestClient, tmp_path: Path, col: str) -> None:
    b = up(client, edited(tmp_path, col, drop_col(col)))
    w = check(b, "missing_columns")
    assert w["level"] == "warning" and w["items"] == [col] and col in w["title"]
    assert commit(client, b).status_code == 409


def test_missing_overview_is_info_only(client: TestClient, tmp_path: Path) -> None:
    b = up(client, edited(tmp_path, "noov", lambda wb: wb.remove(wb["VTT_KPI_overview"])))
    assert codes(b, "warning") == [] and "overview_missing" in codes(b, "info")
    assert commit(client, b).status_code == 200  # không bắt xác nhận 2 lần cho cùng 1 việc


def test_no_valid_rows_explains_why(client: TestClient, tmp_path: Path) -> None:
    def text_pct(wb: Any) -> None:
        ws = wb["server_raw"]
        gi = [c.value for c in ws[1]].index("gpu") + 1
        for r in range(2, ws.max_row + 1):
            ws.cell(r, gi).value = f"{ws.cell(r, gi).value}%"

    with edited(tmp_path, "pct", text_pct).open("rb") as f:
        r = client.post("/api/v1/imports", files={"file": ("pct.xlsx", f, "application/octet-stream")})
    assert r.status_code == 422
    d = r.json()["detail"]
    assert "Sheet 'server_raw' không còn dòng hợp lệ" in d and "thiếu ngày/giá trị" in d and "phải là số" in d
