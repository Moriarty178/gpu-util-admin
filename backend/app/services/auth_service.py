"""Tài khoản & đăng nhập (G2-M2, PLAN §1.3, §9): đăng nhập + khóa 5 lần sai/15 phút, đổi mật khẩu (buộc đổi lần đầu),
admin tạo / sửa / đặt lại mật khẩu tài khoản. Mọi thao tác ghi `audit_log`.

Thời điểm hệ thống lưu UTC không timezone (như GĐ1). Thông báo lỗi tiếng Việt qua ServiceError.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import security as sec
from app.db.models import AppUser, AuditLog
from app.errors import ServiceError
from app.repo.convert import jsonable
from app.scope import CurrentUser, DataScope, Role

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
ROLES: tuple[Role, ...] = ("admin", "owner", "viewer")
ROLE_VI = {"admin": "Quản trị", "owner": "Đầu mối", "viewer": "Chỉ xem"}
BAD_LOGIN = "Sai tên đăng nhập hoặc mật khẩu."


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def audit(s: Session, user: str | None, action: str, target: str | None = None, **payload: Any) -> None:
    s.add(AuditLog(at=utcnow(), username=user, action=action, target=target, payload=jsonable(payload)))


def to_current(u: AppUser) -> CurrentUser:
    return CurrentUser(
        id=u.id,
        username=u.username,
        role=u.role,  # type: ignore[arg-type]
        owner_key=u.owner_key,
        data_scope=u.data_scope,  # type: ignore[arg-type]
        must_change_password=u.must_change_password,
    )


def is_locked(u: AppUser, now: datetime) -> bool:
    return u.locked_until is not None and u.locked_until > now


def user_count(s: Session) -> int:
    return int(s.scalar(select(func.count(AppUser.id))) or 0)


def get_user(s: Session, user_id: int) -> AppUser:
    u = s.get(AppUser, user_id)
    if u is None:
        raise ServiceError(404, f"Không có tài khoản #{user_id}.")
    return u


def find_user(s: Session, username: str) -> AppUser | None:
    return s.scalar(select(AppUser).where(AppUser.username == username.strip().casefold()))


# ------------------------------------------------------------------ đăng nhập


def login(s: Session, username: str, password: str, *, ip: str | None = None, now: datetime | None = None) -> AppUser:
    now = now or utcnow()
    name = username.strip().casefold()[:64]  # chuỗi người gõ — cắt cho vừa cột nhật ký
    u = find_user(s, name)
    if u is None or not u.active:
        sec.burn_time(password)
        audit(s, name or None, "login_failed", name, reason="unknown_or_inactive", ip=ip)
        s.commit()
        raise ServiceError(401, BAD_LOGIN, type_="login_failed")
    if is_locked(u, now):
        audit(s, u.username, "login_locked", u.username, ip=ip)
        s.commit()
        assert u.locked_until is not None
        mins = max(1, int((u.locked_until - now).total_seconds() // 60) + 1)
        raise ServiceError(
            423, f"Tài khoản tạm khóa do nhập sai {sec.MAX_FAILED_ATTEMPTS} lần — thử lại sau {mins} phút."
        )
    if not sec.verify_password(password, u.password_hash):
        u.failed_attempts += 1
        locked = u.failed_attempts >= sec.MAX_FAILED_ATTEMPTS
        if locked:
            u.locked_until = now + timedelta(minutes=sec.LOCK_MINUTES)
            u.failed_attempts = 0
        audit(s, u.username, "login_failed", u.username, reason="bad_password", locked=locked, ip=ip)
        s.commit()
        if locked:
            raise ServiceError(
                423, f"Nhập sai {sec.MAX_FAILED_ATTEMPTS} lần — tài khoản tạm khóa {sec.LOCK_MINUTES} phút."
            )
        raise ServiceError(401, BAD_LOGIN, type_="login_failed")
    u.failed_attempts, u.locked_until, u.last_login_at = 0, None, now
    audit(s, u.username, "login", u.username, ip=ip)
    s.commit()
    return u


def change_password(s: Session, u: AppUser, current: str, new: str, *, rounds: int) -> AppUser:
    if not sec.verify_password(current, u.password_hash):
        raise ServiceError(422, "Mật khẩu hiện tại không đúng.")
    if new == current:
        raise ServiceError(422, "Mật khẩu mới phải khác mật khẩu hiện tại.")
    problem = sec.password_problem(new, u.username)
    if problem:
        raise ServiceError(422, problem)
    u.password_hash = sec.hash_password(new, rounds)
    u.must_change_password = False
    u.session_version += 1  # các phiên khác (máy khác) hết hiệu lực; phiên hiện tại được cấp lại
    audit(s, u.username, "password_changed", u.username)
    s.commit()
    return u


# ------------------------------------------------------------------ quản lý tài khoản (admin)


@dataclass
class UserInput:
    role: Role
    owner_key: str | None = None
    data_scope: DataScope = "own"
    full_name: str | None = None
    email: str | None = None


def _clean(u: UserInput) -> UserInput:
    if u.role not in ROLES:
        raise ServiceError(422, f"Vai trò không hợp lệ: {u.role}.")
    owner_key = (u.owner_key or "").strip().casefold() or None  # = inventory.owner (đã casefold)
    if u.role == "owner" and not owner_key:
        raise ServiceError(422, "Tài khoản đầu mối phải có mã đầu mối (vd kientt6).")
    return UserInput(
        role=u.role,
        owner_key=owner_key if u.role == "owner" else None,
        data_scope=u.data_scope if u.role == "owner" else "all",
        full_name=(u.full_name or "").strip() or None,
        email=(u.email or "").strip() or None,
    )


def create_user(
    s: Session, actor: str, username: str, data: UserInput, *, rounds: int, password: str | None = None
) -> tuple[AppUser, str]:
    """→ (tài khoản, mật khẩu tạm — chỉ trả về 1 lần). Luôn buộc đổi mật khẩu ở lần đăng nhập đầu."""
    name = username.strip().casefold()
    if not USERNAME_RE.match(name):
        raise ServiceError(422, "Tên đăng nhập 3–32 ký tự: chữ thường không dấu, số, dấu . _ - (vd kientt6).")
    if find_user(s, name) is not None:
        raise ServiceError(409, f"Đã có tài khoản '{name}'.")
    d = _clean(data)
    pw = password or sec.temp_password()
    u = AppUser(
        username=name,
        full_name=d.full_name,
        email=d.email,
        password_hash=sec.hash_password(pw, rounds),
        role=d.role,
        owner_key=d.owner_key,
        data_scope=d.data_scope,
        must_change_password=True,
        created_by=actor,
        created_at=utcnow(),
    )
    s.add(u)
    s.flush()
    audit(s, actor, "user_created", name, role=d.role, owner_key=d.owner_key, data_scope=d.data_scope)
    s.commit()
    return u, pw


def _active_admins(s: Session) -> int:
    q = select(func.count(AppUser.id)).where(AppUser.role == "admin", AppUser.active.is_(True))
    return int(s.scalar(q) or 0)


def update_user(
    s: Session, actor: CurrentUser, user_id: int, changes: dict[str, Any], *, unlock: bool = False
) -> AppUser:
    u = get_user(s, user_id)
    merged = UserInput(
        role=changes.get("role", u.role),
        owner_key=changes.get("owner_key", u.owner_key),
        data_scope=changes.get("data_scope", u.data_scope),
        full_name=changes.get("full_name", u.full_name),
        email=changes.get("email", u.email),
    )
    d = _clean(merged)
    active = bool(changes.get("active", u.active))
    if u.id == actor.id and (d.role != "admin" or not active):
        raise ServiceError(409, "Không thể tự hạ quyền hoặc tự khóa tài khoản đang dùng.")
    if u.role == "admin" and u.active and (d.role != "admin" or not active) and _active_admins(s) <= 1:
        raise ServiceError(409, "Phải còn ít nhất 1 tài khoản quản trị đang hoạt động.")
    before = {"role": u.role, "owner_key": u.owner_key, "data_scope": u.data_scope, "active": u.active}
    u.role, u.owner_key, u.data_scope = d.role, d.owner_key, d.data_scope
    u.full_name, u.email = d.full_name, d.email
    if u.active and not active:
        u.session_version += 1  # khóa → đăng xuất ngay mọi phiên
    u.active = active
    if unlock:
        u.failed_attempts, u.locked_until = 0, None
    after = {"role": u.role, "owner_key": u.owner_key, "data_scope": u.data_scope, "active": u.active}
    audit(s, actor.username, "user_updated", u.username, before=before, after=after, unlock=unlock)
    s.commit()
    return u


def reset_password(s: Session, actor: str, user_id: int, *, rounds: int) -> tuple[AppUser, str]:
    u = get_user(s, user_id)
    pw = sec.temp_password()
    u.password_hash = sec.hash_password(pw, rounds)
    u.must_change_password = True
    u.failed_attempts, u.locked_until = 0, None
    u.session_version += 1
    audit(s, actor, "user_password_reset", u.username)
    s.commit()
    return u, pw


def list_users(s: Session) -> list[AppUser]:
    return list(s.scalars(select(AppUser).order_by(AppUser.username)))
