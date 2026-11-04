# Triển khai GĐ2 — Docker Compose (localhost → VM)

Cùng một bộ file (`compose.yaml`) chạy trên máy Windows (Docker Desktop) và trên VM Linux; chỉ khác `.env`.
Dữ liệu GĐ1 (SQLite) chuyển sang PostgreSQL bằng **phát lại các lô** từ file gốc (PLAN ADR-9).

> Có đăng nhập từ G2-M2 (tài khoản riêng, buộc đổi mật khẩu tạm, khóa 5 lần sai/15 phút). Web vẫn **mặc định chỉ mở ở
> `127.0.0.1`** của máy chạy Docker. Mở ra mạng chỉ khi có HTTPS phía trước (mục 4) — HTTP thường thì mật khẩu đi dạng rõ.

## 1. Thành phần

| Service | Image | Việc | Cổng |
|---|---|---|---|
| `web` | build `docker/web.Dockerfile` (Node 22 build → nginx 1.27) | phục vụ giao diện + chuyển `/api` sang `api` | `${HTTP_BIND:-127.0.0.1}:${HTTP_PORT:-8080}` — **cổng duy nhất mở ra ngoài** |
| `api` | build `docker/api.Dockerfile` (Python 3.12 + uv, nhóm `pg`) | FastAPI, cùng code GĐ1; khi khởi động tự `alembic upgrade head` + seed | chỉ trong mạng Docker |
| `db` | `postgres:16-alpine` | CSDL, volume `pgdata` | chỉ trong mạng Docker |
| `backup` | `postgres:16-alpine` | `pg_dump` + nén file gốc mỗi ngày lúc `BACKUP_AT`, giữ `BACKUP_KEEP` bản → `./backups` | — |
| `replay` (profile `tools`) | dùng image của `api` | công cụ 1 lần: phát lại lô GĐ1 → PostgreSQL | — |

Volume: `pgdata` (CSDL) và `uploads` (file gốc `<sha256>.xlsx` của mọi lô — nguồn để xuất Excel và phát lại).
Image không chứa `samples/`, `data/`, `.env` (xem `.dockerignore`).

## 2. Cấu hình `.env`

Thêm vào `.env` ở gốc repo (các biến GĐ1 như `DATABASE_URL=sqlite…` vẫn để nguyên — compose không dùng chúng):

```bash
POSTGRES_PASSWORD=<mật-khẩu-dài-ngẫu-nhiên>   # bắt buộc; thiếu thì compose báo lỗi
SECRET_KEY=<≥ 32 ký tự ngẫu nhiên>            # bắt buộc; ký cookie phiên đăng nhập — đổi khóa = mọi người phải đăng nhập lại
HTTP_PORT=8080                               # cổng web trên máy chạy Docker
# HTTP_BIND=127.0.0.1                        # mặc định; 0.0.0.0 chỉ khi đã có HTTPS phía trước (mục 4)
# COOKIE_SECURE=false                        # true khi web chạy sau HTTPS
# BACKUP_AT=02:00   BACKUP_KEEP=30   BACKUP_DIR=./backups
```
Tạo giá trị ngẫu nhiên (chạy trong Git Bash): `openssl rand -base64 24` (mật khẩu PG), `openssl rand -hex 32` (SECRET_KEY).
Không commit `.env`.

## 3. Chạy trên máy Windows (Docker Desktop)

Cần Docker Desktop đang chạy (biểu tượng cá voi ở khay hệ thống). Các lệnh **chạy trong Git Bash**, tại gốc repo:

```bash
docker compose up -d --build        # lần đầu ~3–5 phút (tải image + build)
docker compose ps                   # db, api: healthy; web: running
```
Tạo tài khoản quản trị đầu tiên (in mật khẩu tạm 1 lần; đăng nhập lần đầu phải đổi):
```bash
docker compose exec api python -m app.tools.users create-admin            # tên mặc định 'admin'
docker compose exec api python -m app.tools.users reset-password admin    # khi quên mật khẩu admin
```
Mở `http://localhost:8080`, đăng nhập, vào **Tài khoản** để tạo tài khoản đầu mối (vai trò *Đầu mối*, mã đầu mối = cột
"Đầu mối sử dụng" trong file thống kê, phạm vi mặc định *Chỉ server của mình*) hoặc *Chỉ xem*. Mật khẩu tạm hiện 1 lần —
gửi cho người dùng qua kênh an toàn. Xem log: `docker compose logs -f api`. Dừng: `docker compose stop` (dữ liệu còn trong volume).

### 3.1 Chuyển dữ liệu GĐ1 sang PostgreSQL (1 lần)

1. Dừng bản GĐ1 nếu đang chạy (`task.sh run`/`dev`), rồi sao lưu: `bash scripts/task.sh backup` → `backups/gpu-util-data-<ngày>.zip`.
2. Giải nén vào 1 thư mục riêng, vd `gd1/` → có `gd1/data/app.db` và `gd1/data/uploads/`.
   (Dùng thẳng `./data` cũng được — đó là giá trị mặc định của `GD1_DATA` — nhưng bản sao thì an toàn hơn.)
