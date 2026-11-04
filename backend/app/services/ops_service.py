"""Vận hành (G2-M4, PLAN §8.6): Cài đặt (các hằng §4 — admin sửa trên UI) và Nhật ký (tra cứu audit_log).

Đổi cài đặt là quyết định của người dùng (admin), không phải của code: service chỉ kiểm giới hạn hợp lệ, ghi nhật ký,
đặt `updated_at` → `data_version` đổi → mọi phân tích tính lại theo giá trị mới. Mặc định vẫn lấy từ gpu_core (1 nguồn).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AppSetting, AuditLog
from app.db.seed import DEFAULT_SETTINGS
from app.errors import ServiceError
from app.services.auth_service import audit, utcnow


@dataclass(frozen=True)
class SettingSpec:
    label: str
    hint: str
    minimum: float
    maximum: float
    integer: bool = False
    unit: str = "%"


SPECS: dict[str, SettingSpec] = {
    "default_threshold": SettingSpec(
        "Ngưỡng T mặc định", "Ngưỡng vùng khi chưa chọn trên giao diện (luật <= T)", 0, 100
    ),
    "vtnet_low_load_t": SettingSpec("Ngưỡng cờ THẤP TẢI VTNet", "gpu < X và mem < X (so sánh < chặt)", 0, 100),
    "bursty_peak": SettingSpec("Đỉnh bursty", "Nguy hiểm nhưng đỉnh util ≥ X → 'bursty' thay vì 'idle thật'", 0, 100),
    "high_load": SettingSpec("Tải cao", "gpu và mem ≥ X → mẫu hình 'tải cao'", 0, 100),
    "thin_coverage": SettingSpec(
        "Dữ liệu mỏng", "Số ngày có mẫu / số ngày trong khoảng < X → gắn cờ dữ liệu mỏng", 0, 1, unit=""
    ),
    "max_upload_mb": SettingSpec(
        "Giới hạn file nhập", "Dung lượng tối đa 1 file .xlsx", 1, 200, integer=True, unit="MB"
    ),
}


def list_settings(s: Session) -> list[dict[str, Any]]:
    rows = {r.key: r for r in s.scalars(select(AppSetting))}
    out = []
    for key, spec in SPECS.items():
        r = rows.get(key)
        out.append(
            {
                "key": key,
                "value": r.value if r is not None else DEFAULT_SETTINGS[key],
                "default": DEFAULT_SETTINGS[key],
                "label": spec.label,
                "hint": spec.hint,
                "min": spec.minimum,
                "max": spec.maximum,
                "integer": spec.integer,
                "unit": spec.unit,
                "updated_by": r.updated_by if r is not None else None,
                "updated_at": r.updated_at if r is not None else None,
            }
        )
    return out


def update_settings(s: Session, actor: str, changes: dict[str, Any]) -> list[dict[str, Any]]:
    if not changes:
        raise ServiceError(422, "Không có thay đổi nào.")
    clean: dict[str, float | int] = {}
    for key, value in changes.items():
        spec = SPECS.get(key)
        if spec is None:
            raise ServiceError(422, f"Không có cài đặt '{key}'.")
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ServiceError(422, f"{spec.label}: phải là số.")
        if not spec.minimum <= value <= spec.maximum:
            raise ServiceError(422, f"{spec.label}: phải trong khoảng {spec.minimum:g}–{spec.maximum:g}{spec.unit}.")
        if spec.integer and int(value) != value:
            raise ServiceError(422, f"{spec.label}: phải là số nguyên.")
        clean[key] = int(value) if spec.integer else float(value)
    now = utcnow()
    before: dict[str, Any] = {}
    for key, value in clean.items():
        row = s.get(AppSetting, key)
        if row is None:
            row = AppSetting(key=key, value=value)
            s.add(row)
            before[key] = None
        else:
            before[key] = row.value
        row.value, row.updated_by, row.updated_at = value, actor, now
    audit(s, actor, "settings_updated", ",".join(sorted(clean)), before=before, after=clean)
    s.commit()
    return list_settings(s)


def list_audit(
    s: Session,
    *,
    username: str | None = None,
    action: str | None = None,
    start: date | None = None,
    end: date | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    """Mới nhất trước. `action` là tiền tố (vd 'login', 'import_', 'user_'); `start`/`end` theo ngày giờ VN (UTC+7)."""
    stmt = select(AuditLog)
    if username:
        stmt = stmt.where(AuditLog.username == username.strip().casefold())
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action.strip()}%"))
    vn = timedelta(hours=7)  # `at` lưu UTC; lọc theo ngày giờ VN
    if start:
        stmt = stmt.where(AuditLog.at >= datetime.combine(start, datetime.min.time()) - vn)
    if end:
        stmt = stmt.where(AuditLog.at < datetime.combine(end + timedelta(days=1), datetime.min.time()) - vn)
    if q:
        stmt = stmt.where(AuditLog.target.like(f"%{q.strip()}%"))
    total = int(s.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = s.scalars(
        stmt.order_by(AuditLog.at.desc(), AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = [
        {"id": r.id, "at": r.at, "username": r.username, "action": r.action, "target": r.target, "payload": r.payload}
        for r in rows
    ]
    actions = sorted(set(s.scalars(select(AuditLog.action).distinct())))
    return {"total": total, "page": page, "page_size": page_size, "actions": actions, "items": items}
