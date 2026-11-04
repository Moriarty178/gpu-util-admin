from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.deps import ScopeDep, SessionDep, UserDep
from app.errors import AuthError
from app.routers.analytics_common import AnalysisDep, errors
from app.schemas.analytics import CatalogOut, ServerDetailOut, ServerTimeseriesOut
from app.schemas.g2 import MultiSeriesOut, NoteIn, NoteListOut, NoteOut
from app.scope import CurrentUser
from app.services import analytics_service as svc
from app.services import compare_service, note_service
from app.services.note_service import KIND_VI, ServerNote

router = APIRouter(prefix="/servers", tags=["servers"])


@router.get(
    "",
    response_model=CatalogOut,
    summary="Danh mục server: thống kê hiện hành ⟕ chỉ số tải trong khoảng + nhóm 'VTNet có – thống kê thiếu'",
    responses=errors(422),
)
def catalog(
    a: AnalysisDep, scope: ScopeDep, sort: Annotated[str | None, Query(description="vd 'owner,-gpu_avg'")] = None
) -> CatalogOut:
    return CatalogOut.model_validate(svc.catalog(a.bundle, a.filters, scope, sort))


@router.get(
    "/timeseries",
    response_model=MultiSeriesOut,
    summary="So sánh tối đa 5 server: chuỗi tải từng server cùng khoảng ngày",
    responses=errors(404, 422),
)
def multi_timeseries(
    a: AnalysisDep,
    scope: ScopeDep,
    ips: Annotated[list[str], Query(description="Lặp được, 1–5 IP (IP VTNet hoặc IP thống kê)")],
    granularity: Annotated[Literal["day", "week", "month"], Query()] = "day",
) -> MultiSeriesOut:
    return MultiSeriesOut.model_validate(compare_service.servers_timeseries(a.bundle, ips, scope, granularity))


@router.get(
    "/{ip}",
    response_model=ServerDetailOut,
    summary="Chi tiết 1 server (IP VTNet hoặc IP trong thống kê): thống kê, liên kết IP, thu hồi, chỉ số, nhận xét",
    responses=errors(404, 422),
)
def detail(ip: str, a: AnalysisDep, scope: ScopeDep) -> ServerDetailOut:
    return ServerDetailOut.model_validate(svc.server_detail(a.bundle, ip, scope))


@router.get(
    "/{ip}/timeseries",
    response_model=ServerTimeseriesOut,
    summary="Chuỗi tải 1 server theo ngày / tuần / tháng (kèm vùng theo T)",
    responses=errors(404, 422),
)
def timeseries(
    ip: str,
    a: AnalysisDep,
    scope: ScopeDep,
    granularity: Annotated[Literal["day", "week", "month"], Query()] = "day",
) -> ServerTimeseriesOut:
    return ServerTimeseriesOut.model_validate(svc.server_timeseries(a.bundle, ip, scope, granularity))


# ------------------------------------------------------------------ ghi chú / giải trình / miễn trừ (G2-M3)


def note_writer(user: UserDep) -> CurrentUser:
    """Viewer chỉ đọc. Admin: mọi loại; đầu mối: giải trình trên server của mình (kiểm ở note_service)."""
    if user.role == "viewer":
        raise AuthError(403, "forbidden", "Tài khoản chỉ xem không thêm / xóa được ghi chú.")
    return user


WriterDep = Annotated[CurrentUser, Depends(note_writer)]


def _server(a: AnalysisDep, ip: str, scope: ScopeDep) -> tuple[str, str | None]:
    """(IP lưu ghi chú = IP phía VTNet, đầu mối của server) — 404 nếu ngoài phạm vi, như trang Server."""
    d = svc.server_detail(a.bundle, ip, scope)
    owner = (d["inventory"] or {}).get("owner") or (d["stats"] or {}).get("owner")
    return str(d["ip"]), owner


def _note_out(n: ServerNote, user: CurrentUser) -> NoteOut:
    today = note_service.today()
    active = n.valid_until is None or n.valid_until >= today
    return NoteOut(
        id=n.id, ip=n.ip, kind=n.kind, kind_label=KIND_VI[n.kind], text=n.text, valid_until=n.valid_until,  # type: ignore[arg-type]
        active=active, created_by=n.created_by, created_at=n.created_at,
        can_delete=user.role == "admin" or (user.role != "viewer" and n.created_by == user.username),
    )  # fmt: skip


@router.get(
    "/{ip}/notes",
    response_model=NoteListOut,
    summary="Ghi chú / giải trình / miễn trừ / hành động của 1 server (mới nhất trước)",
    responses=errors(404),
)
def list_notes(ip: str, a: AnalysisDep, scope: ScopeDep, s: SessionDep, user: UserDep) -> NoteListOut:
    vt_ip, owner = _server(a, ip, scope)
    kinds = [k for k in ("explanation", "note", "action", "exempt") if note_service.can_add(user, k, owner)]
    items = [_note_out(n, user) for n in note_service.list_notes(s, vt_ip)]
    return NoteListOut(ip=vt_ip, can_add=kinds, items=items)  # type: ignore[arg-type]


@router.post(
    "/{ip}/notes",
    status_code=201,
    response_model=NoteOut,
    summary="Thêm ghi chú (admin: mọi loại; đầu mối: giải trình cho server của mình). Miễn trừ cần ngày hết hạn",
    responses=errors(403, 404, 422),
)
def add_note(ip: str, body: NoteIn, user: WriterDep, a: AnalysisDep, scope: ScopeDep, s: SessionDep) -> NoteOut:
    vt_ip, owner = _server(a, ip, scope)
    n = note_service.add_note(s, user, vt_ip, owner, body.kind, body.text, body.valid_until)
    return _note_out(n, user)


@router.delete(
    "/{ip}/notes/{note_id}",
    status_code=204,
    summary="Xóa (mềm) ghi chú — admin, hoặc người viết",
    responses=errors(403, 404),
)
def delete_note(ip: str, note_id: int, user: WriterDep, a: AnalysisDep, scope: ScopeDep, s: SessionDep) -> Response:
    vt_ip, _owner = _server(a, ip, scope)
    note_service.delete_note(s, user, vt_ip, note_id)
    return Response(status_code=204)