3. Phát lại (CSDL đích phải **chưa có lô nào** — tức là chạy ngay sau lần `up` đầu tiên):
   ```bash
   docker compose build api
   GD1_DATA=./gd1/data docker compose run --rm replay
   ```
   Kết quả mong đợi: `Đã phát lại N lô (nguồn → đích): #1→#1, …` và dòng
   `Kiểm: nguồn = đích (số lô, util_effective, …, app_user, server_note, audit_log).` Tài khoản của bản native cũng được chép
   (giữ mật khẩu); tài khoản trùng tên đã tạo sẵn ở đích (vd `admin` từ `create-admin`) được giữ nguyên.
   Lô `staged`/`failed`/`discarded` không có dữ liệu hiệu lực nên được bỏ qua; số lô ở đích có thể khác số ở nguồn (ghi trong
   cột ghi chú của lô: `Phát lại từ lô #…`).
4. Mở web, đối chiếu vài số với bản GĐ1 (Tổng quan, Cảnh báo T=40).

Muốn làm lại từ đầu: `docker compose down -v` (**xóa** volume `pgdata` + `uploads`), rồi `up -d` và phát lại.

## 4. Lên VM Linux

Yêu cầu: Ubuntu 22.04/24.04 (hoặc tương đương), ≥ 2 vCPU, 4 GB RAM, 20 GB đĩa; Docker Engine + plugin `docker compose`
do quản trị VM cài theo hướng dẫn chính thức của Docker. Không cần Python/Node trên VM.

```bash
# trên VM
git clone <repo> gpu-util-admin && cd gpu-util-admin    # hoặc chép thư mục repo, KHÔNG chép samples/ data/ .env
cp .env.example .env && nano .env                       # đặt POSTGRES_PASSWORD (mạnh, khác máy local)
docker compose up -d --build
```
Chuyển dữ liệu: chép file `gpu-util-data-<ngày>.zip` lên VM (`scp`), giải nén, chạy bước 3.1 (mục 3) trên VM.

Tạo admin trên VM: `docker compose exec api python -m app.tools.users create-admin` (mục 3).

Truy cập khi web trên VM vẫn chỉ nghe 127.0.0.1 — đường hầm SSH từ máy mình:
```bash
ssh -N -L 8080:127.0.0.1:8080 <user>@<vm>     # rồi mở http://localhost:8080 trên máy mình
```
Mở cho đầu mối dùng qua mạng nội bộ — **cần HTTPS**, 2 cách (từng bước ở **DEPLOY.md §8**):
- **A. Chứng chỉ `.pem` gắn vào nginx của app** — `compose.tls.yaml`: kiểm file bằng `bash scripts/task.sh tls-check <cert> <key>
  <tên-miền>`, thêm `COMPOSE_FILE=compose.yaml:compose.tls.yaml`, `TLS_CERT_FILE`, `TLS_KEY_FILE`, `HTTPS_BIND`, `HTTPS_PORT`
  vào `.env`, rồi `docker compose up -d` (cổng HTTP tự chuyển hướng sang HTTPS, `COOKIE_SECURE=true` tự bật).
- **B. Proxy TLS của hạ tầng phía trước**: `HTTP_BIND=<IP nội bộ VM>`, `COOKIE_SECURE=true`, `TRUSTED_PROXIES=<IP proxy>`,
  firewall chỉ cho IP proxy, rồi `docker compose up -d`.
Không mở qua HTTP thường: mật khẩu và cookie phiên sẽ đi dạng rõ trên mạng.

## 5. Sao lưu & khôi phục

- Tự động: service `backup` chạy mỗi ngày lúc `BACKUP_AT` (giờ `TZ`), giữ `BACKUP_KEEP` bản mỗi loại trong `./backups`:
  `gpu-util-db-<ngày-giờ>.dump` (pg_dump `-Fc`) + `gpu-util-uploads-<ngày-giờ>.tar.gz` (file gốc). Chép thư mục này ra ngoài VM định kỳ.
- Sao lưu ngay: `docker compose run --rm backup now`.
- Khôi phục (CSDL + file gốc của cùng 1 lần sao lưu):
  ```bash
  docker compose stop web api backup
  docker compose exec -T db pg_restore --clean --if-exists -U gpu -d gpu_util < backups/gpu-util-db-<ngày-giờ>.dump
  docker compose run --rm --no-deps --entrypoint sh -v "$PWD/backups:/b:ro" api \
    -c 'tar -xzf /b/gpu-util-uploads-<ngày-giờ>.tar.gz -C /data'
  docker compose start api web backup
  ```
  (`-U gpu -d gpu_util` = `POSTGRES_USER`/`POSTGRES_DB` nếu đã đổi.)

### 5.1 Bản chạy native (Windows, SQLite)

