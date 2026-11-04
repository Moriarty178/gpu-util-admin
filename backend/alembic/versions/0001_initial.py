"""GĐ1: bảng lô import, mẫu tải, overview, thu hồi, inventory, liên kết IP, cài đặt + 3 view (PLAN §4)

Revision ID: 0001
Revises:
Create Date: 2026-11-03

Lưu ý cho migration sau: SQLite kiểm tra VIEW khi batch-ALTER bảng mà view tham chiếu → trong migration đó
hãy DROP VIEW trước và tạo lại sau khi ALTER.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMPTY_JSON = sa.text("'{}'")
COMMITTED = sa.text("status = 'committed'")


def _batch_fk() -> sa.Column[int]:
    return sa.Column("batch_id", sa.Integer, nullable=False)


def _fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["batch_id"], ["import_batch.id"], ondelete="CASCADE", name=op.f(f"fk_{table}_batch_id_import_batch")
    )


UTIL_EFFECTIVE = """
CREATE VIEW util_effective AS
SELECT ip, ts, gpu, mem, gpu_type, batch_id FROM (
  SELECT s.ip, s.ts, s.gpu, s.mem, s.gpu_type, s.batch_id,
         ROW_NUMBER() OVER (PARTITION BY s.ip, s.ts ORDER BY b.committed_at DESC, b.id DESC) AS rn
  FROM util_sample s JOIN import_batch b ON b.id = s.batch_id AND b.status = 'committed'
) t WHERE rn = 1
"""

INVENTORY_CURRENT = """
CREATE VIEW inventory_current AS
SELECT i.batch_id, i.ip, i.excel_row, i.stt, i.server_class, i.config, i.cpu, i.ram, i.disk, i.hba,
       i.gpu_spec, i.gpu_count, i.gpu_model, i.serial, i.owner, i.model, i.input_load, i.service,
       i.managed_by, i.cluster, i.extra
