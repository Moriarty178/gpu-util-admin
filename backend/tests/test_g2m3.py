"""G2-M3 — đối soát + liên kết IP, so sánh kỳ, xu hướng vùng theo tháng, so sánh server, ghi chú/giải trình/miễn trừ.

Fixture tổng hợp, kết quả biết trước (T=40):
  thống kê riêng: .1–.4 như chuẩn, .5 ghi '3*A30' (VTNet 1×A30 → lệch số card), .7 '8*H200' kientt6 (chưa có số liệu),
  .9 L40S dungha7 (chưa có số liệu, không rõ số card) · VTNet-only: .6 (8×H200) → gợi ý ghép .7 ↔ .6.
  Kỳ A = file T10 tổng hợp (01–05/10); kỳ B (01–05/11): .2 An toàn→Nguy hiểm (xấu đi), .3 Cảnh báo→An toàn (cải thiện),
  .5 biến mất, .7 mới (30/30 → Nguy hiểm), .1 .4 .6 giữ nguyên.
Golden thật (CONTEXT §6–7): T7→T10 20 cải thiện / 5 xấu đi / 9 mới / 5 biến mất; đối soát T10 3 VTNet-only, 48 = 13 + 35,
8 lệch số card — cần file trong samples/, tự skip khi thiếu.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from conftest import FIX, add_user, app_client, login, make_synthetic
from fastapi.testclient import TestClient
from realdata import INV10, T7, T10, needs
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import AuditLog, ServerNote
from app.main import create_app
from app.services.auth_service import utcnow

OCT = {"start": "2026-10-01", "end": "2026-10-05"}
NOV_DAYS = [dt.datetime(2026, 11, d) for d in range(1, 6)]
INV_ROWS = [
    ("192.0.2.1", "4x NVIDIA L40S", "dungha7", "LLM inference"),
    ("192.0.2.2", "2*A30", "dungha7", "OCR"),
    ("192.0.2.3", "2*L4", "kientt6", "Embedding"),
    ("192.0.2.4", "3xNVIDIA A30", "kientt6", "TTS"),
    ("192.0.2.5", "3*A30", "kientt6", "Lab test"),  # VTNet 1×A30 → lệch
    ("192.0.2.7", "8*H200", "kientt6", "Train"),  # chưa có số liệu, cùng nhóm với VTNet-only .6
    ("192.0.2.9", "L40S", "dungha7", "Chưa gắn monitor"),
]
NOV = {
    "192.0.2.1": ("4×NVIDIA L40S", [80] * 5, [85] * 5),
    "192.0.2.2": ("2×NVIDIA A30", [10] * 5, [10] * 5),
    "192.0.2.3": ("2×NVIDIA L4", [50] * 5, [90] * 5),
    "192.0.2.4": ("3×NVIDIA A30", [60] * 5, [20] * 5),
    "192.0.2.6": ("8×NVIDIA H200", [0, 0, 0, 0, 100], [30] * 5),
    "192.0.2.7": ("1×NVIDIA L4", [30] * 5, [30] * 5),
}


def upload(c: TestClient, path: Path) -> None:
    with path.open("rb") as f:
        b = c.post("/api/v1/imports", files={"file": (path.name, f, "application/octet-stream")}).json()
    assert c.post(f"/api/v1/imports/{b['id']}/commit", json={"acknowledge": True}).status_code == 200, b


@pytest.fixture
def data(settings: Settings, engine: Engine, tmp_path: Path) -> Settings:
    inv = tmp_path / "inv.xlsx"
    make_synthetic.make_inventory(inv, INV_ROWS)
    nov = tmp_path / "t11.xlsx"
    make_synthetic.make_t10(nov, series=NOV, days=NOV_DAYS, reclaimed=False)
    with app_client(settings) as c:
        upload(c, FIX / "synthetic_t10.xlsx")
        upload(c, inv)
        upload(c, nov)
    add_user(settings.database_url, "kientt6", "owner", owner_key="kientt6")
    add_user(settings.database_url, "dung", "owner", owner_key="dungha7", data_scope="all")
    add_user(settings.database_url, "sep", "viewer")
    return settings


def client_as(settings: Settings, user: str) -> TestClient:
    c = TestClient(create_app(settings))
    c.__enter__()
    login(c, user)
    return c


def j(r: Any, code: int = 200) -> Any:
    assert r.status_code == code, r.text
    return r.json()


# ------------------------------------------------------------------ đối soát + liên kết IP


def test_gaps_and_suggestions(data: Settings) -> None:
    with app_client(data) as c:
        g = j(c.get("/api/v1/gaps", params=OCT))
        assert g["counts"] == {"vtnet_only": 1, "no_data": 2, "reclaimed": 0, "unknown": 2, "gpu_count_mismatch": 1,
                               "links": 9, "links_unconfirmed": 9, "manual": 0}  # fmt: skip
        assert [r["ip"] for r in g["vtnet_only"]] == ["192.0.2.6"]
        assert sorted(r["inventory_ip"] for r in g["unknown"]) == ["192.0.2.7", "192.0.2.9"]
        mm = g["gpu_count_mismatch"][0]
        assert (mm["inventory_ip"], mm["inventory_gpu_spec"], mm["gpu_type"]) == ("192.0.2.5", "3*A30", "1×NVIDIA A30")
        assert g["suggestions"] == [
            {"gpu_count": 8, "gpu_model": "H200", "vtnet_ips": ["192.0.2.6"], "inventory_ips": ["192.0.2.7"],
             "pairs": [{"inventory_ip": "192.0.2.7", "vtnet_ip": "192.0.2.6"}]}
        ]  # fmt: skip
        links = j(c.get("/api/v1/ip-links", params=OCT))["items"]
        assert len(links) == 9 and not any(x["in_inventory"] or x["vtnet_has_data"] for x in links)
        assert links[0]["created_by"] == "seed"
    k = client_as(data, "kientt6")
    try:  # đầu mối: chỉ phần của mình (không VTNet-only, không .9 của dungha7)
        g = j(k.get("/api/v1/gaps", params=OCT))
        assert g["counts"]["vtnet_only"] == 0 and [r["inventory_ip"] for r in g["unknown"]] == ["192.0.2.7"]
        assert (
            k.post("/api/v1/ip-links", json={"inventory_ip": "192.0.2.7", "vtnet_ip": "192.0.2.6"}).status_code == 403
        )
    finally:
        k.__exit__(None, None, None)


def test_link_lifecycle_changes_analysis_immediately(data: Settings, engine: Engine) -> None:
    with app_client(data) as c:
        q = {**OCT, "threshold": 40, "page_size": 100}
        before = j(c.get("/api/v1/alerts", params=q))["matrix"]
        assert before["rows"]["danger"]["_unmapped"] == 1 and before["rows"]["danger"]["kientt6"] == 1
        body = {"inventory_ip": "192.0.2.7", "vtnet_ip": "192.0.2.6", "reason": "Cùng 8×H200, đã kiểm serial"}
        link = j(c.post("/api/v1/ip-links", json=body, params=OCT), 201)
        assert link["pair_confirmed"] is False and link["vtnet_has_data"] and link["in_inventory"]
        assert link["owner"] == "kientt6" and link["zone"] == "danger" and link["created_by"] == "admin"
        after = j(c.get("/api/v1/alerts", params=q))["matrix"]  # cache theo data_version → tính lại ngay
        assert after["rows"]["danger"]["kientt6"] == 2 and after["rows"]["danger"].get("_unmapped", 0) == 0
        g = j(c.get("/api/v1/gaps", params=OCT))
        assert g["counts"]["vtnet_only"] == 0 and g["suggestions"] == []

        r = j(c.patch("/api/v1/ip-links/192.0.2.7", json={"pair_confirmed": True}, params=OCT))
        assert r["pair_confirmed"] and r["confirmed_by"] == "admin" and r["confirmed_at"]
        r = j(c.patch("/api/v1/ip-links/192.0.2.7", json={"vtnet_ip": "192.0.2.60"}, params=OCT))
        assert r["pair_confirmed"] is False and r["confirmed_by"] is None  # đổi cặp → xác nhận lại

        bad = [
            ({"inventory_ip": "192.0.2.9", "vtnet_ip": "192.0.2.1"}, 409, "cùng trỏ 1 máy"),  # .1 đã có dòng thống kê
            ({"inventory_ip": "192.0.2.9", "vtnet_ip": "192.0.2.60"}, 409, "đã được liên kết"),
            ({"inventory_ip": "192.0.2.7", "vtnet_ip": "192.0.2.61"}, 409, "đã có liên kết"),
            ({"inventory_ip": "192.0.2.9", "vtnet_ip": "192.0.2.9"}, 422, "trùng nhau"),
            ({"inventory_ip": "abc", "vtnet_ip": "192.0.2.61"}, 422, "IPv4"),
        ]
        for b, code, msg in bad:
            r = c.post("/api/v1/ip-links", json=b)
            assert r.status_code == code and msg in r.json()["detail"], (b, r.text)
        assert c.delete("/api/v1/ip-links/192.0.2.7").status_code == 204
        assert c.delete("/api/v1/ip-links/192.0.2.7").status_code == 404
        assert j(c.get("/api/v1/alerts", params=q))["matrix"] == before
    with Session(engine) as s:
        acts = [a.action for a in s.scalars(select(AuditLog).where(AuditLog.action.like("link_%")))]
    assert acts == ["link_created", "link_confirmed", "link_updated", "link_deleted"]


# ------------------------------------------------------------------ so sánh kỳ, xu hướng, so sánh server


def test_compare_default_two_latest_periods(data: Settings) -> None:
    with app_client(data) as c:
        r = j(c.get("/api/v1/compare", params={"threshold": 40}))
        assert (r["a"]["params"]["start"], r["a"]["params"]["end"]) == ("2026-10-01", "2026-10-05")
        assert (r["b"]["params"]["start"], r["b"]["params"]["end"]) == ("2026-11-01", "2026-11-05")
        assert r["counts"] == {"worsened": 1, "improved": 1, "same": 3, "new": 1, "gone": 1}
        mv = {i["ip"]: i["movement"] for i in r["items"]}
        assert mv == {"192.0.2.2": "worsened", "192.0.2.3": "improved", "192.0.2.1": "same", "192.0.2.4": "same",
                      "192.0.2.6": "same", "192.0.2.7": "new", "192.0.2.5": "gone"}  # fmt: skip
        assert r["items"][0]["ip"] == "192.0.2.2"  # xấu đi lên đầu
        two = next(i for i in r["items"] if i["ip"] == "192.0.2.2")
        assert (two["gpu_avg_prev"], two["gpu_avg_cur"], two["d_gpu"], two["owner"]) == (50, 10, -40, "dungha7")
        m = r["matrix"]
        assert m["safe"]["danger"] == 1 and m["warning"]["safe"] == 1 and m["danger"]["gone"] == 1
        assert m["new"]["danger"] == 1 and m["safe"]["safe"] == 1 and m["danger"]["danger"] == 1
        # KPI tự tính: TB các ngày của TB các server (PLAN §6)
        oct_days = [(80 + 50 + 5 + 60 + 2 + 0) / 6] * 4 + [(80 + 50 + 5 + 60 + 2 + 100) / 6]
        assert r["a"]["gpu_avg"] == pytest.approx(sum(oct_days) / 5)
        assert r["a"]["zones"] == {"danger": 2, "warning": 2, "safe": 2}
        assert r["b"]["zones"] == {"danger": 3, "warning": 1, "safe": 2}
        custom = j(c.get("/api/v1/compare", params={"a_start": "2026-10-01", "a_end": "2026-10-05",
                                                    "b_start": "2026-10-01", "b_end": "2026-10-05"}))  # fmt: skip
        assert custom["counts"]["same"] == 6 and custom["counts"]["worsened"] == 0
    k = client_as(data, "kientt6")
    try:
        r = j(k.get("/api/v1/compare", params={"threshold": 40}))
        assert {i["ip"]: i["movement"] for i in r["items"]} == {
            "192.0.2.3": "improved",
            "192.0.2.4": "same",
            "192.0.2.5": "gone",
            "192.0.2.7": "new",
        }  # fmt: skip  (.7 là của kientt6 trong file thống kê, có số liệu ở kỳ B)
    finally:
        k.__exit__(None, None, None)


def test_compare_needs_two_periods(client: TestClient) -> None:
    upload(client, FIX / "synthetic_t10.xlsx")
    r = client.get("/api/v1/compare")
    assert r.status_code == 422 and "2 khoảng ngày" in r.json()["detail"]


def test_trend_zones_by_month(data: Settings) -> None:
    with app_client(data) as c:
        r = j(c.get("/api/v1/trend/zones", params={"threshold": 40}))
        assert [m["month"] for m in r["months"]] == ["2026-10", "2026-11"]
        oct_, nov = r["months"]
        assert (oct_["start"], oct_["end"]) == ("2026-10-01", "2026-10-31")
        assert oct_["zones"] == {"danger": 2, "warning": 2, "safe": 2} and oct_["n_servers"] == 6
        assert nov["zones"] == {"danger": 3, "warning": 1, "safe": 2} and nov["end"] == "2026-11-05"
        assert oct_["cards"]["danger"] == 1 + 8  # .5 1×A30 + .6 8×H200
        r = j(c.get("/api/v1/trend/zones", params={"threshold": 40, "owner": "kientt6"}))
        assert r["months"][1]["zones"] == {
            "danger": 1,
            "warning": 1,
            "safe": 1,
        }  # .7 Nguy hiểm, .4 Cảnh báo, .3 An toàn
        r = j(c.get("/api/v1/trend/zones", params={"start": "2020-01-01", "end": "2026-12-31"}))
        assert [m["month"] for m in r["months"]] == ["2026-10", "2026-11"]  # khoảng vượt dữ liệu → cắt về 01/10–05/11


def test_trend_zones_limit(data: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import compare_service

    monkeypatch.setattr(compare_service, "MAX_TREND_MONTHS", 1)
    with app_client(data) as c:
        assert c.get("/api/v1/trend/zones").status_code == 422  # 2 tháng dữ liệu > giới hạn 1


def test_trend_zones_by_week(data: Settings) -> None:
    """Tuần ISO (thứ 2 → CN), cắt theo dữ liệu 01/10–05/11. Tính tay (T = 40):
    W40 01–04/10: .6 gpu 0 → Nguy hiểm → 2/2/2 · W41 chỉ 05/10: .6 gpu 100 / mem 30 → Cảnh báo → 1/3/2 ·
    W42, W43 không có dữ liệu · W44 26/10–01/11 = ngày 01/11 của T11: .2 10/10, .6 0/30, .7 30/30 Nguy hiểm → 3/1/2 ·
    W45 02–05/11: .6 gpu TB 25 → vẫn Nguy hiểm → 3/1/2."""
    with app_client(data) as c:
        r = j(c.get("/api/v1/trend/zones", params={"threshold": 40, "granularity": "week"}))
        assert r["granularity"] == "week"
        got = [(m["period"], m["start"], m["end"], m["n_days"], m["n_servers"]) for m in r["months"]]
        assert got == [
            ("2026-W40", "2026-10-01", "2026-10-04", 4, 6),
            ("2026-W41", "2026-10-05", "2026-10-11", 7, 6),
            ("2026-W42", "2026-10-12", "2026-10-18", 7, 0),
            ("2026-W43", "2026-10-19", "2026-10-25", 7, 0),
            ("2026-W44", "2026-10-26", "2026-11-01", 7, 6),
            ("2026-W45", "2026-11-02", "2026-11-05", 4, 6),
        ]
        z = [(m["zones"]["danger"], m["zones"]["warning"], m["zones"]["safe"]) for m in r["months"]]
        assert z == [(2, 2, 2), (1, 3, 2), (0, 0, 0), (0, 0, 0), (3, 1, 2), (3, 1, 2)]
        assert all(m["month"] is None for m in r["months"])
        assert c.get("/api/v1/trend/zones", params={"granularity": "quarter"}).status_code == 422


def test_multi_server_timeseries(data: Settings) -> None:
    with app_client(data) as c:
        r = j(c.get("/api/v1/servers/timeseries", params={**OCT, "ips": ["192.0.2.1", "192.0.2.6"]}))
        assert [s["ip"] for s in r["series"]] == ["192.0.2.1", "192.0.2.6"]
        assert [p["gpu"] for p in r["series"][1]["points"]] == [0, 0, 0, 0, 100]
        assert r["series"][0]["owner"] == "dungha7" and r["series"][1]["owner"] is None
        six = [f"192.0.2.{i}" for i in (1, 2, 3, 4, 5, 6)]
        assert c.get("/api/v1/servers/timeseries", params={**OCT, "ips": six}).status_code == 422
        assert c.get("/api/v1/servers/timeseries", params=OCT).status_code == 422
    k = client_as(data, "kientt6")
    try:
        ok = {**OCT, "ips": ["192.0.2.3"]}
        assert k.get("/api/v1/servers/timeseries", params=ok).status_code == 200
        assert k.get("/api/v1/servers/timeseries", params={**OCT, "ips": ["192.0.2.3", "192.0.2.1"]}).status_code == 404
    finally:
        k.__exit__(None, None, None)


# ------------------------------------------------------------------ ghi chú / giải trình / miễn trừ


def test_notes_permissions_and_exemption(data: Settings, engine: Engine) -> None:
    today = utcnow().date()
    q = {**OCT, "threshold": 40, "page_size": 100}
    with app_client(data) as c:
        url = "/api/v1/servers/192.0.2.5/notes"
        assert j(c.get(url, params=OCT))["can_add"] == ["explanation", "note", "action", "exempt"]
        r = c.post(url, json={"kind": "exempt", "text": "Chờ dự án mới"}, params=OCT)
        assert r.status_code == 422 and "ngày hết hạn" in r.json()["detail"]
        past = (today - dt.timedelta(days=1)).isoformat()
        assert c.post(url, json={"kind": "exempt", "text": "x", "valid_until": past}, params=OCT).status_code == 422
        until = (today + dt.timedelta(days=30)).isoformat()
        ex = j(c.post(url, json={"kind": "exempt", "text": "Chờ dự án mới", "valid_until": until}, params=OCT), 201)
        assert ex["kind_label"] == "Miễn trừ" and ex["active"] and ex["can_delete"]

        a = j(c.get("/api/v1/alerts", params=q))
        five = next(i for i in a["items"] if i["ip"] == "192.0.2.5")
        assert five["zone"] == "danger" and five["exempt_until"] == until and five["notes_count"] == 1  # vùng KHÔNG đổi
        assert a["summary"]["exempt"] == 1 and a["matrix"]["totals"]["danger"] == 2
        hidden = j(c.get("/api/v1/alerts", params={**q, "hide_exempt": True}))
        assert "192.0.2.5" not in {i["ip"] for i in hidden["items"]} and hidden["summary"]["exempt"] == 1

    k = client_as(data, "kientt6")
    try:
        url = "/api/v1/servers/192.0.2.5/notes"
        assert j(k.get(url, params=OCT))["can_add"] == ["explanation"]
        ex_note = j(k.get(url, params=OCT))["items"][0]
        assert ex_note["can_delete"] is False
        expl = j(k.post(url, json={"kind": "explanation", "text": "Đang tối ưu batch size"}, params=OCT), 201)
        r = k.post(url, json={"kind": "note", "text": "x"}, params=OCT)
        assert r.status_code == 403 and "giải trình" in r.json()["detail"]
        assert (
            k.post("/api/v1/servers/192.0.2.1/notes", json={"kind": "explanation", "text": "x"}, params=OCT).status_code
            == 404
        )  # fmt: skip  (ngoài phạm vi)
        assert k.delete(f"{url}/{ex_note['id']}", params=OCT).status_code == 403  # không xóa miễn trừ của admin
        assert k.delete(f"{url}/{expl['id']}", params=OCT).status_code == 204
        assert k.delete(f"{url}/{expl['id']}", params=OCT).status_code == 404
    finally:
        k.__exit__(None, None, None)
    d = client_as(data, "dung")  # đầu mối phạm vi 'all': xem được server người khác nhưng không giải trình hộ
    try:
        assert j(d.get("/api/v1/servers/192.0.2.5/notes", params=OCT))["can_add"] == []
        r = d.post("/api/v1/servers/192.0.2.5/notes", json={"kind": "explanation", "text": "x"}, params=OCT)
        assert r.status_code == 403
        assert j(d.post("/api/v1/servers/192.0.2.1/notes", json={"kind": "explanation", "text": "ok"},
                        params=OCT), 201)["created_by"] == "dung"  # fmt: skip
    finally:
        d.__exit__(None, None, None)
    v = client_as(data, "sep")
    try:
        r = v.post("/api/v1/servers/192.0.2.5/notes", json={"kind": "note", "text": "x"}, params=OCT)
        assert r.status_code == 403 and r.json()["type"] == "forbidden"
        assert len(j(v.get("/api/v1/servers/192.0.2.5/notes", params=OCT))["items"]) == 1
    finally:
        v.__exit__(None, None, None)

    with Session(engine) as s, s.begin():  # hết hạn miễn trừ → không còn nhãn (vùng vẫn như cũ)
        s.execute(
            update(ServerNote).where(ServerNote.kind == "exempt").values(valid_until=today - dt.timedelta(days=1))
        )
    with app_client(data) as c:
        five = next(i for i in j(c.get("/api/v1/alerts", params=q))["items"] if i["ip"] == "192.0.2.5")
        assert five["exempt_until"] is None and five["notes_count"] == 1
        note = j(c.get("/api/v1/servers/192.0.2.5/notes", params=OCT))["items"][0]
        assert note["active"] is False
        assert c.delete(f"/api/v1/servers/192.0.2.5/notes/{note['id']}", params=OCT).status_code == 204
        assert j(c.get("/api/v1/servers/192.0.2.5/notes", params=OCT))["items"] == []
    with Session(engine) as s:
        acts = [a.action for a in s.scalars(select(AuditLog).where(AuditLog.action.like("note_%")))]
    assert acts.count("note_created") == 3 and acts.count("note_deleted") == 2


# ------------------------------------------------------------------ golden thật


@needs(T7, T10)
def test_real_compare_t7_t10(client: TestClient) -> None:
    """CONTEXT §7: T7 → T10 (T=40) — 20 cải thiện, 5 xấu đi, 9 mới, 5 biến mất."""
    for f in (T7, T10):
        upload(client, f)
    r = j(client.get("/api/v1/compare", params={"threshold": 40}))
    c = r["counts"]
    assert (c["improved"], c["worsened"], c["new"], c["gone"]) == (20, 5, 9, 5)
    assert r["a"]["zones"]["danger"] == 19 and r["b"]["zones"]["danger"] == 11


@needs(T10, INV10)
def test_real_gaps_t10(client: TestClient) -> None:
    """CONTEXT §6: 3 VTNet-only, 48 thống kê không có số liệu = 13 đã thu hồi + 35 chưa rõ, 8 lệch số card, 9 liên kết."""
    for f in (T10, INV10):
        upload(client, f)
    g = j(client.get("/api/v1/gaps", params={"start": "2026-10-01", "end": "2026-11-01"}))["counts"]
    assert (g["vtnet_only"], g["no_data"], g["reclaimed"], g["unknown"]) == (3, 48, 13, 35)
    assert (g["gpu_count_mismatch"], g["links"]) == (8, 9)
