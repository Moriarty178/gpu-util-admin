"""Báo cáo tháng (Roadmap §14.2): số liệu + deck .pptx. Kỳ vọng tính tay từ fixture tổng hợp (make_synthetic, T = 40):

  T8 (01–05/08): .1 80/85 An toàn · .5 2/3 Nguy hiểm
  T9 (01–05/09): .1 80/85 An toàn · .2 10/10 Nguy hiểm · .3 5/90 Cảnh báo · .4 60/20 Cảnh báo · .5 2/3 Nguy hiểm
                 · .7 50/50 An toàn (chỉ có ở T9)
  T10 = synthetic_t10.xlsx: .1 .2 An toàn · .3 .4 Cảnh báo · .5 Nguy hiểm (1 card) · .6 Nguy hiểm (8 card, chưa có thống kê)
T9 → T10: .2 cải thiện, .6 mới, .7 không còn, 4 server (.1 .3 .4 .5) giữ nguyên. Chuỗi Nguy hiểm: .5 = T8, T9, T10 (3, chạm tháng đầu → '≥').
  T11 = 1 ngày 01/11 (chỉ .1) → tháng 10 "đã qua" (dữ liệu tới 01/11) nên xuất được; tháng 11 chưa đủ → chặn xuất (PLAN §14.8).
"""

from __future__ import annotations

import datetime as dt
import io
from pathlib import Path
from typing import Any

import pytest
from conftest import FIX, make_synthetic
from fastapi.testclient import TestClient
from pptx import Presentation
from realdata import INV7, T7, T8, T9, T10

S = make_synthetic.SERIES
AUG = {"192.0.2.1": S["192.0.2.1"], "192.0.2.5": S["192.0.2.5"]}
SEP = {
    "192.0.2.1": S["192.0.2.1"],
    "192.0.2.2": ("2×NVIDIA A30", [10] * 5, [10] * 5),
    "192.0.2.3": S["192.0.2.3"],
    "192.0.2.4": S["192.0.2.4"],
    "192.0.2.5": S["192.0.2.5"],
    "192.0.2.7": ("1×NVIDIA L4", [50] * 5, [50] * 5),
}
OCT_GPU = (4 * (80 + 50 + 5 + 60 + 2 + 0) / 6 + (80 + 50 + 5 + 60 + 2 + 100) / 6) / 5  # TB ngày, tính tay
SEP_GPU = (80 + 10 + 5 + 60 + 2 + 50) / 6


def upload(c: TestClient, path: Path) -> None:
    with path.open("rb") as f:
        b = c.post("/api/v1/imports", files={"file": (path.name, f, "application/octet-stream")}).json()
    r = c.post(f"/api/v1/imports/{b['id']}/commit", json={"acknowledge": True})
    assert r.status_code == 200, r.text


@pytest.fixture
def three_months(client: TestClient, tmp_path: Path) -> TestClient:
    for name, series, month in (("t8", AUG, 8), ("t9", SEP, 9)):
        p = tmp_path / f"synthetic_{name}.xlsx"
        make_synthetic.make_t10(p, series=series, days=[dt.datetime(2026, month, d) for d in range(1, 6)],
                                reclaimed=False)  # fmt: skip
        upload(client, p)
    upload(client, FIX / "synthetic_inventory.xlsx")
    upload(client, FIX / "synthetic_t10.xlsx")
    p = tmp_path / "synthetic_t11_1ngay.xlsx"
    make_synthetic.make_t10(p, series={"192.0.2.1": ("4×NVIDIA L40S", [80], [85])}, days=[dt.datetime(2026, 11, 1)],
                            reclaimed=False)  # fmt: skip
    upload(client, p)
    return client


def report(c: TestClient, **params: Any) -> dict[str, Any]:
    r = c.get("/api/v1/reports/monthly", params=params)
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


