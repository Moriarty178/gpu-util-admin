from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.deps import ScopeDep, SessionDep
from app.routers.analytics_common import AnalysisDep, errors
from app.schemas.analytics import AlertsOut, Pattern, Zone
from app.services import analytics_service as svc
from app.services import note_service
from app.services.export_service import export_assessed

router = APIRouter(prefix="/alerts", tags=["alerts"])
XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "",
    response_model=AlertsOut,
    summary="Bảng cảnh báo theo ngưỡng T + ma trận vùng × đầu mối + mẫu hình + card theo vùng",
    description="Luật vùng (gpu_core): gpu<=T và mem<=T → Nguy hiểm; đúng 1 trong 2 <=T → Cảnh báo; cả 2 >T → An toàn. "
    "`zones` để trống = mọi vùng (giao diện mặc định lọc Nguy hiểm). "
    "Sắp xếp mặc định: vùng (Nguy hiểm trước), rồi GPU TB tăng dần.",
    responses=errors(422),
)
def alerts(
    a: AnalysisDep,
    scope: ScopeDep,
    s: SessionDep,
    zones: Annotated[list[Zone] | None, Query()] = None,
    patterns: Annotated[list[Pattern] | None, Query()] = None,
    vtnet_flag: Annotated[bool, Query(description="Chỉ server dưới ngưỡng THẤP TẢI VTNet")] = False,
    only_mapped: Annotated[bool, Query(description="Chỉ server có trong thống kê")] = False,
    sort: str = "zone,gpu_avg",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
    hide_exempt: Annotated[bool, Query(description="Ẩn server đang miễn trừ (vùng không đổi)")] = False,
) -> AlertsOut:
    out = svc.alerts(
        a.bundle,
        a.filters,
        scope,
        zones=tuple(zones or ()),
        patterns=tuple(patterns or ()),
        vtnet_flag=vtnet_flag,
        only_mapped=only_mapped,
        sort=sort,
        page=page,
        page_size=page_size,
        notes=note_service.flags(s),
        hide_exempt=hide_exempt,
    )
    return AlertsOut.model_validate(out)


@router.get(
    "/export.xlsx",
    response_class=Response,
    summary="Xuất Excel định dạng skill: file thống kê gốc + cột đánh giá + sheet tổng hợp",
    responses={200: {"content": {XLSX_MEDIA: {}}}, **errors(409, 422)},
)
def export(a: AnalysisDep, scope: ScopeDep, s: SessionDep) -> Response:
    data, name = export_assessed(s, a.bundle, scope)
    disposition = f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"
    return Response(content=data, media_type=XLSX_MEDIA, headers={"Content-Disposition": disposition})
