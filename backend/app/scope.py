"""Người dùng hiện tại & phạm vi dữ liệu.

GĐ2 (G2-M2): `deps.current_user()` đọc cookie phiên → CurrentUser từ bảng app_user. Vai trò (PLAN §1.3):
admin (toàn bộ, mọi quyền) / owner — đầu mối, `data_scope=own` mặc định chỉ thấy server của mình / viewer (chỉ xem).
Service nhận `Scope` (không nhận user) nên phạm vi áp ở tầng service, không chỉ ẩn trên giao diện.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["admin", "owner", "viewer"]
DataScope = Literal["own", "all"]


@dataclass(frozen=True)
class CurrentUser:
    username: str
    role: Role
    id: int | None = None
    owner_key: str | None = None
    data_scope: DataScope = "all"
    must_change_password: bool = False

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


# Người dùng hệ thống cho công cụ dòng lệnh / phát lại lô (không qua HTTP)
LOCAL_ADMIN = CurrentUser(username="local-admin", role="admin")


@dataclass(frozen=True)
class Scope:
    kind: Literal["all", "owner"] = "all"
    owner_key: str | None = None

    @classmethod
    def all(cls) -> Scope:
        return cls()

    @classmethod
    def for_user(cls, user: CurrentUser) -> Scope:
        """owner + data_scope=own → chỉ server có `owner` = owner_key; còn lại → toàn bộ."""
        if user.role == "owner" and user.data_scope == "own":
            return cls(kind="owner", owner_key=user.owner_key)
        return cls.all()
