"""API phân tích G1-M2 trên fixture tổng hợp — kết quả biết trước, tính tay từ thiết kế fixture (make_synthetic.py).

Fixture: 6 server × 01–05/10/2026, T=40
  .1 4×L40S 80/85 safe high_load · .2 2×A30 50/60 safe healthy · .3 2×L4 5/90 warning memory_bound
  .4 3×A30 60/20 warning compute_bound · .5 1×A30 2/3 danger idle (+cờ VTNet) · .6 8×H200 [0,0,0,0,100]/30 danger bursty
Thống kê: .1 .2 .9 = dungha7; .3 .4 .5 = kientt6; .6 chỉ có ở VTNet; .9 chỉ có ở thống kê. 'DS đã thu': .50
"""

from __future__ import annotations

import datetime as dt
import io
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from conftest import FIX, make_synthetic
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session

from app.db.models import IpLink

API = "/api/v1"


def load(client: TestClient, *paths: Path) -> None:
    for p in paths:
        with p.open("rb") as f:
            r = client.post(f"{API}/imports", files={"file": (p.name, f, "application/octet-stream")})
        assert r.status_code == 201, r.text
        assert client.post(f"{API}/imports/{r.json()['id']}/commit", json={"acknowledge": True}).status_code == 200


def get(client: TestClient, path: str, **params: Any) -> Any:
    r = client.get(f"{API}{path}", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def link(engine: Engine, inventory_ip: str, vtnet_ip: str) -> None:
    with Session(engine) as s, s.begin():
        s.add(
            IpLink(inventory_ip=inventory_ip, vtnet_ip=vtnet_ip, created_by="test", created_at=dt.datetime(2026, 11, 3))
        )


@pytest.fixture
def loaded(client: TestClient) -> TestClient:
    load(client, FIX / "synthetic_t10.xlsx", FIX / "synthetic_inventory.xlsx")
    return client


# ------------------------------------------------------------------ Tổng quan


def test_fleet_timeseries_day_server(loaded: TestClient) -> None:
    ts = get(loaded, "/fleet/timeseries")  # mặc định: 4 tuần gần nhất, cắt về dữ liệu (chỉ có 01–05/10)
    assert ts["params"] == {"start": "2026-10-01", "end": "2026-10-05", "threshold": 40.0, "days_in_range": 5,
                            "clamped": False, "requested_start": None, "requested_end": None}  # fmt: skip
    assert [p["date"] for p in ts["points"]] == [f"2026-10-0{d}" for d in range(1, 6)]
    d1, d5 = ts["points"][0], ts["points"][-1]
    assert d1["gpu"] == pytest.approx((80 + 50 + 5 + 60 + 2 + 0) / 6) and d1["mem"] == pytest.approx(288 / 6)
    assert d5["gpu"] == pytest.approx((80 + 50 + 5 + 60 + 2 + 100) / 6) and d1["n_servers"] == 6
    assert ts["avg"]["gpu"] == pytest.approx((4 * 197 / 6 + 297 / 6) / 5)  # mean chuỗi ngày


def test_fleet_timeseries_week_month_gpu_weight(loaded: TestClient) -> None:
    wk = get(loaded, "/fleet/timeseries", granularity="week")["points"]
    # 01/10/2026 là thứ Năm → tuần ISO bắt đầu 28/09 (4 ngày) và 05/10 (1 ngày)
    assert [(p["date"], p["n_days"]) for p in wk] == [("2026-09-28", 4), ("2026-10-05", 1)]
    assert wk[0]["gpu"] == pytest.approx(197 / 6) and wk[1]["gpu"] == pytest.approx(297 / 6)
    mo = get(loaded, "/fleet/timeseries", granularity="month")["points"]
    assert len(mo) == 1 and mo[0]["date"] == "2026-10-01" and mo[0]["gpu"] == pytest.approx((4 * 197 / 6 + 297 / 6) / 5)
    g1 = get(loaded, "/fleet/timeseries", weight="gpu")["points"][0]
    assert g1["gpu"] == pytest.approx((80 * 4 + 50 * 2 + 5 * 2 + 60 * 3 + 2 * 1 + 0 * 8) / 20)  # trọng số số card


def test_fleet_summary(loaded: TestClient) -> None:
    sm = get(loaded, "/fleet/summary")
    assert (sm["n_servers"], sm["n_mapped"], sm["n_unmapped"]) == (6, 5, 1)
    assert sm["zones"] == {"danger": 2, "warning": 2, "safe": 2}
    assert sm["patterns"] == {
        k: 1 for k in ("idle", "bursty_idle", "memory_bound", "compute_bound", "high_load", "healthy")
    }
    assert (sm["vtnet_low_load"], sm["thin_data"]) == (1, 0)
    assert sm["cards_by_zone"]["danger"] == {"H200": 8, "A30": 1} and sm["cards_total"] == {
        "danger": 9,
        "warning": 5,
        "safe": 6,
    }
    m = sm["matrix"]
    assert m["owners"] == ["dungha7", "kientt6", "_unmapped"] and m["mapped_total"] == 5
    assert m["rows"]["safe"] == {"dungha7": 2, "kientt6": 0, "_unmapped": 0}
    assert m["rows"]["warning"] == {"dungha7": 0, "kientt6": 2, "_unmapped": 0}
    assert m["rows"]["danger"] == {"dungha7": 0, "kientt6": 1, "_unmapped": 1}


# ------------------------------------------------------------------ Cảnh báo


def test_alerts_default_and_filters(loaded: TestClient) -> None:
    a = get(loaded, "/alerts")
    assert a["total"] == 6 and [i["ip"] for i in a["items"][:2]] == ["192.0.2.5", "192.0.2.6"]  # Nguy hiểm, GPU TB ↑
    d = get(loaded, "/alerts", zones="danger")
    assert d["total"] == 2 and d["summary"]["cards"] == 9 and d["summary"]["zones"]["danger"] == 2
    i5, i6 = d["items"]
    assert (i5["owner"], i5["pattern"], i5["vtnet_low_load"], i5["mapped"], i5["cards"]) == (
        "kientt6",
        "idle",
        True,
        True,
        1,
    )
    assert (i6["owner"], i6["pattern"], i6["mapped"], i6["gpu_peak"], i6["gpu_avg"]) == (
        None,
        "bursty_idle",
        False,
        100,
        20,
    )
    assert i6["low_streak"] == 0 and i5["low_streak"] == 5 and i5["danger_days"] == 5
    assert "NGUY HIỂM" in i5["assessment"] and "THẤP TẢI" in i5["assessment"]
    assert [i["ip"] for i in get(loaded, "/alerts", zones="danger", only_mapped=True)["items"]] == ["192.0.2.5"]
    assert [i["ip"] for i in get(loaded, "/alerts", vtnet_flag=True)["items"]] == ["192.0.2.5"]
    assert [i["ip"] for i in get(loaded, "/alerts", patterns="bursty_idle")["items"]] == ["192.0.2.6"]
    assert [i["ip"] for i in get(loaded, "/alerts", owner="_unmapped")["items"]] == ["192.0.2.6"]
    k = get(loaded, "/alerts", owner="kientt6")
    assert k["total"] == 3 and k["matrix"]["owners"] == ["kientt6", "_unmapped"]
    assert [i["ip"] for i in get(loaded, "/alerts", q="ocr")["items"]] == ["192.0.2.2"]
    assert [i["ip"] for i in get(loaded, "/alerts", gpu_model="A30")["items"]] == [
        "192.0.2.5",
        "192.0.2.4",
        "192.0.2.2",
    ]
    assert get(loaded, "/alerts", sort="-gpu_avg")["items"][0]["ip"] == "192.0.2.1"
    p2 = get(loaded, "/alerts", page=2, page_size=4)
    assert p2["total"] == 6 and len(p2["items"]) == 2


def test_alerts_threshold_changes_zones(loaded: TestClient) -> None:
    a = get(loaded, "/alerts", threshold=60)
    # biên <=: .2 50/60 và .4 60/20 → cả 2 <=60 → Nguy hiểm
    assert a["params"]["threshold"] == 60 and a["matrix"]["totals"] == {"danger": 4, "warning": 1, "safe": 1}
    assert next(i for i in a["items"] if i["ip"] == "192.0.2.2")["zone"] == "danger"


def test_alerts_range_clip(loaded: TestClient) -> None:
    a = get(loaded, "/alerts", start="2026-10-01", end="2026-10-04")
    i6 = next(i for i in a["items"] if i["ip"] == "192.0.2.6")
    assert i6["gpu_peak"] == 0 and i6["pattern"] == "idle" and i6["low_streak"] == 4  # ngày 05 nằm ngoài khoảng


def test_alerts_bad_params(loaded: TestClient) -> None:
    assert loaded.get(f"{API}/alerts", params={"threshold": 101}).status_code == 422
    r = loaded.get(f"{API}/alerts", params={"start": "2026-10-05", "end": "2026-10-01"})
    assert r.status_code == 422 and "Ngày bắt đầu" in r.json()["detail"]
    assert loaded.get(f"{API}/alerts", params={"sort": "khong_co"}).status_code == 422
    assert loaded.get(f"{API}/alerts", params={"zones": "do"}).status_code == 422


def test_empty_database(client: TestClient) -> None:
    a = get(client, "/alerts")
    assert a["total"] == 0 and a["matrix"]["owners"] == ["_unmapped"]
    assert get(client, "/fleet/timeseries")["points"] == []
    assert get(client, "/servers")["counts"]["inventory_rows"] == 0
    m = get(client, "/meta")
    assert m["periods"] == [] and m["default_range"] is None and m["settings"]["default_threshold"] == 40


def test_ip_link_and_gpu_count_mismatch(client: TestClient, engine: Engine, tmp_path: Path) -> None:
    inv = tmp_path / "inv.xlsx"
    rows = [
        r if r[0] != "192.0.2.5" else ("192.0.2.5", "3*A30", "kientt6", "Lab test") for r in make_synthetic.INVENTORY
    ]
    make_synthetic.make_inventory(inv, rows)
    load(client, FIX / "synthetic_t10.xlsx", inv)
    link(engine, "192.0.2.9", "192.0.2.6")  # .9 trong thống kê chính là máy VTNet đo ở .6
    a = get(client, "/alerts", zones="danger")
    i5, i6 = a["items"]
    assert i5["gpu_count"] == 1 and i5["inventory_gpu_spec"] == "3*A30" and i5["gpu_count_mismatch"] is True
    assert (i6["inventory_ip"], i6["owner"], i6["ip_linked"], i6["pair_confirmed"]) == (
        "192.0.2.9",
        "dungha7",
        True,
        False,
    )
    assert a["matrix"]["rows"]["danger"] == {"dungha7": 1, "kientt6": 1, "_unmapped": 0}  # cache tự mất hiệu lực
    with Session(engine) as s, s.begin():
        s.execute(delete(IpLink).where(IpLink.inventory_ip == "192.0.2.9"))
    assert get(client, "/alerts", zones="danger")["matrix"]["rows"]["danger"]["_unmapped"] == 1


# ------------------------------------------------------------------ Danh mục & chi tiết server


def test_catalog(loaded: TestClient, engine: Engine) -> None:
    c = get(loaded, "/servers")
    assert c["counts"] == {
        "inventory_rows": 6,
        "has_data": 5,
        "reclaimed": 0,
        "no_data": 1,
        "vtnet_only": 1,
        "linked": 0,
        "gpu_count_mismatch": 0,
    }
    by_ip = {i["ip"]: i for i in c["items"]}
    assert by_ip["192.0.2.9"]["data_status"] == "no_data" and by_ip["192.0.2.9"]["gpu_model"] == "L40S"
    assert c["items"][-1]["ip"] == "192.0.2.6" and c["items"][-1]["row_type"] == "vtnet_only"  # nhóm cuối bảng
    assert by_ip["192.0.2.2"]["inventory_gpu_spec"] == "2*A30" and by_ip["192.0.2.2"]["zone"] == "safe"
    link(engine, "192.0.2.9", "192.0.2.6")
    c = get(loaded, "/servers")
    assert (c["counts"]["has_data"], c["counts"]["vtnet_only"], c["counts"]["linked"]) == (6, 0, 1)
    row = next(i for i in c["items"] if i["inventory_ip"] == "192.0.2.9")
    assert (row["ip"], row["ip_linked"], row["zone"]) == ("192.0.2.6", True, "danger")


def test_catalog_reclaimed_status(client: TestClient, tmp_path: Path) -> None:
    inv = tmp_path / "inv.xlsx"
    make_synthetic.make_inventory(inv, [*make_synthetic.INVENTORY, ("192.0.2.50", "4*L40S", "kientt6", "Đã trả")])
    load(client, FIX / "synthetic_t10.xlsx", inv)
    c = get(client, "/servers")
    assert (c["counts"]["reclaimed"], c["counts"]["no_data"], c["counts"]["has_data"]) == (1, 1, 5)
    assert next(i for i in c["items"] if i["ip"] == "192.0.2.50")["data_status"] == "reclaimed"


def test_server_detail_and_timeseries(loaded: TestClient) -> None:
    d = get(loaded, "/servers/192.0.2.5")
    assert d["data_status"] == "has_data" and d["inventory"]["owner"] == "kientt6" and d["stats"]["zone"] == "danger"
    assert get(loaded, "/servers/192.0.2.9")["data_status"] == "no_data"
    six = get(loaded, "/servers/192.0.2.6")
    assert six["data_status"] == "vtnet_only" and six["inventory"] is None
    r50 = get(loaded, "/servers/192.0.2.50")
    assert r50["data_status"] == "reclaimed" and r50["reclaim"]["owner_dcim"] == "locnm2"
    assert loaded.get(f"{API}/servers/10.0.0.1").status_code == 404
    ts = get(loaded, "/servers/192.0.2.6/timeseries")["points"]
    assert [p["zone"] for p in ts] == ["danger"] * 4 + ["warning"]  # ngày 5: gpu 100 > 40, mem 30 <= 40
    assert get(loaded, "/servers/192.0.2.9/timeseries")["points"] == []


def test_hourly_data_aggregated_in_api(client: TestClient) -> None:
    load(client, FIX / "synthetic_t10_hourly.xlsx", FIX / "synthetic_inventory.xlsx")
    i1 = next(i for i in get(client, "/alerts")["items"] if i["ip"] == "192.0.2.1")
    assert (i1["gpu_avg"], i1["gpu_peak"], i1["days"], i1["pattern"]) == (80, 80, 5, "high_load")
    assert len(get(client, "/servers/192.0.2.1/timeseries")["points"]) == 5


# ------------------------------------------------------------------ meta & cache


def test_meta(loaded: TestClient) -> None:
    m = get(loaded, "/meta")
    assert m["data_range"] == {"start": "2026-10-01", "end": "2026-10-05"}
    assert m["default_range"] == {"start": "2026-10-01", "end": "2026-10-05"} and m["periods"][0]["label"] == "2026-W40"
    assert m["owners"] == ["dungha7", "kientt6"] and m["managed_by"] == ["Server độc lập"]
    assert (
        m["gpu_models"] == ["A30", "H200", "L4", "L40S"] and m["inventory"]["file_name"] == "synthetic_inventory.xlsx"
    )


def test_cache_hit_and_invalidated_by_new_batch(loaded: TestClient, tmp_path: Path) -> None:
    cache = loaded.app.state.analytics_cache  # type: ignore[attr-defined]
    get(loaded, "/alerts")
    hits = cache.hits
    get(loaded, "/fleet/summary")
    assert cache.hits == hits + 1  # cùng khoảng/ngưỡng/dữ liệu → dùng lại
    wb = openpyxl.load_workbook(FIX / "synthetic_t10.xlsx")
    for row in wb["server_raw"].iter_rows(min_row=2):
        if row[0].value == "192.0.2.2":
            row[1].value = 5  # .2: 5/60 → Cảnh báo
    p = tmp_path / "t10b.xlsx"
    wb.save(p)
    load(loaded, p)
    assert next(i for i in get(loaded, "/alerts")["items"] if i["ip"] == "192.0.2.2")["zone"] == "warning"


# ------------------------------------------------------------------ Xuất Excel


def _export(client: TestClient, **params: Any) -> openpyxl.Workbook:
    r = client.get(f"{API}/alerts/export.xlsx", params=params)
    assert r.status_code == 200, r.text
    assert "Danh_gia_tai_GPU_20261001-20261005_T40.xlsx" in r.headers["content-disposition"]
    return openpyxl.load_workbook(io.BytesIO(r.content))


def _zones(wb: openpyxl.Workbook) -> dict[str, Any]:
    ws = wb["Thống kê chi tiết"]
    return {ws.cell(r, 10).value: ws.cell(r, 18).value for r in range(2, ws.max_row + 1)}


def test_export_xlsx(loaded: TestClient, engine: Engine) -> None:
    from gpu_core.export import ASSESS_HEADER, SUMMARY_SHEET

    wb = _export(loaded)
    assert wb.sheetnames[0] == SUMMARY_SHEET and wb["Thống kê chi tiết"].cell(1, 17).value == ASSESS_HEADER
    z = _zones(wb)
    assert z["192.0.2.5"] == "Nguy hiểm" and z["192.0.2.9"] == "Chưa có dữ liệu VTNet"
    assert sum(v in ("Nguy hiểm", "Cảnh báo", "An toàn") for v in z.values()) == 5
    link(engine, "192.0.2.9", "192.0.2.6")  # liên kết .9 ↔ .6 → số map được 5 → 6
    z = _zones(_export(loaded))
    assert z["192.0.2.9"] == "Nguy hiểm" and sum(v in ("Nguy hiểm", "Cảnh báo", "An toàn") for v in z.values()) == 6


def test_export_needs_inventory(client: TestClient) -> None:
    load(client, FIX / "synthetic_t10.xlsx")
    r = client.get(f"{API}/alerts/export.xlsx")
    assert r.status_code == 409 and "thống kê" in r.json()["detail"]


def test_export_parity_with_skill_cli(loaded: TestClient, tmp_path: Path) -> None:
    """Parity (PLAN §11): file xuất từ API và CLI skill trên cùng dữ liệu → cùng vùng cho từng IP."""
    import runpy

    cli = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / ".claude/skills/gpu-util-vtnet/scripts/analyze_gpu_util.py")
    )
    out = tmp_path / "cli.xlsx"
    cli["run"](str(FIX / "synthetic_t10.xlsx"), str(FIX / "synthetic_inventory.xlsx"), str(out), threshold=40)
    assert _zones(openpyxl.load_workbook(out)) == _zones(_export(loaded))


