"""Đối soát (PLAN §14.12, người dùng chốt 06/11/2026):
1. Bổ sung server "VTNet có – thống kê thiếu": admin điền đủ cột như file (bắt buộc đầu mối) → server rời mục đó và được tính cho
   đầu mối như server chuẩn (ma trận vùng × đầu mối, phạm vi tài khoản đầu mối, xuất Excel); TB toàn bộ / tổng vùng không đổi.
2. "Sửa cặp" liên kết IP đổi được cả IP thống kê.

Kỳ vọng tính tay từ make_synthetic (01–05/10/2026, T = 40): .6 (8×H200, gpu [0,0,0,0,100] TB 20 / mem 30) là VTNet-only, vùng
Nguy hiểm; Nguy hiểm theo đầu mối trước khi bổ sung: kientt6 1 (.5) · chưa map 1 (.6). Thống kê: .1 .2 .9 dungha7, .3 .4 .5 kientt6.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from conftest import FIX, app_client, make_synthetic
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_analytics_api import API, get, load

from app.config import Settings
from app.db.models import AuditLog, IpLink

Q = {"start": "2026-10-01", "end": "2026-10-05"}
BOTH = {"danger": 2, "warning": 2, "safe": 2}
H200 = {
    "ip": "192.0.2.6",
    "owner": "KienTT6",
    "server_class": "GPU loại 2",
    "cpu": "2x Xeon 8480",
    "ram": "2 TB",
    "gpu_spec": "8*H200",
    "serial": "SN-H200-01",
    "model": "llama-70b",
    "input_load": "200 CCU",
    "service": "Train",
    "managed_by": "cụm k8s",
    "cluster": "5",
}


@pytest.fixture
def loaded(client: TestClient) -> TestClient:
    load(client, FIX / "synthetic_t10.xlsx", FIX / "synthetic_inventory.xlsx")
    return client


def add(c: TestClient, **over: Any) -> Any:
    return c.post(f"{API}/inventory/manual", json={**H200, **over})


def test_add_manual_counts_like_inventory(loaded: TestClient, engine: Engine) -> None:
    before = get(loaded, "/fleet/summary", **Q)
    assert [r["ip"] for r in get(loaded, "/gaps", **Q)["vtnet_only"]] == ["192.0.2.6"]
    assert get(loaded, "/alerts", **Q)["matrix"]["rows"]["danger"] == {"dungha7": 0, "kientt6": 1, "_unmapped": 1}

    r = add(loaded)
    assert r.status_code == 201, r.text
    st = r.json()
    assert st["manual"] is True and st["values"]["owner"] == "kientt6" and st["edited"] == {}

    gaps = get(loaded, "/gaps", **Q)
    assert gaps["vtnet_only"] == [] and gaps["counts"]["vtnet_only"] == 0 and gaps["counts"]["manual"] == 1
    cat = get(loaded, "/servers", **Q)
    row = next(x for x in cat["items"] if x["ip"] == "192.0.2.6")
    assert (row["row_type"], row["data_status"], row["manual"], row["owner"]) == (
        "inventory",
        "has_data",
        True,
        "kientt6",
    )
    assert (row["inventory_ip"], row["inventory_gpu_spec"], row["gpu_count"], row["service"]) == (
        "192.0.2.6", "8*H200", 8, "Train",
    )  # fmt: skip
    assert cat["counts"]["manual"] == 1 and cat["counts"]["vtnet_only"] == 0 and cat["counts"]["inventory_rows"] == 7

    a = get(loaded, "/alerts", **Q)
    assert a["matrix"]["totals"] == BOTH  # tổng vùng không đổi
    assert a["matrix"]["rows"]["danger"] == {"dungha7": 0, "kientt6": 2, "_unmapped": 0}
    after = get(loaded, "/fleet/summary", **Q)
    assert (after["gpu_avg"], after["mem_avg"], after["n_servers"]) == (
        before["gpu_avg"], before["mem_avg"], before["n_servers"],
    )  # fmt: skip
    assert (after["n_mapped"], after["n_unmapped"]) == (6, 0)
    detail = get(loaded, "/servers/192.0.2.6", **Q)
    assert detail["data_status"] == "has_data" and detail["inventory"]["cpu"] == "2x Xeon 8480"
    assert detail["inventory"]["manual"] is True

    with Session(engine) as s:
        log = s.scalars(select(AuditLog).where(AuditLog.action == "inventory_manual_added")).one()
        assert log.target == "192.0.2.6" and log.payload["values"]["service"] == "Train"


def test_owner_account_sees_manual_server(loaded: TestClient, settings: Settings) -> None:
    with app_client(settings, "kientt6", "owner", owner_key="kientt6") as k:
        assert k.get(f"{API}/servers/192.0.2.6", params=Q).status_code == 404
        assert add(loaded).status_code == 201
        assert k.get(f"{API}/servers/192.0.2.6", params=Q).status_code == 200
        assert sorted(x["ip"] for x in get(k, "/alerts", **Q, zones="danger")["items"]) == ["192.0.2.5", "192.0.2.6"]
        assert add(k).status_code == 403  # chỉ admin


@pytest.mark.parametrize(
    ("over", "code"),
    [
        ({"ip": "192.0.2.3"}, 409),  # đã có trong file thống kê
        ({"ip": "10.0.0.1"}, 404),  # VTNet chưa gửi số liệu
        ({"ip": "abc"}, 422),
        ({"owner": ""}, 422),
        ({"stt": "1"}, 422),  # cột không nhận
    ],
)
def test_add_validation(loaded: TestClient, over: dict[str, Any], code: int) -> None:
    assert add(loaded, **over).status_code == code


def test_linked_target_is_rejected(loaded: TestClient) -> None:
    assert (
        loaded.post(f"{API}/ip-links", json={"inventory_ip": "192.0.2.9", "vtnet_ip": "192.0.2.6"}).status_code == 201
    )
    assert add(loaded).status_code == 409


def test_edit_and_remove_manual(loaded: TestClient) -> None:
    assert add(loaded).status_code == 201
    st = loaded.patch(f"{API}/inventory/192.0.2.6", json={"service": "Fine-tune", "reclaim_status": "reclaimed"}).json()
    assert st["values"]["service"] == "Fine-tune" and st["edited"] == {} and st["reclaim_status"] == "reclaimed"
    assert loaded.patch(f"{API}/inventory/192.0.2.6", json={"owner": ""}).status_code == 422  # phải có đầu mối
    st = loaded.patch(f"{API}/inventory/192.0.2.6", json={"service": None, "reclaim_status": "in_use"}).json()
    assert st["manual"] is True and st["values"]["service"] is None  # dòng bổ sung không bị xóa khi các ô trống

    assert loaded.delete(f"{API}/inventory/manual/192.0.2.6").status_code == 204
    assert [r["ip"] for r in get(loaded, "/gaps", **Q)["vtnet_only"]] == ["192.0.2.6"]
    assert get(loaded, "/alerts", **Q)["matrix"]["rows"]["danger"]["_unmapped"] == 1
    assert loaded.delete(f"{API}/inventory/manual/192.0.2.6").status_code == 404
    assert loaded.delete(f"{API}/inventory/manual/192.0.2.3").status_code == 404  # dòng file, không phải bổ sung


def test_new_inventory_with_manual_ip(loaded: TestClient, tmp_path: Path) -> None:
    assert add(loaded).status_code == 201
    rows = [*make_synthetic.INVENTORY, ("192.0.2.6", "8xH200", "kientt6", "Train v2")]
    p = tmp_path / "Thong_ke_co_H200.xlsx"
    make_synthetic.make_inventory(p, rows)
    with p.open("rb") as f:
        b = loaded.post(f"{API}/imports", files={"file": (p.name, f, "application/octet-stream")}).json()
    assert b["summary"]["manual_in_file"] == ["192.0.2.6"]
    assert any("1 server đã bổ sung trên web nay có trong file này" in w for w in b["validation"]["warnings"])
    assert loaded.post(f"{API}/imports/{b['id']}/commit", json={"acknowledge": False}).status_code == 200
    row = next(x for x in get(loaded, "/servers", **Q)["items"] if x["ip"] == "192.0.2.6")
    # theo file (STT, GPU theo file); cột sửa tay trên web vẫn giữ và hiện là "sửa tay khác file"
    assert (row["manual"], row["stt"], row["inventory_gpu_spec"]) == (False, "7", "8xH200")
    assert row["service"] == "Train" and row["edited"]["service"] == "Train v2"


def test_export_includes_manual_row(loaded: TestClient, settings: Settings) -> None:
    assert add(loaded).status_code == 201
    r = loaded.get(f"{API}/alerts/export.xlsx", params={**Q, "threshold": 40})
    assert r.status_code == 200, r.text
    ws = openpyxl.load_workbook(io.BytesIO(r.content))["Thống kê chi tiết"]
    head = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
    ip_c, owner_c, cpu_c = (head.index(h) + 1 for h in ("IP", "Đầu mối sử dụng", "CPU"))
    zone_c = head.index("Vùng (VTNet)") + 1
    rows = {ws.cell(r, ip_c).value: r for r in range(2, ws.max_row + 1)}
    r6 = rows["192.0.2.6"]
    assert (ws.cell(r6, owner_c).value, ws.cell(r6, cpu_c).value, ws.cell(r6, zone_c).value) == (
        "kientt6", "2x Xeon 8480", "Nguy hiểm",
    )  # fmt: skip
    assert ws.cell(r6, ip_c).comment.text.startswith("Bổ sung trên web")
    with app_client(settings, "kientt6", "owner", owner_key="kientt6") as k:
        wk = openpyxl.load_workbook(io.BytesIO(k.get(f"{API}/alerts/export.xlsx", params=Q).content))[
            "Thống kê chi tiết"
        ]
        ips = {wk.cell(r, ip_c).value for r in range(2, wk.max_row + 1)}
        assert ips == {"192.0.2.3", "192.0.2.4", "192.0.2.5", "192.0.2.6"}


# ------------------------------------------------------------------ Sửa cặp: đổi IP thống kê


def test_link_change_inventory_ip(loaded: TestClient, engine: Engine) -> None:
    assert (
        loaded.post(f"{API}/ip-links", json={"inventory_ip": "192.0.2.9", "vtnet_ip": "192.0.2.6"}).status_code == 201
    )
    assert loaded.patch(f"{API}/ip-links/192.0.2.9", json={"pair_confirmed": True}).status_code == 200
    assert loaded.patch(f"{API}/ip-links/192.0.2.9", json={"inventory_ip": "192.0.2.77"}).status_code == 422  # không có
    r = loaded.patch(f"{API}/ip-links/192.0.2.9", json={"inventory_ip": "192.0.2.4"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["inventory_ip"], out["vtnet_ip"], out["pair_confirmed"], out["owner"]) == (
        "192.0.2.4", "192.0.2.6", False, "kientt6",
    )  # cặp mới phải xác nhận lại  # fmt: skip
    links = {
        x["inventory_ip"]: x["vtnet_ip"] for x in get(loaded, "/ip-links", **Q)["items"] if x["vtnet_ip"] == "192.0.2.6"
    }
    assert links == {"192.0.2.4": "192.0.2.6"}  # dòng cũ .9 đã bỏ (9 liên kết RTX6000 của seed không liên quan)
    # đổi đồng thời IP thống kê + IP VTNet; IP thống kê đã có liên kết khác → 409
    assert loaded.post(f"{API}/ip-links", json={"inventory_ip": "192.0.2.2", "vtnet_ip": "10.0.0.9"}).status_code == 201
    assert loaded.patch(f"{API}/ip-links/192.0.2.4", json={"inventory_ip": "192.0.2.2"}).status_code == 409
    r = loaded.patch(f"{API}/ip-links/192.0.2.4", json={"inventory_ip": "192.0.2.9", "vtnet_ip": "192.0.2.60"})
    assert r.status_code == 200 and (r.json()["inventory_ip"], r.json()["vtnet_ip"]) == ("192.0.2.9", "192.0.2.60")
    with Session(engine) as s:
        mine = {x.inventory_ip for x in s.scalars(select(IpLink)) if x.inventory_ip.startswith("192.0.2.")}
        assert mine == {"192.0.2.9", "192.0.2.2"}
        log = s.scalars(select(AuditLog).where(AuditLog.action == "link_updated").order_by(AuditLog.id.desc())).first()
        assert log is not None and log.payload["before"]["inventory_ip"] == "192.0.2.4"
