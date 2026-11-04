"""GĐ2 (G2-M2): tài khoản app_user, nhật ký audit_log, ghi chú server_note (PLAN §4.9)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-03

Thêm so với PLAN §4.9: `app_user.session_version` (tăng khi đổi/đặt lại mật khẩu, khóa tài khoản → phiên cũ hết hiệu lực).
Chỉ tạo bảng mới, không ALTER bảng mà view tham chiếu → không phải DROP/CREATE lại view.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMPTY_JSON = sa.text("'{}'")


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer, nullable=False),
        sa.Column("username", sa.String(32), nullable=False),
        sa.Column("full_name", sa.Text),
        sa.Column("email", sa.Text),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("owner_key", sa.String(64)),
        sa.Column("data_scope", sa.String(8), nullable=False, server_default=sa.text("'own'")),
        sa.Column("must_change_password", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("failed_attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("locked_until", sa.DateTime),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("session_version", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("last_login_at", sa.DateTime),
        sa.Column("created_by", sa.String(64)),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_user")),
        sa.UniqueConstraint("username", name=op.f("uq_app_user_username")),
        sa.CheckConstraint("role IN ('admin', 'owner', 'viewer')", name=op.f("ck_app_user_role")),
        sa.CheckConstraint("data_scope IN ('own', 'all')", name=op.f("ck_app_user_data_scope")),
        sa.CheckConstraint("role <> 'owner' OR owner_key IS NOT NULL", name=op.f("ck_app_user_owner_has_key")),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, nullable=False),
        sa.Column("at", sa.DateTime, nullable=False),
        sa.Column("username", sa.String(64)),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("target", sa.Text),
        sa.Column("payload", sa.JSON, nullable=False, server_default=EMPTY_JSON),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index("ix_audit_at", "audit_log", ["at"])

    op.create_table(
        "server_note",
        sa.Column("id", sa.Integer, nullable=False),
        sa.Column("ip", sa.String(15), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("valid_until", sa.Date),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("deleted_at", sa.DateTime),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_server_note")),
        sa.CheckConstraint("kind IN ('note', 'explanation', 'exempt', 'action')", name=op.f("ck_server_note_kind")),
    )
    op.create_index("ix_server_note_ip", "server_note", ["ip"])


def downgrade() -> None:
    op.drop_index("ix_server_note_ip", table_name="server_note")
    op.drop_table("server_note")
    op.drop_index("ix_audit_at", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("app_user")
