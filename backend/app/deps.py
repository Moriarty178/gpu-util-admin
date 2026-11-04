"""Dependency dùng chung cho router: CSDL, cài đặt, người dùng hiện tại (cookie phiên), phân quyền, phạm vi dữ liệu.

Phân quyền gắn ở mức router trong main.py (mặc định chặn): `require_user` (đã đăng nhập + đã đổi mật khẩu tạm),
`require_admin`. Riêng `/auth/*` dùng `session_user` (cho phép tài khoản đang phải đổi mật khẩu).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app import security as sec
from app.config import Settings
from app.db.models import AppUser
from app.errors import AuthError
from app.scope import CurrentUser, Scope
from app.services.auth_service import to_current, user_count


def get_engine(request: Request) -> Engine:
    engine: Engine = request.app.state.engine
    return engine


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session(engine: Annotated[Engine, Depends(get_engine)]) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


EngineDep = Annotated[Engine, Depends(get_engine)]
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def session_user(request: Request, s: SessionDep) -> CurrentUser:
    """Người dùng của cookie phiên (chưa xét buộc đổi mật khẩu). Kiểm CSRF cho request ghi."""
    token = request.cookies.get(sec.SESSION_COOKIE)
    claims = sec.read_session(token, request.app.state.secret) if token else None
    if claims is None:
        if user_count(s) == 0:
            raise AuthError(
                401, "setup_required", "Chưa có tài khoản nào — tạo admin: bash scripts/task.sh create-admin"
            )
        raise AuthError(401, "not_authenticated", "Chưa đăng nhập hoặc phiên đã hết hạn.")
    u = s.get(AppUser, claims.user_id)
    if u is None or not u.active or u.session_version != claims.version:
        raise AuthError(401, "not_authenticated", "Phiên đăng nhập không còn hiệu lực — hãy đăng nhập lại.")
    if request.method in sec.UNSAFE_METHODS and not sec.csrf_ok(claims.csrf, request.headers.get(sec.CSRF_HEADER)):
        raise AuthError(403, "csrf_failed", "Thiếu hoặc sai mã chống giả mạo (CSRF) — tải lại trang rồi thử lại.")
    request.state.user = to_current(u)
    return request.state.user  # type: ignore[no-any-return]


SessionUserDep = Annotated[CurrentUser, Depends(session_user)]


def current_user(user: SessionUserDep) -> CurrentUser:
    """Người dùng đã đăng nhập và đã đổi mật khẩu tạm — điều kiện cho mọi API dữ liệu."""
    if user.must_change_password:
        raise AuthError(403, "password_change_required", "Cần đổi mật khẩu tạm trước khi dùng hệ thống.")
    return user


UserDep = Annotated[CurrentUser, Depends(current_user)]


def require_user(user: UserDep) -> CurrentUser:
    return user


def require_admin(user: UserDep) -> CurrentUser:
    if not user.is_admin:
        raise AuthError(403, "forbidden", "Chỉ tài khoản quản trị được dùng chức năng này.")
    return user


def get_scope(user: UserDep) -> Scope:
    return Scope.for_user(user)


AdminDep = Annotated[CurrentUser, Depends(require_admin)]
ScopeDep = Annotated[Scope, Depends(get_scope)]
