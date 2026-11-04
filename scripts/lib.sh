#!/usr/bin/env bash
# Hàm dùng chung cho scripts/*.sh (source, không chạy trực tiếp).
# Chạy được trong Git Bash (Windows) và bash Linux/WSL/VM.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PYTHONUTF8=1        # Windows: in tiếng Việt ra console không lỗi cp1252
export UV_LINK_MODE=copy   # cache uv và repo có thể nằm khác ổ đĩa (Windows) → không hardlink được

# env_get KEY MẶC_ĐỊNH — đọc 1 khóa trong .env (chịu được CRLF, dấu nháy). Không export cả file:
# backend (pydantic-settings) và Vite tự đọc .env; export TZ=Asia/... sẽ làm Python trên Windows hiểu sai giờ.
env_get() {
  local key="$1" def="$2" line val=""
  if [[ -f .env ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      line="${line%$'\r'}"
      if [[ "$line" =~ ^[[:space:]]*${key}[[:space:]]*=(.*)$ ]]; then val="${BASH_REMATCH[1]}"; fi
    done < .env
  fi
  val="${val#"${val%%[![:space:]]*}"}"; val="${val%"${val##*[![:space:]]}"}"
  val="${val#\"}"; val="${val%\"}"; val="${val#\'}"; val="${val%\'}"
  printf '%s\n' "${val:-$def}"
}

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "Thiếu '$1' trong PATH — xem README mục 'Chạy GĐ1'." >&2; exit 1; }
}
