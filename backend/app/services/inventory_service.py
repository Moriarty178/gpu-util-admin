"""Sửa tay danh mục server (PLAN §14.11, người dùng chốt 05/11/2026) — chỉ admin.

- Sửa được: Đầu mối, Model, Đầu vào hệ thống, Dịch vụ, Quản lý bằng, Cụm + "Trạng thái thu hồi" (Đang sử dụng / VTNet đã thu
  hồi; mặc định Đang sử dụng). Khóa = IP trong file thống kê; chỉ sửa được IP có trong lô thống kê hiện hành.
- Lưu ở bảng `inventory_override`, đè lên file khi hiển thị — **kể cả sau khi nhập file thống kê mới** (xem trước nhập liệt kê
  các ô file mới khác giá trị đã sửa). Lô nhập, file gốc, mẫu tải giữ nguyên. Giá trị trùng file → không lưu (theo file).
- Chỉ là thông tin: phép tính tải vẫn chỉ theo server có log VTNet trong khoảng xem. Đổi đầu mối → phạm vi xem của tài khoản
  đầu mối đổi theo ngay (`data_version` đổi → phân tích tính lại).
- **Bổ sung server VTNet-only** (PLAN §14.12, người dùng chốt 06/11/2026, trang Đối soát): server VTNet có log nhưng file thống kê
  thiếu → admin điền đủ cột như file (bắt buộc đầu mối) → dòng `is_manual` thành 1 dòng thống kê (khóa = IP VTNet): rời mục
  "VTNet có – thống kê thiếu", tính cho đầu mối như server chuẩn. File thống kê mới có IP đó → theo file (6 cột sửa tay vẫn giữ).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

import gpu_core as g
from app.db.models import InventoryOverride
from app.errors import ServiceError
from app.repo import inventory_repo, util_repo
from app.repo.convert import py
from app.services.auth_service import audit, utcnow

EDITABLE_FIELDS = inventory_repo.EDITABLE_FIELDS
MANUAL_FIELDS = inventory_repo.MANUAL_FIELDS
FIELD_LABEL = {
    "owner": "Đầu mối",
    "model": "Model",
    "input_load": "Đầu vào hệ thống",
    "service": "Dịch vụ",
    "managed_by": "Quản lý bằng",
    "cluster": "Cụm",
    "server_class": "Loại server",
    "config": "Cấu hình",
    "cpu": "CPU",
    "ram": "RAM",
    "disk": "Disk",
    "hba": "HBA",
    "gpu_spec": "GPU",
    "serial": "Serial",
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


def _is_active_manual(s: Session, ov: InventoryOverride | None) -> bool:
    """Dòng bổ sung trên web đang đóng vai dòng thống kê (file chưa có IP, IP chưa là đích liên kết)."""
    if ov is None or not ov.is_manual:
        return False
    ip = ov.inventory_ip
    return inventory_repo.current_row(s, ip) is None and ip not in set(inventory_repo.links_frame(s)["vtnet_ip"])


def _base_row(s: Session, ip: str) -> tuple[dict[str, Any] | None, bool]:
    """(giá trị theo file, là dòng bổ sung). Dòng bổ sung: không có "file" → mọi cột None."""
    file_row = inventory_repo.current_row(s, ip)
    if file_row is not None:
        return file_row, False
    if _is_active_manual(s, inventory_repo.get_override(s, ip)):
        return {c: None for c in inventory_repo.INVENTORY_FIELDS} | {"ip": ip}, True
    return None, False


def state(s: Session, inventory_ip: str) -> dict[str, Any]:
    """Giá trị hiệu lực 1 server sau sửa tay + giá trị theo file."""
    file_row, manual = _base_row(s, inventory_ip)
    if file_row is None:
        raise ServiceError(404, f"IP {inventory_ip} không có trong file thống kê hiện hành.")
    ov = inventory_repo.get_override(s, inventory_ip)
    ovf = inventory_repo.overrides_frame(s)
    eff = inventory_repo.apply_overrides(pd.DataFrame([file_row]), ovf[ovf["inventory_ip"] == inventory_ip]).iloc[0]
    return {
        "inventory_ip": inventory_ip,
        "manual": manual,
        "values": {c: py(eff[c]) for c in EDITABLE_FIELDS},
        "file_values": {c: py(file_row.get(c)) for c in EDITABLE_FIELDS},
        "edited": {} if manual else eff["edited"],  # dòng bổ sung không có giá trị "theo file" để so
        "reclaim_status": eff["reclaim_status"],
        "updated_by": ov.updated_by if ov is not None else None,
        "updated_at": ov.updated_at if ov is not None else None,
    }


def update(s: Session, actor: str, inventory_ip: str, changes: dict[str, Any]) -> dict[str, Any]:
    """`changes`: chỉ các khóa cần đổi. Giá trị None = về theo file; '' = để trống; reclaim_status 'in_use'|'reclaimed'."""
    iip = g.norm_ip(inventory_ip)
    file_row, manual = _base_row(s, iip)
    if file_row is None:
        raise ServiceError(
            404, f"IP {iip} không có trong file thống kê hiện hành — chỉ sửa được server có trong danh mục."
        )
    if manual and "owner" in changes and not (changes["owner"] or "").strip():
        raise ServiceError(422, "Server bổ sung trên web phải có đầu mối.")
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
        if all(v is None for v in after.values()) and not (ov is not None and ov.is_manual):
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


def add_manual(s: Session, actor: str, ip: str, data: dict[str, Any]) -> dict[str, Any]:
    """Bổ sung server VTNet có log mà file thống kê thiếu (trang Đối soát). `data`: cột như file (bắt buộc owner)."""
    vip = g.norm_ip(ip)
    if not g.is_ipv4(vip):
        raise ServiceError(422, f"IP không hợp lệ: {ip}.")
    if inventory_repo.current_row(s, vip) is not None:
        raise ServiceError(409, f"IP {vip} đã có trong file thống kê — sửa ở Danh mục server.")
    if vip in set(inventory_repo.links_frame(s)["vtnet_ip"]):
        raise ServiceError(
            409, f"IP {vip} đã được liên kết với 1 IP thống kê — sửa ở Danh mục server hoặc Liên kết IP."
        )
    if not util_repo.has_samples(s, vip):
        raise ServiceError(404, f"VTNet chưa gửi số liệu nào cho IP {vip}.")
    values = {c: _clean(c, str(data[c])) or None if data.get(c) is not None else None
              for c in (*EDITABLE_FIELDS, *MANUAL_FIELDS)}  # fmt: skip
    if not values["owner"]:
        raise ServiceError(422, "Phải có đầu mối sử dụng.")
    rs = data.get("reclaim_status") or "in_use"
    if rs not in RECLAIM_LABEL:
        raise ServiceError(422, f"Trạng thái thu hồi phải là một trong: {', '.join(RECLAIM_LABEL)}.")
    ov = inventory_repo.get_override(s, vip)
    if ov is None:
        ov = InventoryOverride(inventory_ip=vip)
        s.add(ov)
    for k, v in values.items():
        setattr(ov, k, v)
    ov.is_manual = True
    ov.reclaim_status = None if rs == "in_use" else rs
    ov.updated_by, ov.updated_at = actor, utcnow()
    audit(s, actor, "inventory_manual_added", vip, values={k: v for k, v in values.items() if v is not None})
    s.commit()
    return state(s, vip)


def remove_manual(s: Session, actor: str, ip: str) -> None:
    """Bỏ phần bổ sung → server quay về mục "VTNet có – thống kê thiếu"."""
    vip = g.norm_ip(ip)
    ov = inventory_repo.get_override(s, vip)
    if ov is None or not ov.is_manual:
        raise ServiceError(404, f"IP {vip} không phải server bổ sung trên web.")
    audit(s, actor, "inventory_manual_removed", vip, owner=ov.owner, service=ov.service)
    if inventory_repo.current_row(s, vip) is not None:  # file đã có IP: giữ 6 cột sửa tay, bỏ phần bổ sung
        ov.is_manual = False
        for c in MANUAL_FIELDS:
            setattr(ov, c, None)
        if all(getattr(ov, k) is None for k in (*EDITABLE_FIELDS, "reclaim_status")):
            s.delete(ov)
        else:
            ov.updated_by, ov.updated_at = actor, utcnow()
    else:
        s.delete(ov)
    s.commit()


def manual_now_in_file(s: Session, ips: set[str]) -> list[str]:
    """Server bổ sung trên web mà file thống kê mới đã có → từ nay theo file (6 cột sửa tay vẫn giữ)."""
    return sorted(inventory_repo.manual_ips(s) & ips)


def manual_warning(ips: list[str]) -> str:
    return (
        f"{len(ips)} server đã bổ sung trên web nay có trong file này — từ nay theo file "
        f"(đầu mối, dịch vụ… đã sửa trên web vẫn giữ): {', '.join(ips)}"
    )


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
