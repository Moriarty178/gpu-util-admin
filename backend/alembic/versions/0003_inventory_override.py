"""Sửa tay danh mục server: bảng inventory_override (PLAN §14.11)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-05

Chỉ tạo bảng mới (không ALTER bảng mà view tham chiếu). Giá trị sửa tay đè lên lô thống kê hiện hành khi hiển thị;
mẫu tải, lô nhập và file gốc giữ nguyên.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_override",
        sa.Column("inventory_ip", sa.String(15), nullable=False),
        sa.Column("owner", sa.String(64)),
        sa.Column("model", sa.Text),
        sa.Column("input_load", sa.Text),
        sa.Column("service", sa.Text),
        sa.Column("managed_by", sa.Text),
        sa.Column("cluster", sa.Text),
        sa.Column("reclaim_status", sa.String(16)),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.PrimaryKeyConstraint("inventory_ip", name=op.f("pk_inventory_override")),
        sa.CheckConstraint(
            "reclaim_status IS NULL OR reclaim_status IN ('in_use', 'reclaimed')",
            name=op.f("ck_inventory_override_reclaim_status"),
        ),
    )


def downgrade() -> None:
    op.drop_table("inventory_override")
