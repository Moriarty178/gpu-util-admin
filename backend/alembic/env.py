"""Môi trường Alembic. render_as_batch=True để ALTER chạy được trên SQLite (GĐ1) và vẫn đúng trên PostgreSQL (GĐ2).

Gọi từ code (app.db.migrate) thì truyền sẵn `connection` qua config.attributes và không cấu hình lại logging.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from app.config import get_settings
from app.db import models  # noqa: F401  (đăng ký bảng vào metadata)
from app.db.base import Base
from app.db.session import make_engine, resolve_database_url

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _configure(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    url = resolve_database_url(get_settings().database_url)
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        return
    engine = make_engine(get_settings().database_url)
    try:
        with engine.begin() as conn:
            _configure(conn)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
