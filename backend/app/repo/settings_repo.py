from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AppSetting


def get(s: Session, key: str, default: Any) -> Any:
    row = s.get(AppSetting, key)
    return default if row is None else row.value


def all_values(s: Session) -> dict[str, Any]:
    return {row.key: row.value for row in s.query(AppSetting).all()}
