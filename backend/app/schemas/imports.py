from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.db.models import ImportBatch
from app.services.import_service import KIND_VI, STATUS_VI

BatchKind = Literal["vtnet_util", "inventory"]
BatchStatus = Literal["staged", "committed", "rolled_back", "failed", "discarded"]


class BatchOut(BaseModel):
    """1 lô import. Thời điểm hệ thống là UTC (không timezone)."""

    id: int
    kind: BatchKind
    kind_label: str
    file_name: str
    file_sha256: str
    schema_version: str | None
    status: BatchStatus
    status_label: str
    period_start: date | None
    period_end: date | None
    period_label: str | None
    summary: dict[str, Any] = Field(description="Số dòng, IP, IP mới/biến mất, ngày chồng lấn, số mẫu bị thay…")
    validation: dict[str, Any] = Field(description="Đối soát overview, cảnh báo, sheet bỏ qua, lỗi (nếu failed)")
    uploaded_by: str
    uploaded_at: datetime
    committed_by: str | None
    committed_at: datetime | None
    rolled_back_by: str | None
    rolled_back_at: datetime | None
    note: str | None

    @classmethod
    def from_batch(cls, b: ImportBatch) -> BatchOut:
        return cls(
            id=b.id,
            kind=b.kind,  # type: ignore[arg-type]
            kind_label=KIND_VI[b.kind],
            file_name=b.file_name,
            file_sha256=b.file_sha256,
            schema_version=b.schema_version,
            status=b.status,  # type: ignore[arg-type]
            status_label=STATUS_VI[b.status],
            period_start=b.period_start,
            period_end=b.period_end,
            period_label=b.period_label,
            summary=b.summary or {},
            validation=b.validation or {},
            uploaded_by=b.uploaded_by,
            uploaded_at=b.uploaded_at,
            committed_by=b.committed_by,
            committed_at=b.committed_at,
            rolled_back_by=b.rolled_back_by,
            rolled_back_at=b.rolled_back_at,
            note=b.note,
        )


class BatchListOut(BaseModel):
    items: list[BatchOut]
