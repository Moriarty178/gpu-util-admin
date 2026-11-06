"""Schema I/O G2-M3: đối soát, liên kết IP, so sánh kỳ, xu hướng vùng, so sánh server, ghi chú."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analytics import AnalyticsParams, Zone

Movement = Literal["worsened", "improved", "same", "new", "gone"]
NoteKind = Literal["note", "explanation", "exempt", "action"]


# ------------------------------------------------------------------ đối soát


class VtnetOnlyRow(BaseModel):
    ip: str
    gpu_type: str | None = None
    gpu_count: int | None = None
    gpu_model: str | None = None
    zone: Zone | None = None
    pattern: str | None = None
    gpu_avg: float | None = None
    mem_avg: float | None = None
    days: int | None = None
    vtnet_low_load: bool | None = None


class InventoryGapRow(BaseModel):
    inventory_ip: str
    ip: str
    owner: str | None = None
    service: str | None = None
    model: str | None = None
    cluster: str | None = None
    inventory_gpu_spec: str | None = None
    gpu_count: int | None = None
    gpu_model: str | None = None
    data_status: str
    excel_row: int | None = None


class MismatchRow(BaseModel):
    inventory_ip: str
    ip: str
    owner: str | None = None
    service: str | None = None
    inventory_gpu_spec: str | None = None
    gpu_type: str | None = None
    gpu_count: int | None = None
    gpu_model: str | None = None
    zone: Zone | None = None
    ip_linked: bool = False


class LinkPair(BaseModel):
    inventory_ip: str
    vtnet_ip: str


class Suggestion(BaseModel):
    gpu_count: int
    gpu_model: str
    vtnet_ips: list[str]
    inventory_ips: list[str]
    pairs: list[LinkPair] = Field(
        description="Đề xuất ghép theo IP tăng dần khi 2 bên cùng số máy; rỗng = admin tự chọn"
    )


class GapCounts(BaseModel):
    vtnet_only: int
    no_data: int
    reclaimed: int
    unknown: int
    gpu_count_mismatch: int
    links: int
    links_unconfirmed: int
    manual: int = Field(0, description="Server VTNet-only đã bổ sung trên web (file thống kê chưa có) — PLAN §14.12")


class GapsOut(BaseModel):
    params: AnalyticsParams
    counts: GapCounts
    vtnet_only: list[VtnetOnlyRow]
    reclaimed: list[InventoryGapRow]
    unknown: list[InventoryGapRow]
    gpu_count_mismatch: list[MismatchRow]
    suggestions: list[Suggestion]


# ------------------------------------------------------------------ liên kết IP


class LinkOut(BaseModel):
    inventory_ip: str
    vtnet_ip: str
    pair_confirmed: bool
    reason: str | None = None
    owner: str | None = None
    service: str | None = None
    inventory_gpu_spec: str | None = None
    in_inventory: bool = Field(description="IP thống kê có trong file thống kê hiện hành")
    vtnet_has_data: bool = Field(description="IP VTNet có số liệu trong khoảng đang xem")
    zone: Zone | None = None
    created_by: str | None = None
    created_at: dt.datetime | None = None
    confirmed_by: str | None = None
    confirmed_at: dt.datetime | None = None


class LinkListOut(BaseModel):
    items: list[LinkOut]


class LinkCreateIn(BaseModel):
    inventory_ip: str = Field(max_length=15)
    vtnet_ip: str = Field(max_length=15)
    reason: str | None = Field(default=None, max_length=500)


class LinkUpdateIn(BaseModel):
    inventory_ip: str | None = Field(
        default=None,
        max_length=15,
        description="Đổi IP thống kê của cặp (phải có trong file thống kê; cặp mới chưa xác nhận)",
    )
    vtnet_ip: str | None = Field(default=None, max_length=15)
    pair_confirmed: bool | None = None
    reason: str | None = Field(default=None, max_length=500)


# ------------------------------------------------------------------ so sánh kỳ / xu hướng / so sánh server


class PeriodKpi(BaseModel):
    params: AnalyticsParams
    gpu_avg: float | None
    mem_avg: float | None
    n_servers: int
    zones: dict[str, int]
    cards_total: dict[str, int]


class CompareItem(BaseModel):
    ip: str
    inventory_ip: str | None = None
    owner: str | None = None
    service: str | None = None
    model: str | None = None
    gpu_type: str | None = None
    gpu_model: str | None = None
    cards: int | None = None
    mapped: bool | None = None
    zone_prev: Zone | None = None
    zone_cur: Zone | None = None
    gpu_avg_prev: float | None = None
    gpu_avg_cur: float | None = None
    mem_avg_prev: float | None = None
    mem_avg_cur: float | None = None
    d_gpu: float | None = None
    d_mem: float | None = None
    movement: Movement


class CompareOut(BaseModel):
    a: PeriodKpi = Field(description="Kỳ A (trước)")
    b: PeriodKpi = Field(description="Kỳ B (sau)")
    threshold: float
    zone_metric: Literal["both", "gpu", "mem"] = "both"
    counts: dict[str, int] = Field(description="worsened / improved / same / new / gone")
    matrix: dict[str, dict[str, int]] = Field(description="vùng kỳ A (+new) → vùng kỳ B (+gone) → số server")
    items: list[CompareItem]


class TrendMonth(BaseModel):
    period: str = Field(description="YYYY-MM (theo tháng) hoặc YYYY-Www (tuần ISO, thứ 2 → CN)")
    month: str | None = Field(None, description="YYYY-MM — chỉ có khi granularity=month")
    start: dt.date
    end: dt.date
    n_days: int = Field(description="Số ngày của kỳ (kỳ đầu/cuối cắt theo ngày có dữ liệu)")
    n_servers: int
    zones: dict[str, int]
    cards: dict[str, int]
    gpu_avg: float | None
    mem_avg: float | None


class TrendOut(BaseModel):
    threshold: float | None
    zone_metric: Literal["both", "gpu", "mem"] | None = None
    granularity: Literal["month", "week"] = "month"
    months: list[TrendMonth] = Field(description="Các kỳ (tháng hoặc tuần theo `granularity`), cũ → mới")


class SeriesPoint(BaseModel):
    date: dt.date
    gpu: float
    mem: float
    zone: Zone
    vtnet_low_load: bool
    n_days: int


class ServerSeries(BaseModel):
    ip: str
    inventory_ip: str | None = None
    owner: str | None = None
    service: str | None = None
    gpu_type: str | None = None
    zone: Zone | None = None
    gpu_avg: float | None = None
    mem_avg: float | None = None
    points: list[SeriesPoint]


class MultiSeriesOut(BaseModel):
    params: AnalyticsParams
    granularity: Literal["day", "week", "month"]
    series: list[ServerSeries]


# ------------------------------------------------------------------ ghi chú


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ip: str
    kind: NoteKind
    kind_label: str
    text: str
    valid_until: dt.date | None
    active: bool = Field(description="Miễn trừ / hành động còn hạn (hoặc ghi chú không có hạn)")
    created_by: str
    created_at: dt.datetime
    can_delete: bool


class NoteListOut(BaseModel):
    ip: str
    can_add: list[NoteKind] = Field(description="Loại ghi chú tài khoản hiện tại được thêm cho server này")
    items: list[NoteOut]


class NoteIn(BaseModel):
    kind: NoteKind
    text: str = Field(min_length=1, max_length=2000)
    valid_until: dt.date | None = None
