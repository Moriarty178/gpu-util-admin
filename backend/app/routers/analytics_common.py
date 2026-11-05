"""Tham số chung của API phân tích (PLAN §7): start, end, threshold, zone_metric, owner, gpu_model, cluster, managed_by (lặp được), q."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query, Request

from app.deps import SessionDep
from app.schemas.common import Problem
from app.services.analytics_service import AnalyticsCache, Bundle, Filters, ZoneMetric, get_bundle, resolve_context


def get_cache(request: Request) -> AnalyticsCache:
    cache: AnalyticsCache = request.app.state.analytics_cache
    return cache


@dataclass
class Analysis:
    bundle: Bundle
    filters: Filters


def filters(
    owner: Annotated[list[str] | None, Query(description="Lặp được; '_unmapped' = chưa có trong thống kê")] = None,
    gpu_model: Annotated[list[str] | None, Query()] = None,
    cluster: Annotated[list[str] | None, Query()] = None,
    managed_by: Annotated[list[str] | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100, description="Tìm theo IP / dịch vụ / model / đầu mối")] = None,
) -> Filters:
    return Filters(
        owner=tuple(owner or ()),
        gpu_model=tuple(gpu_model or ()),
        cluster=tuple(cluster or ()),
        managed_by=tuple(managed_by or ()),
        q=q or None,
    )


FiltersDep = Annotated[Filters, Depends(filters)]
CacheDep = Annotated[AnalyticsCache, Depends(get_cache)]
Threshold = Annotated[float | None, Query(ge=0, le=100, description="Ngưỡng T %; mặc định = cài đặt")]
ZoneMetricQ = Annotated[
    ZoneMetric | None,
    Query(description="Áp ngưỡng T cho: both = cả 2 chỉ số (3 vùng) · gpu / mem = chỉ 1 chỉ số (2 vùng: Nguy hiểm / "
          "An toàn); mặc định = cài đặt"),
]  # fmt: skip


def analysis(
    s: SessionDep,
    cache: CacheDep,
    f: FiltersDep,
    start: Annotated[date | None, Query(description="YYYY-MM-DD; mặc định = kỳ file VTNet mới nhất")] = None,
    end: Annotated[date | None, Query(description="YYYY-MM-DD, tính trọn ngày")] = None,
    threshold: Threshold = None,
    zone_metric: ZoneMetricQ = None,
) -> Analysis:
    ctx = resolve_context(s, start, end, threshold, zone_metric)
    return Analysis(bundle=get_bundle(s, cache, ctx), filters=f)


AnalysisDep = Annotated[Analysis, Depends(analysis)]


def errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {c: {"model": Problem} for c in codes}
