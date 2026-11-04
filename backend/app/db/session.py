"""Engine SQLAlchemy. GĐ1: SQLite (bật foreign_keys + WAL mỗi kết nối). GĐ2: chỉ đổi DATABASE_URL sang PostgreSQL."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import URL, make_url

from app.config import resolve_path


def _sqlite_file(url: URL) -> Path | None:
    db = url.database
    if url.get_backend_name() != "sqlite" or not db or db == ":memory:" or db.startswith("file:"):
        return None
    return Path(db)


def resolve_database_url(database_url: str) -> URL:
    """SQLite đường dẫn tương đối (vd `sqlite:///./data/app.db`) → tuyệt đối, tính từ gốc repo."""
    url = make_url(database_url)
    path = _sqlite_file(url)
    if path is not None:
        url = url.set(database=str(resolve_path(path)))
    return url


def _sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.close()


def make_engine(database_url: str) -> Engine:
    url = resolve_database_url(database_url)
    if url.get_backend_name() == "sqlite":
        path = _sqlite_file(url)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})
        event.listen(engine, "connect", _sqlite_pragmas)
        return engine
    return create_engine(url, pool_pre_ping=True)


def check_db(engine: Engine) -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