def test_monthly_numbers(three_months: TestClient) -> None:
    d = report(three_months)  # mặc định = tháng ĐỦ dữ liệu mới nhất (tháng 11 mới có 01/11)
    assert (d["month"], d["label"], d["start"], d["end"]) == ("2026-10", "tháng 10/2026", "2026-10-01", "2026-10-31")
    assert d["available_months"] == ["2026-11", "2026-10", "2026-09", "2026-08"] and d["threshold"] == 40
    assert d["incomplete_months"] == ["2026-11"]
    c = d["completeness"]
    assert (c["days_in_month"], c["days_with_data"], c["first"], c["last"], c["complete"]) == (
        31, 5, "2026-10-01", "2026-10-05", True)  # fmt: skip
    assert c["missing_days"] == [f"2026-10-{d:02d}" for d in range(6, 32)]  # tháng đã qua, thiếu ngày → vẫn xuất được
    k = d["kpi"]
    assert k["zones"] == {"danger": 2, "warning": 2, "safe": 2} and k["n_servers"] == 6 and k["n_unmapped"] == 1
    assert k["gpu_avg"] == pytest.approx(OCT_GPU) and k["mem_avg"] == pytest.approx((85 + 60 + 90 + 20 + 3 + 30) / 6)
    assert k["cards_total"]["danger"] == 1 + 8 and k["cards"] == 4 + 2 + 2 + 3 + 1 + 8
    assert [(m["month"], m["zones"]["danger"]) for m in d["trend"]] == [("2026-08", 1), ("2026-09", 2), ("2026-10", 2)]
    assert d["trend"][1]["gpu_avg"] == pytest.approx(SEP_GPU)
    assert d["previous"]["month"] == "2026-09" and d["previous"]["gpu_avg"] == pytest.approx(SEP_GPU)
    mv = d["movement"]
    assert mv["counts"] == {"worsened": 0, "improved": 1, "same": 4, "new": 1, "gone": 1}
    assert (
        mv["matrix"]["danger"]["safe"] == 1 and mv["matrix"]["new"]["danger"] == 1 and mv["matrix"]["safe"]["gone"] == 1
    )
    assert d["owners"]["rows"]["danger"] == {"dungha7": 0, "kientt6": 1, "_unmapped": 1}
    dz = [(r["ip"], r["cards"], r["streak_months"], r["streak_open"], r["mapped"]) for r in d["danger"]]
    assert dz == [("192.0.2.5", 1, 3, True, True), ("192.0.2.6", 8, 1, False, False)]
    sug = d["suggestion"]
    assert sug["message"] == (
        "TB GPU tháng 10/2026 đạt 36,2% (+1,7 điểm so với tháng 9/2026); 2/6 server Nguy hiểm (9 card) cần rà soát "
        "với đầu mối."
    )
    assert [r["title"] for r in sug["recommendations"]] == [
        "Rà soát 2 server Nguy hiểm (9 card)", "Cập nhật file thống kê server",
    ]  # fmt: skip
    assert (
        "kientt6 (1)" in sug["recommendations"][0]["detail"]
        and "1 server Nguy hiểm từ 3 tháng" in (sug["recommendations"][0]["detail"])
    )


def test_earlier_month_and_errors(three_months: TestClient) -> None:
    d = report(three_months, month="2026-08")
    assert d["previous"] is None and d["movement"] is None and [m["month"] for m in d["trend"]] == ["2026-08"]
    assert d["danger"][0]["streak_open"] is True  # tháng đầu có dữ liệu → có thể dài hơn
    assert three_months.get("/api/v1/reports/monthly", params={"month": "2026-12"}).status_code == 404
    assert three_months.get("/api/v1/reports/monthly", params={"month": "2026-13"}).status_code == 422


