from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

import gpu_core as g
from app.db.models import InventoryItem, InventoryOverride, IpLink
from app.db.views import inventory_current, reclaim_current
from app.repo.convert import frame, py

INVENTORY_FIELDS = [c.name for c in inventory_current.columns if c.name not in ("batch_id", "extra")]
RECLAIM_FIELDS = [c.name for c in reclaim_current.columns]
LINK_FIELDS = ["inventory_ip", "vtnet_ip", "pair_confirmed", "reason"]
# Cột admin sửa tay được (PLAN §14.11) — cùng tên cột với inventory_current
EDITABLE_FIELDS = ["owner", "model", "input_load", "service", "managed_by", "cluster"]
# Cột phần cứng chỉ dùng cho server bổ sung trên web (VTNet-only, PLAN §14.12) — đủ cột như file thống kê (trừ STT)
MANUAL_FIELDS = ["server_class", "config", "cpu", "ram", "disk", "hba", "gpu_spec", "serial"]
OVERRIDE_FIELDS = [
    "inventory_ip", *EDITABLE_FIELDS, "reclaim_status", "is_manual", *MANUAL_FIELDS, "updated_by", "updated_at",
]  # fmt: skip


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


def overrides_frame(s: Session) -> pd.DataFrame:
    """Giá trị admin sửa tay (mỗi IP thống kê 1 dòng; NULL = theo file)."""
    stmt = select(*[InventoryOverride.__table__.c[c] for c in OVERRIDE_FIELDS]).order_by(InventoryOverride.inventory_ip)
    return frame(s, stmt, OVERRIDE_FIELDS)


def get_override(s: Session, inventory_ip: str) -> InventoryOverride | None:
    return s.get(InventoryOverride, inventory_ip)


def current_row(s: Session, inventory_ip: str) -> dict[str, Any] | None:
    """1 dòng thống kê hiện hành (giá trị theo file, chưa đè sửa tay)."""
    stmt = select(*[inventory_current.c[c] for c in INVENTORY_FIELDS]).where(inventory_current.c.ip == inventory_ip)
    row = s.execute(stmt).mappings().first()
    return dict(row) if row is not None else None


def apply_overrides(inv: pd.DataFrame, ov: pd.DataFrame) -> pd.DataFrame:
    """Đè giá trị sửa tay lên snapshot thống kê (khóa = IP thống kê). Thêm cột:
    `reclaim_status` ('in_use' mặc định | 'reclaimed') và `edited` (cột → giá trị theo file, chỉ các ô sửa tay KHÁC file).
    Chỉ ghép dữ liệu hiển thị — không phải phép tính nghiệp vụ. IP không còn trong file thống kê hiện hành → sửa tay
    "ngủ" (giữ trong CSDL, hiện lại nếu IP quay lại)."""
    out = inv.copy()
    by_ip = {r["inventory_ip"]: r for r in ov.to_dict("records")} if not ov.empty else {}
    status: list[str] = []
    edited: list[dict[str, Any]] = []
    values: dict[str, list[Any]] = {c: list(out[c]) if c in out.columns else [None] * len(out) for c in EDITABLE_FIELDS}
    for i, ip in enumerate(out["ip"]):
        r = by_ip.get(ip)
        status.append((r or {}).get("reclaim_status") or "in_use")
        diff: dict[str, Any] = {}
        if r is not None:
            for c in EDITABLE_FIELDS:
                if r[c] is None:
                    continue  # theo file
                file_v = py(values[c][i])
                new_v = r[c] or None  # '' = để trống
                if new_v != file_v:
                    diff[c] = file_v
                values[c][i] = new_v
        edited.append(diff)
    for c in EDITABLE_FIELDS:
        out[c] = pd.Series(values[c], index=out.index, dtype=object)
    out["reclaim_status"] = pd.Series(status, index=out.index, dtype=object)
    out["edited"] = pd.Series(edited, index=out.index, dtype=object)
    return out


def manual_rows(inv: pd.DataFrame, ov: pd.DataFrame, link_targets: set[str]) -> pd.DataFrame:
    """Server bổ sung trên web (is_manual) thành dòng thống kê: khóa = IP VTNet, không STT / dòng Excel. Bỏ qua (ngủ) khi
    file thống kê đã có IP đó (khi ấy 6 cột sửa tay đè lên dòng file như sửa tay thường) hoặc IP đã là đích của 1 liên kết."""
    cols = [*INVENTORY_FIELDS, "reclaim_status", "edited", "manual"]
    if ov.empty:
        return pd.DataFrame(columns=cols)
    have = set(inv["ip"])
    rows: list[dict[str, Any]] = []
    for r in ov.to_dict("records"):
        ip = r["inventory_ip"]
        if not r["is_manual"] or ip in have or ip in link_targets:
            continue
        count, model = g.parse_gpu_spec(r["gpu_spec"])  # cùng cách đọc cột GPU với file thống kê
        row: dict[str, Any] = {c: None for c in INVENTORY_FIELDS}
        row.update({c: r[c] or None for c in (*EDITABLE_FIELDS, *MANUAL_FIELDS)})
        row.update(ip=ip, gpu_count=count, gpu_model=model, reclaim_status=r["reclaim_status"] or "in_use", edited={},
                   manual=True)  # fmt: skip
        rows.append(row)
    return pd.DataFrame(rows, columns=cols)


def effective_frame(s: Session) -> pd.DataFrame:
    """Snapshot thống kê hiện hành + sửa tay + server bổ sung trên web (nguồn cho phân tích, danh mục, bộ lọc)."""
    inv, ov = current_frame(s), overrides_frame(s)
    out = apply_overrides(inv, ov)
    out["manual"] = False
    extra = manual_rows(inv, ov, set(links_frame(s)["vtnet_ip"]))
    if extra.empty:
        return out
    extra["gpu_count"] = extra["gpu_count"].astype("Int64")
    merged = pd.concat([out, extra.astype({c: object for c in extra.columns if c != "gpu_count"})], ignore_index=True)
    merged["gpu_count"] = merged["gpu_count"].astype("Int64")
    return merged


def manual_ips(s: Session) -> set[str]:
    return set(s.scalars(select(InventoryOverride.inventory_ip).where(InventoryOverride.is_manual.is_(True))))


def distinct_values(s: Session, column: str) -> list[str]:
    if column in EDITABLE_FIELDS:  # theo giá trị sau sửa tay (vd đầu mối mới / đầu mối cũ đã hết server)
        values = set(effective_frame(s)[column])
    else:
        values = set(s.scalars(select(inventory_current.c[column]).distinct()))
    return sorted(v for v in values if isinstance(v, str) and v)
