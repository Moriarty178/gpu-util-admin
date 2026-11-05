"""/inventory/{inventory_ip} — admin sửa tay thông tin server trong danh mục (PLAN §14.11). Gắn require_admin ở main.py."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.deps import AdminDep, SessionDep
from app.routers.analytics_common import errors
from app.services import inventory_service as svc

router = APIRouter(tags=["inventory"])

ReclaimStatus = Literal["in_use", "reclaimed"]


class InventoryEditIn(BaseModel):
    """Chỉ gửi các khóa cần đổi. Chuỗi = giá trị mới ('' = để trống); null = về theo file thống kê."""

    model_config = ConfigDict(extra="forbid")

    owner: str | None = Field(None, description="Đầu mối (tự chuyển chữ thường như file thống kê)")
    model: str | None = None
    input_load: str | None = Field(None, description="Đầu vào hệ thống (CCU, Request…)")
    service: str | None = None
    managed_by: str | None = None
    cluster: str | None = None
    reclaim_status: ReclaimStatus | None = Field(
        None, description="in_use = Đang sử dụng (mặc định) · reclaimed = VTNet đã thu hồi"
    )


class InventoryFields(BaseModel):
    owner: str | None = None
    model: str | None = None
    input_load: str | None = None
    service: str | None = None
    managed_by: str | None = None
    cluster: str | None = None


class InventoryStateOut(BaseModel):
    inventory_ip: str
    values: InventoryFields = Field(description="Giá trị hiệu lực (sau sửa tay)")
    file_values: InventoryFields = Field(description="Giá trị theo file thống kê hiện hành")
    edited: dict[str, str | None] = Field(description="Ô sửa tay khác file: cột → giá trị theo file")
    reclaim_status: ReclaimStatus
    updated_by: str | None = None
    updated_at: dt.datetime | None = Field(None, description="UTC")


@router.patch(
    "/inventory/{inventory_ip}",
    response_model=InventoryStateOut,
    summary="Sửa tay thông tin 1 server trong danh mục (đầu mối, model, dịch vụ…, trạng thái thu hồi) — chỉ admin",
    responses=errors(404, 422),
)
def update_item(inventory_ip: str, body: InventoryEditIn, admin: AdminDep, s: SessionDep) -> InventoryStateOut:
    out = svc.update(s, admin.username, inventory_ip, body.model_dump(exclude_unset=True))
    return InventoryStateOut.model_validate(out)
