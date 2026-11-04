#!/usr/bin/env bash
# Lệnh dự án (GĐ1 native + công cụ GĐ2). Dùng:  bash scripts/task.sh <lệnh> [tham số]     (có GNU make thì: make <lệnh>)
# Windows: chạy trong Git Bash (KHÔNG gõ `bash` trong PowerShell — đó là bash của WSL).
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() {
  cat <<'EOF'
Lệnh:
  setup       cài thư viện backend (uv sync) + frontend (npm ci); tạo .env nếu chưa có
  dev         phát triển: API 127.0.0.1:API_PORT (tự nạp lại) + Vite :WEB_PORT; Ctrl-C dừng cả hai
  run         dùng hằng ngày: build frontend → 1 tiến trình FastAPI tại http://localhost:API_PORT
  test        pytest backend (+ tham số pytest, vd: test -k healthz) + Vitest frontend
  lint        skill đồng bộ? + ruff + mypy + eslint + tsc
  e2e         build frontend + Playwright (luồng admin + đầu mối, Edge có sẵn, CSDL tạm)
  fmt         ruff format/fix + eslint --fix
  migrate     tạo/nâng cấp CSDL (alembic upgrade head); 'migrate down' = về base (XÓA hết bảng)
  seed        nạp app_setting mặc định + 9 liên kết IP (chạy lại không nhân đôi)
  create-admin [tên]     tạo tài khoản quản trị (mặc định 'admin'); in mật khẩu tạm 1 lần
  reset-password <tên>   đặt lại mật khẩu tạm + gỡ khóa (khi quên mật khẩu)
  backup      nén data/ (app.db + file gốc đã nhập) vào backups/ kèm ngày giờ
  restore <file.zip> --yes   khôi phục data/ từ bản sao lưu (DỪNG app trước; dữ liệu hiện tại được sao lưu trước)
  sync-skill  đồng bộ backend/gpu_core → .claude/skills/gpu-util-vtnet
GĐ2 (PostgreSQL):
  test-pg     pytest trên cả SQLite và PostgreSQL (cần TEST_PG_URL trong .env hoặc biến môi trường)
  pg-temp     start|stop|url — cụm PostgreSQL tạm cho test-pg (dùng initdb/pg_ctl đã cài; dữ liệu ở data/pg-temp)
  replay      phát lại các lô GĐ1 sang CSDL mới (--target URL; --help để xem tham số)
  tls-check <cert.pem> [key.pem] [tên-miền]   kiểm chứng chỉ trước khi bật HTTPS (hạn, khớp khóa, SAN, chuỗi)
EOF
}

uvb() { uv run --directory backend "$@"; }   # chạy lệnh trong venv của backend
db_ready() { uvb alembic upgrade head && uvb python -m app.db.seed; }   # idempotent

# Cụm PostgreSQL tạm chỉ cho test (127.0.0.1, xác thực trust, user gpu_test). Không đụng service PostgreSQL có sẵn.
PG_TEMP_DIR="data/pg-temp"
PG_TEMP_PORT="$(env_get PG_TEMP_PORT 55432)"
pg_bin() {
  if command -v "$1" >/dev/null 2>&1; then command -v "$1"; return; fi
  local d
  for d in "/c/Program Files/PostgreSQL"/*/bin /usr/lib/postgresql/*/bin; do
    if [[ -x "$d/$1" || -x "$d/$1.exe" ]]; then echo "$d/$1"; return; fi
  done
  echo "Không thấy '$1' (PostgreSQL). Cài PostgreSQL hoặc dùng Docker: docker compose -f compose.yaml -f compose.dev.yaml up -d db" >&2
  exit 1
}
pg_temp() {
  local url="postgresql+psycopg://gpu_test@127.0.0.1:${PG_TEMP_PORT}/postgres"
  case "$1" in
    start)
      if [[ ! -f "$PG_TEMP_DIR/PG_VERSION" ]]; then
        mkdir -p "$PG_TEMP_DIR"
        "$(pg_bin initdb)" -D "$PG_TEMP_DIR" -U gpu_test -A trust -E UTF8 --no-locale >/dev/null
      fi
      if "$(pg_bin pg_ctl)" -D "$PG_TEMP_DIR" status >/dev/null 2>&1; then echo "Đang chạy sẵn."
      # Windows: postgres con giữ stdout/stderr của pg_ctl → chuyển hướng hết, log nằm ở server.log
      elif ! "$(pg_bin pg_ctl)" -D "$PG_TEMP_DIR" -l "$PG_TEMP_DIR/server.log" -w \
          -o "-p ${PG_TEMP_PORT} -c listen_addresses=127.0.0.1 -c fsync=off" start </dev/null >/dev/null 2>&1; then
        echo "Không khởi động được — xem $PG_TEMP_DIR/server.log" >&2; exit 1
      fi
      echo "TEST_PG_URL=$url"
      ;;
    stop) "$(pg_bin pg_ctl)" -D "$PG_TEMP_DIR" -m fast stop ;;
    url) echo "TEST_PG_URL=$url" ;;
    *) echo "Dùng: task.sh pg-temp start|stop|url" >&2; exit 2 ;;
  esac
}

