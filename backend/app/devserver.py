"""API cho `make dev`, được `watchfiles` khởi động lại cả tiến trình mỗi khi sửa file .py.

Không dùng `uvicorn --reload`: trên Windows, reloader của uvicorn dừng worker bằng CTRL_C_EVENT; khi chạy dưới
concurrently/Git Bash, worker không có console chung nên không nhận được → reloader treo, code mới không được nạp.
Chạy: `watchfiles --filter python --target-type function app.devserver.serve app gpu_core` (trong backend/).
"""

from __future__ import annotations

import uvicorn

from app.config import get_settings
from app.main import create_app


def serve() -> None:
    settings = get_settings()
    # GĐ1 không đăng nhập → chỉ nghe 127.0.0.1. log_config=None: dùng cấu hình log của create_app (stdout).
    uvicorn.run(create_app(settings), host="127.0.0.1", port=settings.api_port, log_config=None)
