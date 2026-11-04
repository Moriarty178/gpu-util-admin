"""File VTNet theo TUẦN (PLAN §14.8, người dùng chốt 04/11/2026): nhãn kỳ tuần ISO, kiểm tên file, khoảng trống giữa các
lô, khoảng xem mặc định 4 tuần gần nhất, cắt khoảng xem về ngày có dữ liệu. Kỳ vọng tính tay từ make_synthetic.SERIES
(giá trị mỗi server không đổi theo ngày, trừ .6: gpu 0 → vùng Nguy hiểm khi T = 40) — không sinh từ code đang test."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from conftest import make_synthetic
from fastapi.testclient import TestClient
from realdata import T7, T8, needs

from app.services.import_checks import coverage_gaps, period_label, week_in_filename

S = make_synthetic.SERIES
FLAT = {ip: (gt, [g[0]], [m[0]]) for ip, (gt, g, m) in S.items()}  # 1 giá trị/ngày; .6 → gpu 0 / mem 30


def week_file(tmp: Path, name: str, start: dt.date, n: int = 7) -> Path:
    days = [dt.datetime(start.year, start.month, start.day) + dt.timedelta(days=i) for i in range(n)]
    series = {ip: (gt, g * n, m * n) for ip, (gt, g, m) in FLAT.items()}
    p = tmp / name
    make_synthetic.make_t10(p, series=series, days=days, reclaimed=False)
    return p


def up(c: TestClient, path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        r = c.post("/api/v1/imports", files={"file": (path.name, f, "application/octet-stream")})
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


def commit(c: TestClient, b: dict[str, Any]) -> None:
    r = c.post(f"/api/v1/imports/{b['id']}/commit", json={"acknowledge": True})
    assert r.status_code == 200, r.text


def checks(b: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {x["code"]: x for x in b["validation"]["checks"]}


@pytest.mark.parametrize(
    "name,week",
    [("HSSD_GPU_Tuan_42_2026_VTT.xlsx", 42), ("Tuần 7 2026.xlsx", 7), ("HSSD W45.xlsx", 45), ("week_01.xlsx", 1),
     ("tuan 2 thang 11.xlsx", None), ("HSSD GPU Thang 8 2026 - VTT.xlsx", None), ("tuan_60.xlsx", None),
     ("bao_cao.xlsx", None)],
)  # fmt: skip
def test_week_in_filename(name: str, week: int | None) -> None:
    assert week_in_filename(name) == week  # 'tuần 2 tháng 11' = tuần thứ 2 của tháng, không phải tuần ISO → bỏ qua


def test_period_label() -> None:
    d = dt.date
    oct5 = [d(2026, 10, i) for i in range(1, 6)]  # 01–04/10 thuộc W40 (thứ 5 → CN), 05/10 thứ 2 W41
    assert period_label(d(2026, 10, 1), d(2026, 10, 5), oct5, "2026-10") == "2026-W40"
    wk = [d(2026, 9, 28) + dt.timedelta(days=i) for i in range(7)]  # 28/09 (thứ 2) → 04/10 vắt 2 tháng
    assert period_label(wk[0], wk[-1], wk, "2026-10") == "2026-W40"
    tie = [d(2026, 10, 4), d(2026, 10, 5)]  # 1 ngày W40, 1 ngày W41 → tuần sớm hơn
    assert period_label(tie[0], tie[1], tie, "2026-10") == "2026-W40"
    jan = [d(2026, 12, 28) + dt.timedelta(days=i) for i in range(7)]  # tuần ISO 53 của 2026 (28/12/2026 → 03/01/2027)
    assert period_label(jan[0], jan[-1], jan, "2026-12") == "2026-W53"
    month = [d(2026, 10, 1) + dt.timedelta(days=i) for i in range(32)]  # file tháng (> 10 ngày) → giữ nhãn tháng
    assert period_label(month[0], month[-1], month, "2026-10") == "2026-10"


def test_weekly_label_and_filename_checks(client: TestClient, tmp_path: Path) -> None:
    b = up(client, week_file(tmp_path, "HSSD_GPU_Tuan_42_2026_VTT.xlsx", dt.date(2026, 10, 12)))
    assert (b["period_start"], b["period_end"], b["period_label"]) == ("2026-10-12", "2026-10-18", "2026-W42")
    assert "filename_week" not in checks(b) and "filename_month" not in checks(b)
    assert [x for x in b["validation"]["checks"] if x["level"] == "warning"] == []
    wrong = up(client, week_file(tmp_path, "HSSD_GPU_Tuan_43_2026_VTT.xlsx", dt.date(2026, 10, 12)))
    assert checks(wrong)["filename_week"]["title"] == "Tên file ghi tuần 43 nhưng dữ liệu là tuần 42"
    # tuần vắt tháng 28/09–04/10 (4 ngày tháng 10): tên ghi tháng 9 vẫn hợp lệ, tháng 11 thì không
    assert "filename_month" not in checks(up(client, week_file(tmp_path, "Tuan 40 thang 9.xlsx", dt.date(2026, 9, 28))))
    assert "filename_month" in checks(up(client, week_file(tmp_path, "Tuan 40 thang 11.xlsx", dt.date(2026, 9, 28))))


def test_coverage_gap_between_batches(client: TestClient, tmp_path: Path) -> None:
    commit(client, up(client, week_file(tmp_path, "w41.xlsx", dt.date(2026, 10, 5))))  # 05–11/10
    b = up(client, week_file(tmp_path, "w43.xlsx", dt.date(2026, 10, 19)))  # 19–25/10 → thiếu cả tuần 12–18/10
    gap = checks(b)["coverage_gap"]
    assert gap["level"] == "warning" and gap["title"] == "Khoảng trống 7 ngày chưa có dữ liệu VTNet giữa các lô"
    assert gap["items"] == [f"2026-10-{d}" for d in range(12, 19)] and gap["detail"].startswith(
        "12/10/2026 → 18/10/2026"
    )
    assert client.post(f"/api/v1/imports/{b['id']}/commit").status_code == 409  # cảnh báo → phải xác nhận đã xem
    commit(client, b)
    back = up(client, week_file(tmp_path, "bu.xlsx", dt.date(2026, 10, 12), n=3))  # nhập bù 12–14/10 → còn 15–18/10
    assert checks(back)["coverage_gap"]["items"] == [f"2026-10-{d}" for d in range(15, 19)]
    commit(client, back)
    assert "coverage_gap" not in checks(up(client, week_file(tmp_path, "lap.xlsx", dt.date(2026, 10, 15), n=4)))


def test_coverage_gaps_unit() -> None:
    d = dt.date
    cov = [(d(2026, 10, 5), d(2026, 10, 11)), (d(2026, 10, 19), d(2026, 10, 25)), (d(2026, 10, 12), d(2026, 10, 14))]
    # đang có khoảng trống 15–18/10. Nhập lại 12–14/10 (đã có, sửa số) → không thêm ngày nào → không báo lại
    assert coverage_gaps(d(2026, 10, 12), d(2026, 10, 14), cov) == []
    assert coverage_gaps(d(2026, 10, 12), d(2026, 10, 15), cov) == [(d(2026, 10, 16), d(2026, 10, 18))]
    assert coverage_gaps(d(2026, 10, 27), d(2026, 11, 2), cov) == [(d(2026, 10, 26), d(2026, 10, 26))]
    assert coverage_gaps(d(2026, 9, 1), d(2026, 9, 7), cov) == [(d(2026, 9, 8), d(2026, 10, 4))]  # nhập bù kỳ cũ
    assert coverage_gaps(d(2026, 10, 5), d(2026, 10, 11), []) == []  # lô đầu tiên


@needs(T7, T8)
def test_real_t8_after_t7_reports_missing_july_31(client: TestClient) -> None:
    """File T7 thật dừng ở 30/07 (CONTEXT §7: 30 ngày), T8 bắt đầu 01/08 → khoảng trống đúng 1 ngày 31/07."""
    commit(client, up(client, T7))
    gap = checks(up(client, T8))["coverage_gap"]
    assert gap["items"] == ["2026-07-31"] and gap["title"].startswith("Khoảng trống 1 ngày")


@pytest.fixture
def five_weeks(client: TestClient, tmp_path: Path) -> TestClient:
    for i, start in enumerate(dt.date(2026, 9, 21) + dt.timedelta(days=7 * k) for k in range(5)):  # 21/09 → 25/10
        commit(client, up(client, week_file(tmp_path, f"tuan_{39 + i}.xlsx", start)))
    return client


def test_default_range_is_last_4_weeks(five_weeks: TestClient) -> None:
    m = five_weeks.get("/api/v1/meta").json()
    assert m["data_range"] == {"start": "2026-09-21", "end": "2026-10-25"}
    assert m["default_range"] == {"start": "2026-09-28", "end": "2026-10-25"}  # 28 ngày, kết thúc ngày cuối có dữ liệu
    assert [p["label"] for p in m["periods"]] == ["2026-W43", "2026-W42", "2026-W41", "2026-W40", "2026-W39"]
    p = five_weeks.get("/api/v1/fleet/summary").json()["params"]
    assert (p["start"], p["end"], p["days_in_range"], p["clamped"]) == ("2026-09-28", "2026-10-25", 28, False)


def test_range_clamped_to_data(five_weeks: TestClient) -> None:
    s = five_weeks.get("/api/v1/fleet/summary", params={"start": "2026-10-01", "end": "2026-10-31"}).json()
    p = s["params"]
    assert (p["start"], p["end"], p["days_in_range"], p["clamped"]) == ("2026-10-01", "2026-10-25", 25, True)
    assert (p["requested_start"], p["requested_end"]) == ("2026-10-01", "2026-10-31")
    assert s["thin_data"] == 0 and s["n_servers"] == 6  # không cắt: 25/31 ngày < 0,8 → cả 6 server "dữ liệu mỏng"
    assert s["zones"] == {"danger": 2, "warning": 2, "safe": 2}  # .5 2/3, .6 0/30 · .3 5/90, .4 60/20 · .1, .2
    out = five_weeks.get("/api/v1/fleet/summary", params={"start": "2026-12-01", "end": "2026-12-31"}).json()
    assert out["params"]["clamped"] is False and out["n_servers"] == 0  # hoàn toàn ngoài dữ liệu → giữ nguyên
