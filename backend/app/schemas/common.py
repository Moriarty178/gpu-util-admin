from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class Problem(BaseModel):
    """Định dạng lỗi chung của API: {type, title, detail} — chuỗi hiển thị tiếng Việt."""

    type: str
    title: str
    detail: Any = None


class HealthOut(BaseModel):
    db: Literal["ok"]
    gpu_core: str
