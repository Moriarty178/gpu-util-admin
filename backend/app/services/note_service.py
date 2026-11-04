"""Ghi chú / giải trình / miễn trừ / hành động theo server (G2-M3, PLAN §1.3, §4.9, §8.6).

Quyền: admin thêm mọi loại; đầu mối chỉ thêm **giải trình** trên server của mình (owner = owner_key); viewer chỉ đọc.
Xóa mềm (`deleted_at`): admin xóa mọi ghi chú, người viết xóa ghi chú của mình. Miễn trừ bắt buộc có `valid_until`
(hôm nay → tối đa 1 năm). Miễn trừ **không đổi vùng** (luật vùng giữ nguyên) — chỉ gắn nhãn và cho phép ẩn khỏi bảng cảnh báo.
Ghi chú không vào cache phân tích (đọc riêng mỗi request) → không phải đổi `data_version`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import NOTE_KINDS, ServerNote

__all__ = ["KIND_VI", "ServerNote", "add_note", "can_add", "delete_note", "flags", "list_notes", "today"]
from app.errors import ServiceError
from app.scope import CurrentUser
from app.services.auth_service import audit, utcnow

KIND_VI = {"note": "Ghi chú", "explanation": "Giải trình", "exempt": "Miễn trừ", "action": "Hành động"}
MAX_EXEMPT_DAYS = 366
MAX_TEXT = 2000


@dataclass(frozen=True)
class NoteFlags:
    count: int = 0
    exempt_until: date | None = None


def today() -> date:
    return utcnow().date()


def _active(q: Any) -> Any:
    return q.where(ServerNote.deleted_at.is_(None))


def list_notes(s: Session, ip: str) -> list[ServerNote]:
    q = _active(select(ServerNote).where(ServerNote.ip == ip)).order_by(
        ServerNote.created_at.desc(), ServerNote.id.desc()
    )
    return list(s.scalars(q))


def flags(s: Session, on: date | None = None) -> dict[str, NoteFlags]:
    """IP → (số ghi chú đang hiệu lực, miễn trừ tới ngày nào nếu còn hạn) — gắn vào bảng cảnh báo."""
    on = on or today()
    counts = dict(s.execute(_active(select(ServerNote.ip, func.count(ServerNote.id))).group_by(ServerNote.ip)).all())
    q = _active(
        select(ServerNote.ip, func.max(ServerNote.valid_until)).where(
            ServerNote.kind == "exempt", ServerNote.valid_until >= on
        )
    ).group_by(ServerNote.ip)
    exempt = dict(s.execute(q).all())
    return {ip: NoteFlags(count=int(n), exempt_until=exempt.get(ip)) for ip, n in counts.items()}


def can_add(user: CurrentUser, kind: str, server_owner: str | None) -> bool:
    if user.role == "admin":
        return True
    return (
        user.role == "owner" and kind == "explanation" and server_owner is not None and server_owner == user.owner_key
    )


def add_note(
    s: Session, user: CurrentUser, ip: str, server_owner: str | None, kind: str, text: str, valid_until: date | None
) -> ServerNote:
    if kind not in NOTE_KINDS:
        raise ServiceError(422, f"Loại ghi chú không hợp lệ: {kind}.")
    if not can_add(user, kind, server_owner):
        if user.role == "owner":
            raise ServiceError(403, "Đầu mối chỉ được thêm giải trình cho server của mình.")
        raise ServiceError(403, "Tài khoản chỉ xem không thêm được ghi chú.")
    body = (text or "").strip()
    if not body:
        raise ServiceError(422, "Nội dung không được để trống.")
    if len(body) > MAX_TEXT:
        raise ServiceError(422, f"Nội dung tối đa {MAX_TEXT} ký tự.")
    if kind == "exempt":
        if valid_until is None:
            raise ServiceError(422, "Miễn trừ phải có ngày hết hạn.")
        if valid_until < today() or valid_until > today() + timedelta(days=MAX_EXEMPT_DAYS):
            raise ServiceError(422, f"Ngày hết hạn miễn trừ phải từ hôm nay tới tối đa {MAX_EXEMPT_DAYS} ngày.")
    elif valid_until is not None and kind != "action":
        valid_until = None  # chỉ miễn trừ / hành động (hạn xử lý) có ngày
    n = ServerNote(ip=ip, kind=kind, text=body, valid_until=valid_until, created_by=user.username, created_at=utcnow())
    s.add(n)
    s.flush()
    audit(s, user.username, "note_created", ip, note_id=n.id, kind=kind, valid_until=valid_until)
    s.commit()
    return n


def delete_note(s: Session, user: CurrentUser, ip: str, note_id: int) -> None:
    n = s.get(ServerNote, note_id)
    if n is None or n.ip != ip or n.deleted_at is not None:
        raise ServiceError(404, f"Không có ghi chú #{note_id} của server {ip}.")
    if not (user.role == "admin" or n.created_by == user.username):
        raise ServiceError(403, "Chỉ quản trị hoặc người viết được xóa ghi chú này.")
    n.deleted_at = utcnow()
    audit(s, user.username, "note_deleted", ip, note_id=n.id, kind=n.kind)
    s.commit()