cmd="${1:-help}"
shift || true
case "$cmd" in
  setup)
    need uv; need node; need npm
    if [[ ! -f .env ]]; then cp .env.example .env; echo "Đã tạo .env từ .env.example"; fi
    uv sync --directory backend
    if [[ -f frontend/package-lock.json ]]; then npm --prefix frontend ci --no-fund --no-audit
    else npm --prefix frontend install --no-fund --no-audit; fi
    db_ready
    echo "Xong. Chạy: bash scripts/task.sh dev"
    ;;
  dev)
    db_ready
    exec bash scripts/dev.sh
    ;;
  run)
    need uv; need npm
    db_ready
    npm --prefix frontend run build
    port="$(env_get API_PORT 8000)"
    echo "Mở http://localhost:${port}   (Ctrl-C để dừng)"
    exec uv run --directory backend uvicorn app.main:create_app --factory --host 127.0.0.1 --port "$port"
    ;;
  test)
    uvb pytest -q "$@"
    npm --prefix frontend test --silent
    ;;
  lint)
    bash scripts/sync_skill.sh --check
    uvb ruff check app tests alembic
    uvb ruff format --check app tests alembic
    uvb mypy
    npm --prefix frontend run lint
    ;;
  fmt)
    uvb ruff check --fix app tests alembic
    uvb ruff format app tests alembic
    npm --prefix frontend run fix
    ;;
  migrate)
    if [[ "${1:-}" == "down" ]]; then uvb alembic downgrade base; else uvb alembic upgrade head; fi
    ;;
  seed)
    uvb python -m app.db.seed
    ;;
  create-admin|reset-password)
    db_ready >/dev/null
    uvb python -m app.tools.users "$cmd" "$@"
    ;;
  backup)
    uvb python -m app.tools.backup
    ;;
  restore)
    [[ $# -ge 1 ]] || { echo "Dùng: bash scripts/task.sh restore backups/gpu-util-data-<ngày>.zip --yes" >&2; exit 2; }
    zip="$1"; shift
    [[ "$zip" = /* || "$zip" =~ ^[A-Za-z]: ]] || zip="$ROOT/$zip"   # đường dẫn tương đối tính từ gốc repo
    uvb python -m app.tools.restore "$zip" "$@"
    ;;
  sync-skill)
    bash scripts/sync_skill.sh
    ;;
  e2e)
    need npm
    npm --prefix frontend run build
    npm --prefix frontend run e2e -- "$@"   # Playwright dùng Edge có sẵn (E2E_CHANNEL=chrome để đổi); CSDL tạm, không đụng data/
    ;;
  test-pg)
    url="${TEST_PG_URL:-$(env_get TEST_PG_URL '')}"
    if [[ -z "$url" ]]; then
      echo "Chưa có TEST_PG_URL. Cách nhanh: bash scripts/task.sh pg-temp start  rồi chép URL nó in ra vào .env" >&2
      exit 2
    fi
    TEST_PG_URL="$url" uvb pytest -q "$@"
    ;;
  pg-temp)
    pg_temp "${1:-url}"
    ;;
  replay)
    uvb python -m app.tools.replay "$@"
    ;;
  tls-check)
    # đường dẫn tương đối tính từ thư mục người dùng đang đứng (lib.sh đã cd về gốc repo)
    (cd "${OLDPWD:-$ROOT}" && bash "$ROOT/scripts/tls_check.sh" "$@")
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "Lệnh không hợp lệ: $cmd" >&2
    usage >&2
    exit 2
    ;;
esac
