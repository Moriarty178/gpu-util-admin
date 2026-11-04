"""Fixture chung: sinh fixture tổng hợp; mỗi test API 1 CSDL tạm (đã migrate + seed), không đụng `.env`/data/ thật.

Đa CSDL (G2-M1, PLAN §11): mặc định chỉ SQLite. Đặt `TEST_PG_URL` (URL quản trị tới 1 PostgreSQL có quyền CREATE DATABASE,
vd `postgresql+psycopg://gpu_test@127.0.0.1:55432/postgres`) → mọi test dùng `settings`/`engine`/`client` chạy thêm trên PG,
id test có hậu tố `[sqlite]` / `[postgresql]`. Mỗi test PG = 1 database clone từ database mẫu đã migrate + seed.
"""

from __future__ import annotations

import importlib.util
import itertools
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.db.migrate import upgrade
from app.db.seed import seed
from app.db.session import make_engine
from app.main import create_app
from app.security import CSRF_COOKIE, CSRF_HEADER
from app.services import auth_service, import_checks

FIX = Path(__file__).parent / "fixtures"
PG_ADMIN_URL = os.environ.get("TEST_PG_URL", "").strip()
BACKENDS = ["sqlite", "postgresql"] if PG_ADMIN_URL else ["sqlite"]


def _load_make_synthetic() -> ModuleType:
    spec = importlib.util.spec_from_file_location("make_synthetic", FIX / "make_synthetic.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


make_synthetic = _load_make_synthetic()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "sqlite_only: test riêng của SQLite (PRAGMA, file .db) — bỏ qua trên PostgreSQL")


TEST_TODAY = date(2026, 12, 31)  # dữ liệu tổng hợp tới 05/11/2026 → không bị coi là "ngày tương lai" bất kể đồng hồ máy


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(import_checks, "today", lambda: TEST_TODAY)


@pytest.fixture(scope="session", autouse=True)
def synthetic_fixtures() -> None:
    make_synthetic.ensure(force=True)  # luôn sinh lại để khớp phiên bản make_synthetic.py hiện tại


class PgDatabases:
    """Tạo/xóa database test trên PostgreSQL: 1 database mẫu (migrate + seed 1 lần) → mỗi test 1 bản clone."""

    def __init__(self, admin_url: str) -> None:
        self.base = make_url(admin_url)
        self.admin = create_engine(self.base, isolation_level="AUTOCOMMIT", poolclass=NullPool)
        self.prefix = f"gpu_test_{os.getpid()}"
        self.template = f"{self.prefix}_tpl"
        self._seq = itertools.count(1)
        self._exec(f'DROP DATABASE IF EXISTS "{self.template}" WITH (FORCE)')
        self._exec(f"CREATE DATABASE \"{self.template}\" ENCODING 'UTF8' TEMPLATE template0")
        eng = make_engine(self.url(self.template))
        try:
            upgrade(eng)
            seed(eng)
        finally:
            eng.dispose()

    def _exec(self, sql: str) -> None:
        with self.admin.connect() as c:
            c.execute(text(sql))

    def url(self, name: str) -> str:
        return self.base.set(database=name).render_as_string(hide_password=False)

    def create(self) -> str:
        name = f"{self.prefix}_{next(self._seq)}"
        self._exec(f'CREATE DATABASE "{name}" TEMPLATE "{self.template}"')
        return self.url(name)

    def drop(self, url: str) -> None:
        self._exec(f'DROP DATABASE IF EXISTS "{make_url(url).database}" WITH (FORCE)')

    def close(self) -> None:
        self._exec(f'DROP DATABASE IF EXISTS "{self.template}" WITH (FORCE)')
        self.admin.dispose()


@pytest.fixture(scope="session", params=BACKENDS)
def db_backend(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture(scope="session")
def pg_databases(db_backend: str) -> Iterator[PgDatabases | None]:
    if db_backend != "postgresql":
        yield None
        return
    dbs = PgDatabases(PG_ADMIN_URL)
    yield dbs
    dbs.close()


DbFactory = Callable[[Path], str]


@pytest.fixture(scope="session")
def new_database(db_backend: str, pg_databases: PgDatabases | None) -> Iterator[DbFactory]:
    """Hàm tạo 1 CSDL rỗng-đã-migrate mới: SQLite = file trong thư mục tạm; PG = database clone (xóa cuối phiên)."""
    created: list[str] = []

    def make(tmp: Path) -> str:
        if pg_databases is None:
            return f"sqlite:///{(tmp / 'app.db').as_posix()}"
        url = pg_databases.create()
        created.append(url)
        return url

    yield make
    if pg_databases is not None:
        for url in created:
            pg_databases.drop(url)


def make_settings(database_url: str, tmp: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database_url,
        upload_dir=tmp / "uploads",
        frontend_dist=tmp / "dist",
        warm_cache=False,  # không chạy luồng nền trong test (test gọi warm_up trực tiếp khi cần)
        secret_key="khoa-bi-mat-chi-dung-cho-test-0123456789",
        bcrypt_rounds=4,  # bcrypt nhanh cho test (thật: 12)
    )


# ------------------------------------------------------------------ tài khoản & đăng nhập (G2-M2)

ADMIN_USER = "admin"
TEST_PASSWORD = "Mat-khau-test-01"


def add_user(
    database_url: str, username: str = ADMIN_USER, role: str = "admin", *, must_change: bool = False, **kw: str
) -> None:
    """Tạo tài khoản (nếu chưa có) với mật khẩu TEST_PASSWORD; mặc định đã đổi mật khẩu tạm."""
    eng = make_engine(database_url)
    try:
        with Session(eng) as s:
            if auth_service.find_user(s, username) is None:
                data = auth_service.UserInput(role=role, **kw)  # type: ignore[arg-type]
                u, _ = auth_service.create_user(s, "test", username, data, rounds=4, password=TEST_PASSWORD)
                u.must_change_password = must_change
                s.commit()
    finally:
        eng.dispose()


def login(c: TestClient, username: str = ADMIN_USER, password: str = TEST_PASSWORD) -> None:
    r = c.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    c.headers[CSRF_HEADER] = c.cookies[CSRF_COOKIE]


@contextmanager
def app_client(settings: Settings, username: str = ADMIN_USER, role: str = "admin", **kw: str) -> Iterator[TestClient]:
    """TestClient đã đăng nhập (tạo tài khoản nếu chưa có)."""
    add_user(settings.database_url, username, role, **kw)
    with TestClient(create_app(settings)) as c:
        login(c, username)
        yield c


@pytest.fixture
def settings(request: pytest.FixtureRequest, db_backend: str, new_database: DbFactory, tmp_path: Path) -> Settings:
    if db_backend != "sqlite" and request.node.get_closest_marker("sqlite_only"):
        pytest.skip("test riêng của SQLite")
    return make_settings(new_database(tmp_path), tmp_path)


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    """CSDL tạm đã `alembic upgrade head` + seed (như `task.sh migrate && task.sh seed`)."""
    eng = make_engine(settings.database_url)
    upgrade(eng)
    seed(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def client(settings: Settings, engine: Engine) -> Iterator[TestClient]:
    """Đã đăng nhập bằng admin."""
    with app_client(settings) as c:
        yield c


@pytest.fixture
def anon(settings: Settings, engine: Engine) -> Iterator[TestClient]:
    """Chưa đăng nhập."""
    with TestClient(create_app(settings)) as c:
        yield c
