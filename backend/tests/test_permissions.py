"""G2-M2 — phạm vi dữ liệu theo đầu mối (Scope ở tầng service) + ma trận quyền mọi route × vai trò (PLAN §1.3, §10.2).

Fixture tổng hợp T=40 (kết quả biết trước, make_synthetic.py): .1 .2 An toàn (dungha7) · .3 .4 Cảnh báo, .5 Nguy hiểm (kientt6)
· .6 Nguy hiểm VTNet-only (không đầu mối) · .9 chỉ có trong thống kê (dungha7).
Golden thật (CONTEXT §7): T10 + thống kê T10 + 9 liên kết → kientt6 = 48 server (16/27/5); cần file trong samples/.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from typing import Any

import openpyxl
import pytest
from conftest import FIX, DbFactory, add_user, app_client, login, make_settings
from fastapi.testclient import TestClient
from realdata import INV10, T10, needs

from app import security as sec
from app.config import Settings
from app.main import create_app

PERIOD = {"start": "2026-10-01", "end": "2026-10-05"}
T40 = {**PERIOD, "threshold": 40, "page_size": 500}


def load(c: TestClient, *names: str) -> None:
    for n in names:
        with (FIX / n).open("rb") as f:
            b = c.post("/api/v1/imports", files={"file": (n, f, "application/octet-stream")}).json()
        assert c.post(f"/api/v1/imports/{b['id']}/commit", json={"acknowledge": True}).status_code == 200


@pytest.fixture
def loaded(settings: Settings, engine: Any) -> Settings:
    with app_client(settings) as c:
        load(c, "synthetic_t10.xlsx", "synthetic_inventory.xlsx")
    add_user(settings.database_url, "kientt6", "owner", owner_key="kientt6")
    add_user(settings.database_url, "dung", "owner", owner_key="DungHa7", data_scope="all")
    add_user(settings.database_url, "sep", "viewer")
    add_user(settings.database_url, "moi", "viewer", must_change=True)
    return settings


def as_user(settings: Settings, username: str) -> TestClient:
    c = TestClient(create_app(settings))
    c.__enter__()
    login(c, username)
    return c


def alerts(c: TestClient) -> dict[str, Any]:
    r = c.get("/api/v1/alerts", params=T40)
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def test_owner_own_sees_only_own_servers(loaded: Settings) -> None:
    c = as_user(loaded, "kientt6")
    try:
        a = alerts(c)
        assert a["matrix"]["totals"] == {"safe": 0, "warning": 2, "danger": 1}
        assert sorted(i["ip"] for i in a["items"]) == ["192.0.2.3", "192.0.2.4", "192.0.2.5"]
        assert a["matrix"]["owners"] == ["kientt6"]
        assert c.get("/api/v1/meta").json()["owners"] == ["kientt6"]  # bộ lọc đầu mối khóa
        assert c.get("/api/v1/fleet/summary", params=PERIOD).json()["n_servers"] == 3
        ts = c.get("/api/v1/fleet/timeseries", params=PERIOD).json()["points"]
        assert ts[0]["n_servers"] == 3 and ts[0]["gpu"] == pytest.approx((5 + 60 + 2) / 3)
        cat = c.get("/api/v1/servers", params=PERIOD).json()["items"]
        assert sorted(r["ip"] for r in cat) == ["192.0.2.3", "192.0.2.4", "192.0.2.5"]
        # lọc sang đầu mối khác không mở rộng được phạm vi
        assert alerts_with(c, owner="dungha7")["items"] == []
        # ngoài phạm vi → 404 (không lộ là server có tồn tại)
        for ip in ("192.0.2.1", "192.0.2.6", "192.0.2.9"):
            r = c.get(f"/api/v1/servers/{ip}", params=PERIOD)
            assert r.status_code == 404, ip
            assert c.get(f"/api/v1/servers/{ip}/timeseries", params=PERIOD).status_code == 404
        assert c.get("/api/v1/servers/192.0.2.3", params=PERIOD).status_code == 200
        # Excel chỉ đánh giá server của mình
        r = c.get("/api/v1/alerts/export.xlsx", params={**PERIOD, "threshold": 40})
        assert r.status_code == 200
        sheets, rows = export_rows(r.content)
        assert sheets == ["Đánh giá tải VTNet", "Thống kê chi tiết"]
        assert rows == {
            "192.0.2.3": "Cảnh báo",
            "192.0.2.4": "Cảnh báo",
            "192.0.2.5": "Nguy hiểm",
        }  # không lộ dòng khác
        assert "kientt6" in r.headers["content-disposition"]
        # không vào được chức năng quản trị
        assert c.get("/api/v1/imports").status_code == 403
        assert c.get("/api/v1/users").status_code == 403
    finally:
        c.__exit__(None, None, None)


def alerts_with(c: TestClient, **extra: Any) -> dict[str, Any]:
    r = c.get("/api/v1/alerts", params={**T40, **extra})
    assert r.status_code == 200
    body: dict[str, Any] = r.json()
    return body


def export_rows(xlsx: bytes) -> tuple[list[str], dict[str, Any]]:
    """(tên các sheet, {IP: vùng}) của sheet 'Thống kê chi tiết' trong file xuất (IP cột 10, vùng cột 18)."""
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    ws = wb["Thống kê chi tiết"]
    rows = {ws.cell(r, 10).value: ws.cell(r, 18).value for r in range(2, ws.max_row + 1)}
    return wb.sheetnames, rows


def test_owner_all_and_viewer_see_everything(loaded: Settings) -> None:
    with app_client(loaded) as admin:
        ref = alerts(admin)
        ref_meta = admin.get("/api/v1/meta").json()["owners"]
    for name in ("dung", "sep"):
        c = as_user(loaded, name)
        try:
            a = alerts(c)
            assert a["matrix"] == ref["matrix"] and a["items"] == ref["items"], name
            assert c.get("/api/v1/meta").json()["owners"] == ref_meta
            assert c.get("/api/v1/servers/192.0.2.1", params=PERIOD).status_code == 200
            assert c.get("/api/v1/imports").status_code == 403  # chỉ xem
        finally:
            c.__exit__(None, None, None)
    assert ref["matrix"]["totals"] == {"safe": 2, "warning": 2, "danger": 2}


# ------------------------------------------------------------------ ma trận quyền

PUBLIC = {("GET", "/api/v1/healthz"), ("POST", "/api/v1/auth/login"), ("POST", "/api/v1/auth/logout")}
SESSION = {("GET", "/api/v1/auth/me"), ("POST", "/api/v1/auth/change-password")}  # cho cả tài khoản phải đổi mật khẩu
ADMIN_PREFIXES = ("/api/v1/imports", "/api/v1/users", "/api/v1/settings", "/api/v1/audit", "/api/v1/inventory")
PERSONAS = ["anon", "must_change", "admin", "owner_own", "owner_all", "viewer"]


def required(method: str, path: str) -> str:
    if (method, path) in PUBLIC:
        return "public"
    if (method, path) in SESSION:
        return "session"
    if path.startswith(ADMIN_PREFIXES):
        return "admin"
    if path.startswith("/api/v1/ip-links") and method != "GET":
        return "admin"  # sửa liên kết IP (G2-M3)
    if path.startswith("/api/v1/servers/{ip}/notes") and method != "GET":
        return "writer"  # ghi chú: admin + đầu mối (đầu mối chỉ giải trình server của mình — kiểm ở service)
    return "user"


def allowed(level: str, persona: str) -> bool:
    if level == "public":
        return True
    if persona == "anon":
        return False
    if level == "session":
        return True
    if persona == "must_change":
        return False
    if level == "writer":
        return persona != "viewer"
    return level == "user" or persona == "admin"


def api_routes(settings: Settings) -> list[tuple[str, str]]:
    """Mọi endpoint API theo đặc tả OpenAPI (route mới thêm tự vào ma trận → buộc phải xếp mức quyền)."""
    paths = create_app(settings).openapi()["paths"]
    return sorted((m.upper(), p) for p, ops in paths.items() for m in ops)


@pytest.fixture
def personas(loaded: Settings) -> Iterator[dict[str, TestClient]]:
    add_user(loaded.database_url, "victim", "viewer")  # đích cho reset-password / PATCH (không làm mất phiên của ai)
    users = {"must_change": "moi", "admin": "admin", "owner_own": "kientt6", "owner_all": "dung", "viewer": "sep"}
    clients = {"anon": TestClient(create_app(loaded))}
    clients["anon"].__enter__()
    for p, u in users.items():
        clients[p] = as_user(loaded, u)
    yield clients
    for c in clients.values():
        c.__exit__(None, None, None)


def call(c: TestClient, method: str, path: str, victim_id: int) -> int:
    url = path.replace("{batch_id}", "1").replace("{ip}", "192.0.2.3").replace("{user_id}", str(victim_id))
    url = url.replace("{inventory_ip}", "10.207.188.9").replace("{note_id}", "999")
    if method == "GET":
        return c.get(url, params=PERIOD).status_code
    if method == "POST" and url.endswith("/auth/login"):
        return c.post(url, json={}).status_code  # 422: không đăng nhập lại ai
    if method == "POST" and url == "/api/v1/imports":
        return c.post(url, files={}).status_code
    return c.request(method, url, json={}).status_code


def test_permission_matrix(loaded: Settings, personas: dict[str, TestClient]) -> None:
    routes = api_routes(loaded)
    assert len(routes) >= 33  # 15 GĐ1 + auth 4 + users 3 + G2-M3: gaps, ip-links 4, compare, trend, timeseries, notes 3
    victim = next(u for u in personas["admin"].get("/api/v1/users").json()["items"] if u["username"] == "victim")
    failures = []
    for method, path in routes:
        if (method, path) == ("POST", "/api/v1/auth/logout"):
            continue  # kiểm riêng ở cuối (xóa cookie của client)
        level = required(method, path)
        for persona in PERSONAS:
            code = call(personas[persona], method, path, victim["id"])
            ok = code not in (401, 403)
            if ok != allowed(level, persona):
                failures.append(f"{method} {path} [{level}] as {persona} → {code}")
    assert failures == []
    for persona in PERSONAS:
        assert personas[persona].post("/api/v1/auth/logout").status_code == 204
        assert personas[persona].get("/api/v1/alerts").status_code == 401


def test_unauthenticated_codes(personas: dict[str, TestClient]) -> None:
    anon, mc = personas["anon"], personas["must_change"]
    assert anon.get("/api/v1/alerts").json()["type"] == "not_authenticated"
    assert (
        anon.post("/api/v1/imports/1/commit", json={"acknowledge": True}).status_code == 401
    )  # thiếu phiên trước, rồi mới tới CSRF
    assert mc.get("/api/v1/alerts").json()["type"] == "password_change_required"
    assert personas["viewer"].get("/api/v1/users").json()["type"] == "forbidden"
    del personas["viewer"].headers[sec.CSRF_HEADER]
    assert personas["viewer"].post("/api/v1/auth/change-password", json={}).json()["type"] == "csrf_failed"


# ------------------------------------------------------------------ golden thật


@needs(T10, INV10)
def test_real_owner_scope_kientt6(new_database: DbFactory, tmp_path_factory: pytest.TempPathFactory) -> None:
    """CONTEXT §7: T10 + thống kê T10 + 9 liên kết, T=40 — kientt6 = 48 server (16/27/5); dungha7 → 404."""
    tmp = tmp_path_factory.mktemp("scope")
    st = make_settings(new_database(tmp), tmp)
    with app_client(st) as admin:
        for f in (T10, INV10):
            with f.open("rb") as fh:
                b = admin.post("/api/v1/imports", files={"file": (f.name, fh, "application/octet-stream")}).json()
            assert admin.post(f"/api/v1/imports/{b['id']}/commit", json={"acknowledge": True}).status_code == 200
        full = admin.get("/api/v1/alerts", params={"start": "2026-10-01", "end": "2026-11-01", "threshold": 40}).json()
        dung_ip = next(i["ip"] for i in full["items"] if i["owner"] == "dungha7") if full["items"] else None
    add_user(st.database_url, "kientt6", "owner", owner_key="kientt6")
    add_user(st.database_url, "kall", "owner", owner_key="kientt6", data_scope="all")
    q = {"start": "2026-10-01", "end": "2026-11-01", "threshold": 40, "page_size": 500}
    c = as_user(st, "kientt6")
    try:
        a = c.get("/api/v1/alerts", params=q).json()
        assert a["matrix"]["totals"] == {"safe": 16, "warning": 27, "danger": 5}
        assert len(a["items"]) == 48
        if dung_ip:
            assert c.get(f"/api/v1/servers/{dung_ip}", params=q).status_code == 404
    finally:
        c.__exit__(None, None, None)
    c = as_user(st, "kall")
    try:
        assert c.get("/api/v1/alerts", params=q).json()["matrix"] == full["matrix"]  # scope all → như admin
    finally:
        c.__exit__(None, None, None)
