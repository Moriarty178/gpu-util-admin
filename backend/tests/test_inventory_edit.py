"""Sửa tay danh mục server (PLAN §14.11, người dùng chốt 05/11/2026): admin sửa Đầu mối / Model / Đầu vào hệ thống / Dịch vụ /
Quản lý bằng / Cụm + "Trạng thái thu hồi" (Đang sử dụng mặc định / VTNet đã thu hồi). Sửa tay giữ cả khi nhập file mới.

Kỳ vọng tính tay từ make_synthetic (01–05/10/2026, T = 40): thống kê .1 .2 .9 dungha7 · .3 .4 .5 kientt6; .3 dịch vụ
'Embedding', model 'model-x'; .6 VTNet-only. Vùng (cả 2 chỉ số): Nguy hiểm .5 .6 · Cảnh báo .3 .4 · An toàn .1 .2.
Sửa tay KHÔNG đổi phép tính: tổng vùng giữ 2/2/2; chỉ đổi thông tin + phạm vi theo đầu mối.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from conftest import FIX, app_client, make_synthetic
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session
from test_analytics_api import API, get, load

from app.config import Settings
from app.db.models import AuditLog, InventoryOverride

Q = {"start": "2026-10-01", "end": "2026-10-05"}
BOTH = {"danger": 2, "warning": 2, "safe": 2}


@pytest.fixture
def loaded(client: TestClient) -> TestClient:
    load(client, FIX / "synthetic_t10.xlsx", FIX / "synthetic_inventory.xlsx")
    return client


def patch(c: TestClient, ip: str, **body: Any) -> Any:
    return c.patch(f"{API}/inventory/{ip}", json=body)


def catalog_row(c: TestClient, ip: str) -> dict[str, Any]:
    items = get(c, "/servers", **Q)["items"]
    return next(r for r in items if r["inventory_ip"] == ip)


def test_edit_fields_and_reclaim_status(loaded: TestClient, engine: Engine) -> None:
    before = get(loaded, "/servers", **Q)  # làm ấm cache → kiểm data_version đổi sau khi sửa
    assert {r["reclaim_status"] for r in before["items"] if r["row_type"] == "inventory"} == {"in_use"}  # mặc định
    assert before["counts"]["reclaim_marked"] == 0 and before["counts"]["edited"] == 0

    r = patch(loaded, "192.0.2.3", service="  Rerank ", owner="DungHa7", reclaim_status="reclaimed")
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["values"]["service"] == "Rerank" and st["values"]["owner"] == "dungha7"  # chuẩn hóa như file thống kê
    assert st["file_values"]["service"] == "Embedding" and st["file_values"]["owner"] == "kientt6"
    assert st["edited"] == {"service": "Embedding", "owner": "kientt6"}
    assert st["reclaim_status"] == "reclaimed" and st["updated_by"] == "admin"

    row = catalog_row(loaded, "192.0.2.3")
    assert (row["service"], row["owner"], row["model"], row["reclaim_status"]) == (
        "Rerank",
        "dungha7",
        "model-x",
        "reclaimed",
    )
    assert row["edited"] == {"service": "Embedding", "owner": "kientt6"}
    after = get(loaded, "/servers", **Q)
    assert after["counts"]["reclaim_marked"] == 1 and after["counts"]["edited"] == 1
    vt_only = next(r for r in after["items"] if r["ip"] == "192.0.2.6")
    assert vt_only["reclaim_status"] is None and vt_only["edited"] is None

    # phép tính giữ nguyên; .3 (Cảnh báo) chuyển sang đầu mối dungha7 theo sửa tay
    a = get(loaded, "/alerts", **Q)
    assert a["matrix"]["totals"] == BOTH
    mine = get(loaded, "/alerts", **Q, owner="dungha7")
    assert sorted(x["ip"] for x in mine["items"]) == ["192.0.2.1", "192.0.2.2", "192.0.2.3"]
    assert get(loaded, "/servers/192.0.2.3", **Q)["inventory"]["service"] == "Rerank"
    assert get(loaded, "/meta")["owners"] == ["dungha7", "kientt6"]  # kientt6 còn .4 .5

    with Session(engine) as s:
        log = s.scalars(select(AuditLog).where(AuditLog.action == "inventory_edited")).one()
        assert log.target == "192.0.2.3" and log.payload["changes"]["service"] == {"before": None, "after": "Rerank"}


def test_owner_scope_follows_edit(loaded: TestClient, settings: Settings) -> None:
    with app_client(settings, "kientt6", "owner", owner_key="kientt6") as k:
        assert k.get(f"{API}/servers/192.0.2.3", params=Q).status_code == 200
        assert patch(loaded, "192.0.2.3", owner="dungha7").status_code == 200
        assert k.get(f"{API}/servers/192.0.2.3", params=Q).status_code == 404  # ngoài phạm vi ngay lập tức
        assert sorted(x["ip"] for x in get(k, "/alerts", **Q)["items"]) == ["192.0.2.4", "192.0.2.5"]
        assert patch(k, "192.0.2.4", service="x").status_code == 403  # chỉ admin sửa


def test_same_as_file_and_reset(loaded: TestClient, engine: Engine) -> None:
    def n_rows() -> int:
        with Session(engine) as s:
            return int(s.scalar(select(func.count()).select_from(InventoryOverride)) or 0)

    st = patch(loaded, "192.0.2.3", service="Embedding").json()  # trùng file → không lưu
    assert st["edited"] == {} and n_rows() == 0
    st = patch(loaded, "192.0.2.3", model="", reclaim_status="reclaimed").json()  # '' = để trống
    assert st["values"]["model"] is None and st["edited"] == {"model": "model-x"} and n_rows() == 1
    assert catalog_row(loaded, "192.0.2.3")["model"] is None
    st = patch(loaded, "192.0.2.3", model=None, reclaim_status="in_use").json()  # về theo file
    assert st["values"]["model"] == "model-x" and st["reclaim_status"] == "in_use" and n_rows() == 0
    assert catalog_row(loaded, "192.0.2.3")["edited"] == {}


@pytest.mark.parametrize(
    ("ip", "body", "code"),
    [
        ("192.0.2.6", {"service": "x"}, 404),  # VTNet-only: không có dòng thống kê
        ("10.0.0.1", {"service": "x"}, 404),
        ("192.0.2.3", {"stt": "9"}, 422),  # cột không sửa được
        ("192.0.2.3", {"reclaim_status": "free"}, 422),
        ("192.0.2.3", {"owner": "a" * 65}, 422),
    ],
)
def test_validation(loaded: TestClient, ip: str, body: dict[str, Any], code: int) -> None:
    assert loaded.patch(f"{API}/inventory/{ip}", json=body).status_code == code


def test_new_inventory_keeps_edits_and_warns(loaded: TestClient, tmp_path: Path) -> None:
    assert patch(loaded, "192.0.2.3", service="Rerank").status_code == 200
    rows = [
        (ip, spec, owner, "Embedding v2" if ip == "192.0.2.3" else svc)
        for ip, spec, owner, svc in make_synthetic.INVENTORY
    ]
    p = tmp_path / "Thong_ke_moi.xlsx"
    make_synthetic.make_inventory(p, rows)
    with p.open("rb") as f:
        b = loaded.post(f"{API}/imports", files={"file": (p.name, f, "application/octet-stream")}).json()
    assert b["summary"]["edit_conflicts"] == [
        {"ip": "192.0.2.3", "field": "service", "file": "Embedding v2", "kept": "Rerank"}
    ]
    assert any("1 ô đã sửa tay" in w for w in b["validation"]["warnings"])
    assert loaded.post(f"{API}/imports/{b['id']}/commit", json={"acknowledge": False}).status_code == 200  # không chặn
    row = catalog_row(loaded, "192.0.2.3")
    assert row["service"] == "Rerank" and row["edited"] == {"service": "Embedding v2"}


def test_export_writes_edits_and_reclaim_column(loaded: TestClient, settings: Settings) -> None:
    assert patch(loaded, "192.0.2.3", owner="dungha7", model="model-y", reclaim_status="reclaimed").status_code == 200
    r = loaded.get(f"{API}/alerts/export.xlsx", params={**Q, "threshold": 40})
    assert r.status_code == 200, r.text
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb["Thống kê chi tiết"]
    head = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
    assert head[-1] == "Trạng thái thu hồi"
    ip_c, owner_c, model_c, svc_c = (
        head.index(h) + 1 for h in ("IP", "Đầu mối sử dụng", "Model", "Dịch vụ/nghiệp vụ đang chạy")
    )
    rows = {ws.cell(r, ip_c).value: r for r in range(2, ws.max_row + 1)}
    r3 = rows["192.0.2.3"]
    assert (ws.cell(r3, owner_c).value, ws.cell(r3, model_c).value) == ("dungha7", "model-y")
    assert ws.cell(r3, model_c).comment.text.startswith("Sửa tay trên web — theo file: model-x")
    assert ws.cell(r3, svc_c).value == "Embedding" and ws.cell(r3, svc_c).comment is None  # ô không sửa giữ nguyên
    assert ws.cell(r3, ws.max_column).value == "VTNet đã thu hồi"
    assert ws.cell(rows["192.0.2.4"], ws.max_column).value == "Đang sử dụng"
    assert ws.cell(rows["192.0.2.4"], model_c).comment is None
    # đầu mối dungha7 (phạm vi own) thấy .3 trong file xuất theo đầu mối đã sửa; kientt6 không còn thấy
    with app_client(settings, "dungha7", "owner", owner_key="dungha7") as d:
        ws_d = openpyxl.load_workbook(io.BytesIO(d.get(f"{API}/alerts/export.xlsx", params=Q).content))[
            "Thống kê chi tiết"
        ]
        ips = {ws_d.cell(r, ip_c).value for r in range(2, ws_d.max_row + 1)}
        assert ips == {"192.0.2.1", "192.0.2.2", "192.0.2.3", "192.0.2.9"}
