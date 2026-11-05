"""Áp ngưỡng T cho 1 chỉ số (PLAN §14.9, người dùng chốt 05/11/2026): cài đặt `zone_metric` + chọn khi xem (`zone_metric=`).
Luật: both = 3 vùng (giữ nguyên); gpu / mem = 2 vùng — chỉ số đó <= T → Nguy hiểm, còn lại → An toàn.

Kỳ vọng tính tay từ make_synthetic.SERIES, 01–05/10/2026, T = 40 (không sinh từ code đang test):
  .1 80/85 · .2 50/60 · .3 5/90 · .4 60/20 · .5 2/3 · .6 gpu [0,0,0,0,100] (TB 20) / mem 30
  both: Nguy hiểm .5 .6 · Cảnh báo .3 .4 · An toàn .1 .2
  gpu : Nguy hiểm .3 .5 .6 · An toàn .1 .2 .4          mem: Nguy hiểm .4 .5 .6 · An toàn .1 .2 .3
"""

from __future__ import annotations

import io
from typing import Any

import openpyxl
import pytest
from conftest import FIX
from fastapi.testclient import TestClient
from test_analytics_api import API, get, load

Q = {"start": "2026-10-01", "end": "2026-10-05"}
BOTH = {"danger": 2, "warning": 2, "safe": 2}
SINGLE = {"danger": 3, "warning": 0, "safe": 3}


@pytest.fixture
def loaded(client: TestClient) -> TestClient:
    load(client, FIX / "synthetic_t10.xlsx", FIX / "synthetic_inventory.xlsx")
    return client


def danger_ips(c: TestClient, **params: Any) -> list[str]:
    a = get(c, "/alerts", **Q, zones="danger", **params)
    return sorted(r["ip"] for r in a["items"])


def set_metric(c: TestClient, value: Any) -> Any:
    return c.patch(f"{API}/settings", json={"values": {"zone_metric": value}})


def test_query_override(loaded: TestClient) -> None:
    a = get(loaded, "/alerts", **Q)
    assert a["matrix"]["totals"] == BOTH and a["params"]["zone_metric"] == "both"
    g = get(loaded, "/alerts", **Q, zone_metric="gpu")
    assert g["matrix"]["totals"] == SINGLE and g["params"]["zone_metric"] == "gpu"
    assert danger_ips(loaded, zone_metric="gpu") == ["192.0.2.3", "192.0.2.5", "192.0.2.6"]
    assert danger_ips(loaded, zone_metric="mem") == ["192.0.2.4", "192.0.2.5", "192.0.2.6"]
    assert get(loaded, "/fleet/summary", **Q, zone_metric="mem")["zones"] == SINGLE
    assert loaded.get(f"{API}/alerts", params={**Q, "zone_metric": "cpu"}).status_code == 422
    # ngày nguy hiểm / chuỗi ngày theo chế độ: .6 ngày 05/10 = 100/30 → nguy hiểm chỉ khi xét memory
    st = {m: get(loaded, "/servers/192.0.2.6", **Q, zone_metric=m)["stats"] for m in ("both", "gpu", "mem")}
    assert [(s["danger_days"], s["low_streak"]) for s in st.values()] == [(4, 0), (4, 0), (5, 5)]
    assert st["gpu"]["zone"] == "danger" and st["gpu"]["pattern"] == "bursty_idle"  # mẫu hình giữ theo cả 2 chỉ số
    pts = {
        m: get(loaded, "/servers/192.0.2.6/timeseries", **Q, zone_metric=m)["points"] for m in ("both", "gpu", "mem")
    }
    assert [pts[m][-1]["zone"] for m in ("both", "gpu", "mem")] == ["warning", "safe", "danger"]
    three = get(loaded, "/servers/192.0.2.3", **Q, zone_metric="gpu")["stats"]
    assert "NGUY HIỂM (theo compute) – memory-bound" in three["assessment"]


def test_setting_is_default_and_validated(loaded: TestClient) -> None:
    items = {i["key"]: i for i in loaded.get(f"{API}/settings").json()["items"]}
    zm = items["zone_metric"]
    assert (zm["value"], zm["default"], zm["kind"]) == ("both", "both", "choice")
    assert [c["value"] for c in zm["choices"]] == ["both", "gpu", "mem"]
    assert items["default_threshold"]["kind"] == "number" and items["default_threshold"]["choices"] == []
    for bad in ("cpu", 1, None):
        r = set_metric(loaded, bad)
        assert r.status_code == 422 and "Áp ngưỡng T cho" in r.json()["detail"]
    r = set_metric(loaded, "gpu")
    assert r.status_code == 200
    item = next(i for i in r.json()["items"] if i["key"] == "zone_metric")
    assert (item["value"], item["updated_by"]) == ("gpu", "admin")
    # cài đặt đổi → data_version đổi → tính lại ngay; tham số khi xem vẫn ghi đè được
    assert get(loaded, "/alerts", **Q)["matrix"]["totals"] == SINGLE
    assert get(loaded, "/alerts", **Q, zone_metric="both")["matrix"]["totals"] == BOTH
    assert get(loaded, "/meta")["settings"]["zone_metric"] == "gpu"
    log = loaded.get(f"{API}/audit", params={"action": "settings_updated"}).json()["items"][0]
    assert log["payload"] == {"before": {"zone_metric": "both"}, "after": {"zone_metric": "gpu"}}


def test_import_preview_uses_setting(client: TestClient) -> None:
    assert set_metric(client, "mem").status_code == 200
    with (FIX / "synthetic_t10.xlsx").open("rb") as f:
        b = client.post(f"{API}/imports", files={"file": ("synthetic_t10.xlsx", f, "application/octet-stream")}).json()
    pv = b["summary"]["preview"]
    assert (pv["zone_metric"], pv["zones"]) == ("mem", SINGLE)


def test_compare_and_trend(loaded: TestClient) -> None:
    """A = 01–02/10, B = 05/10: chỉ .6 đổi (A 0/30 → B 100/30)."""
    q = {"a_start": "2026-10-01", "a_end": "2026-10-02", "b_start": "2026-10-05", "b_end": "2026-10-05"}
    cmp = {m: get(loaded, "/compare", **q, zone_metric=m) for m in ("both", "gpu", "mem")}
    assert [cmp[m]["counts"]["improved"] for m in cmp] == [1, 1, 0]  # both Nguy hiểm→Cảnh báo, gpu →An toàn, mem giữ
    assert cmp["gpu"]["matrix"]["danger"]["safe"] == 1 and cmp["gpu"]["zone_metric"] == "gpu"
    tr = get(loaded, "/trend/zones", zone_metric="mem")
    assert tr["zone_metric"] == "mem" and tr["months"][0]["zones"] == SINGLE
    assert get(loaded, "/trend/zones")["zone_metric"] == "both"


def test_export_xlsx_single_metric(loaded: TestClient) -> None:
    r = loaded.get(f"{API}/alerts/export.xlsx", params={**Q, "zone_metric": "gpu"})
    assert r.status_code == 200
    assert "Danh_gia_tai_GPU_20261001-20261005_T40_gpu.xlsx" in r.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb["Thống kê chi tiết"]
    z = {ws.cell(i, 10).value: ws.cell(i, 18).value for i in range(2, ws.max_row + 1)}
    assert (z["192.0.2.3"], z["192.0.2.4"], z["192.0.2.5"]) == ("Nguy hiểm", "An toàn", "Nguy hiểm")
    assert "chỉ xét compute" in wb.worksheets[0].cell(2, 1).value
