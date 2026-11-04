"""/gaps (đối soát) và /ip-links (liên kết IP) — G2-M3, PLAN §7, §8.6. Đọc: mọi tài khoản (theo phạm vi); sửa: admin."""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.deps import AdminDep, ScopeDep, SessionDep
from app.routers.analytics_common import AnalysisDep, CacheDep, errors
from app.schemas.g2 import GapsOut, LinkCreateIn, LinkListOut, LinkOut, LinkUpdateIn
from app.scope import Scope
from app.services import gaps_service as svc
from app.services.analytics_service import get_bundle

router = APIRouter(tags=["gaps"])


@router.get(
    "/gaps",
    response_model=GapsOut,
    summary="Đối soát: VTNet-only, thống kê không có số liệu (đã thu hồi / chưa rõ), lệch số card, gợi ý liên kết IP",
    responses=errors(422),
)
def gaps(a: AnalysisDep, scope: ScopeDep) -> GapsOut:
    return GapsOut.model_validate(svc.gaps(a.bundle, scope))


def _links(a: AnalysisDep, scope: ScopeDep, s: SessionDep) -> LinkListOut:
    extra = svc.link_details(s)
    return LinkListOut(items=[LinkOut(**r, **extra.get(r["inventory_ip"], {})) for r in svc.link_rows(a.bundle, scope)])


@router.get("/ip-links", response_model=LinkListOut, summary="Liên kết IP thống kê ↔ VTNet (kèm trạng thái số liệu)")
def list_links(a: AnalysisDep, scope: ScopeDep, s: SessionDep) -> LinkListOut:
    return _links(a, scope, s)


@router.post(
    "/ip-links",
    status_code=201,
    response_model=LinkOut,
    summary="Tạo liên kết IP (chưa xác nhận cặp) — chỉ admin",
    responses=errors(409, 422),
)
def create_link(
    body: LinkCreateIn, admin: AdminDep, a: AnalysisDep, scope: ScopeDep, s: SessionDep, cache: CacheDep
) -> LinkOut:
    link = svc.create_link(s, admin.username, body.inventory_ip, body.vtnet_ip, body.reason)
    return _one(link.inventory_ip, a, scope, s, cache)


@router.patch(
    "/ip-links/{inventory_ip}",
    response_model=LinkOut,
    summary="Sửa cặp / xác nhận cặp / lý do — chỉ admin (đổi IP VTNet → phải xác nhận lại)",
    responses=errors(404, 409, 422),
)
def update_link(
    inventory_ip: str,
    body: LinkUpdateIn,
    admin: AdminDep,
    a: AnalysisDep,
    scope: ScopeDep,
    s: SessionDep,
    cache: CacheDep,
) -> LinkOut:
    link = svc.update_link(s, admin.username, inventory_ip, body.model_dump(exclude_unset=True))
    return _one(link.inventory_ip, a, scope, s, cache)


@router.delete("/ip-links/{inventory_ip}", status_code=204, summary="Xóa liên kết — chỉ admin", responses=errors(404))
def delete_link(inventory_ip: str, admin: AdminDep, s: SessionDep) -> Response:
    svc.delete_link(s, admin.username, inventory_ip)
    return Response(status_code=204)


def _one(inventory_ip: str, a: AnalysisDep, scope: ScopeDep, s: SessionDep, cache: CacheDep) -> LinkOut:
    """Dòng liên kết sau khi đổi: data_version đã đổi → bundle tính lại với liên kết mới (cùng khoảng ngày)."""
    b = get_bundle(s, cache, a.bundle.ctx)
    row = next(r for r in svc.link_rows(b, Scope.all()) if r["inventory_ip"] == inventory_ip)
    return LinkOut(**row, **svc.link_details(s).get(inventory_ip, {}))
