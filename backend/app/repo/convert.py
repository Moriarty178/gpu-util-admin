"""Chuyển giá trị pandas/numpy → kiểu Python thuần (để ghi CSDL và JSON)."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Executable
from sqlalchemy.orm import Session


def py(v: Any) -> Any:
    """NaN/NA/NaT → None; numpy số → int/float; Timestamp → datetime."""
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating | float):
        f = float(v)
        return None if math.isnan(f) else f
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def jsonable(obj: Any) -> Any:
    """Đệ quy: dữ liệu an toàn cho cột JSON (SQLite & PostgreSQL JSONB không nhận NaN)."""
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple | set):
        return [jsonable(v) for v in obj]
    v = py(obj)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def frame(s: Session, stmt: Executable, columns: list[str]) -> pd.DataFrame:
    """Chạy câu SELECT (Core) → DataFrame dựng theo CỘT (nhanh hơn ~8 lần so với DataFrame(list[Row]))."""
    rows = s.connection().execute(stmt).all()
    data = dict(zip(columns, map(list, zip(*rows, strict=False)), strict=False)) if rows else {c: [] for c in columns}
    return pd.DataFrame(data, columns=columns)
