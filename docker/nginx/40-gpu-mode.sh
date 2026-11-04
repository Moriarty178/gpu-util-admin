#!/bin/sh
# Chạy trong entrypoint của image nginx (/docker-entrypoint.d) trước khi nginx khởi động. Chọn chế độ:
#   GPU_TLS=1  → HTTPS (cần /etc/nginx/tls/cert.pem + key.pem, compose.tls.yaml gắn vào) + HSTS + cổng 80 chuyển hướng
#   còn lại    → HTTP như cũ
# TRUSTED_PROXIES="10.0.0.5 10.1.0.0/24" (tùy chọn): proxy của hạ tầng đứng phía trước → lấy IP người dùng từ
# X-Forwarded-For do proxy đó gửi (chỉ tin các địa chỉ này).
set -eu
GPU=/etc/nginx/gpu
CONF=/etc/nginx/conf.d/default.conf

: > "$GPU/realip.conf"
if [ -n "${TRUSTED_PROXIES:-}" ]; then
  for p in $(echo "$TRUSTED_PROXIES" | tr ',' ' '); do
    echo "set_real_ip_from $p;" >> "$GPU/realip.conf"
  done
  { echo "real_ip_header X-Forwarded-For;"; echo "real_ip_recursive on;"; } >> "$GPU/realip.conf"
  echo "gpu-util: tin proxy phía trước: $TRUSTED_PROXIES"
fi

if [ "${GPU_TLS:-0}" = "1" ]; then
  for f in /etc/nginx/tls/cert.pem /etc/nginx/tls/key.pem; do
    # -f: đường dẫn trên máy không tồn tại thì Docker gắn vào 1 THƯ MỤC rỗng → phải là file, có nội dung
    if [ ! -f "$f" ] || [ ! -s "$f" ]; then
      echo "gpu-util: LỖI — bật HTTPS (GPU_TLS=1) nhưng thiếu/không đọc được $f. Kiểm TLS_CERT_FILE / TLS_KEY_FILE trong .env." >&2
      exit 1
    fi
  done
  port="${PUBLIC_HTTPS_PORT:-443}"
  suffix=""
  [ "$port" = "443" ] || suffix=":$port"
  sed "s/__HTTPS_PORT_SUFFIX__/$suffix/" "$GPU/https.conf" > "$CONF"
  # HSTS 180 ngày (không includeSubDomains): trình duyệt chỉ vào site này qua HTTPS
  echo 'add_header Strict-Transport-Security "max-age=15552000" always;' > "$GPU/tls-headers.conf"
  echo "gpu-util: chế độ HTTPS (cổng công khai $port)"
else
  cp "$GPU/http.conf" "$CONF"
  : > "$GPU/tls-headers.conf"
  echo "gpu-util: chế độ HTTP"
fi
