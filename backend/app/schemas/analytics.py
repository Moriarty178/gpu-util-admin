"""Schema I/O API phân tích (PLAN §7). Số liệu % trả nguyên giá trị (UI tự làm tròn 1 chữ số, định dạng vi-VN)."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

Zone = Literal["danger", "warning", "safe"]
Pattern = Literal["idle", "bursty_idle", "memory_bound", "compute_bound", "high_load", "healthy"]


class AnalyticsParams(BaseModel):
    start: dt.date
    end: dt.date = Field(description="Tính trọn ngày")
    threshold: float = Field(description="Ngưỡng T (%)")
    zone_metric: Literal["both", "gpu", "mem"] = Field(
        "both", description="Áp T cho: both = cả 2 chỉ số (3 vùng) · gpu / mem = chỉ 1 chỉ số (Nguy hiểm / An toàn)"
    )
    days_in_range: int
    clamped: bool = Field(False, description="Khoảng yêu cầu vượt ra ngoài ngày có dữ liệu → đã cắt về [start, end]")
    requested_start: dt.date | None = Field(None, description="Khoảng người dùng chọn (chỉ có khi clamped)")
    requested_end: dt.date | None = None


class ZoneMatrix(BaseModel):
    owners: list[str] = Field(description="Đầu mối + '_unmapped' (server VTNet chưa có trong thống kê)")
    rows: dict[str, dict[str, int]] = Field(description="vùng → đầu mối → số server")
    totals: dict[str, int] = Field(description="Số server mỗi vùng (mọi server trong phạm vi lọc)")
    mapped_total: int


class ServerItem(BaseModel):
    ip: str = Field(description="IP phía VTNet")
    inventory_ip: str | None = Field(None, description="IP trong file thống kê (khác ip nếu có liên kết)")
    owner: str | None = None
    service: str | None = None
    model: str | None = None
    cluster: str | None = None
    managed_by: str | None = None
    gpu_type: str | None = Field(None, description="Nguyên văn VTNet, vd '4×NVIDIA L40S'")
    gpu_count: int | None = Field(None, description="Theo VTNet; thiếu thì theo thống kê")
    gpu_model: str | None = None
    inventory_gpu_spec: str | None = None
    gpu_avg: float | None = None
    mem_avg: float | None = None
    gpu_peak: float | None = None
    gpu_p95: float | None = None
    mem_peak: float | None = None
    days: int | None = None
    coverage: float | None = None
    low_streak: int | None = None
    danger_days: int | None = None
    zone: Zone | None = None
    pattern: Pattern | None = None
    vtnet_low_load: bool | None = None
    thin_data: bool | None = None
    assessment: str | None = None
    reclaimed: bool = False
    mapped: bool = False
    ip_linked: bool = False
    pair_confirmed: bool | None = None
    gpu_count_mismatch: bool = False
    cards: int | None = None
    notes_count: int = Field(0, description="Số ghi chú / giải trình đang hiệu lực (G2-M3)")
    exempt_until: dt.date | None = Field(None, description="Đang miễn trừ tới ngày (không đổi vùng)")


class AlertsSummary(BaseModel):
    zones: dict[str, int]
    patterns: dict[str, int]
    cards: int
    vtnet_low_load: int
    thin_data: int
    exempt: int = Field(0, description="Số dòng đang miễn trừ (trước khi ẩn)")


class AlertsOut(BaseModel):
    params: AnalyticsParams
    matrix: ZoneMatrix
    pattern_counts: dict[str, int]
    cards_by_zone: dict[str, dict[str, int]] = Field(description="vùng → model GPU → số card")
    summary: AlertsSummary = Field(description="Tóm tắt các dòng sau khi lọc vùng/mẫu hình/cờ")
    total: int
    page: int
    page_size: int
    items: list[ServerItem]


class FleetPoint(BaseModel):
    date: dt.date = Field(description="Ngày (hoặc ngày đầu tuần/tháng)")
    gpu: float
    mem: float
    n_servers: int
    n_days: int


class Avg(BaseModel):
    gpu: float | None
    mem: float | None


class FleetTimeseriesOut(BaseModel):
    params: AnalyticsParams
    granularity: Literal["day", "week", "month"]
    weight: Literal["server", "gpu"]
    points: list[FleetPoint]
    avg: Avg = Field(description="TB toàn khoảng = mean chuỗi ngày (PLAN §6)")
    n_servers: int


class FleetSummaryOut(BaseModel):
    params: AnalyticsParams
    gpu_avg: float | None
    mem_avg: float | None
    n_servers: int
    n_mapped: int
    n_unmapped: int
    zones: dict[str, int]
    patterns: dict[str, int]
    vtnet_low_load: int
    thin_data: int
    cards_by_zone: dict[str, dict[str, int]]
    cards_total: dict[str, int]
    matrix: ZoneMatrix


DataStatus = Literal["has_data", "reclaimed", "no_data", "vtnet_only"]


class CatalogItem(BaseModel):
    row_type: Literal["inventory", "vtnet_only"]
    data_status: DataStatus
    inventory_ip: str | None = None
    ip: str
    ip_linked: bool = False
    pair_confirmed: bool | None = None
    stt: str | None = None
    excel_row: int | None = None
    owner: str | None = None
    inventory_gpu_spec: str | None = None
    gpu_type: str | None = None
    gpu_count: int | None = None
    gpu_model: str | None = None
    gpu_count_mismatch: bool = False
    model: str | None = None
    service: str | None = None
    input_load: str | None = None
    managed_by: str | None = None
    cluster: str | None = None
    zone: Zone | None = None
    pattern: Pattern | None = None
    gpu_avg: float | None = None
    mem_avg: float | None = None
    days: int | None = None
    coverage: float | None = None
    vtnet_low_load: bool | None = None
    reclaimed: bool = False
    reclaim_status: Literal["in_use", "reclaimed"] | None = Field(
        None, description="Trạng thái thu hồi (admin đặt; mặc định in_use = Đang sử dụng). VTNet-only: null"
    )
    edited: dict[str, str | None] | None = Field(None, description="Ô admin sửa tay khác file: cột → giá trị theo file")
    manual: bool = Field(
        False, description="Server bổ sung trên web (VTNet có log, file thống kê chưa có) — PLAN §14.12"
    )


class CatalogCounts(BaseModel):
    inventory_rows: int
    has_data: int
    reclaimed: int
    no_data: int
    vtnet_only: int
    linked: int
    gpu_count_mismatch: int
    reclaim_marked: int = Field(0, description="Số dòng admin đánh dấu 'VTNet đã thu hồi'")
    edited: int = Field(0, description="Số dòng có ô sửa tay khác file")
    manual: int = Field(0, description="Số server bổ sung trên web (file thống kê chưa có)")


class CatalogOut(BaseModel):
    params: AnalyticsParams
    counts: CatalogCounts
    items: list[CatalogItem]


class ServerDetailOut(BaseModel):
    params: AnalyticsParams
    ip: str
    inventory_ip: str | None
    data_status: DataStatus
    inventory: dict[str, Any] | None
    link: dict[str, Any] | None
    reclaim: dict[str, Any] | None
    stats: ServerItem | None


class ServerPoint(BaseModel):
    date: dt.date
    gpu: float
    mem: float
    zone: Zone
    vtnet_low_load: bool
    n_days: int


class ServerTimeseriesOut(BaseModel):
    params: AnalyticsParams
    ip: str
    granularity: Literal["day", "week", "month"]
    points: list[ServerPoint]


class Period(BaseModel):
    batch_id: int
    label: str | None
    start: dt.date | None
    end: dt.date | None
    file_name: str
    committed_at: dt.datetime | None


class DateRange(BaseModel):
    start: dt.date | None
    end: dt.date | None


class InventoryRef(BaseModel):
    batch_id: int
    file_name: str
    committed_at: dt.datetime | None


class MetaOut(BaseModel):
    gpu_core: str
    data_range: DateRange
    default_range: DateRange | None = Field(description="Kỳ file VTNet mới nhất ('Theo kỳ file VTNet')")
    periods: list[Period]
    inventory: InventoryRef | None
    owners: list[str]
    gpu_models: list[str]
    clusters: list[str]
    managed_by: list[str]
    settings: dict[str, Any]
