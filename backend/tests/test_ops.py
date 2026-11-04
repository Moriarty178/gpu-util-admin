"""G2-M4 — Cài đặt (admin sửa hằng §4, phân tích tính lại), Nhật ký, tăng cứng bảo mật (header, openapi cần đăng nhập,
đăng xuất làm hết hạn mọi phiên)."""

from __future__ import annotations

from conftest import FIX, login
from fastapi.testclient import TestClient

from app import security as sec
from app.config import Settings
from app.main import create_app

Q = {"start": "2026-10-01", "end": "2026-10-05"}


def upload(c: TestClient, name: str) -> None:
    with (FIX / name).open("rb") as f:
        b = c.post("/api/v1/imports", files={"file": (name, f, "application/octet-stream")}).json()
    assert c.post(f"/api/v1/imports/{b['id']}/commit", json={"acknowledge": True}).status_code == 200


def test_settings_change_recomputes_analysis(client: TestClient) -> None:
    upload(client, "synthetic_t10.xlsx")
    items = {i["key"]: i for i in client.get("/api/v1/settings").json()["items"]}
    assert set(items) == {
        "default_threshold",
        "vtnet_low_load_t",
        "bursty_peak",
        "high_load",
        "thin_coverage",
        "max_upload_mb",
    }
    assert items["default_threshold"]["value"] == items["default_threshold"]["default"] == 40
    assert client.get("/api/v1/alerts", params=Q).json()["matrix"]["totals"] == {"danger": 2, "warning": 2, "safe": 2}

    r = client.patch("/api/v1/settings", json={"values": {"default_threshold": 55}})
    assert r.status_code == 200
    item = next(i for i in r.json()["items"] if i["key"] == "default_threshold")
    assert (item["value"], item["updated_by"]) == (55, "admin") and item["updated_at"]
    # T mặc định 55: .2 (50/60) → Cảnh báo, .4 (60/20) → Cảnh báo, .1 (80/85) vẫn An toàn — tính lại ngay (data_version)
    a = client.get("/api/v1/alerts", params=Q).json()
    assert a["params"]["threshold"] == 55 and a["matrix"]["totals"] == {"danger": 2, "warning": 3, "safe": 1}
    assert client.get("/api/v1/meta").json()["settings"]["default_threshold"] == 55

    bad = [
        ({"default_threshold": 120}, "0–100"),
        ({"thin_coverage": 2}, "0–1"),
        ({"max_upload_mb": 2.5}, "số nguyên"),
        ({"khong_co": 1}, "Không có cài đặt"),
        ({"high_load": True}, "phải là số"),
    ]
    for body, msg in bad:
        r = client.patch("/api/v1/settings", json={"values": body})
        assert r.status_code == 422 and msg in r.json()["detail"], body
    assert client.patch("/api/v1/settings", json={"values": {}}).status_code == 422
    log = client.get("/api/v1/audit", params={"action": "settings"}).json()
    assert log["total"] == 1 and log["items"][0]["payload"] == {"before": {"default_threshold": 40},
                                                                 "after": {"default_threshold": 55.0}}  # fmt: skip


def test_audit_filters_and_paging(client: TestClient) -> None:
    upload(client, "synthetic_t10.xlsx")
    client.post("/api/v1/users", json={"username": "kientt6", "role": "owner", "owner_key": "kientt6"})
    log = client.get("/api/v1/audit").json()
    acts = [i["action"] for i in log["items"]]
    assert acts[:4] == ["user_created", "import_committed", "import_uploaded", "login"]  # mới nhất trước
    assert {"login", "user_created", "import_uploaded", "import_committed"} <= set(log["actions"])
    assert client.get("/api/v1/audit", params={"action": "import_"}).json()["total"] == 2
    n_admin = sum(1 for i in log["items"] if i["username"] == "admin")  # (1 dòng user_created của fixture: "test")
    assert client.get("/api/v1/audit", params={"username": "ADMIN"}).json()["total"] == n_admin
    assert client.get("/api/v1/audit", params={"q": "kientt6"}).json()["items"][0]["action"] == "user_created"
    p = client.get("/api/v1/audit", params={"page_size": 1, "page": 2}).json()
    assert len(p["items"]) == 1 and p["items"][0]["action"] == "import_committed"
    assert client.get("/api/v1/audit", params={"start": "2000-01-01", "end": "2000-01-02"}).json()["total"] == 0


def test_security_headers_and_openapi_requires_login(client: TestClient, anon: TestClient) -> None:
    for c, path in ((client, "/api/v1/alerts"), (anon, "/api/v1/healthz")):
        h = c.get(path).headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
        assert "default-src 'self'" in h["content-security-policy"] and h["cache-control"] == "no-store"
    assert anon.get("/api/v1/openapi.json").status_code == 401
    assert client.get("/api/v1/openapi.json").json()["info"]["title"].startswith("GPU Util Admin")


def test_logout_invalidates_all_sessions_of_user(client: TestClient, settings: Settings) -> None:
    with TestClient(create_app(settings)) as other:
        login(other)
        stolen = other.cookies[sec.SESSION_COOKIE]
        assert client.post("/api/v1/auth/logout").status_code == 204
        assert other.get("/api/v1/auth/me").status_code == 401  # phiên ở máy khác cũng hết
        other.cookies.set(sec.SESSION_COOKIE, stolen)
        assert other.get("/api/v1/auth/me").status_code == 401  # token cũ (vd bị lộ) không dùng lại được
