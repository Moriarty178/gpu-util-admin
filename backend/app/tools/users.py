"""Quản lý tài khoản từ dòng lệnh — tạo admin đầu tiên, cứu khi quên mật khẩu admin (G2-M2).

Native (Git Bash):  bash scripts/task.sh create-admin [tên]         (mặc định 'admin')
                    bash scripts/task.sh reset-password <tên>
Docker:             docker compose exec api python -m app.tools.users create-admin [tên]
In mật khẩu tạm ĐÚNG 1 LẦN ra màn hình (không ghi log); đăng nhập lần đầu phải đổi.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.migrate import is_migrated
from app.db.session import make_engine
from app.errors import ServiceError
from app.services import auth_service as svc

CLI_ACTOR = "cli"


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # console Windows cp1252
        stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser(prog="users", description="Tạo admin / đặt lại mật khẩu từ dòng lệnh.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-admin", help="Tạo tài khoản quản trị (mật khẩu tạm, buộc đổi khi đăng nhập)")
    c.add_argument("username", nargs="?", default="admin")
    r = sub.add_parser("reset-password", help="Đặt lại mật khẩu tạm + gỡ khóa cho 1 tài khoản")
    r.add_argument("username")
    args = ap.parse_args(argv)

    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        if not is_migrated(engine):
            print("CSDL chưa có bảng — chạy: bash scripts/task.sh migrate", file=sys.stderr)
            return 2
        with Session(engine) as s:
            try:
                if args.cmd == "create-admin":
                    u, pw = svc.create_user(
                        s, CLI_ACTOR, args.username, svc.UserInput(role="admin"), rounds=settings.bcrypt_rounds
                    )
                    what = "Đã tạo tài khoản quản trị"
                else:
                    found = svc.find_user(s, args.username)
                    if found is None:
                        print(f"Không có tài khoản '{args.username}'.", file=sys.stderr)
                        return 1
                    u, pw = svc.reset_password(s, CLI_ACTOR, found.id, rounds=settings.bcrypt_rounds)
                    what = "Đã đặt lại mật khẩu"
            except ServiceError as exc:
                print(f"Lỗi: {exc.detail}", file=sys.stderr)
                return 1
            name = u.username
        print(f"{what}: {name}")
        print(f"Mật khẩu tạm (chỉ hiện lần này): {pw}")
        print("Đăng nhập rồi đổi mật khẩu ngay (≥ 10 ký tự).")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
