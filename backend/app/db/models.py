"""Bảng GĐ1 (PLAN §4) — schema trung tính SQLite ↔ PostgreSQL: IP là TEXT, JSON qua sa.JSON, DateTime không timezone.

Thời điểm mẫu (`ts`) theo giờ VN; thời điểm hệ thống (uploaded_at, committed_at…) lưu UTC.
Các VIEW (util_effective, inventory_current, reclaim_current) tạo trong migration, khai báo để truy vấn ở app/db/views.py.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    false,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

BATCH_KINDS = ("vtnet_util", "inventory")
BATCH_STATUSES = ("staged", "committed", "rolled_back", "failed", "discarded")
_EMPTY_JSON = text("'{}'")
_COMMITTED = text("status = 'committed'")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class ImportBatch(Base):
    __tablename__ = "import_batch"
    __table_args__ = (
        CheckConstraint(_in("kind", BATCH_KINDS), name="kind"),
        CheckConstraint(_in("status", BATCH_STATUSES), name="status"),
        # Chống nhập trùng: 1 file (sha256) chỉ có tối đa 1 lô committed mỗi loại — partial index chạy cả SQLite & PG
        Index(
            "uq_batch_committed_file",
            "kind",
            "file_sha256",
            unique=True,
            sqlite_where=_COMMITTED,
            postgresql_where=_COMMITTED,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    file_name: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str] = mapped_column(String(64))
    file_path: Mapped[str] = mapped_column(Text)
    schema_version: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    period_label: Mapped[str | None] = mapped_column(String(20))
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, server_default=_EMPTY_JSON, default=dict)
    validation: Mapped[dict[str, Any]] = mapped_column(JSON, server_default=_EMPTY_JSON, default=dict)
    uploaded_by: Mapped[str] = mapped_column(String(64))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime)
    committed_by: Mapped[str | None] = mapped_column(String(64))
    committed_at: Mapped[datetime | None] = mapped_column(DateTime)
    rolled_back_by: Mapped[str | None] = mapped_column(String(64))
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime)
    note: Mapped[str | None] = mapped_column(Text)


class UtilSample(Base):
    """Mẫu tải append-only theo lô. Giá trị hiệu lực = lô committed mới nhất (VIEW util_effective)."""

    __tablename__ = "util_sample"
    __table_args__ = (
        Index("ix_sample_ip_ts", "ip", "ts"),
        Index("ix_sample_ts", "ts"),
    )

    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id", ondelete="CASCADE"), primary_key=True)
    ip: Mapped[str] = mapped_column(String(15), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    gpu: Mapped[float] = mapped_column(Float)
    mem: Mapped[float] = mapped_column(Float)
    gpu_type: Mapped[str | None] = mapped_column(Text)
    don_vi: Mapped[str | None] = mapped_column(String(20))


class VtnetOverview(Base):
    """Sheet VTT_KPI_overview — chỉ để đối soát."""

    __tablename__ = "vtnet_overview"

    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id", ondelete="CASCADE"), primary_key=True)
    ip: Mapped[str] = mapped_column(String(15), primary_key=True)
    gpu: Mapped[float | None] = mapped_column(Float)
    mem: Mapped[float | None] = mapped_column(Float)


class VtnetReclaim(Base):
    """Sheet 'DS đã thu' — server VTNet đã thu hồi."""

    __tablename__ = "vtnet_reclaim"

    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id", ondelete="CASCADE"), primary_key=True)
    ip: Mapped[str] = mapped_column(String(15), primary_key=True)
    gpu_type: Mapped[str | None] = mapped_column(Text)
    beneficiary: Mapped[str | None] = mapped_column(Text)
    owner_dcim: Mapped[str | None] = mapped_column(Text)
    service_manager: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)


class InventoryItem(Base):
    """File thống kê theo snapshot: mỗi lô inventory = 1 snapshot đầy đủ."""

    __tablename__ = "inventory_item"

    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id", ondelete="CASCADE"), primary_key=True)
    ip: Mapped[str] = mapped_column(String(15), primary_key=True)
    excel_row: Mapped[int | None] = mapped_column(Integer)
    stt: Mapped[str | None] = mapped_column(Text)
    server_class: Mapped[str | None] = mapped_column(Text)
    config: Mapped[str | None] = mapped_column(Text)
    cpu: Mapped[str | None] = mapped_column(Text)
    ram: Mapped[str | None] = mapped_column(Text)
    disk: Mapped[str | None] = mapped_column(Text)
    hba: Mapped[str | None] = mapped_column(Text)
    gpu_spec: Mapped[str | None] = mapped_column(Text)
    gpu_count: Mapped[int | None] = mapped_column(Integer)
    gpu_model: Mapped[str | None] = mapped_column(Text)
    serial: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(Text)
    input_load: Mapped[str | None] = mapped_column(Text)
    service: Mapped[str | None] = mapped_column(Text)
    managed_by: Mapped[str | None] = mapped_column(Text)
    cluster: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, server_default=_EMPTY_JSON, default=dict)


class IpLink(Base):
    """Cùng 1 máy nhưng IP thống kê ≠ IP VTNet. GĐ1: chỉ nạp từ seed; GĐ2: sửa/xác nhận trên UI."""

    __tablename__ = "ip_link"
    __table_args__ = (CheckConstraint("inventory_ip <> vtnet_ip", name="distinct_ips"),)

    inventory_ip: Mapped[str] = mapped_column(String(15), primary_key=True)
    vtnet_ip: Mapped[str] = mapped_column(String(15), unique=True)
    pair_confirmed: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    confirmed_by: Mapped[str | None] = mapped_column(String(64))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)


class AppSetting(Base):
    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_by: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)


# ------------------------------------------------------------------ GĐ2 (migration 0002, PLAN §4.9)

USER_ROLES = ("admin", "owner", "viewer")
DATA_SCOPES = ("own", "all")
NOTE_KINDS = ("note", "explanation", "exempt", "action")


class AppUser(Base):
    """Tài khoản riêng của công cụ (ADR-8). Mật khẩu băm bcrypt; `session_version` tăng → mọi phiên cũ mất hiệu lực."""

    __tablename__ = "app_user"
    __table_args__ = (
        CheckConstraint(_in("role", USER_ROLES), name="role"),
        CheckConstraint(_in("data_scope", DATA_SCOPES), name="data_scope"),
        CheckConstraint("role <> 'owner' OR owner_key IS NOT NULL", name="owner_has_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    full_name: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16))
    owner_key: Mapped[str | None] = mapped_column(String(64))  # = inventory.owner (đã casefold), vd 'kientt6'
    data_scope: Mapped[str] = mapped_column(String(8), server_default=text("'own'"), default="own")
    must_change_password: Mapped[bool] = mapped_column(Boolean, server_default=true(), default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    active: Mapped[bool] = mapped_column(Boolean, server_default=true(), default=True)
    session_version: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class AuditLog(Base):
    """Nhật ký thao tác (đăng nhập, nhập dữ liệu, tài khoản…). Chỉ thêm, không sửa."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_at", "at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime)
    username: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(40))
    target: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, server_default=_EMPTY_JSON, default=dict)


