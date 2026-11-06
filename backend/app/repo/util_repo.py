"""Mẫu tải VTNet: ghi theo lô, đọc giá trị hiệu lực từ VIEW util_effective. Chỉ lọc/lấy — không tính toán."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import String, func, insert, select, type_coerce
from sqlalchemy.orm import Session

from app.db.models import ImportBatch, UtilSample, VtnetOverview, VtnetReclaim
from app.db.views import util_effective
from app.repo.convert import frame, py

EFFECTIVE_COLUMNS = ["ip", "ts", "gpu", "mem", "gpu_type", "batch_id"]


def insert_samples(s: Session, batch_id: int, raw: pd.DataFrame) -> int:
    rows = [
        {
            "batch_id": batch_id,
            "ip": r.ip,
            "ts": py(r.ts),
            "gpu": float(r.gpu),
            "mem": float(r.mem),
            "gpu_type": py(r.gpu_type),
            "don_vi": py(r.don_vi),
        }
        for r in raw.itertuples(index=False)
    ]
    if rows:
        s.execute(insert(UtilSample), rows)
    return len(rows)


def insert_overview(s: Session, batch_id: int, overview: pd.DataFrame) -> int:
    rows = [
        {"batch_id": batch_id, "ip": r.ip, "gpu": py(r.gpu), "mem": py(r.mem)}
        for r in overview.drop_duplicates("ip", keep="last").itertuples(index=False)
    ]
    if rows:
        s.execute(insert(VtnetOverview), rows)
    return len(rows)


def insert_reclaim(s: Session, batch_id: int, reclaimed: pd.DataFrame) -> int:
    cols = ["gpu_type", "beneficiary", "owner_dcim", "service_manager", "status"]
    rows: list[dict[str, Any]] = [
        {"batch_id": batch_id, "ip": r["ip"], **{c: py(r.get(c)) for c in cols}}
        for r in reclaimed.drop_duplicates("ip", keep="last").to_dict("records")
    ]
    if rows:
        s.execute(insert(VtnetReclaim), rows)
    return len(rows)


def data_days(s: Session) -> list[date]:
    """Các ngày có ít nhất 1 mẫu tải hiệu lực (hợp các lô VTNet committed — ngày của util_effective), tăng dần."""
    stmt = (
        select(UtilSample.ts)
        .join(ImportBatch, ImportBatch.id == UtilSample.batch_id)
        .where(ImportBatch.kind == "vtnet_util", ImportBatch.status == "committed")
        .distinct()
    )
    return sorted({(t.date() if isinstance(t, datetime) else t) for t in s.scalars(stmt)})


def batch_ips(s: Session, batch_id: int) -> set[str]:
    return set(s.scalars(select(UtilSample.ip).where(UtilSample.batch_id == batch_id).distinct()))


def effective_frame(
    s: Session,
    start: date | datetime | None = None,
    end: date | datetime | None = None,
    ips: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Mẫu hiệu lực trong [start, end] — `end` tính trọn ngày; bỏ trống = toàn bộ."""
    # ts lấy nguyên giá trị driver (SQLite: chuỗi ISO) rồi đổi cả cột 1 lần — nhanh hơn nhiều so với đổi từng dòng
    cols = [
        type_coerce(util_effective.c.ts, String).label("ts") if c == "ts" else util_effective.c[c]
        for c in EFFECTIVE_COLUMNS
    ]
    stmt = select(*cols)
    if start is not None:
        stmt = stmt.where(util_effective.c.ts >= datetime(start.year, start.month, start.day))
    if end is not None:
        stmt = stmt.where(util_effective.c.ts < datetime(end.year, end.month, end.day) + timedelta(days=1))
    if ips is not None:
        stmt = stmt.where(util_effective.c.ip.in_(sorted(set(ips))))
    df = frame(s, stmt, EFFECTIVE_COLUMNS)
    df["ts"] = pd.to_datetime(df["ts"], format="ISO8601")
    return df


def data_range(s: Session) -> tuple[date | None, date | None]:
    """Khoảng ngày có số liệu = hợp kỳ các lô VTNet committed (kỳ lô = min/max ts của file, nên trùng với
    min/max ngày của util_effective) — không phải quét cả view."""
    stmt = select(func.min(ImportBatch.period_start), func.max(ImportBatch.period_end)).where(
        ImportBatch.kind == "vtnet_util", ImportBatch.status == "committed"
    )
    row = s.execute(stmt).one()
    return row[0], row[1]


def distinct_gpu_types(s: Session) -> list[str]:
    return sorted(v for v in s.scalars(select(util_effective.c.gpu_type).distinct()) if v)


def has_samples(s: Session, ip: str) -> bool:
    """IP có ít nhất 1 mẫu hiệu lực (lô VTNet committed)."""
    return s.scalar(select(util_effective.c.ip).where(util_effective.c.ip == ip).limit(1)) is not None
