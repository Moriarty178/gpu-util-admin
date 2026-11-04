from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.db.models import InventoryItem, IpLink
from app.db.views import inventory_current, reclaim_current
from app.repo.convert import frame

INVENTORY_FIELDS = [c.name for c in inventory_current.columns if c.name not in ("batch_id", "extra")]
RECLAIM_FIELDS = [c.name for c in reclaim_current.columns]
LINK_FIELDS = ["inventory_ip", "vtnet_ip", "pair_confirmed", "reason"]


def insert_items(s: Session, rows: list[dict[str, Any]]) -> int:
    if rows:
        s.execute(insert(InventoryItem), rows)
    return len(rows)


def current_ips(s: Session) -> set[str]:
    return set(s.scalars(select(inventory_current.c.ip)))


def linked_inventory_ips(s: Session) -> set[str]:
    return set(s.scalars(select(IpLink.inventory_ip)))


def current_frame(s: Session) -> pd.DataFrame:
    """Snapshot thống kê hiện hành (lô inventory committed mới nhất)."""
    stmt = select(*[inventory_current.c[c] for c in INVENTORY_FIELDS]).order_by(inventory_current.c.excel_row)
    df = frame(s, stmt, INVENTORY_FIELDS)
    df["gpu_count"] = df["gpu_count"].astype("Int64")
    return df


def links_frame(s: Session) -> pd.DataFrame:
    stmt = select(IpLink.inventory_ip, IpLink.vtnet_ip, IpLink.pair_confirmed, IpLink.reason)
    return frame(s, stmt, LINK_FIELDS)


def reclaim_frame(s: Session) -> pd.DataFrame:
    """Hợp 'DS đã thu' của mọi lô committed (mỗi IP bản mới nhất + kỳ đầu tiên xuất hiện)."""
    stmt = select(*[reclaim_current.c[c] for c in RECLAIM_FIELDS])
    return frame(s, stmt, RECLAIM_FIELDS)


def distinct_values(s: Session, column: str) -> list[str]:
    col = inventory_current.c[column]
    return sorted(v for v in s.scalars(select(col).distinct()) if v)