class ServerNote(Base):
    """Ghi chú / giải trình / miễn trừ / hành động theo server (dùng ở G2-M3). Xóa mềm qua `deleted_at`."""

    __tablename__ = "server_note"
    __table_args__ = (CheckConstraint(_in("kind", NOTE_KINDS), name="kind"), Index("ix_server_note_ip", "ip"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ip: Mapped[str] = mapped_column(String(15))
    kind: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    valid_until: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


# ------------------------------------------------------------------ Sửa tay danh mục server (migration 0003, PLAN §14.11)

RECLAIM_STATUSES = ("in_use", "reclaimed")


class InventoryOverride(Base):
    """Admin sửa tay thông tin 1 server trong danh mục (khóa = IP trong file thống kê). Đè lên lô thống kê hiện hành khi
    hiển thị, kể cả sau khi nhập file thống kê mới (người dùng chốt 05/11/2026). Cột NULL = theo file; '' = để trống.
    `reclaim_status` NULL = 'in_use' (mặc định "Đang sử dụng"). Chỉ là thông tin — không đổi phép tính tải.

    `is_manual` (migration 0004, PLAN §14.12): server VTNet có log nhưng file thống kê thiếu, admin bổ sung ở Đối soát → dòng
    này đóng vai 1 dòng thống kê (khóa = IP VTNet, đủ cột như file) cho tới khi file thống kê có IP đó."""

    __tablename__ = "inventory_override"
    __table_args__ = (
        CheckConstraint(f"reclaim_status IS NULL OR {_in('reclaim_status', RECLAIM_STATUSES)}", name="reclaim_status"),
    )

    inventory_ip: Mapped[str] = mapped_column(String(15), primary_key=True)
    owner: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(Text)
    input_load: Mapped[str | None] = mapped_column(Text)
    service: Mapped[str | None] = mapped_column(Text)
    managed_by: Mapped[str | None] = mapped_column(Text)
    cluster: Mapped[str | None] = mapped_column(Text)
    reclaim_status: Mapped[str | None] = mapped_column(String(16))
    is_manual: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    server_class: Mapped[str | None] = mapped_column(Text)
    config: Mapped[str | None] = mapped_column(Text)
    cpu: Mapped[str | None] = mapped_column(Text)
    ram: Mapped[str | None] = mapped_column(Text)
    disk: Mapped[str | None] = mapped_column(Text)
    hba: Mapped[str | None] = mapped_column(Text)
    gpu_spec: Mapped[str | None] = mapped_column(Text)
    serial: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime)
