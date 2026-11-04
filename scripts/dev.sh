#!/usr/bin/env bash
# Phát triển: API (tự khởi động lại khi sửa .py) + Vite (HMR) chạy cùng lúc; Ctrl-C dừng cả hai.
# Dùng `concurrently` (devDependency của frontend) để dừng trọn cây tiến trình trên cả Windows lẫn Linux.
# API dùng `watchfiles` thay `uvicorn --reload` (lý do: xem backend/app/devserver.py).
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

need uv; need npm
CONCURRENTLY="frontend/node_modules/.bin/concurrently"
[[ -e "$CONCURRENTLY" ]] || { echo "Chưa cài frontend — chạy: bash scripts/task.sh setup" >&2; exit 1; }

api_port="$(env_get API_PORT 8000)"
web_port="$(env_get WEB_PORT 5173)"
echo "API : http://127.0.0.1:${api_port}/api/v1/healthz   (đặc tả: /api/v1/openapi.json)"
echo "Web : http://localhost:${web_port}                    (Ctrl-C dừng cả hai)"

exec "$CONCURRENTLY" --kill-others --names api,web --prefix-colors blue,green \
  "uv run --directory backend watchfiles --filter python --target-type function app.devserver.serve app gpu_core" \
  "npm --prefix frontend run dev"
