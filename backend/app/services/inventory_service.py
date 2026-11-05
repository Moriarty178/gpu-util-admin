"""Sửa tay danh mục server (PLAN §14.11, người dùng chốt 05/11/2026) — chỉ admin.

- Sửa được: Đầu mối, Model, Đầu vào hệ thống, Dịch vụ, Quản lý bằng, Cụm + "Trạng thái thu hồi" (Đang sử dụng / VTNet đã thu
  hồi; mặc định Đang sử dụng). Khóa = IP trong file thống kê; chỉ sửa được IP có trong lô thống kê hiện hành.
- Lưu ở bảng `inventory_override`, đè lên file khi hiển thị — **kể cả sau khi nhập file thống kê mới** (xem trước nhập liệt kê
  các ô file mới khác giá trị đã sửa). Lô nhập, file gốc, mẫu tải giữ nguyên. Giá trị trùng file → không lưu (theo file).
- Chỉ là thông tin: phép tính tải vẫn chỉ theo server có log VTNet trong khoảng xem. Đổi đầu mối → phạm vi xem của tài khoản
  đầu mối đổi theo ngay (`data_version` đổi → phân tích tính lại).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

import gpu_core as g
from app.db.models import InventoryOverride
from app.errors import ServiceError
from app.repo import inventory_repo
from app.repo.convert import py
from app.services.auth_service import audit, utcnow

EDITABLE_FIELDS = inventory_repo.EDITABLE_FIELDS
FIELD_LABEL = {
    "owner": "Đầu mối",
    "model": "Model",
    "input_load": "Đầu vào hệ thống",
    "service": "Dịch vụ",
    "managed_by": "Quản lý bằng",
    "cluster": "Cụm",
}
RECLAIM_LABEL = {"in_use": "Đang sử dụng", "reclaimed": "VTNet đã thu hồi"}
MAX_LEN = {"owner": 64}
DEFAULT_MAX_LEN = 500
MAX_CONFLICTS_SHOWN = 20


def _clean(field: str, value: str) -> str:
    v = g.norm_text(value)
    if field == "owner":
        v = v.casefold()  # cùng chuẩn với file thống kê (gpu_core.read_inventory) và owner_key của tài khoản
    limit = MAX_LEN.get(field, DEFAULT_MAX_LEN)
    if len(v) > limit:
        raise ServiceError(422, f"{FIELD_LABEL[field]}: tối đa {limit} ký tự.")
    return v


def _snapshot(ov: InventoryOverride | None) -> dict[str, Any]:
    keys = [*EDITABLE_FIELDS, "reclaim_status"]
    return {k: getattr(ov, k) if ov is not None else None for k in keys}


def state(s: Session, inventory_ip: str) -> dict[str, Any]:
    """Giá trị hiệu lực 1 server sau sửa tay + giá trị theo file."""
    file_row = inventory_repo.current_row(s, inventory_ip)
    if file_row is None:
        raise ServiceError(404, f"IP {inventory_ip} không có trong file thống kê hiện hành.")
    ov = inventory_repo.get_override(s, inventory_ip)
    ovf = inventory_repo.overrides_frame(s)
    eff = inventory_repo.apply_overrides(pd.DataFrame([file_row]), ovf[ovf["inventory_ip"] == inventory_ip]).iloc[0]
    return {
        "inventory_ip": inventory_ip,
        "values": {c: py(eff[c]) for c in EDITABLE_FIELDS},
        "file_values": {c: py(file_row.get(c)) for c in EDITABLE_FIELDS},
        "edited": eff["edited"],
        "reclaim_status": eff["reclaim_status"],
        "updated_by": ov.updated_by if ov is not None else None,
        "updated_at": ov.updated_at if ov is not None else None,
    }


def update(s: Session, actor: str, inventory_ip: str, changes: dict[str, Any]) -> dict[str, Any]:
    """`changes`: chỉ các khóa cần đổi. Giá trị None = về theo file; '' = để trống; reclaim_status 'in_use'|'reclaimed'."""
    iip = g.norm_ip(inventory_ip)
    file_row = inventory_repo.current_row(s, iip)
    if file_row is None:
        raise ServiceError(
            404, f"IP {iip} không có trong file thống kê hiện hành — chỉ sửa được server có trong danh mục."
        )
    ov = inventory_repo.get_override(s, iip)
    before = _snapshot(ov)
    after = dict(before)
    for c in EDITABLE_FIELDS:
        if c not in changes:
            continue
        v = changes[c]
        if v is None:
            after[c] = None
            continue
        v = _clean(c, str(v))
        after[c] = None if (v or None) == py(file_row.get(c)) else v  # trùng file → không cần lưu
    if "reclaim_status" in changes:
        rs = changes["reclaim_status"]
        if rs not in (None, *RECLAIM_LABEL):
            raise ServiceError(422, f"Trạng thái thu hồi phải là một trong: {', '.join(RECLAIM_LABEL)}.")
        after["reclaim_status"] = None if rs in (None, "in_use") else rs
    if after != before:
        if all(v is None for v in after.values()):
            if ov is not None:
                s.delete(ov)  # hết sửa tay → hoàn toàn theo file
        else:
            if ov is None:
                ov = InventoryOverride(inventory_ip=iip)
                s.add(ov)
            for k, v in after.items():
                setattr(ov, k, v)
            ov.updated_by, ov.updated_at = actor, utcnow()
        changed = {k: {"before": before[k], "after": after[k]} for k in after if after[k] != before[k]}
        audit(s, actor, "inventory_edited", iip, changes=changed)
        s.commit()
    return state(s, iip)


def import_conflicts(s: Session, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Khi nhập file thống kê mới: các ô admin đã sửa tay mà file mới ghi khác → web vẫn giữ giá trị sửa tay."""
    ov = inventory_repo.overrides_frame(s)
    if ov.empty:
        return []
    by_ip = {r["ip"]: r for r in rows}
    out: list[dict[str, Any]] = []
    for o in ov.to_dict("records"):
        r = by_ip.get(o["inventory_ip"])
        if r is None:
            continue
        for c in EDITABLE_FIELDS:
            if o[c] is None:
                continue
            file_v, kept = py(r.get(c)), o[c] or None
            if file_v != kept:
                out.append({"ip": o["inventory_ip"], "field": c, "file": file_v, "kept": kept})
    return out


def conflict_warning(conflicts: list[dict[str, Any]]) -> str:
    parts = [
        f"{x['ip']} {FIELD_LABEL[x['field']]}: file '{x['file'] or '(trống)'}' ≠ sửa tay '{x['kept'] or '(trống)'}'"
        for x in conflicts[:MAX_CONFLICTS_SHOWN]
    ]
    more = f"; … và {len(conflicts) - MAX_CONFLICTS_SHOWN} ô khác" if len(conflicts) > MAX_CONFLICTS_SHOWN else ""
    return (
        f"{len(conflicts)} ô đã sửa tay trên web khác giá trị trong file này — web vẫn giữ giá trị sửa tay "
        f"(Danh mục server → Sửa → 'Về theo file' nếu muốn dùng giá trị file): {'; '.join(parts)}{more}"
    )