def test_incomplete_month_blocks_export(three_months: TestClient) -> None:
    d = report(three_months, month="2026-11")  # xem được số
    c = d["completeness"]
    assert (c["days_with_data"], c["days_in_month"], c["last"], c["complete"], c["missing_days"]) == (
        1, 30, "2026-11-01", False, [])  # fmt: skip
    r = three_months.post("/api/v1/reports/monthly.pptx", json={"month": "2026-11"})
    assert r.status_code == 409 and r.json()["type"] == "month_incomplete"
    assert r.json()["detail"] == (
        "Tháng 11/2026 chưa đủ dữ liệu: mới có dữ liệu tới 01/11/2026 (1/30 ngày). "
        "Chỉ xuất được báo cáo khi đã nhập file VTNet tới hết 30/11/2026."
    )
    log = three_months.get("/api/v1/audit", params={"action": "report_exported"}).json()["items"]
    assert log == []  # bị chặn → không ghi "đã xuất"


def test_no_data(client: TestClient) -> None:
    r = client.get("/api/v1/reports/monthly")
    assert r.status_code == 422 and "Chưa có file tải VTNet" in r.json()["detail"]


def slides_text(prs: Any) -> list[str]:
    out = []
    for sl in prs.slides:
        parts = [sh.text_frame.text for sh in sl.shapes if sh.has_text_frame]
        for sh in sl.shapes:
            if sh.has_table:
                parts += [c.text for row in sh.table.rows for c in row.cells]
        out.append("\n".join(parts))
    return out


def charts(slide: Any) -> list[Any]:
    return [sh.chart for sh in slide.shapes if sh.has_chart]


def test_pptx_matches_numbers(three_months: TestClient) -> None:
    r = three_months.post("/api/v1/reports/monthly.pptx", json={"month": "2026-10"})
    assert r.status_code == 200, r.text
    assert "Bao_cao_GPU_thang_10_2026.pptx" in r.headers["content-disposition"]
    prs = Presentation(io.BytesIO(r.content))
    assert len(prs.slides) == 7 and prs.slide_width == 9144000 and prs.slide_height == 5143500  # 10 × 5.625 in
    txt = slides_text(prs)
    msg = report(three_months)["suggestion"]["message"]
    assert msg in txt[0] and msg in txt[6] and "[Cần" not in "".join(txt)  # đủ số liệu → không còn placeholder
    donut = charts(prs.slides[1])[0]
    assert list(donut.plots[0].series[0].values) == [2, 2, 2]
    line, bars = charts(prs.slides[2])
    assert list(line.plots[0].categories) == ["T8/2026", "T9/2026", "T10/2026"]
    assert line.plots[0].series[0].values[1:] == pytest.approx((SEP_GPU, OCT_GPU))
    assert list(bars.plots[0].series[0].values) == [1, 2, 2]  # Nguy hiểm theo tháng
    assert "So với T9/2026: 0 server xấu đi, 1 cải thiện" in txt[3]
    owners = charts(prs.slides[4])[0]
    assert list(owners.plots[0].categories) == ["kientt6", "dungha7", "Chưa có trong thống kê"]
    tbl = next(sh.table for sh in prs.slides[5].shapes if sh.has_table)
    rows = [[c.text for c in row.cells] for row in tbl.rows]
    assert [r[0] for r in rows[1:]] == ["192.0.2.5", "192.0.2.6"] and rows[1][-1] == "≥3 tháng"
    assert rows[2][1] == "(chưa có)" and rows[1][5] == "2,0%"
    for t in ("Rà soát 2 server Nguy hiểm (9 card)", "Cập nhật file thống kê server"):
        assert t in txt[6]
    log = three_months.get("/api/v1/audit", params={"action": "report_exported"}).json()["items"][0]
    assert log["target"] == "2026-10" and log["payload"]["edited"] is False


