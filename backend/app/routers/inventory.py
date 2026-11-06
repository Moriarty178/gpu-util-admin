"""/inventory — admin sửa tay thông tin server trong danh mục (PLAN §14.11) và bổ sung server VTNet có log mà file thống kê
thiếu (PLAN §14.12, dùng ở trang Đối soát). Gắn require_admin ở main.py."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, Response
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


class InventoryManualIn(BaseModel):
    """Bổ sung 1 server VTNet-only: đủ cột như file thống kê (trừ STT). Bắt buộc đầu mối."""

    model_config = ConfigDict(extra="forbid")

    ip: str = Field(max_length=15, description="IP phía VTNet (có log, chưa có trong file thống kê)")
    owner: str = Field(min_length=1, max_length=64, description="Đầu mối sử dụng (tự chuyển chữ thường)")
    server_class: str | None = Field(None, description="Loại server")
    config: str | None = Field(None, description="Cấu hình")
    cpu: str | None = None
    ram: str | None = None
    disk: str | None = None
    hba: str | None = None
    gpu_spec: str | None = Field(None, description="GPU, vd '4x NVIDIA L40S' (đọc số card/model như file thống kê)")
    serial: str | None = None
    model: str | None = None
    input_load: str | None = Field(None, description="Đầu vào hệ thống (CCU, Request…)")
    service: str | None = None
    managed_by: str | None = None
    cluster: str | None = None
    reclaim_status: ReclaimStatus = "in_use"


class InventoryStateOut(BaseModel):
    inventory_ip: str
    manual: bool = Field(False, description="Server bổ sung trên web (không có trong file thống kê)")
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


@router.post(
    "/inventory/manual",
    status_code=201,
    response_model=InventoryStateOut,
    summary="Bổ sung server VTNet có log mà file thống kê thiếu (trang Đối soát) — chỉ admin",
    responses=errors(404, 409, 422),
)
def add_manual(body: InventoryManualIn, admin: AdminDep, s: SessionDep) -> InventoryStateOut:
    out = svc.add_manual(s, admin.username, body.ip, body.model_dump(exclude={"ip"}))
    return InventoryStateOut.model_validate(out)


@router.delete(
    "/inventory/manual/{ip}",
    status_code=204,
    summary="Bỏ phần bổ sung → server quay về 'VTNet có – thống kê thiếu' — chỉ admin",
    responses=errors(404),
)
def remove_manual(ip: str, admin: AdminDep, s: SessionDep) -> Response:
    svc.remove_manual(s, admin.username, ip)
    return Response(status_code=204)
