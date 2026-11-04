#!/bin/sh
# Sao lưu GĐ2 (PLAN §9): pg_dump (định dạng custom) + nén file gốc đã nhập; giữ BACKUP_KEEP bản mới nhất mỗi loại.
#   loop : chạy nền, sao lưu mỗi ngày lúc BACKUP_AT (giờ TZ)
#   now  : sao lưu ngay 1 lần (docker compose run --rm backup now)
set -eu
OUT=/backups
KEEP="${BACKUP_KEEP:-30}"
AT="${BACKUP_AT:-02:00}"

prune() {  # $1 = mẫu tên file
  ls -1t $OUT/$1 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r f; do rm -f -- "$f"; done
}

run_once() {
  stamp="$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$OUT"
  pg_dump -Fc -f "$OUT/.gpu-util-db-$stamp.dump.part"
  mv "$OUT/.gpu-util-db-$stamp.dump.part" "$OUT/gpu-util-db-$stamp.dump"
  tar -czf "$OUT/.gpu-util-uploads-$stamp.tar.gz.part" -C /data uploads
  mv "$OUT/.gpu-util-uploads-$stamp.tar.gz.part" "$OUT/gpu-util-uploads-$stamp.tar.gz"
  prune 'gpu-util-db-*.dump'
  prune 'gpu-util-uploads-*.tar.gz'
  echo "$(date '+%F %T') Đã sao lưu: gpu-util-db-$stamp.dump + gpu-util-uploads-$stamp.tar.gz"
}

case "${1:-loop}" in
  now) run_once ;;
  loop)
    echo "Sao lưu hằng ngày lúc $AT ($TZ), giữ $KEEP bản → $OUT"
    last=""
    while true; do
      if [ "$(date +%H:%M)" = "$AT" ] && [ "$(date +%F)" != "$last" ]; then
        run_once || echo "$(date '+%F %T') LỖI sao lưu" >&2
        last="$(date +%F)"
      fi
      sleep 30
    done
    ;;
  *) echo "Dùng: backup.sh loop|now" >&2; exit 2 ;;
esac
