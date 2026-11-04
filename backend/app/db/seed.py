"""Seed idempotent: cài đặt mặc định + 9 liên kết IP RTX6000. Chạy nhiều lần không nhân đôi, không ghi đè giá trị đã có.

Chạy: `bash scripts/task.sh seed` (= `uv run python -m app.db.seed` trong backend/).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

import gpu_core as g
from app.db.migrate import BACKEND_DIR
from app.db.models import AppSetting, IpLink

log = logging.getLogger(__name__)

SEED_LINKS = BACKEND_DIR / "seeds" / "ip_links.csv"
SEED_USER = "seed"

# PLAN §4: giá trị mặc định lấy từ gpu_core.rules (1 nguồn chân lý); max_upload_mb là của app.
DEFAULT_SETTINGS: dict[str, Any] = {
    "default_threshold": g.DEFAULT_THRESHOLD,
    "vtnet_low_load_t": g.VTNET_LOW_LOAD_T,
    "bursty_peak": g.BURSTY_PEAK,
    "high_load": g.HIGH_LOAD,
    "thin_coverage": g.THIN_COVERAGE,
    "max_upload_mb": 20,
}


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def seed(engine: Engine, links_csv: Path = SEED_LINKS, now: datetime | None = None) -> dict[str, int]:
    now = now or utcnow()
    added_settings = added_links = skipped_links = 0
    links = g.load_ip_links(links_csv)
    with Session(engine) as s, s.begin():
        have = set(s.scalars(select(AppSetting.key)))
        for key, value in DEFAULT_SETTINGS.items():
            if key not in have:
                s.add(AppSetting(key=key, value=value, updated_by=SEED_USER, updated_at=now))
                added_settings += 1
        have_inv = set(s.scalars(select(IpLink.inventory_ip)))
        have_vt = set(s.scalars(select(IpLink.vtnet_ip)))
        for row in links.itertuples(index=False):
            if row.inventory_ip in have_inv or row.vtnet_ip in have_vt:
                skipped_links += 1  # đã có (hoặc admin đã đổi) — seed không tự sửa
                continue
            s.add(
                IpLink(
                    inventory_ip=row.inventory_ip,
                    vtnet_ip=row.vtnet_ip,
                    pair_confirmed=bool(row.pair_confirmed),
                    reason=row.reason or None,
                    created_by=SEED_USER,
                    created_at=now,
                )
            )
            added_links += 1
    return {"settings_added": added_settings, "links_added": added_links, "links_skipped": skipped_links}


def main() -> int:
    from app.config import get_settings
    from app.db.migrate import is_migrated
    from app.db.session import make_engine

    engine = make_engine(get_settings().database_url)
    try:
        if not is_migrated(engine):
            print("CSDL chưa có bảng — chạy: bash scripts/task.sh migrate")
            return 1
        r = seed(engine)
    finally:
        engine.dispose()
    print(
        f"Seed xong: thêm {r['settings_added']} cài đặt, {r['links_added']} liên kết IP "
        f"(bỏ qua {r['links_skipped']} liên kết đã có)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
