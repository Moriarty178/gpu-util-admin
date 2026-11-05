"""/settings (cài đặt) và /audit (nhật ký) — G2-M4, chỉ admin (gắn require_admin ở main.py)."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.deps import AdminDep, SessionDep
from app.routers.analytics_common import errors
from app.services import ops_service as svc

router = APIRouter(tags=["ops"])


class SettingChoice(BaseModel):
    value: str
    label: str


class SettingOut(BaseModel):
    key: str
    value: float | int | str
    default: float | int | str
    label: str
    hint: str
    min: float
    max: float
    integer: bool
    unit: str
    kind: Literal["number", "choice"] = "number"
    choices: list[SettingChoice] = Field(default_factory=list, description="Chỉ có khi kind = choice")
    updated_by: str | None = None
    updated_at: dt.datetime | None = None


class SettingsOut(BaseModel):
    items: list[SettingOut]


class SettingsIn(BaseModel):
    values: dict[str, Any] = Field(
        description="khóa → giá trị mới (chỉ các khóa cần đổi); kiểm kiểu + giới hạn ở service"
    )


class AuditItem(BaseModel):
    id: int
    at: dt.datetime = Field(description="UTC")
    username: str | None
    action: str
    target: str | None
    payload: dict[str, Any]


class AuditOut(BaseModel):
    total: int
    page: int
    page_size: int
    actions: list[str]
    items: list[AuditItem]


@router.get("/settings", response_model=SettingsOut, summary="Cài đặt (giá trị hiện hành, mặc định, giới hạn)")
def get_settings(s: SessionDep) -> SettingsOut:
    return SettingsOut.model_validate({"items": svc.list_settings(s)})


@router.patch(
    "/settings",
    response_model=SettingsOut,
    summary="Đổi cài đặt — phân tích tính lại theo giá trị mới (data_version đổi)",
    responses=errors(422),
)
def update_settings(body: SettingsIn, admin: AdminDep, s: SessionDep) -> SettingsOut:
    return SettingsOut.model_validate({"items": svc.update_settings(s, admin.username, body.values)})


@router.get("/audit", response_model=AuditOut, summary="Nhật ký thao tác (mới nhất trước)")
def audit(
    s: SessionDep,
    username: str | None = None,
    action: Annotated[str | None, Query(description="Tiền tố, vd 'login', 'import_', 'user_', 'link_'")] = None,
    start: dt.date | None = None,
    end: dt.date | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Tìm trong đối tượng (IP, lô, tên)")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
) -> AuditOut:
    out = svc.list_audit(s, username=username, action=action, start=start, end=end, q=q, page=page, page_size=page_size)
    return AuditOut.model_validate(out)
