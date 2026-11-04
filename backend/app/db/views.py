"""Khai báo các VIEW (tạo trong migration 0001) để truy vấn bằng SQLAlchemy Core.
MetaData riêng → không bao giờ bị create_all/autogenerate coi là bảng."""

from __future__ import annotations

from sqlalchemy import JSON, Column, Date, DateTime, Float, Integer, MetaData, String, Table, Text

view_metadata = MetaData()

# Mỗi (ip, ts) lấy mẫu của lô COMMITTED mới nhất (theo committed_at, rồi id)
util_effective = Table(
    "util_effective",
    view_metadata,
    Column("ip", String(15)),
    Column("ts", DateTime),
    Column("gpu", Float),
    Column("mem", Float),
    Column("gpu_type", Text),
    Column("batch_id", Integer),
)

# Dòng của lô inventory committed mới nhất
inventory_current = Table(
    "inventory_current",
    view_metadata,
    Column("batch_id", Integer),
    Column("ip", String(15)),
    Column("excel_row", Integer),
    Column("stt", Text),
    Column("server_class", Text),
    Column("config", Text),
    Column("cpu", Text),
    Column("ram", Text),
    Column("disk", Text),
    Column("hba", Text),
    Column("gpu_spec", Text),
    Column("gpu_count", Integer),
    Column("gpu_model", Text),
    Column("serial", Text),
    Column("owner", String(64)),
    Column("model", Text),
    Column("input_load", Text),
    Column("service", Text),
    Column("managed_by", Text),
    Column("cluster", Text),
    Column("extra", JSON),
)

# Hợp 'DS đã thu' của mọi lô committed: mỗi IP lấy bản mới nhất + kỳ đầu tiên xuất hiện
reclaim_current = Table(
    "reclaim_current",
    view_metadata,
    Column("ip", String(15)),
    Column("gpu_type", Text),
    Column("beneficiary", Text),
    Column("owner_dcim", Text),
    Column("service_manager", Text),
    Column("status", Text),
    Column("batch_id", Integer),
    Column("first_seen", Date),
)
