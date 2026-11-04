# Rà soát bảo mật — G2-M4 (03/11/2026)

Phạm vi: backend FastAPI, frontend React, Docker Compose (nginx + api + PostgreSQL), bản chạy native (Windows, SQLite).
Mỗi mục: kiểm thế nào → kết quả. ✅ đạt · 🔧 đã sửa trong G2-M4 · ⚠️ còn lại / khuyến nghị.

## 1. Xác thực & phiên

| Mục | Kiểm | Kết quả |
|---|---|---|
| Mật khẩu băm bcrypt (12 vòng), không lưu/không log mật khẩu | đọc `security.py`, `audit_log` payload | ✅ |
| Chính sách mật khẩu ≥ 10 ký tự, không chứa tên đăng nhập, mật khẩu tạm buộc đổi | `test_auth.py` | ✅ |
| Khóa 5 lần sai / 15 phút; thông báo sai chung cho "không có tài khoản" và "sai mật khẩu"; tốn thời gian như nhau | `test_bad_login_is_generic_and_locks_after_5` | ✅ |
| Cookie phiên httpOnly + SameSite=Strict + hết hạn 12 giờ; `COOKIE_SECURE=true` khi có HTTPS | kiểm header qua nginx (G2-M2) | ✅ |
| CSRF double-submit cho mọi request ghi | `test_csrf_required_for_writes` | ✅ |
| JWT HS256 cố định thuật toán, chữ ký sai / hết hạn → 401; khóa ≥ 32 ký tự | `test_tampered_or_expired_session` | ✅ |
| Đổi / đặt lại mật khẩu, khóa tài khoản → mọi phiên cũ hết hiệu lực (`session_version`) | `test_admin_reset_lock_and_guards` | ✅ |
| **Đăng xuất chỉ xóa cookie — token bị lộ vẫn dùng được tới hết hạn** | đọc `routers/auth.py` | 🔧 đăng xuất tăng `session_version` → mọi phiên của tài khoản hết hiệu lực (`test_logout_invalidates_all_sessions_of_user`) |
| Không có admin "cửa sau": tài khoản đầu tiên tạo bằng CLI (`create-admin`), mật khẩu tạm in 1 lần | — | ✅ |

## 2. Phân quyền & phạm vi dữ liệu

| Mục | Kiểm | Kết quả |
|---|---|---|
| Mặc định chặn: mọi route API cần đăng nhập trừ `/healthz`, `/auth/login`, `/auth/logout` | ma trận mọi route (lấy từ OpenAPI) × 6 loại người dùng — `test_permission_matrix` | ✅ 38 route |
| Phạm vi đầu mối áp ở service (`Scope`), ngoài phạm vi → 404 (không lộ server tồn tại) | `test_permissions.py`, `test_g2m3.py`, E2E | ✅ |
| Xuất Excel của đầu mối không chứa dòng / sheet ngoài phạm vi | `test_owner_own_sees_only_own_servers` | ✅ |
| **Đặc tả `/api/v1/openapi.json` công khai** (lộ cấu trúc API) | `curl` không cookie | 🔧 cần đăng nhập (`test_security_headers_and_openapi_requires_login`) |
| `/docs`, `/redoc` (Swagger tải CDN) | — | ✅ đã tắt (Q17) |

## 3. Đầu vào & dữ liệu

| Mục | Kiểm | Kết quả |
|---|---|---|
| Upload: chỉ `.xlsx`, giới hạn dung lượng (cài đặt, mặc định 20 MB; nginx 25 MB), `defusedxml` | `test_upload_size_limit_413`; nginx 413 | ✅ |
| File gốc lưu theo sha256 (không dùng tên người dùng đặt làm đường dẫn) | `import_service._store_file` | ✅ |
| SQL injection: chỉ SQLAlchemy Core/ORM có tham số; `LIKE` nhận chuỗi người dùng chỉ ảnh hưởng ký tự đại diện | đọc repo/service | ✅ |
| Đường dẫn SPA không thoát khỏi `frontend/dist` | `test_spa_fallback` (`%2e%2e`) | ✅ |
| Khôi phục bản sao lưu: zip chỉ được chứa `data/app.db` + `data/uploads/…`, không `..` / đường dẫn tuyệt đối | `test_restore_roundtrip_and_safety_backup` | ✅ |
| XSS: React tự thoát chuỗi; ghi chú hiển thị dạng văn bản | — | ✅ |
| **CSV xuất từ Danh mục: ô bắt đầu bằng `= + - @` bị Excel chạy như công thức** (chèn công thức qua dữ liệu file thống kê) | `csv.test.ts` | 🔧 thêm `'` ở đầu ô văn bản như vậy (số âm giữ nguyên) |
| Giới hạn khối lượng: xu hướng ≤ 36 tháng, so sánh ≤ 5 server, phân trang ≤ 500 | test API | ✅ |

