#!/usr/bin/env bash
# Kiểm file chứng chỉ .pem trước khi bật HTTPS (compose.tls.yaml, DEPLOY.md §8). Chỉ ĐỌC file, không gửi đi đâu.
#   bash scripts/tls_check.sh <cert.pem> [key.pem] [tên-miền-hoặc-IP]
#   (= bash scripts/task.sh tls-check …). Không truyền key → coi khóa nằm chung trong file cert.
# Kiểm: đọc được · còn hạn (cảnh báo < 30 ngày) · khóa không passphrase · khóa khớp chứng chỉ · tên miền/IP có trong SAN ·
# có chuỗi trung gian. Thoát 1 khi có LỖI (nginx sẽ không chạy / trình duyệt sẽ chặn), 0 khi chỉ có CẢNH BÁO.
set -uo pipefail

[[ $# -ge 1 ]] || { echo "Dùng: bash scripts/task.sh tls-check <cert.pem> [key.pem] [tên-miền-hoặc-IP]" >&2; exit 2; }
command -v openssl >/dev/null 2>&1 || { echo "Thiếu 'openssl' (Git Bash có sẵn; Ubuntu: gói openssl)." >&2; exit 2; }
# OPENSSL_CONF trỏ tới file không còn (vd bộ cài psqlODBC trên Windows) → openssl báo lỗi → bỏ biến, dùng cấu hình mặc định
if [[ -n "${OPENSSL_CONF:-}" && ! -f "$OPENSSL_CONF" ]]; then unset OPENSSL_CONF; fi

cert="$1"; key="${2:-$1}"; host="${3:-}"
if [[ $# -eq 2 && ! -f "$2" ]]; then key="$1"; host="$2"; fi   # tls-check cert.pem tên-miền (khóa chung file)
errors=0; warns=0
ok()   { echo "  OK        $*"; }
warn() { echo "  CẢNH BÁO  $*"; warns=$((warns + 1)); }
fail() { echo "  LỖI       $*"; errors=$((errors + 1)); }

echo "Chứng chỉ: $cert"
echo "Khóa riêng: $key"
for f in "$cert" "$key"; do
  [[ -r "$f" ]] || { fail "không đọc được file $f"; echo "→ Có lỗi."; exit 1; }
done

n_certs=$(grep -c -- "-----BEGIN CERTIFICATE-----" "$cert" || true)
if [[ "$n_certs" -eq 0 ]]; then
  fail "file chứng chỉ không có khối '-----BEGIN CERTIFICATE-----' (sai định dạng; nếu là .crt/.cer dạng DER: openssl x509 -inform der -in X -out cert.pem)"
  echo "→ Có lỗi."; exit 1
fi
if ! openssl x509 -in "$cert" -noout 2>/dev/null; then
  fail "openssl không đọc được chứng chỉ đầu tiên trong file"; echo "→ Có lỗi."; exit 1
fi

subject=$(openssl x509 -in "$cert" -noout -subject 2>/dev/null | sed 's/^subject= *//')
issuer=$(openssl x509 -in "$cert" -noout -issuer 2>/dev/null | sed 's/^issuer= *//')
end=$(openssl x509 -in "$cert" -noout -enddate 2>/dev/null | sed 's/^notAfter=//')
san=$(openssl x509 -in "$cert" -noout -ext subjectAltName 2>/dev/null | tail -n +2 | sed 's/^ *//')
keyinfo=$(openssl x509 -in "$cert" -noout -text 2>/dev/null | grep -m1 "Public-Key" | sed 's/^ *//')
echo "  Chủ thể:   $subject"
echo "  Cấp bởi:   $issuer"
echo "  Hết hạn:   $end"
echo "  SAN:       ${san:-(không có)}"
echo "  Khóa:      ${keyinfo:-?}"

if ! openssl x509 -in "$cert" -noout -checkend 0 >/dev/null 2>&1; then
  fail "chứng chỉ ĐÃ HẾT HẠN ($end)"
elif ! openssl x509 -in "$cert" -noout -checkend $((30 * 86400)) >/dev/null 2>&1; then
  warn "chứng chỉ hết hạn trong < 30 ngày ($end) — xin gia hạn"
else
  ok "còn hạn tới $end"
fi
[[ -n "$san" ]] || warn "không có SubjectAltName — trình duyệt hiện đại báo lỗi tên miền dù CN đúng"

if grep -q -- "ENCRYPTED" "$key"; then
  fail "khóa riêng có passphrase — nginx không tự mở được. Gỡ: openssl pkey -in key.pem -out key-nopass.pem (giữ quyền 600)"
elif ! grep -q -- "PRIVATE KEY-----" "$key"; then
  fail "không thấy khối '... PRIVATE KEY-----' trong $key"
elif ! openssl pkey -in "$key" -passin pass: -noout 2>/dev/null; then
  fail "openssl không đọc được khóa riêng"
else
  cert_pub=$(openssl x509 -in "$cert" -noout -pubkey 2>/dev/null | openssl pkey -pubin -outform der 2>/dev/null | openssl dgst -sha256 | sed 's/^.*= *//')
  key_pub=$(openssl pkey -in "$key" -passin pass: -pubout -outform der 2>/dev/null | openssl dgst -sha256 | sed 's/^.*= *//')
  if [[ -n "$cert_pub" && "$cert_pub" == "$key_pub" ]]; then ok "khóa riêng khớp chứng chỉ"
  else fail "khóa riêng KHÔNG khớp chứng chỉ (nhầm cặp file?)"; fi
  if [[ "$key" == "$cert" ]]; then warn "khóa nằm chung file với chứng chỉ — nên tách: TLS_KEY_FILE riêng, quyền 600"; fi
fi

if [[ -n "$host" ]]; then
  if [[ "$host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then res=$(openssl x509 -in "$cert" -noout -checkip "$host" 2>&1)
  else res=$(openssl x509 -in "$cert" -noout -checkhost "$host" 2>&1); fi
  if [[ "$res" == *"does match"* ]]; then ok "'$host' có trong chứng chỉ"
  else fail "'$host' KHÔNG có trong chứng chỉ — người dùng phải vào đúng tên trong SAN"; fi
else
  warn "chưa kiểm tên miền — thêm tham số thứ 3 (tên miền hoặc IP người dùng sẽ gõ)"
fi

if [[ "$subject" == "$issuer" ]]; then
  warn "chứng chỉ tự ký — trình duyệt chỉ tin khi đã cài chính chứng chỉ này (chỉ dùng để thử)"
elif [[ "$n_certs" -eq 1 ]]; then
  warn "file chỉ có 1 chứng chỉ (thiếu chuỗi trung gian) — ổn nếu CA nội bộ cấp trực tiếp và đã cài trên máy người dùng; nếu không, ghép: cat cert.pem intermediate.pem > fullchain.pem"
else
  ok "có $n_certs chứng chỉ trong file (chứng chỉ + chuỗi trung gian)"
fi

echo
if [[ $errors -gt 0 ]]; then echo "→ Có $errors lỗi, $warns cảnh báo — sửa lỗi trước khi bật HTTPS."; exit 1; fi
echo "→ Dùng được ($warns cảnh báo). Đặt TLS_CERT_FILE / TLS_KEY_FILE trong .env (DEPLOY.md §8)."
