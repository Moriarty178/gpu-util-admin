"""Băm mật khẩu (bcrypt), phiên đăng nhập (JWT HS256 trong cookie httpOnly), CSRF double-submit (PLAN §9 GĐ2).

Phiên = cookie `gpu_session` (httpOnly, SameSite=Strict) chứa JWT {sub, ver, csrf, iat, exp}.
CSRF = cookie `gpu_csrf` (đọc được bằng JS) — mọi request ghi (POST/PUT/PATCH/DELETE) phải gửi header `X-CSRF-Token`
bằng đúng giá trị `csrf` trong JWT. `ver` = app_user.session_version → đổi/đặt lại mật khẩu, khóa tài khoản là phiên cũ hết hạn.
"""

from __future__ import annotations

import hmac
import secrets
import string
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

SESSION_COOKIE = "gpu_session"
CSRF_COOKIE = "gpu_csrf"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

MIN_PASSWORD_LEN = 10  # PLAN §9
MAX_PASSWORD_BYTES = 72  # giới hạn của bcrypt
MAX_FAILED_ATTEMPTS = 5  # sai 5 lần → khóa 15 phút (PLAN §9)
LOCK_MINUTES = 15
_ALG = "HS256"
# Mật khẩu tạm: bỏ ký tự dễ nhầm (0/O, 1/l/I)
_TEMP_ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")


def hash_password(password: str, rounds: int = 12) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    data = password.encode("utf-8")
    if len(data) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(data, password_hash.encode("ascii"))
    except ValueError:
        return False


# Băm sẵn 1 mật khẩu ngẫu nhiên: user không tồn tại vẫn tốn thời gian kiểm như thường (không lộ tên đăng nhập qua thời gian)
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16), rounds=12)


def burn_time(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def password_problem(password: str, username: str) -> str | None:
    """Câu báo lỗi tiếng Việt nếu mật khẩu mới không đạt chính sách; None nếu đạt."""
    if len(password) < MIN_PASSWORD_LEN:
        return f"Mật khẩu phải có ít nhất {MIN_PASSWORD_LEN} ký tự."
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return f"Mật khẩu quá dài (tối đa {MAX_PASSWORD_BYTES} byte)."
    if password.strip() != password:
        return "Mật khẩu không được bắt đầu hoặc kết thúc bằng khoảng trắng."
    if username and username.casefold() in password.casefold():
        return "Mật khẩu không được chứa tên đăng nhập."
    if len(set(password)) < 4:
        return "Mật khẩu quá đơn giản (cần ít nhất 4 ký tự khác nhau)."
    return None


def temp_password(length: int = 14) -> str:
    """Mật khẩu tạm (admin cấp, hiện 1 lần, buộc đổi khi đăng nhập). Luôn có chữ hoa, chữ thường, chữ số."""
    while True:
        pw = "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(length))
        if any(c.islower() for c in pw) and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw):
            return pw


@dataclass(frozen=True)
class SessionClaims:
    user_id: int
    version: int
    csrf: str


def new_session(user_id: int, version: int, secret: str, hours: float, now: datetime | None = None) -> tuple[str, str]:
    """→ (JWT cho cookie phiên, token CSRF)."""
    now = now or datetime.now(UTC)
    csrf = secrets.token_urlsafe(24)
    payload = {"sub": str(user_id), "ver": version, "csrf": csrf, "iat": now, "exp": now + timedelta(hours=hours)}
    return jwt.encode(payload, secret, algorithm=_ALG), csrf


def read_session(token: str, secret: str) -> SessionClaims | None:
    """None nếu token sai chữ ký / hết hạn / thiếu trường."""
    try:
        p = jwt.decode(token, secret, algorithms=[_ALG], options={"require": ["sub", "ver", "csrf", "exp", "iat"]})
        return SessionClaims(user_id=int(p["sub"]), version=int(p["ver"]), csrf=str(p["csrf"]))
    except (jwt.PyJWTError, ValueError, TypeError):
        return None


def csrf_ok(expected: str, got: str | None) -> bool:
    return bool(got) and hmac.compare_digest(expected, got or "")
