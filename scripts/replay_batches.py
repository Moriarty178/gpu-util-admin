"""Chuyển dữ liệu GĐ1 (SQLite + data/uploads) sang PostgreSQL bằng cách phát lại các lô (PLAN ADR-9).

Vỏ mỏng gọi `app.tools.replay` (logic + test nằm trong backend). Chạy trong Git Bash, tại gốc repo:
    bash scripts/task.sh replay --target postgresql+psycopg://gpu:<mật khẩu>@127.0.0.1:15432/gpu_util
Trong Docker Compose:  docker compose run --rm replay   (xem docs/DEPLOY_VM.md)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
for stream in (sys.stdout, sys.stderr):  # console Windows cp1252 → in tiếng Việt không lỗi
    stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from app.tools.replay import main

if __name__ == "__main__":
    raise SystemExit(main())
