#!/usr/bin/env bash
# Đồng bộ thư viện lõi backend/gpu_core vào skill (skill phải tự chứa để upload claude.ai).
# Chạy sau MỌI thay đổi trong backend/gpu_core.  Kiểm tra: scripts/sync_skill.sh --check
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/backend/gpu_core"
DST="$ROOT/.claude/skills/gpu-util-vtnet/scripts/gpu_core"
if [[ "${1:-}" == "--check" ]]; then
  diff -r -x '__pycache__' "$SRC" "$DST" >/dev/null && echo "skill đã đồng bộ" || { echo "LỆCH: chạy scripts/sync_skill.sh"; exit 1; }
  exit 0
fi
rm -rf "$DST" && mkdir -p "$DST"
cp "$SRC"/*.py "$DST"/
echo "Đã đồng bộ gpu_core -> skill"
