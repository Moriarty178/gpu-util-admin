"""Cấu hình đọc từ `.env` ở gốc repo (pydantic-settings). Đường dẫn tương đối tính từ gốc repo."""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


def resolve_path(p: Path) -> Path:
    """Đường dẫn tương đối trong `.env` luôn tính từ gốc repo, không phụ thuộc thư mục đang chạy."""
    return p if p.is_absolute() else (ROOT_DIR / p).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./data/app.db"
    upload_dir: Path = Path("./data/uploads")
    frontend_dist: Path = Path("./frontend/dist")
    api_port: int = 8000
    web_port: int = 5173
    tz: str = "Asia/Ho_Chi_Minh"
    log_level: str = "INFO"
    warm_cache: bool = True  # đọc sẵn dữ liệu phân tích khi khởi động / sau khi xác nhận, hoàn tác lô
    # GĐ2 — đăng nhập (G2-M2). SECRET_KEY trống → tự tạo 1 lần ở data/secret_key (chạy native); Docker bắt buộc đặt.
    secret_key: str | None = None
    session_hours: float = 12  # phiên hết hạn sau N giờ kể từ lúc đăng nhập
    cookie_secure: bool = False  # True khi chạy sau HTTPS (cookie chỉ gửi qua TLS)
    bcrypt_rounds: int = 12  # test đặt 4 cho nhanh

    def resolved_secret(self) -> str:
        if self.secret_key:
            if len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY phải dài ít nhất 32 ký tự.")
            return self.secret_key
        path = resolve_path(Path("./data/secret_key"))
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_text(secrets.token_urlsafe(48), encoding="utf-8")
            os.replace(tmp, path)
        return path.read_text(encoding="utf-8").strip()

    @property
    def upload_path(self) -> Path:
        return resolve_path(self.upload_dir)

    @property
    def dist_path(self) -> Path:
        return resolve_path(self.frontend_dist)


@lru_cache
def get_settings() -> Settings:
    return Settings()
