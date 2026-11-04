"""/compare (so sánh 2 kỳ) và /trend/zones (xu hướng vùng theo tháng) — G2-M3, PLAN §1.1 B5b/B6, §8.6."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.deps import ScopeDep, SessionDep
from app.routers.analytics_common import CacheDep, FiltersDep, Threshold, errors
from app.schemas.g2 import CompareOut, TrendOut
from app.services import compare_service as svc

router = APIRouter(tags=["compare"])
D = Annotated[date | None, Query()]


@router.get(
    "/compare",
    response_model=CompareOut,
    summary="So sánh 2 kỳ: KPI, ma trận chuyển vùng, danh sách xấu đi / cải thiện / mới / biến mất",
    description="Mặc định A = kỳ file VTNet trước, B = kỳ mới nhất. Cùng ngưỡng T cho 2 kỳ (gpu_core.compare_periods).",
    responses=errors(422),
)
def compare(
    s: SessionDep,
    cache: CacheDep,
    f: FiltersDep,
    scope: ScopeDep,
    a_start: D = None,
    a_end: D = None,
    b_start: D = None,
    b_end: D = None,
    threshold: Threshold = None,
) -> CompareOut:
    out = svc.compare(s, cache, (a_start, a_end), (b_start, b_end), threshold, f, scope)
    return CompareOut.model_validate(out)


@router.get(
    "/trend/zones",
    response_model=TrendOut,
    summary="Số server / số card mỗi vùng theo tháng hoặc tuần (mỗi kỳ tính TB riêng) + TB GPU/VRAM của kỳ",
    description="Mặc định = toàn bộ dữ liệu đã nhập, theo tháng; tối đa 36 tháng / 156 tuần (tuần ISO thứ 2 → CN).",
    responses=errors(422),
)
def trend(
    s: SessionDep, cache: CacheDep, f: FiltersDep, scope: ScopeDep, start: D = None, end: D = None,
    threshold: Threshold = None, granularity: Annotated[Literal["month", "week"], Query()] = "month",
) -> TrendOut:  # fmt: skip
    return TrendOut.model_validate(svc.trend_zones(s, cache, start, end, threshold, f, scope, granularity))