FROM inventory_item i
WHERE i.batch_id = (
  SELECT b.id FROM import_batch b
  WHERE b.kind = 'inventory' AND b.status = 'committed'
  ORDER BY b.committed_at DESC, b.id DESC
  LIMIT 1
)
"""

RECLAIM_CURRENT = """
CREATE VIEW reclaim_current AS
SELECT ip, gpu_type, beneficiary, owner_dcim, service_manager, status, batch_id, first_seen FROM (
  SELECT r.ip, r.gpu_type, r.beneficiary, r.owner_dcim, r.service_manager, r.status, r.batch_id,
         ROW_NUMBER() OVER (PARTITION BY r.ip ORDER BY b.committed_at DESC, b.id DESC) AS rn,
         MIN(b.period_start) OVER (PARTITION BY r.ip) AS first_seen
  FROM vtnet_reclaim r JOIN import_batch b ON b.id = r.batch_id AND b.status = 'committed'
) t WHERE rn = 1
"""


def upgrade() -> None:
    op.create_table(
        "import_batch",
        sa.Column("id", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("file_name", sa.Text, nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("schema_version", sa.String(20)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date),
        sa.Column("period_end", sa.Date),
        sa.Column("period_label", sa.String(20)),
        sa.Column("summary", sa.JSON, nullable=False, server_default=EMPTY_JSON),
        sa.Column("validation", sa.JSON, nullable=False, server_default=EMPTY_JSON),
        sa.Column("uploaded_by", sa.String(64), nullable=False),
        sa.Column("uploaded_at", sa.DateTime, nullable=False),
        sa.Column("committed_by", sa.String(64)),
        sa.Column("committed_at", sa.DateTime),
        sa.Column("rolled_back_by", sa.String(64)),
        sa.Column("rolled_back_at", sa.DateTime),
        sa.Column("note", sa.Text),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_batch")),
        sa.CheckConstraint("kind IN ('vtnet_util', 'inventory')", name=op.f("ck_import_batch_kind")),
        sa.CheckConstraint(
            "status IN ('staged', 'committed', 'rolled_back', 'failed', 'discarded')",
            name=op.f("ck_import_batch_status"),
        ),
    )
    op.create_index(
        "uq_batch_committed_file",
        "import_batch",
        ["kind", "file_sha256"],
        unique=True,
        sqlite_where=COMMITTED,
        postgresql_where=COMMITTED,
    )

    op.create_table(
        "util_sample",
        _batch_fk(),
        sa.Column("ip", sa.String(15), nullable=False),
        sa.Column("ts", sa.DateTime, nullable=False),
        sa.Column("gpu", sa.Float, nullable=False),
        sa.Column("mem", sa.Float, nullable=False),
        sa.Column("gpu_type", sa.Text),
        sa.Column("don_vi", sa.String(20)),
        sa.PrimaryKeyConstraint("batch_id", "ip", "ts", name=op.f("pk_util_sample")),
        _fk("util_sample"),
    )
    op.create_index("ix_sample_ip_ts", "util_sample", ["ip", "ts"])
    op.create_index("ix_sample_ts", "util_sample", ["ts"])

    op.create_table(
        "vtnet_overview",
        _batch_fk(),
        sa.Column("ip", sa.String(15), nullable=False),
        sa.Column("gpu", sa.Float),
        sa.Column("mem", sa.Float),
        sa.PrimaryKeyConstraint("batch_id", "ip", name=op.f("pk_vtnet_overview")),
        _fk("vtnet_overview"),
    )

    op.create_table(
        "vtnet_reclaim",
        _batch_fk(),
        sa.Column("ip", sa.String(15), nullable=False),
        sa.Column("gpu_type", sa.Text),
        sa.Column("beneficiary", sa.Text),
        sa.Column("owner_dcim", sa.Text),
        sa.Column("service_manager", sa.Text),
        sa.Column("status", sa.Text),
        sa.PrimaryKeyConstraint("batch_id", "ip", name=op.f("pk_vtnet_reclaim")),
        _fk("vtnet_reclaim"),
    )

    op.create_table(
        "inventory_item",
        _batch_fk(),
        sa.Column("ip", sa.String(15), nullable=False),
        sa.Column("excel_row", sa.Integer),
        *[sa.Column(c, sa.Text) for c in ("stt", "server_class", "config", "cpu", "ram", "disk", "hba", "gpu_spec")],
        sa.Column("gpu_count", sa.Integer),
        sa.Column("gpu_model", sa.Text),
        sa.Column("serial", sa.Text),
        sa.Column("owner", sa.String(64)),
        *[sa.Column(c, sa.Text) for c in ("model", "input_load", "service", "managed_by", "cluster")],
        sa.Column("extra", sa.JSON, nullable=False, server_default=EMPTY_JSON),
        sa.PrimaryKeyConstraint("batch_id", "ip", name=op.f("pk_inventory_item")),
        _fk("inventory_item"),
    )

    op.create_table(
        "ip_link",
        sa.Column("inventory_ip", sa.String(15), nullable=False),
        sa.Column("vtnet_ip", sa.String(15), nullable=False),
        sa.Column("pair_confirmed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.Text),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("confirmed_by", sa.String(64)),
        sa.Column("confirmed_at", sa.DateTime),
        sa.PrimaryKeyConstraint("inventory_ip", name=op.f("pk_ip_link")),
        sa.UniqueConstraint("vtnet_ip", name=op.f("uq_ip_link_vtnet_ip")),
        sa.CheckConstraint("inventory_ip <> vtnet_ip", name=op.f("ck_ip_link_distinct_ips")),
    )

    op.create_table(
        "app_setting",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("updated_by", sa.String(64)),
        sa.Column("updated_at", sa.DateTime),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_setting")),
    )

    op.execute(UTIL_EFFECTIVE)
    op.execute(INVENTORY_CURRENT)
    op.execute(RECLAIM_CURRENT)


def downgrade() -> None:
    for view in ("reclaim_current", "inventory_current", "util_effective"):
        op.execute(f"DROP VIEW IF EXISTS {view}")
    op.drop_table("app_setting")
    op.drop_table("ip_link")
    op.drop_table("inventory_item")
    op.drop_table("vtnet_reclaim")
    op.drop_table("vtnet_overview")
    op.drop_index("ix_sample_ts", table_name="util_sample")
    op.drop_index("ix_sample_ip_ts", table_name="util_sample")
    op.drop_table("util_sample")
    op.drop_index("uq_batch_committed_file", table_name="import_batch")
    op.drop_table("import_batch")
