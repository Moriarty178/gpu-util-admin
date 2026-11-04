"""Khôi phục `data/` (app.db + file gốc) từ 1 file zip do `task.sh backup` tạo (G2-M4). Chỉ cho bản chạy native (SQLite);
Docker/PostgreSQL khôi phục bằng pg_restore — docs/DEPLOY_VM.md §5.

An toàn: (1) DỪNG app trước khi khôi phục; (2) luôn sao lưu dữ liệu hiện tại thành `backups/truoc-khoi-phuc-*.zip` trước khi
ghi đè; (3) kiểm zip (đúng cấu trúc, không đường dẫn lạ, `PRAGMA integrity_check`, đã migrate) trước khi động vào data/.
Chạy (Git Bash): `bash scripts/task.sh restore backups/gpu-util-data-<ngày>.zip --yes`
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath

from app.config import ROOT_DIR, get_settings
from app.db.session import resolve_database_url
from app.tools.backup import backup


class RestoreError(Exception):
    pass


def _check_zip(zf: zipfile.ZipFile) -> list[str]:
    names = zf.namelist()
    if "data/app.db" not in names:
        raise RestoreError("File zip không có data/app.db — không phải bản sao lưu của công cụ.")
    for n in names:
        p = PurePosixPath(n)
        if p.is_absolute() or ".." in p.parts or not (n == "data/app.db" or n.startswith("data/uploads/")):
            raise RestoreError(f"File zip chứa đường dẫn không hợp lệ: {n}")
    return names


def _check_db(path: Path) -> None:
    con = sqlite3.connect(path)
    try:
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    if ok != "ok":
        raise RestoreError(f"app.db trong bản sao lưu bị hỏng (integrity_check: {ok}).")
    if not {"import_batch", "alembic_version"} <= tables:
        raise RestoreError("app.db trong bản sao lưu chưa có bảng của công cụ.")


def restore(
    zip_path: Path, db_path: Path, upload_dir: Path, backups_dir: Path, now: datetime | None = None
) -> dict[str, object]:
    if not zip_path.is_file():
        raise RestoreError(f"Không thấy file {zip_path}.")
    now = now or datetime.now()
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(zip_path) as zf:
        names = _check_zip(zf)
        zf.extractall(tmp)
        new_db = Path(tmp) / "data" / "app.db"
        _check_db(new_db)
        # sao lưu hiện trạng trước khi ghi đè (nếu có gì)
        safety = backup(db_path if db_path.is_file() else None, upload_dir, backups_dir, now=now)
        if safety is not None:
            renamed = safety.with_name(safety.name.replace("gpu-util-data-", "truoc-khoi-phuc-"))
            safety.rename(renamed)
            safety = renamed
        db_path.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(f"{db_path}{suffix}").unlink(missing_ok=True)
        shutil.copyfile(new_db, db_path)
        n_up = 0
        src_up = Path(tmp) / "data" / "uploads"
        if src_up.is_dir():
            for f in src_up.rglob("*"):
                if f.is_file():
                    dest = upload_dir / f.relative_to(src_up)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(f, dest)
                    n_up += 1
    return {"files": len(names), "uploads": n_up, "safety_backup": safety}


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser(prog="restore", description="Khôi phục data/ từ file zip của task.sh backup.")
    ap.add_argument("zip", type=Path)
    ap.add_argument("--yes", action="store_true", help="Xác nhận đã dừng app và đồng ý ghi đè data/ hiện tại")
    args = ap.parse_args(argv)
    settings = get_settings()
    url = resolve_database_url(settings.database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        print("Chỉ khôi phục được bản native (SQLite). PostgreSQL: xem docs/DEPLOY_VM.md §5.", file=sys.stderr)
        return 2
    if not args.yes:
        print(
            "Dừng app (task.sh run/dev) trước, rồi chạy lại kèm --yes. Dữ liệu hiện tại sẽ được sao lưu trước khi ghi đè."
        )
        return 2
    zip_path = args.zip if args.zip.is_absolute() else (Path.cwd() / args.zip)
    try:
        r = restore(zip_path.resolve(), Path(url.database), settings.upload_path, ROOT_DIR / "backups")
    except (RestoreError, zipfile.BadZipFile) as exc:
        print(f"Dừng, chưa thay đổi gì: {exc}", file=sys.stderr)
        return 1
    if r["safety_backup"]:
        print(f"Đã sao lưu dữ liệu cũ → {r['safety_backup']}")
    print(f"Đã khôi phục app.db + {r['uploads']} file gốc từ {zip_path.name}. Chạy lại: bash scripts/task.sh run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
