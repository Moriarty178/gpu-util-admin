"""Schema I/O báo cáo tháng (Roadmap §14.2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
MAX_MESSAGE, MAX_REC_TITLE, MAX_REC_DETAIL = 220, 60, 150  # vừa khung slide bìa/kết (đã đo khi dựng)


class ZoneCount(BaseModel):
    danger: int
    warning: int
    safe: int


class ReportKpi(BaseModel):
    gpu_avg: float | None
    mem_avg: float | None
    n_servers: int
    n_mapped: int
    n_unmapped: int
    cards: int
    zones: ZoneCount
    cards_total: ZoneCount
    patterns: dict[str, int]
    vtnet_low_load: int
    thin_data: int


class ReportMonth(BaseModel):
    month: str
    n_servers: int
    zones: ZoneCount
    cards: ZoneCount
    gpu_avg: float | None
    mem_avg: float | None


class ReportPrevious(BaseModel):
    month: str
    gpu_avg: float | None
    mem_avg: float | None
    n_servers: int
    zones: ZoneCount
    cards_total: ZoneCount


class ReportMovement(BaseModel):
    counts: dict[str, int]
    matrix: dict[str, dict[str, int]]


class ReportOwners(BaseModel):
    owners: list[str]
    rows: dict[str, dict[str, int]]
    totals: dict[str, int]
    mapped_total: int


class ReportDangerRow(BaseModel):
    ip: str
    owner: str | None
    service: str | None
    gpu_model: str | None
    cards: int | None
    gpu_avg: float | None
    mem_avg: float | None
    pattern: str | None
    vtnet_low_load: bool
    mapped: bool
    streak_months: int = Field(description="Số tháng liên tiếp (tính đến tháng báo cáo) server ở vùng Nguy hiểm")
    streak_open: bool = Field(description="Chuỗi chạm tháng sớm nhất đang xét — có thể dài hơn (hiển thị '≥')")


class Recommendation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=MAX_REC_TITLE)
    detail: str = Field("", max_length=MAX_REC_DETAIL)


class ReportSuggestion(BaseModel):
    message: str
    recommendations: list[Recommendation]


class MonthlyReportOut(BaseModel):
    month: str
    label: str
    start: str
    end: str
    threshold: float
    vtnet_t: float
    scope_owner: str | None
    available_months: list[str]
    kpi: ReportKpi
    trend: list[ReportMonth]
    previous: ReportPrevious | None
    movement: ReportMovement | None
    owners: ReportOwners
    danger: list[ReportDangerRow]
    suggestion: ReportSuggestion


class MonthlyReportIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    month: str | None = Field(None, pattern=MONTH_PATTERN, description="YYYY-MM; mặc định = tháng mới nhất")
    threshold: float | None = Field(None, ge=0, le=100)
    message: str | None = Field(None, max_length=MAX_MESSAGE, description="Trống = thông điệp gợi ý")
    recommendations: list[Recommendation] | None = Field(None, max_length=3, description="Trống = kiến nghị gợi ý")