Sao lưu: `bash scripts/task.sh backup` → `backups/gpu-util-data-<ngày-giờ>.zip` (app.db + file gốc; an toàn khi app đang chạy).
Khôi phục (chạy trong Git Bash): **dừng app** (`task.sh run`/`dev`) rồi
```bash
bash scripts/task.sh restore backups/gpu-util-data-<ngày-giờ>.zip --yes
```
Trước khi ghi đè, dữ liệu hiện tại được sao lưu thành `backups/truoc-khoi-phuc-<ngày-giờ>.zip`; zip được kiểm (đúng cấu trúc,
`integrity_check`) trước khi động vào `data/`. `data/secret_key` không nằm trong bản sao lưu → sau khi khôi phục sang máy khác,
mọi người đăng nhập lại (tài khoản, mật khẩu giữ nguyên).

## 6. Nâng cấp phiên bản

```bash
docker compose run --rm backup now          # luôn sao lưu trước
git pull                                    # hoặc chép bản mới
docker compose up -d --build                # api tự chạy migration (alembic upgrade head) khi khởi động
docker compose ps && docker compose logs --tail 50 api
```
Quay lại bản cũ: checkout bản cũ + khôi phục bản sao lưu vừa tạo (mục 5) — migration mới có thể không lùi được dữ liệu.

## 7. Phát triển bằng Docker (tùy chọn)

`task.sh dev` (native, mục README) vẫn là cách chính trên Windows. Muốn chạy cả stack trong Docker với tự tải lại:
```bash
docker compose -f compose.yaml -f compose.dev.yaml up --build
```
Web (Vite) `http://localhost:5173`, API `http://127.0.0.1:8000`, PostgreSQL `127.0.0.1:15432` (15432 để không đụng PostgreSQL
cài sẵn trên máy). Code bind-mount từ repo; thư viện nằm trong image/volume. Mọi cổng chỉ bind 127.0.0.1.

## 8. Test trên PostgreSQL

Bộ test API chạy trên cả SQLite và PostgreSQL khi có `TEST_PG_URL` (URL quản trị có quyền `CREATE DATABASE`; mỗi test tạo/xóa
database riêng). Hai cách có PostgreSQL cho test (chạy trong Git Bash):
```bash
bash scripts/task.sh pg-temp start   # cụm tạm từ PostgreSQL đã cài (initdb/pg_ctl), 127.0.0.1:55432, dữ liệu data/pg-temp
bash scripts/task.sh test-pg         # TEST_PG_URL lấy từ biến môi trường hoặc .env
bash scripts/task.sh pg-temp stop
```
Hoặc dùng `db` của compose.dev.yaml: `TEST_PG_URL=postgresql+psycopg://gpu:<mật khẩu>@127.0.0.1:15432/postgres`.

## 9. Sự cố thường gặp

| Hiện tượng | Nguyên nhân / cách xử lý |
|---|---|
| `required variable POSTGRES_PASSWORD is missing` | Chưa đặt `POSTGRES_PASSWORD` trong `.env` |
| `failed to connect to the docker API … dockerDesktopLinuxEngine` | Docker Desktop chưa chạy |
| `web` không lên, `api` unhealthy | `docker compose logs api` — thường do sai mật khẩu sau khi đã tạo volume `pgdata` (mật khẩu chỉ áp dụng lần tạo đầu) |
| Cổng 8080/15432 bị chiếm | Đổi `HTTP_PORT` / `PG_PORT` trong `.env` |
| `replay`: `CSDL đích đã có lô import` | Chỉ phát lại vào CSDL trống — xem cuối mục 3.1 |
| `replay`: `Thiếu file gốc` / `không khớp sha256` | Bản sao `uploads/` thiếu hoặc hỏng — giải nén lại từ file sao lưu GĐ1 |
| `required variable SECRET_KEY is missing` | Chưa đặt `SECRET_KEY` (≥ 32 ký tự) trong `.env` |
| Trang đăng nhập báo "Chưa có tài khoản nào" | Chạy `create-admin` (mục 3) |
| Quên mật khẩu admin / admin bị khóa do nhập sai | `docker compose exec api python -m app.tools.users reset-password admin` |
| Đăng nhập xong lại bị đẩy về trang đăng nhập | `COOKIE_SECURE=true` nhưng đang mở bằng `http://` → bỏ (false) hoặc dùng HTTPS |
| `required variable TLS_CERT_FILE is missing` | Đã bật `compose.tls.yaml` (qua `COMPOSE_FILE` hoặc `-f`) mà chưa khai đường dẫn chứng chỉ trong `.env` |
| `web` khởi động lại liên tục, log `gpu-util: LỖI — bật HTTPS … thiếu` | Đường dẫn `TLS_CERT_FILE`/`TLS_KEY_FILE` sai hoặc file rỗng (Docker tạo thư mục rỗng khi đường dẫn không tồn tại) |
| log `web`: `PEM_read_bio_PrivateKey` / `key values mismatch` / hỏi passphrase | Khóa có passphrase hoặc nhầm cặp — chạy `task.sh tls-check` (DEPLOY.md §8.1) |
| Trình duyệt báo chứng chỉ không tin cậy / sai tên | Thiếu chuỗi trung gian, CA nội bộ chưa cài trên máy người dùng, hoặc tên gõ không có trong SAN |
