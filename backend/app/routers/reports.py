"""/reports/monthly — báo cáo tháng cho lãnh đạo (Roadmap §14.2): xem số + gợi ý, tải deck .pptx phong cách TT.CN."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.deps import ScopeDep, SessionDep, UserDep
from app.reports import monthly_deck
from app.routers.analytics_common import CacheDep, Threshold, errors
from app.schemas.report import MONTH_PATTERN, MonthlyReportIn, MonthlyReportOut
from app.services import report_service as svc
from app.services.auth_service import audit
from app.services.import_checks import today

router = APIRouter(prefix="/reports", tags=["reports"])
PPTX_MEDIA = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@router.get(
    "/monthly",
    response_model=MonthlyReportOut,
    summary="Số liệu báo cáo tháng: KPI, xu hướng ≤ 6 tháng, so với tháng trước, đầu mối, server Nguy hiểm + gợi ý",
    description="Tháng dương lịch (01 → cuối tháng). Mặc định = tháng có lô VTNet mới nhất. Áp phạm vi người dùng.",
    responses=errors(404, 422),
)
def monthly(
    s: SessionDep,
    cache: CacheDep,
    scope: ScopeDep,
    month: Annotated[str | None, Query(pattern=MONTH_PATTERN, description="YYYY-MM")] = None,
    threshold: Threshold = None,
) -> MonthlyReportOut:
    return MonthlyReportOut.model_validate(svc.monthly(s, cache, month, threshold, scope))


@router.post(
    "/monthly.pptx",
    response_class=Response,
    summary="Tải deck báo cáo tháng (.pptx, 7 slide) — thông điệp / kiến nghị trống = dùng gợi ý",
    responses={200: {"content": {PPTX_MEDIA: {}}}, **errors(404, 422)},
)
def monthly_pptx(body: MonthlyReportIn, s: SessionDep, cache: CacheDep, scope: ScopeDep, user: UserDep) -> Response:
    data = svc.monthly(s, cache, body.month, body.threshold, scope)
    sug = data["suggestion"]
    message = body.message or sug["message"]
    recs = (
        [(r.title, r.detail) for r in body.recommendations]
        if body.recommendations
        else [(r["title"], r["detail"]) for r in sug["recommendations"]]
    )
    content = monthly_deck.build(data, message, recs, today())
    audit(s, user.username, "report_exported", data["month"], threshold=data["threshold"],
          scope_owner=data["scope_owner"], edited=bool(body.message or body.recommendations))  # fmt: skip
    s.commit()
    name = f"Bao_cao_GPU_thang_{int(data['month'][5:7])}_{data['month'][:4]}.pptx"
    disposition = f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"
    return Response(content=content, media_type=PPTX_MEDIA, headers={"Content-Disposition": disposition})