## 4. Header & trình duyệt

| Mục | Kiểm | Kết quả |
|---|---|---|
| CSP chỉ `'self'` (không CDN), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy` | Docker: nginx (G2-M1) | ✅ |
| **Chạy native (không nginx) thiếu các header trên** | `curl -I` | 🔧 middleware trong app đặt cùng bộ header + `Cache-Control: no-store` cho `/api/*` |
| Không CORS (chỉ cùng nguồn) | không có CORSMiddleware | ✅ |
| HSTS (`max-age=15552000`, không includeSubDomains) ở chế độ HTTPS | `curl -I https://…` (04/11/2026) | 🔧 `docker/nginx/40-gpu-mode.sh` |

## 5. Thư viện (quét 03/11/2026)

| Mục | Kết quả |
|---|---|
| Python runtime (`uv export --no-dev --extra pg` → `pip-audit`) | ✅ không có lỗ hổng đã biết |
| npm runtime (`npm audit --omit=dev`) | ⚠️ **ECharts 5** — XSS mức trung bình (GHSA-fgmj-fm8m-jvvx), bản vá ở ECharts 6 (thay đổi lớn; PLAN chốt ECharts 5). Giảm thiểu: CSP `script-src 'self'` chặn script chèn vào; 🔧 tên series lấy từ dữ liệu (dịch vụ) được lọc ký tự HTML (`safeLabel`). **Khuyến nghị**: nâng ECharts 6 ở 1 đợt riêng (cần người dùng duyệt) |

Chạy lại (Git Bash): `npm --prefix frontend audit --omit=dev` · `cd backend && uv export --frozen --no-dev --extra pg --no-hashes
--no-emit-project -o /tmp/req.txt && uvx pip-audit -r /tmp/req.txt --no-deps --disable-pip`.

## 6. Triển khai & vận hành

| Mục | Kết quả |
|---|---|
| Mặc định chỉ bind `127.0.0.1` (native lẫn Docker); chỉ `web` mở cổng; db/api trong mạng Docker | ✅ |
| Image không chứa `samples/ data/ .env`; container api chạy user không phải root | ✅ (G2-M1) |
| Bí mật (`POSTGRES_PASSWORD`, `SECRET_KEY`) qua `.env` — không commit; native tự tạo `data/secret_key` | ✅ · ⚠️ biến môi trường container đọc được bằng `docker inspect` (người có quyền Docker trên VM = quản trị) |
| Nhật ký: đăng nhập (đúng/sai/khóa), đăng xuất, mật khẩu, tài khoản, nhập/hoàn tác, liên kết, ghi chú, cài đặt — trang Nhật ký (admin) | ✅ |
| Sao lưu hằng đêm (Docker) / `task.sh backup` (native); khôi phục đã thử (DEPLOY_VM §5, `task.sh restore`) | ✅ |
| **HTTPS (04/11/2026)**: chế độ A — nginx giữ chứng chỉ `.pem` (`compose.tls.yaml`): TLS 1.2/1.3, bộ mã AEAD (Mozilla intermediate), HTTP → 301 HTTPS, HSTS, `COOKIE_SECURE=true` bắt buộc; chế độ B — proxy hạ tầng giữ TLS. Mặc định vẫn bind 127.0.0.1 (mở mạng = đặt `HTTPS_BIND` chủ động). `task.sh tls-check` kiểm hạn / khớp khóa / SAN / passphrase trước khi bật | ✅ cấu hình + thử bằng chứng chỉ tự ký · ⚠️ chưa thử chứng chỉ thật trên VM (DEPLOY.md §8) |
| 🔧 **IP trong Nhật ký giả được** (04/11/2026): nginx *nối thêm* `X-Forwarded-For` của trình duyệt, uvicorn (`--forwarded-allow-ips *`) lấy địa chỉ đầu → gửi header tự đặt là đổi được IP ghi nhật ký. Sửa: nginx ghi đè `X-Forwarded-For $remote_addr`; proxy hạ tầng tin cậy khai qua `TRUSTED_PROXIES` (module realip) | ✅ đã kiểm bằng curl giả header |
| ⚠️ Chưa giới hạn số lần đăng nhập theo IP (chỉ khóa theo tài khoản) — chấp nhận được cho mạng nội bộ; nếu mở rộng nên thêm ở reverse proxy | — |
