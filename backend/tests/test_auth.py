"""G2-M2 — đăng nhập, phiên, CSRF, khóa tài khoản, buộc đổi mật khẩu, quản lý tài khoản, nhật ký (PLAN §1.3, §9)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from conftest import ADMIN_USER, TEST_PASSWORD, add_user, login
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app import security as sec
from app.config import Settings
from app.db.models import AppUser, AuditLog
from app.main import create_app
from app.services.auth_service import utcnow
from app.tools import users as users_cli

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def actions(engine: Engine) -> list[tuple[str | None, str]]:
    with Session(engine) as s:
        return [(a.username, a.action) for a in s.scalars(select(AuditLog).order_by(AuditLog.id))]


def new_client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def test_setup_required_then_login_logout(anon: TestClient, settings: Settings, engine: Engine) -> None:
    r = anon.get(ME)
    assert r.status_code == 401 and r.json()["type"] == "setup_required" and "create-admin" in r.json()["detail"]
    add_user(settings.database_url)
    assert anon.get(ME).json()["type"] == "not_authenticated"
    assert anon.get("/api/v1/alerts").status_code == 401

    r = anon.post(LOGIN, json={"username": " ADMIN ", "password": TEST_PASSWORD})  # tên không phân biệt hoa/thường
    assert r.status_code == 200 and r.json()["role"] == "admin" and r.json()["role_label"] == "Quản trị"
    raw = r.headers.get_list("set-cookie")
    session = next(c for c in raw if c.startswith(sec.SESSION_COOKIE + "="))
    csrf = next(c for c in raw if c.startswith(sec.CSRF_COOKIE + "="))
    assert "HttpOnly" in session and "SameSite=strict" in session and "Max-Age=43200" in session
    assert "HttpOnly" not in csrf and "SameSite=strict" in csrf
    assert anon.get(ME).json()["username"] == "admin"
    assert anon.get("/api/v1/alerts").status_code == 200

    anon.headers[sec.CSRF_HEADER] = anon.cookies[sec.CSRF_COOKIE]
    assert anon.post("/api/v1/auth/logout").status_code == 204
    assert anon.get(ME).status_code == 401
    assert [a for _, a in actions(engine)] == ["user_created", "login", "logout"]


def test_bad_login_is_generic_and_locks_after_5(anon: TestClient, settings: Settings, engine: Engine) -> None:
    add_user(settings.database_url)
    r_unknown = anon.post(LOGIN, json={"username": "khong-co", "password": "x" * 12})
    r_bad = anon.post(LOGIN, json={"username": ADMIN_USER, "password": "sai-mat-khau-1"})
    assert r_unknown.status_code == r_bad.status_code == 401
    assert r_unknown.json()["detail"] == r_bad.json()["detail"] == "Sai tên đăng nhập hoặc mật khẩu."
    assert r_bad.json()["type"] == "login_failed"  # khác 'not_authenticated' → giao diện không coi là hết phiên
    for _ in range(3):
        assert anon.post(LOGIN, json={"username": ADMIN_USER, "password": "sai"}).status_code == 401
    r = anon.post(LOGIN, json={"username": ADMIN_USER, "password": "sai"})  # lần sai thứ 5
    assert r.status_code == 423 and r.json()["type"] == "account_locked" and "15 phút" in r.json()["detail"]
    r = anon.post(LOGIN, json={"username": ADMIN_USER, "password": TEST_PASSWORD})  # đúng mật khẩu vẫn bị khóa
    assert r.status_code == 423 and "thử lại sau" in r.json()["detail"]
    with Session(engine) as s, s.begin():  # 15 phút sau
        s.execute(update(AppUser).values(locked_until=utcnow() - timedelta(seconds=1)))
    assert anon.post(LOGIN, json={"username": ADMIN_USER, "password": TEST_PASSWORD}).status_code == 200
    with Session(engine) as s:
        u = s.scalar(select(AppUser))
        assert u is not None and u.failed_attempts == 0 and u.locked_until is None and u.last_login_at is not None
    acts = [a for _, a in actions(engine)]
    assert acts.count("login_failed") == 6 and "login_locked" in acts and acts[-1] == "login"


def test_csrf_required_for_writes(client: TestClient) -> None:
    del client.headers[sec.CSRF_HEADER]
    r = client.post("/api/v1/imports/999/commit", json={"acknowledge": True})
    assert r.status_code == 403 and r.json()["type"] == "csrf_failed"
    client.headers[sec.CSRF_HEADER] = "sai"
    assert client.post("/api/v1/imports/999/commit", json={"acknowledge": True}).status_code == 403
    assert client.get("/api/v1/imports").status_code == 200  # GET không cần CSRF
    client.headers[sec.CSRF_HEADER] = client.cookies[sec.CSRF_COOKIE]
    assert client.post("/api/v1/imports/999/commit", json={"acknowledge": True}).status_code == 404


def test_tampered_or_expired_session(client: TestClient, settings: Settings) -> None:
    token = client.cookies[sec.SESSION_COOKIE]
    client.cookies.set(sec.SESSION_COOKIE, token[:-2] + ("aa" if not token.endswith("aa") else "bb"))
    assert client.get(ME).status_code == 401
    forged, _ = sec.new_session(1, 0, "khoa-khac-cua-ke-gian-0123456789abcdef", 1)
    client.cookies.set(sec.SESSION_COOKIE, forged)
    assert client.get(ME).status_code == 401
    expired, _ = sec.new_session(1, 0, settings.resolved_secret(), -1)
    client.cookies.set(sec.SESSION_COOKIE, expired)
    assert client.get(ME).status_code == 401


def test_must_change_password_flow(client: TestClient, settings: Settings) -> None:
    r = client.post("/api/v1/users", json={"username": "kientt6", "role": "owner", "owner_key": "KienTT6"})
    assert r.status_code == 201, r.text
    body = r.json()
    temp = body["temp_password"]
    assert len(temp) == 14 and body["user"]["owner_key"] == "kientt6" and body["user"]["data_scope"] == "own"
    assert body["user"]["must_change_password"] is True
    assert "temp_password" not in client.get("/api/v1/users").text

    with new_client(settings) as c:
        login(c, "kientt6", temp)
        assert c.get(ME).json()["must_change_password"] is True
        r = c.get("/api/v1/alerts")
        assert r.status_code == 403 and r.json()["type"] == "password_change_required"
        cp = "/api/v1/auth/change-password"
        cases = {
            "ngan": "ít nhất 10 ký tự",
            "kientt6-moi-2026": "không được chứa tên đăng nhập",
            "aaaaaaaaaaaa": "quá đơn giản",
            temp: "phải khác",
        }
        for pw, msg in cases.items():
            r = c.post(cp, json={"current_password": temp, "new_password": pw})
            assert r.status_code == 422 and msg in r.json()["detail"], pw
        assert c.post(cp, json={"current_password": "sai", "new_password": "Mat-khau-moi-99"}).status_code == 422
        with new_client(settings) as other:  # phiên thứ 2 của cùng tài khoản (máy khác)
            login(other, "kientt6", temp)
            r = c.post(cp, json={"current_password": temp, "new_password": "Mat-khau-moi-99"})
            assert r.status_code == 200 and r.json()["must_change_password"] is False
            assert other.get(ME).status_code == 401  # phiên khác hết hiệu lực
        c.headers[sec.CSRF_HEADER] = c.cookies[sec.CSRF_COOKIE]  # phiên hiện tại được cấp lại
        assert c.get("/api/v1/alerts").status_code == 200
        assert c.get(ME).json()["must_change_password"] is False


def test_admin_reset_lock_and_guards(client: TestClient, settings: Settings, engine: Engine) -> None:
    add_user(settings.database_url, "viewer1", "viewer")
    with Session(engine) as s:
        vid = s.scalar(select(AppUser.id).where(AppUser.username == "viewer1"))
        aid = s.scalar(select(AppUser.id).where(AppUser.username == "admin"))
    with new_client(settings) as v:
        login(v, "viewer1")
        assert v.get("/api/v1/alerts").status_code == 200
        r = client.post(f"/api/v1/users/{vid}/reset-password")
        assert r.status_code == 200 and r.json()["user"]["must_change_password"] is True
        assert v.get(ME).status_code == 401  # đặt lại mật khẩu → đăng xuất mọi phiên
        login(v, "viewer1", r.json()["temp_password"])
        assert client.patch(f"/api/v1/users/{vid}", json={"active": False}).json()["active"] is False
        assert v.get(ME).status_code == 401  # khóa → mất phiên ngay
        assert v.post(LOGIN, json={"username": "viewer1", "password": TEST_PASSWORD}).status_code == 401

    r = client.patch(f"/api/v1/users/{aid}", json={"role": "viewer"})
    assert r.status_code == 409 and "tự hạ quyền" in r.json()["detail"]
    assert client.patch(f"/api/v1/users/{aid}", json={"active": False}).status_code == 409
    r = client.patch(f"/api/v1/users/{vid}", json={"role": "owner"})
    assert r.status_code == 422 and "mã đầu mối" in r.json()["detail"]
    r = client.patch(f"/api/v1/users/{vid}", json={"role": "owner", "owner_key": "dungha7", "data_scope": "all"})
    assert r.json()["role"] == "owner" and r.json()["data_scope"] == "all" and r.json()["owner_key"] == "dungha7"
    r = client.patch(f"/api/v1/users/{vid}", json={"role": "viewer"})
    assert r.json()["owner_key"] is None and r.json()["data_scope"] == "all"  # owner_key chỉ có nghĩa với đầu mối

    assert client.post("/api/v1/users", json={"username": "viewer1", "role": "viewer"}).status_code == 409
    for bad in ("ab", "Có dấu", "a b c"):
        assert client.post("/api/v1/users", json={"username": bad, "role": "viewer"}).status_code == 422
    assert client.patch("/api/v1/users/9999", json={}).status_code == 404

    # gỡ khóa do nhập sai
    with Session(engine) as s, s.begin():
        s.execute(update(AppUser).where(AppUser.id == vid).values(locked_until=utcnow() + timedelta(minutes=10)))
    users = {u["username"]: u for u in client.get("/api/v1/users").json()["items"]}
    assert users["viewer1"]["locked"] is True
    assert client.patch(f"/api/v1/users/{vid}", json={"unlock": True}).json()["locked"] is False
    acts = [a for _, a in actions(engine)]
    assert {"user_password_reset", "user_updated"} <= set(acts)


def test_last_admin_guard(client: TestClient, settings: Settings, engine: Engine) -> None:
    add_user(settings.database_url, "admin2", "admin")
    with Session(engine) as s:
        a2 = s.scalar(select(AppUser.id).where(AppUser.username == "admin2"))
    with new_client(settings) as c2:
        login(c2, "admin2")
        assert c2.patch("/api/v1/users/1", json={"role": "viewer"}).status_code == 200  # còn admin2
        assert client.get(ME).json()["role"] == "viewer"  # vai trò đổi có hiệu lực ngay
        assert client.get("/api/v1/users").status_code == 403
        assert c2.patch(f"/api/v1/users/{a2}", json={"role": "viewer"}).status_code == 409


def test_import_actions_are_audited(client: TestClient, engine: Engine) -> None:
    from conftest import FIX

    with (FIX / "synthetic_t10.xlsx").open("rb") as f:
        b = client.post("/api/v1/imports", files={"file": ("t10.xlsx", f, "application/octet-stream")}).json()
    client.post(f"/api/v1/imports/{b['id']}/commit", json={"acknowledge": True})
    client.post(f"/api/v1/imports/{b['id']}/rollback")
    with Session(engine) as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action.like("import_%")).order_by(AuditLog.id)))
    got: list[tuple[Any, ...]] = [(r.username, r.action, r.target, r.payload["status"]) for r in rows]
    assert got == [
        ("admin", "import_uploaded", f"lô #{b['id']}", "staged"),
        ("admin", "import_committed", f"lô #{b['id']}", "committed"),
        ("admin", "import_rolled_back", f"lô #{b['id']}", "rolled_back"),
    ]


def test_cli_create_admin_and_reset(
    settings: Settings, engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(users_cli, "get_settings", lambda: settings)
    assert users_cli.main(["create-admin"]) == 0
    out = capsys.readouterr().out
    temp = out.split("Mật khẩu tạm (chỉ hiện lần này): ")[1].split()[0]
    assert users_cli.main(["create-admin"]) == 1 and "Đã có tài khoản" in capsys.readouterr().err
    with new_client(settings) as c:
        login(c, "admin", temp)
        assert c.get(ME).json()["must_change_password"] is True
        assert users_cli.main(["reset-password", "admin"]) == 0
        temp2 = capsys.readouterr().out.split("chỉ hiện lần này): ")[1].split()[0]
        assert c.get(ME).status_code == 401 and temp2 != temp
        login(c, "admin", temp2)
    assert users_cli.main(["reset-password", "khong-co"]) == 1
