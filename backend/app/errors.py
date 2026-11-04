"""Chuyển mọi lỗi HTTP / lỗi kiểm tra dữ liệu sang JSON {type, title, detail} tiếng Việt."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.common import Problem

_TITLES: dict[int, tuple[str, str]] = {
    400: ("bad_request", "Yêu cầu không hợp lệ"),
    401: ("not_authenticated", "Chưa đăng nhập"),
    403: ("forbidden", "Không có quyền"),
    404: ("not_found", "Không tìm thấy"),
    405: ("method_not_allowed", "Phương thức không được hỗ trợ"),
    409: ("conflict", "Xung đột dữ liệu"),
    413: ("payload_too_large", "File quá lớn"),
    422: ("validation_error", "Dữ liệu không hợp lệ"),
    423: ("account_locked", "Tài khoản tạm khóa"),
    503: ("service_unavailable", "Dịch vụ tạm thời không sẵn sàng"),
}


def problem_response(
    status: int, detail: Any = None, headers: dict[str, str] | None = None, type_: str | None = None
) -> JSONResponse:
    default_type, title = _TITLES.get(status, ("error", "Lỗi máy chủ" if status >= 500 else "Lỗi yêu cầu"))
    body = Problem(type=type_ or default_type, title=title, detail=detail).model_dump()
    return JSONResponse(body, status_code=status, headers=headers)


async def _http_exc(_req: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    detail = exc.detail
    if exc.status_code == 404 and detail == "Not Found":
        detail = "Đường dẫn không tồn tại."
    elif exc.status_code == 405 and detail == "Method Not Allowed":
        detail = "Đường dẫn này không hỗ trợ phương thức đã gọi."
    return problem_response(exc.status_code, detail, getattr(exc, "headers", None), getattr(exc, "type_", None))


class AuthError(StarletteHTTPException):
    """401/403 có `type` riêng để giao diện biết phải làm gì: not_authenticated (đăng nhập), setup_required (chưa có
    admin), password_change_required (đổi mật khẩu tạm), csrf_failed, forbidden."""

    def __init__(self, status: int, type_: str, detail: str) -> None:
        super().__init__(status_code=status, detail=detail)
        self.type_ = type_


async def _validation_exc(_req: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", "")} for e in exc.errors()]
    return problem_response(422, errors)


class ServiceError(Exception):
    """Lỗi nghiệp vụ từ service → HTTP {type,title,detail}. `detail` là câu tiếng Việt cho người dùng."""

    def __init__(self, status: int, detail: Any, type_: str | None = None) -> None:
        super().__init__(str(detail))
        self.status = status
        self.detail = detail
        self.type_ = type_


async def _service_exc(_req: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ServiceError)
    return problem_response(exc.status, exc.detail, type_=exc.type_)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exc)
    app.add_exception_handler(RequestValidationError, _validation_exc)
    app.add_exception_handler(ServiceError, _service_exc)
