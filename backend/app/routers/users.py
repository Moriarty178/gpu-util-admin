"""/users — quản lý tài khoản (chỉ admin; G2-M2, PLAN §7, §8.6)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.deps import AdminDep, SessionDep, SettingsDep
from app.schemas.auth import UserCreateIn, UserListOut, UserOut, UserUpdateIn, UserWithPasswordOut
from app.schemas.common import Problem
from app.services import auth_service as svc

router = APIRouter(prefix="/users", tags=["users"])


def _errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {c: {"model": Problem} for c in codes}


@router.get("", response_model=UserListOut, summary="Danh sách tài khoản")
def list_users(s: SessionDep) -> UserListOut:
    return UserListOut(items=[UserOut.build(u) for u in svc.list_users(s)])


@router.post(
    "",
    status_code=201,
    response_model=UserWithPasswordOut,
    summary="Tạo tài khoản → mật khẩu tạm (hiện 1 lần, buộc đổi khi đăng nhập)",
    responses=_errors(409, 422),
)
def create_user(body: UserCreateIn, admin: AdminDep, s: SessionDep, st: SettingsDep) -> UserWithPasswordOut:
    data = svc.UserInput(
        role=body.role, owner_key=body.owner_key, data_scope=body.data_scope, full_name=body.full_name, email=body.email
    )
    u, pw = svc.create_user(s, admin.username, body.username, data, rounds=st.bcrypt_rounds)
    return UserWithPasswordOut(user=UserOut.build(u), temp_password=pw)


@router.patch(
    "/{user_id}",
    response_model=UserOut,
    summary="Sửa vai trò / đầu mối / phạm vi / khóa-mở; `unlock` = gỡ khóa do nhập sai",
    responses=_errors(404, 409, 422),
)
def update_user(user_id: int, body: UserUpdateIn, admin: AdminDep, s: SessionDep) -> UserOut:
    changes = body.model_dump(exclude_unset=True, exclude={"unlock"})
    u = svc.update_user(s, admin, user_id, changes, unlock=body.unlock)
    return UserOut.build(u)


@router.post(
    "/{user_id}/reset-password",
    response_model=UserWithPasswordOut,
    summary="Đặt lại mật khẩu tạm (hiện 1 lần); đăng xuất mọi phiên của tài khoản",
    responses=_errors(404),
)
def reset_password(user_id: int, admin: AdminDep, s: SessionDep, st: SettingsDep) -> UserWithPasswordOut:
    u, pw = svc.reset_password(s, admin.username, user_id, rounds=st.bcrypt_rounds)
    return UserWithPasswordOut(user=UserOut.build(u), temp_password=pw)
