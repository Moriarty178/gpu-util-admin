"""/auth — đăng nhập, đăng xuất, thông tin phiên, đổi mật khẩu (G2-M2, PLAN §7, §9)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response

from app import security as sec
from app.db.models import AppUser
from app.deps import SessionDep, SessionUserDep, SettingsDep
from app.schemas.auth import ChangePasswordIn, LoginIn, MeOut
from app.schemas.common import Problem
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {c: {"model": Problem} for c in codes}


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def set_session(response: Response, request: Request, u: AppUser) -> None:
    settings = request.app.state.settings
    token, csrf = sec.new_session(u.id, u.session_version, request.app.state.secret, settings.session_hours)
    max_age = int(settings.session_hours * 3600)
    common: dict[str, Any] = {"max_age": max_age, "secure": settings.cookie_secure, "samesite": "strict", "path": "/"}
    response.set_cookie(sec.SESSION_COOKIE, token, httponly=True, **common)
    response.set_cookie(sec.CSRF_COOKIE, csrf, httponly=False, **common)  # JS đọc để gửi header X-CSRF-Token


def clear_session(response: Response) -> None:
    for name in (sec.SESSION_COOKIE, sec.CSRF_COOKIE):
        response.delete_cookie(name, path="/", samesite="strict")


@router.post(
    "/login",
    response_model=MeOut,
    summary="Đăng nhập → cookie phiên httpOnly + cookie CSRF",
    responses=_errors(401, 423),
)
def login(body: LoginIn, request: Request, response: Response, s: SessionDep) -> MeOut:
    u = auth_service.login(s, body.username, body.password, ip=_client_ip(request))
    set_session(response, request, u)
    return MeOut.build(u)


@router.post("/logout", status_code=204, summary="Đăng xuất: xóa cookie + làm hết hạn MỌI phiên của tài khoản")
def logout(request: Request, s: SessionDep) -> Response:
    """Không bắt buộc còn phiên hợp lệ: luôn xóa cookie. Có phiên hợp lệ (đúng CSRF) thì tăng session_version → token cũ
    (kể cả bị lộ) không dùng lại được; ghi nhật ký."""
    resp = Response(status_code=204)
    token = request.cookies.get(sec.SESSION_COOKIE)
    claims = sec.read_session(token, request.app.state.secret) if token else None
    if claims is not None and sec.csrf_ok(claims.csrf, request.headers.get(sec.CSRF_HEADER)):
        u = s.get(AppUser, claims.user_id)
        if u is not None and u.session_version == claims.version:
            u.session_version += 1
            auth_service.audit(s, u.username, "logout", u.username)
            s.commit()
    clear_session(resp)
    return resp


@router.get("/me", response_model=MeOut, summary="Tài khoản đang đăng nhập", responses=_errors(401))
def me(user: SessionUserDep, s: SessionDep) -> MeOut:
    u = s.get(AppUser, user.id)
    return MeOut.build(user, u.full_name if u else None)


@router.post(
    "/change-password",
    response_model=MeOut,
    summary="Đổi mật khẩu (bắt buộc ở lần đăng nhập đầu); phiên khác của tài khoản hết hiệu lực",
    responses=_errors(401, 403, 422),
)
def change_password(
    body: ChangePasswordIn, user: SessionUserDep, request: Request, response: Response, s: SessionDep, st: SettingsDep
) -> MeOut:
    u = s.get(AppUser, user.id)
    assert u is not None
    u = auth_service.change_password(s, u, body.current_password, body.new_password, rounds=st.bcrypt_rounds)
    set_session(response, request, u)  # cấp phiên mới (session_version đã tăng)
    return MeOut.build(u)
