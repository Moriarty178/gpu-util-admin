"""Sao lưu `data/` (app.db + file gốc đã nhập) thành 1 file zip có ngày giờ trong `backups/`.

Dùng API backup của sqlite3 trong Python → an toàn khi app đang chạy, không cần cài `sqlite3` CLI.
Chạy: `bash scripts/task.sh backup` (hoặc `make backup`).
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from app.config import ROOT_DIR, get_settings
from app.db.session import resolve_database_url


def backup(db_path: Path | None, upload_dir: Path, out_dir: Path, now: datetime | None = None) -> Path | None:
    """Trả về đường dẫn file zip, hoặc None nếu chưa có gì để sao lưu."""
    has_db = db_path is not None and db_path.is_file()
    uploads = sorted(p for p in upload_dir.rglob("*") if p.is_file()) if upload_dir.is_dir() else []
    if not has_db and not uploads:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"gpu-util-data-{(now or datetime.now()):%Y%m%d-%H%M%S}.zip"
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        if has_db and db_path is not None:
            snap = Path(tmp) / "app.db"
            src, dst = sqlite3.connect(db_path), sqlite3.connect(snap)
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
            zf.write(snap, "data/app.db")
        for p in uploads:
            zf.write(p, f"data/uploads/{p.relative_to(upload_dir).as_posix()}")
    return out


def main() -> int:
    settings = get_settings()
    url = resolve_database_url(settings.database_url)
    if url.get_backend_name() != "sqlite":
        print("GĐ1 chỉ sao lưu SQLite. PostgreSQL (GĐ2) dùng pg_dump.", file=sys.stderr)
        return 2
    db_path = Path(url.database) if url.database and url.database != ":memory:" else None
    out = backup(db_path, settings.upload_path, ROOT_DIR / "backups")
    if out is None:
        print("Chưa có dữ liệu để sao lưu (không thấy app.db và data/uploads/).")
        return 0
    print(f"Đã sao lưu → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
