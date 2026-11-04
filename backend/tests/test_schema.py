"""Model SQLAlchemy ≡ migration Alembic (trên mọi CSDL test): autogenerate không thấy khác biệt nào."""

from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine

from app.db import models  # noqa: F401  (đăng ký bảng)
from app.db.base import Base


def test_models_match_migrations(engine: Engine) -> None:
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True, "render_as_batch": True})
        diffs = compare_metadata(ctx, Base.metadata)
    # bảng alembic_version và các VIEW không nằm trong metadata của model
    diffs = [d for d in diffs if not (d[0] == "remove_table" and d[1].name == "alembic_version")]
    assert diffs == []
