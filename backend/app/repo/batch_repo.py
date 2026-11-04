from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import AppSetting, ImportBatch, InventoryItem, IpLink, UtilSample, VtnetOverview, VtnetReclaim


def get(s: Session, batch_id: int) -> ImportBatch | None:
    return s.get(ImportBatch, batch_id)


def find_committed(s: Session, kind: str, sha256: str) -> ImportBatch | None:
    stmt = select(ImportBatch).where(
        ImportBatch.kind == kind, ImportBatch.file_sha256 == sha256, ImportBatch.status == "committed"
    )
    return s.scalars(stmt).first()


def latest_committed(s: Session, kind: str) -> ImportBatch | None:
    stmt = (
        select(ImportBatch)
        .where(ImportBatch.kind == kind, ImportBatch.status == "committed")
        .order_by(ImportBatch.committed_at.desc(), ImportBatch.id.desc())
        .limit(1)
    )
    return s.scalars(stmt).first()


def list_batches(s: Session, limit: int = 200) -> Sequence[ImportBatch]:
    return s.scalars(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(limit)).all()


def staged_before(s: Session, before: datetime) -> Sequence[ImportBatch]:
    stmt = select(ImportBatch).where(ImportBatch.status == "staged", ImportBatch.uploaded_at < before)
    return s.scalars(stmt).all()


def delete_rows(s: Session, batch_id: int) -> None:
    """Xóa dữ liệu chi tiết của lô CHƯA từng có hiệu lực (staged → discarded). Không dùng cho lô committed."""
    for model in (UtilSample, VtnetOverview, VtnetReclaim, InventoryItem):
        s.execute(delete(model).where(model.batch_id == batch_id))


def committed_batches(s: Session, kind: str) -> Sequence[ImportBatch]:
    stmt = (
        select(ImportBatch)
        .where(ImportBatch.kind == kind, ImportBatch.status == "committed")
        .order_by(ImportBatch.period_start.desc(), ImportBatch.id.desc())
    )
    return s.scalars(stmt).all()


def data_version(s: Session) -> tuple[object, ...]:
    """Đổi khi có lô xác nhận / hoàn tác, liên kết IP hay cài đặt thay đổi → khóa cache phân tích."""
    b = s.execute(
        select(
            func.max(ImportBatch.committed_at), func.max(ImportBatch.rolled_back_at), func.count(ImportBatch.id)
        ).where(ImportBatch.status.in_(("committed", "rolled_back")))
    ).one()
    # liên kết IP: toàn bộ nội dung (ít dòng) — sửa cặp / xác nhận / xóa đều làm khóa đổi (G2-M3)
    links = tuple(
        s.execute(
            select(IpLink.inventory_ip, IpLink.vtnet_ip, IpLink.pair_confirmed).order_by(IpLink.inventory_ip)
        ).all()
    )
    settings = s.execute(select(func.count(AppSetting.key), func.max(AppSetting.updated_at))).one()
    return (*b, links, *settings)
