"""Điểm vào FastAPI. Chạy: `uvicorn app.main:create_app --factory --host 127.0.0.1`.

Phân quyền gắn ở mức router (mặc định chặn, PLAN §9): dữ liệu → `require_user`; /imports, /users → `require_admin`;
/auth/* tự kiểm; chỉ /healthz (Docker healthcheck) và /auth/login không cần đăng nhập.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app import __version__
from app.config import Settings, get_settings
from app.db.migrate import is_migrated
from app.db.session import make_engine
from app.deps import require_admin, require_user
from app.errors import install_error_handlers
from app.logging_setup import setup_logging
from app.routers import alerts, auth, compare, fleet, gaps, imports, inventory, meta, ops, reports, servers, users
from app.services.analytics_service import AnalyticsCache, warm_up
from app.services.auth_service import user_count
from app.services.import_service import discard_stale_staged
from app.spa import mount_frontend

API_PREFIX = "/api/v1"
# Không tải tài nguyên ngoài (không CDN). AntD chèn <style> → 'unsafe-inline' cho style; script chỉ từ chính site.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)
log = logging.getLogger(__name__)


def _on_startup(engine: Engine, cache: AnalyticsCache, warm: bool) -> None:
    if not is_migrated(engine):
        log.warning("CSDL chưa có bảng — chạy: bash scripts/task.sh migrate && bash scripts/task.sh seed")
        return
    with Session(engine) as s:
        n = discard_stale_staged(s)
        if user_count(s) == 0:
            log.warning("Chưa có tài khoản nào — tạo admin: bash scripts/task.sh create-admin")
    if n:
        log.info("Tự hủy %d lô chờ xác nhận quá 24 giờ", n)
    if warm:
        threading.Thread(target=warm_up, args=(engine, cache), name="warm-up", daemon=True).start()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    engine = make_engine(settings.database_url)
    cache = AnalyticsCache()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        _on_startup(engine, cache, settings.warm_cache)
        yield
        engine.dispose()

    app = FastAPI(
        title="GPU Util Admin — TTCN-VTT",
        version=__version__,
        description="API quản trị tải GPU TTCN-VTT — đăng nhập bằng cookie phiên (POST /auth/login).",
        openapi_url=None,  # đặc tả phục vụ qua route riêng bên dưới (bắt buộc đăng nhập)
        # Q17: tắt /docs và /redoc — Swagger UI/ReDoc mặc định tải JS/CSS từ CDN (trái quy tắc "không CDN").
        # Đặc tả máy đọc ở /api/v1/openapi.json (cần đăng nhập — G2-M4 rà soát bảo mật).
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.analytics_cache = cache
    app.state.secret = settings.resolved_secret()
    install_error_handlers(app)
    user, admin = [Depends(require_user)], [Depends(require_admin)]
    app.include_router(meta.router, prefix=API_PREFIX)  # /healthz công khai; /meta cần đăng nhập (qua ScopeDep)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(users.router, prefix=API_PREFIX, dependencies=admin)
    app.include_router(imports.router, prefix=API_PREFIX, dependencies=admin)
    app.include_router(fleet.router, prefix=API_PREFIX, dependencies=user)
    app.include_router(servers.router, prefix=API_PREFIX, dependencies=user)
    app.include_router(alerts.router, prefix=API_PREFIX, dependencies=user)
    app.include_router(gaps.router, prefix=API_PREFIX, dependencies=user)  # sửa liên kết: AdminDep trên từng route
    app.include_router(compare.router, prefix=API_PREFIX, dependencies=user)
    app.include_router(reports.router, prefix=API_PREFIX, dependencies=user)
    app.include_router(ops.router, prefix=API_PREFIX, dependencies=admin)
    app.include_router(inventory.router, prefix=API_PREFIX, dependencies=admin)  # sửa tay danh mục (PLAN §14.11)

    @app.get(f"{API_PREFIX}/openapi.json", include_in_schema=False, dependencies=user)
    def openapi_spec() -> JSONResponse:
        return JSONResponse(app.openapi())

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        """Header bảo mật cho mọi response (chạy native không có nginx phía trước; Docker: nginx đặt thêm CSP giống hệt)."""
        resp: Response = await call_next(request)
        h = resp.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "same-origin")
        h.setdefault("Content-Security-Policy", CSP)
        if request.url.path.startswith(API_PREFIX):
            h.setdefault(
                "Cache-Control", "no-store"
            )  # số liệu theo phiên đăng nhập — không cache ở trình duyệt / proxy
        return resp

    if mount_frontend(app, settings.dist_path):
        log.info("Phục vụ frontend từ %s", settings.dist_path)
    else:
        log.info(
            "API không phục vụ giao diện (chưa có %s) — dev: Vite :5173; Docker: service web (nginx).",
            settings.dist_path,
        )
    return app