def test_pptx_custom_text_and_limits(three_months: TestClient) -> None:
    body = {"month": "2026-09", "message": "Thông điệp do admin viết.",
            "recommendations": [{"title": "Kiến nghị A", "detail": "Chi tiết A"}]}  # fmt: skip
    r = three_months.post("/api/v1/reports/monthly.pptx", json=body)
    assert r.status_code == 200
    txt = slides_text(Presentation(io.BytesIO(r.content)))
    assert "Thông điệp do admin viết." in txt[0] and "Kiến nghị A" in txt[6] and "Rà soát" not in txt[6]
    assert "tháng 9/2026" in txt[0]
    too_long = {**body, "message": "x" * 221}
    assert three_months.post("/api/v1/reports/monthly.pptx", json=too_long).status_code == 422
    four = {**body, "recommendations": [{"title": f"K{i}"} for i in range(4)]}
    assert three_months.post("/api/v1/reports/monthly.pptx", json=four).status_code == 422


def test_real_t7_t10_golden(client: TestClient) -> None:
    """Golden độc lập (CONTEXT §7): T7 = 21/48/19 (An toàn/Cảnh báo/Nguy hiểm, 88 server); Nguy hiểm T7 → T10: 19 → 11."""
    missing = [p.name for p in (INV7, T7, T8, T9, T10) if not p.exists()]
    if missing:
        pytest.skip(f"thiếu dữ liệu thật trong samples/: {', '.join(missing)}")
    for p in (INV7, T7, T8, T9, T10):
        upload(client, p)
    d = report(client, month="2026-10")
    assert [m["month"] for m in d["trend"]] == ["2026-07", "2026-08", "2026-09", "2026-10"]  # không có "tháng 11"
    assert d["incomplete_months"] == ["2026-11"]  # ngày tràn 01/11 của file T10 → tháng 11 có 1 ngày, chưa đủ
    t7 = report(client, month="2026-07")["completeness"]
    assert (t7["complete"], t7["days_with_data"], t7["missing_days"]) == (
        True,
        30,
        ["2026-07-31"],
    )  # file T7 dừng ở 30/07
    t7 = d["trend"][0]
    assert (t7["n_servers"], t7["zones"]) == (88, {"danger": 19, "warning": 48, "safe": 21})
    assert d["kpi"]["zones"]["danger"] == 11 and len(d["danger"]) == 11
    assert d["kpi"]["vtnet_low_load"] == 1 and any(
        r["ip"] == "10.221.122.33" and r["vtnet_low_load"] for r in d["danger"]
    )
    r = client.post("/api/v1/reports/monthly.pptx", json={"month": "2026-10"})
    assert r.status_code == 200 and len(Presentation(io.BytesIO(r.content)).slides) == 7


def test_single_metric_report(three_months: TestClient) -> None:
    """Áp T chỉ cho compute (PLAN §14.9), tính tay: T8 Nguy hiểm .5 · T9 .2 (10/10) .3 (5/90) .5 · T10 .3 .5 .6;
    .4 (60/20) An toàn mọi tháng. T9 → T10: .2 cải thiện, .3 .5 giữ Nguy hiểm."""
    d = report(three_months, month="2026-10", zone_metric="gpu")
    assert d["zone_metric"] == "gpu" and d["kpi"]["zones"] == {"danger": 3, "warning": 0, "safe": 3}
    assert [m["zones"]["danger"] for m in d["trend"]] == [1, 3, 3]
    assert d["movement"]["counts"]["improved"] == 1 and d["movement"]["counts"]["worsened"] == 0
    streak = {r["ip"]: (r["streak_months"], r["streak_open"]) for r in d["danger"]}
    assert streak == {"192.0.2.3": (2, False), "192.0.2.5": (3, True), "192.0.2.6": (1, False)}
    r = three_months.post("/api/v1/reports/monthly.pptx", json={"month": "2026-10", "zone_metric": "gpu"})
    assert r.status_code == 200, r.text
    txt = slides_text(Presentation(io.BytesIO(r.content)))
    assert "Ngưỡng T = 40% · chỉ compute" in txt[0] and "Vùng theo ngưỡng T = 40% · chỉ compute" in txt[6]
    assert report(three_months, month="2026-10")["kpi"]["zones"] == {"danger": 2, "warning": 2, "safe": 2}