def test_store_slice_equals_sql_range_and_reloads(loaded: TestClient, engine: Engine, tmp_path: Path) -> None:
    """Kho mẫu hiệu lực trong bộ nhớ: cắt theo khoảng = truy vấn util_effective theo khoảng; đọc lại khi dữ liệu đổi."""
    import pandas as pd

    from app.repo import util_repo
    from app.services.analytics_service import warm_up

    cache = loaded.app.state.analytics_cache  # type: ignore[attr-defined]
    warm_up(engine, cache)
    assert cache.store_loads == 1
    get(loaded, "/alerts", start="2026-10-02", end="2026-10-03")
    get(loaded, "/alerts", start="2026-10-01", end="2026-10-04", threshold=30)
    assert cache.store_loads == 1  # khoảng/ngưỡng khác nhưng dữ liệu không đổi → không đọc lại CSDL
    bundle = next(iter(cache._data.values()))
    with Session(engine) as s:
        sql = util_repo.effective_frame(s, bundle.ctx.start, bundle.ctx.end)
    cols = ["ip", "ts", "gpu", "mem", "gpu_type", "batch_id"]
    pd.testing.assert_frame_equal(
        bundle.raw[cols].sort_values(["ip", "ts"]).reset_index(drop=True),
        sql[cols].sort_values(["ip", "ts"]).reset_index(drop=True),
    )
    load(loaded, FIX / "synthetic_t10_hourly.xlsx")  # dữ liệu đổi → phiên bản mới
    get(loaded, "/alerts")
    assert cache.store_loads == 2


def test_data_version_changes_when_link_pair_edited(engine: Engine) -> None:
    """Sửa cặp liên kết (không đổi created_at/confirmed_at) vẫn phải đổi data_version → cache không trả số cũ."""
    from sqlalchemy import update as sa_update
    from sqlalchemy.orm import Session as S

    from app.db.models import IpLink
    from app.repo.batch_repo import data_version

    with S(engine) as s:
        v1 = data_version(s)
        s.execute(sa_update(IpLink).where(IpLink.inventory_ip == "10.207.188.1").values(vtnet_ip="10.205.36.99"))
        s.commit()
        v2 = data_version(s)
        s.execute(sa_update(IpLink).where(IpLink.inventory_ip == "10.207.188.2").values(pair_confirmed=True))
        s.commit()
        assert v1 != v2 != data_version(s)
