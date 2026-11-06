"""Bổ sung server VTNet-only vào danh mục: inventory_override.is_manual + cột phần cứng (PLAN §14.12)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-06

Chỉ thêm cột vào bảng `inventory_override` (không view nào tham chiếu). Dòng `is_manual` = server VTNet có log nhưng file
thống kê thiếu, admin bổ sung ở trang Đối soát.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEXT_COLUMNS = ["server_class", "config", "cpu", "ram", "disk", "hba", "gpu_spec", "serial"]


def upgrade() -> None:
    with op.batch_alter_table("inventory_override") as b:
        b.add_column(sa.Column("is_manual", sa.Boolean, nullable=False, server_default=sa.false()))
        for c in TEXT_COLUMNS:
            b.add_column(sa.Column(c, sa.Text))


def downgrade() -> None:
    with op.batch_alter_table("inventory_override") as b:
        for c in reversed(TEXT_COLUMNS):
            b.drop_column(c)
        b.drop_column("is_manual")
