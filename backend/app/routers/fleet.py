from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.deps import ScopeDep
from app.routers.analytics_common import AnalysisDep, errors
from app.schemas.analytics import FleetSummaryOut, FleetTimeseriesOut
from app.services import analytics_service as svc

router = APIRouter(prefix="/fleet", tags=["fleet"])


@router.get(
    "/timeseries",
    response_model=FleetTimeseriesOut,
    summary="Tải trung bình toàn bộ server theo ngày / tuần / tháng",
    description="weight=server: mean đơn giản qua server có mẫu trong ngày (= sheet VTNet 'HSSD theo ngay VTT'). "
    "weight=gpu: trọng số số card. Tuần/tháng = mean các giá trị ngày trong tuần ISO / tháng.",
    responses=errors(422),
)
def timeseries(
    a: AnalysisDep,
    scope: ScopeDep,
    granularity: Annotated[Literal["day", "week", "month"], Query()] = "day",
    weight: Annotated[Literal["server", "gpu"], Query()] = "server",
) -> FleetTimeseriesOut:
    return FleetTimeseriesOut.model_validate(svc.fleet_timeseries(a.bundle, a.filters, scope, granularity, weight))


@router.get(
    "/summary",
    response_model=FleetSummaryOut,
    summary="KPI: TB GPU/VRAM, số server, số server mỗi vùng, dưới ngưỡng VTNet, card theo vùng, ma trận vùng × đầu mối",
    responses=errors(422),
)
def summary(a: AnalysisDep, scope: ScopeDep) -> FleetSummaryOut:
    return FleetSummaryOut.model_validate(svc.fleet_summary(a.bundle, a.filters, scope))
