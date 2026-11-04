"""Schema I/O cho /auth và /users (G2-M2)."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import AppUser
from app.scope import CurrentUser
from app.services.auth_service import ROLE_VI, is_locked, utcnow

RoleLit = Literal["admin", "owner", "viewer"]
ScopeLit = Literal["own", "all"]


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class MeOut(BaseModel):
    username: str
    full_name: str | None = None
    role: RoleLit
    role_label: str
    owner_key: str | None = None
    data_scope: ScopeLit
    must_change_password: bool

    @classmethod
    def build(cls, u: AppUser | CurrentUser, full_name: str | None = None) -> MeOut:
        return cls(
            username=u.username,
            full_name=getattr(u, "full_name", None) or full_name,
            role=u.role,  # type: ignore[arg-type]
            role_label=ROLE_VI[u.role],
            owner_key=u.owner_key,
            data_scope=u.data_scope,  # type: ignore[arg-type]
            must_change_password=u.must_change_password,
        )


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str | None
    email: str | None
    role: RoleLit
    role_label: str
    owner_key: str | None
    data_scope: ScopeLit
    must_change_password: bool
    active: bool
    locked: bool
    locked_until: dt.datetime | None
    last_login_at: dt.datetime | None
    created_by: str | None
    created_at: dt.datetime

    @classmethod
    def build(cls, u: AppUser) -> UserOut:
        locked = is_locked(u, utcnow())
        return cls(
            id=u.id,
            username=u.username,
            full_name=u.full_name,
            email=u.email,
            role=u.role,  # type: ignore[arg-type]
            role_label=ROLE_VI[u.role],
            owner_key=u.owner_key,
            data_scope=u.data_scope,  # type: ignore[arg-type]
            must_change_password=u.must_change_password,
            active=u.active,
            locked=locked,
            locked_until=u.locked_until if locked else None,
            last_login_at=u.last_login_at,
            created_by=u.created_by,
            created_at=u.created_at,
        )


class UserListOut(BaseModel):
    items: list[UserOut]


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    role: RoleLit
    owner_key: str | None = Field(default=None, max_length=64)
    data_scope: ScopeLit = "own"
    full_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)


class UserUpdateIn(BaseModel):
    role: RoleLit | None = None
    owner_key: str | None = Field(default=None, max_length=64)
    data_scope: ScopeLit | None = None
    full_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    active: bool | None = None
    unlock: bool = False


class UserWithPasswordOut(BaseModel):
    """Trả mật khẩu tạm đúng 1 lần (tạo / đặt lại). Không lưu, không ghi log."""

    user: UserOut
    temp_password: str
