"""Test khung app G1-M0: healthz, PRAGMA SQLite, định dạng lỗi, phục vụ frontend build, sao lưu."""

from __future__ import annotations

import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import ROOT_DIR, Settings
from app.db.session import make_engine, resolve_database_url
from app.main import create_app
from app.tools.backup import backup


def test_healthz(client: TestClient) -> None:
    r = client.get("/api/v1/healthz")
    assert r.status_code == 200
    assert r.json() == {"db": "ok", "gpu_core": "2.5.0"}  # gpu_core 2.5 (zone_metric)


@pytest.mark.sqlite_only
def test_sqlite_pragmas(settings: Settings) -> None:
    engine = make_engine(settings.database_url)
    with engine.connect() as c:
        assert c.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert c.execute(text("PRAGMA journal_mode")).scalar() == "wal"
    engine.dispose()


def test_relative_sqlite_path_is_from_repo_root() -> None:
    url = resolve_database_url("sqlite:///./data/app.db")
    assert Path(url.database or "") == (ROOT_DIR / "data" / "app.db").resolve()


def test_unknown_api_path_returns_problem_json(client: TestClient) -> None:
    r = client.get("/api/v1/khong-co")
    assert r.status_code == 404
    body = r.json()
    assert set(body) == {"type", "title", "detail"} and body["title"] == "Không tìm thấy"


def test_method_not_allowed_is_vietnamese(client: TestClient) -> None:
    r = client.post("/api/v1/healthz")
    assert r.status_code == 405 and r.json()["title"] == "Phương thức không được hỗ trợ"


def test_no_cdn_docs_pages(client: TestClient) -> None:
    """Q17: không phục vụ Swagger UI / ReDoc (tải tài nguyên từ CDN); đặc tả OpenAPI JSON vẫn có."""
    for path in ("/docs", "/redoc", "/docs/oauth2-redirect"):
        r = client.get(path)
        assert r.status_code == 404 and "swagger" not in r.text.lower()
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200 and r.json()["info"]["title"].startswith("GPU Util Admin")


def test_spa_fallback(settings: Settings) -> None:
    dist = settings.dist_path
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>SPA</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    with TestClient(create_app(settings)) as c:
        assert c.get("/").text == "<html>SPA</html>"
        assert c.get("/alerts?threshold=40").text == "<html>SPA</html>"  # route của React Router
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/favicon.svg").text == "<svg/>"
        assert c.get("/%2e%2e/%2e%2e/pyproject.toml").text == "<html>SPA</html>"  # không lộ file ngoài dist
        r = c.get("/api/v1/khong-co")
        assert r.status_code == 404 and r.json()["type"] == "not_found"
        assert c.get("/api/v1/healthz").json()["db"] == "ok"


def test_backup_zip(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE t (x INTEGER)")
    con.execute("INSERT INTO t VALUES (42)")
    con.commit()
    con.close()
    up = tmp_path / "uploads"
    up.mkdir()
    (up / "abc.xlsx").write_bytes(b"x")
    out = backup(db, up, tmp_path / "backups", now=datetime(2026, 11, 3, 9, 30, 0))
    assert out is not None and out.name == "gpu-util-data-20261103-093000.zip"
    with zipfile.ZipFile(out) as zf:
        assert sorted(zf.namelist()) == ["data/app.db", "data/uploads/abc.xlsx"]
        zf.extract("data/app.db", tmp_path / "restore")
    con = sqlite3.connect(tmp_path / "restore" / "data" / "app.db")
    assert con.execute("SELECT x FROM t").fetchall() == [(42,)]
    con.close()


def test_backup_nothing(tmp_path: Path) -> None:
    assert backup(None, tmp_path / "uploads", tmp_path / "backups") is None


def test_openapi_lists_all_phase1_endpoints(client: TestClient) -> None:
    """Nghiệm thu G1-M2: OpenAPI (/api/v1/openapi.json) đủ các endpoint GĐ1 của PLAN §7, mỗi endpoint có mô tả."""
    spec = client.get("/api/v1/openapi.json").json()
    expected = {
        "/api/v1/healthz", "/api/v1/meta", "/api/v1/imports", "/api/v1/imports/{batch_id}",
        "/api/v1/imports/{batch_id}/file", "/api/v1/imports/{batch_id}/commit", "/api/v1/imports/{batch_id}/rollback",
        "/api/v1/imports/{batch_id}/discard", "/api/v1/fleet/timeseries", "/api/v1/fleet/summary", "/api/v1/servers",
        "/api/v1/servers/{ip}", "/api/v1/servers/{ip}/timeseries", "/api/v1/alerts", "/api/v1/alerts/export.xlsx",
    }  # fmt: skip
    assert expected <= set(spec["paths"])
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            assert op.get("summary"), f"{method.upper()} {path} thiếu summary"


def test_restore_roundtrip_and_safety_backup(tmp_path: Path) -> None:
    """G2-M4: sao lưu → đổi dữ liệu → khôi phục → về đúng bản sao lưu; dữ liệu trước khôi phục được sao lưu riêng."""
    from app.tools.restore import RestoreError, restore

    data = tmp_path / "data"
    up = data / "uploads"
    up.mkdir(parents=True)
    db = data / "app.db"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE import_batch (x INTEGER); CREATE TABLE alembic_version (v TEXT); INSERT INTO import_batch VALUES (1);"
    )
    con.commit()
    con.close()
    (up / "a.xlsx").write_bytes(b"goc")
    zip1 = backup(db, up, tmp_path / "backups", now=datetime(2026, 11, 3, 9, 0, 0))
    assert zip1 is not None
    con = sqlite3.connect(db)
    con.execute("INSERT INTO import_batch VALUES (2)")
    con.commit()
    con.close()
    (up / "a.xlsx").write_bytes(b"da-sua")

    r = restore(zip1, db, up, tmp_path / "backups", now=datetime(2026, 11, 3, 10, 0, 0))
    con = sqlite3.connect(db)
    assert [x[0] for x in con.execute("SELECT x FROM import_batch")] == [1]
    con.close()
    assert (up / "a.xlsx").read_bytes() == b"goc" and r["uploads"] == 1
    safety = r["safety_backup"]
    assert isinstance(safety, Path) and safety.name == "truoc-khoi-phuc-20261103-100000.zip"
    with zipfile.ZipFile(safety) as zf:
        assert zf.read("data/uploads/a.xlsx") == b"da-sua"

    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("data/app.db", b"x")
        zf.writestr("../evil.txt", b"x")
    with pytest.raises(RestoreError, match="không hợp lệ"):
        restore(bad, db, up, tmp_path / "backups")
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("khac.txt", b"x")
    with pytest.raises(RestoreError, match="không có data/app.db"):
        restore(empty, db, up, tmp_path / "backups")
