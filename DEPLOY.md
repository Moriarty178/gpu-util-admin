# DEPLOY.md — Sổ tay triển khai GPU Util Admin lên server

> **Đọc file này trước khi hướng dẫn deploy.** Viết cho người vận hành *và* cho mọi công cụ AI (Claude Code, Codex, Copilot…)
> đọc repo để dẫn từng bước. Chi tiết lệnh khôi phục / dev / sự cố: [docs/DEPLOY_VM.md](docs/DEPLOY_VM.md).
> Bối cảnh nghiệp vụ: [CONTEXT.md](CONTEXT.md) · kiến trúc & milestone: [PLAN.md](PLAN.md) · quy tắc code: [CLAUDE.md](CLAUDE.md).
>
> **Giữ file này luôn đúng**: thay đổi nào ảnh hưởng deploy (biến môi trường, thư viện, cổng, image, script, bước chuyển dữ liệu,
> kết quả đã kiểm / chưa kiểm) → cập nhật mục liên quan + mục 12 "Trạng thái & nhật ký deploy" ngay trong cùng việc đó.

---

## 0. Tóm tắt 1 phút

- Ứng dụng web nội bộ theo dõi tải GPU của TTCN-VTT: admin upload file tải VTNet hằng tháng + file thống kê server → xem
  biểu đồ, cảnh báo theo ngưỡng T%, so sánh kỳ, báo cáo tháng (.pptx).
- **Hai cách chạy** cùng một mã nguồn:
  | | Native (đang dùng trên máy Windows của admin) | Docker Compose (dùng cho **server thật**) |
  |---|---|---|
  | CSDL | SQLite `data/app.db` | PostgreSQL 16 (volume `pgdata`) |
  | File gốc đã nhập | `data/uploads/<sha256>.xlsx` | volume `uploads` |
  | Lệnh | `bash scripts/task.sh run` → http://localhost:8000 | `docker compose up -d --build` → http://localhost:8080 |
- **Deploy = 4 việc**: (1) chuẩn bị VM + Docker, (2) đưa mã nguồn / image lên, (3) tạo `.env` có bí mật, (4) `up` rồi
  **phát lại dữ liệu** từ bản native (`replay`), tạo tài khoản admin, kiểm số.
- Mặc định **chỉ nghe 127.0.0.1**. Mở cho người khác qua mạng chỉ khi đã có **HTTPS** phía trước (mục 8).

---

## 1. Kiến trúc khi chạy trên server

```
 Trình duyệt ──HTTPS (proxy/TLS của hạ tầng, mục 8)──▶ web (nginx 1.27, cổng HTTP_PORT, mặc định 127.0.0.1:8080)
                                                          │  phục vụ giao diện React đã build (frontend/dist)
                                                          │  /api/*  ──proxy──▶ api (FastAPI, Python 3.12, cổng 8000 nội bộ)
                                                          │                       │ khi khởi động: alembic upgrade head + seed
                                                          │                       ├──▶ db (postgres:16-alpine, volume pgdata)
                                                          │                       └──▶ volume uploads (file gốc .xlsx)
 backup (postgres:16-alpine) ── mỗi ngày BACKUP_AT: pg_dump + nén uploads ──▶ ./backups trên VM
 replay (image api, profile tools) ── chạy 1 lần: phát lại lô từ bản native (app.db + uploads) vào PostgreSQL
```

| Service | Ý nghĩa | Cổng / dữ liệu |
|---|---|---|
| `web` | nginx: giao diện + chuyển `/api` sang `api`; gắn header bảo mật, CSP chỉ `'self'` (không CDN); upload ≤ 25 MB | **cổng duy nhất mở ra ngoài**: `${HTTP_BIND:-127.0.0.1}:${HTTP_PORT:-8080}` |
| `api` | toàn bộ logic (tính toán qua `backend/gpu_core`), đăng nhập, phân quyền, nhập file, xuất Excel/pptx. **1 worker** (cache phân tích nằm trong bộ nhớ tiến trình — đừng tăng `--workers`) | chỉ trong mạng Docker; ghi file vào volume `uploads` |
| `db` | PostgreSQL 16, UTF-8; mật khẩu lấy từ `.env` **chỉ ở lần tạo volume đầu tiên** | volume `pgdata` |
| `backup` | sao lưu tự động hằng ngày, giữ `BACKUP_KEEP` bản mỗi loại | ghi `./backups` (bind-mount trên VM) |
| `replay` | công cụ 1 lần chuyển dữ liệu native → PostgreSQL (không chạy khi `up`) | đọc `${GD1_DATA:-./data}` |

Hai volume **`pgdata` + `uploads` là toàn bộ dữ liệu** — phải sao lưu cả hai cùng thời điểm (service `backup` làm việc này).

---

## 2. Cấu trúc repo — phần nào dùng khi deploy

| Đường dẫn | Ý nghĩa | Lên server? |
|---|---|---|
| `compose.yaml` | định nghĩa 5 service ở trên — **file chính khi deploy** | ✅ |
| `compose.dev.yaml` | chỉ để phát triển (tự tải lại, mở PG 127.0.0.1:15432) — **không dùng trên server** | (đi kèm repo, không chạy) |
| `docker/api.Dockerfile` | image api: `python:3.12-slim-bookworm` + `uv 0.13.0`, `uv sync --frozen --no-dev --extra pg`, chạy user `app` (uid 10001) | ✅ (khi build trên VM) |
| `docker/web.Dockerfile` | image web: `node:22-alpine` build frontend → `nginx:1.27-alpine` | ✅ (khi build trên VM) |
| `docker/api-entrypoint.sh` | trước khi chạy api: `alembic upgrade head` + `python -m app.db.seed` (idempotent) | ✅ (nằm trong image) |
| `docker/nginx/` | `app.conf` (proxy `/api`, cache `/assets`, upload ≤ 25 MB) · `headers.conf` (CSP, header bảo mật) · `http.conf` / `https.conf` (2 chế độ) · `40-gpu-mode.sh` (chọn chế độ lúc khởi động, HSTS, `TRUSTED_PROXIES`) | ✅ (nằm trong image) |
| `compose.tls.yaml` | lớp HTTPS: cổng 443 + gắn chứng chỉ `.pem` vào `web`, `COOKIE_SECURE=true` cho `api` (mục 8) | ✅ khi bật HTTPS |
| `scripts/tls_check.sh` | `task.sh tls-check`: kiểm file `.pem` (hạn, khớp khóa, SAN, chuỗi, passphrase) | ✅ (chạy bằng bash, cần `openssl`) |
| `docker/backup.sh` | sao lưu `loop` (hằng ngày) / `now` (ngay) — **mount từ thư mục repo**, phải có trên VM | ✅ **bắt buộc** |
| `.env.example` | mẫu biến môi trường → chép thành `.env` trên VM | ✅ |
| `.dockerignore` | loại `samples/ data/ backups/ .env node_modules .venv` khỏi image | ✅ |
| `backend/` | mã FastAPI + `gpu_core` + migration Alembic (`backend/alembic/`) + seed (`backend/seeds/ip_links.csv`) | ✅ |
| `frontend/` | React + Vite (build trong image web) | ✅ |
| `scripts/task.sh` | lệnh native (Windows/Git Bash): setup, run, test, backup, replay… — trên VM chỉ cần nếu chạy native | tùy |
| `samples/`, `data/`, `backups/`, `.env` | **dữ liệu nội bộ / bí mật** — không đưa vào image, không commit | ❌ (dữ liệu chỉ đi qua file sao lưu, mục 6) |
| `.claude/` | skill & cấu hình riêng của Claude Code | không cần |

---

## 3. Chuẩn bị server (VM)

**Phần cứng tối thiểu**: 2 vCPU, 4 GB RAM, 20 GB đĩa (dữ liệu thật hiện ~0,6 MB file gốc / tháng; image api ~1 GB, web ~80 MB).
**Hệ điều hành**: Ubuntu 22.04/24.04 x86_64 (hoặc Linux tương đương). Image build trên Windows/Docker Desktop là `linux/amd64`
→ VM phải là **x86_64** nếu mang image sang (mục 5B).

**Phần mềm** (quản trị VM cài theo hướng dẫn chính thức của Docker — repo không tự cài):
- Docker Engine ≥ 24 + plugin `docker compose` (v2). Kiểm: `docker version` và `docker compose version`.
- **Không cần** Python, Node, PostgreSQL trên VM (tất cả nằm trong image).
- `openssl` (tạo bí mật), `unzip`/`tar` (giải nén bản sao lưu), `ssh`/`scp` (chép file).

**Mạng**:
- Build trên VM (mục 5A) cần ra Internet tới: Docker Hub (`python`, `node`, `nginx`, `postgres`), `ghcr.io` (`astral-sh/uv`),
  PyPI, npm registry. Nếu VM không ra được Internet → dùng mục 5B (build ở máy có mạng rồi mang image sang).
- Lúc chạy **không** tải gì từ ngoài (không CDN; `/docs` Swagger đã tắt; đặc tả API ở `/api/v1/openapi.json`, cần đăng nhập).
- Firewall: chỉ mở cổng web (mặc định 8080 trên 127.0.0.1) hoặc cổng HTTPS của reverse proxy cho dải IP nội bộ cần thiết.

**Người dùng hệ thống**: user thuộc nhóm `docker` (hoặc dùng `sudo docker …` theo chính sách VM). Thư mục ví dụ `/opt/gpu-util-admin`.

---

## 4. Biến môi trường `.env` (đặt ở thư mục gốc repo trên VM)

Tạo: `cp .env.example .env` rồi sửa. **Không commit, không gửi `.env` qua kênh không an toàn.**

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|
| `POSTGRES_PASSWORD` | ✅ | — | mật khẩu PostgreSQL. Tạo: `openssl rand -base64 24`. Chỉ có hiệu lực lần tạo volume `pgdata` đầu tiên |
| `SECRET_KEY` | ✅ | — | ký cookie phiên đăng nhập (≥ 32 ký tự). Tạo: `openssl rand -hex 32`. Đổi khóa = mọi người phải đăng nhập lại |
| `HTTP_PORT` | | `8080` | cổng web trên VM |
| `HTTP_BIND` | | `127.0.0.1` | địa chỉ nghe cổng HTTP. Chế độ B (proxy hạ tầng): IP nội bộ VM. Chế độ A (HTTPS tại nginx): cổng này chỉ chuyển hướng |
| `COOKIE_SECURE` | | `false` | `true` khi người dùng vào qua HTTPS (cookie chỉ gửi qua TLS). Đặt `true` mà vào bằng `http://` → không đăng nhập được. `compose.tls.yaml` tự đặt `true` |
| `COMPOSE_FILE` | chế độ A | — | `compose.yaml:compose.tls.yaml` (Windows `;`) → mọi lệnh `docker compose` tự áp HTTPS |
| `TLS_CERT_FILE` / `TLS_KEY_FILE` | chế độ A | — | đường dẫn file chứng chỉ (fullchain) / khóa riêng `.pem` trên VM, ngoài repo |
| `HTTPS_BIND` / `HTTPS_PORT` | | `127.0.0.1` / `443` | địa chỉ + cổng HTTPS (chế độ A). `0.0.0.0`/IP nội bộ để mở cho đầu mối |
| `TRUSTED_PROXIES` | | (rỗng) | IP/CIDR proxy hạ tầng phía trước (cách nhau dấu cách/phẩy) → Nhật ký ghi đúng IP người dùng |
| `POSTGRES_USER` / `POSTGRES_DB` | | `gpu` / `gpu_util` | tên user / database PostgreSQL |
| `TZ` | | `Asia/Ho_Chi_Minh` | múi giờ container (giờ mẫu tải = giờ VN, giờ chạy backup) |
| `LOG_LEVEL` | | `INFO` | mức log api |
| `BACKUP_AT` / `BACKUP_KEEP` / `BACKUP_DIR` | | `02:00` / `30` / `./backups` | giờ sao lưu hằng ngày, số bản giữ, thư mục ghi |
| `GD1_DATA` | | `./data` | thư mục chứa `app.db` + `uploads/` của bản native — chỉ cho lệnh `replay` |
| `DATABASE_URL`, `UPLOAD_DIR`, `API_PORT`, `WEB_PORT` | | (SQLite) | **chỉ cho chạy native** — compose tự đặt `DATABASE_URL` trỏ vào `db`, không cần sửa |

---

## 5. Đưa ứng dụng lên VM — chọn 1 trong 2 cách

Repo hiện **không phải git repo** → mang mã nguồn bằng file nén. Trên máy Windows (chạy trong **Git Bash**, tại gốc repo):
```bash
tar -czf ../gpu-util-src.tar.gz --exclude=./samples --exclude=./data --exclude=./backups --exclude=./.env \
  --exclude=./backend/.venv --exclude=./frontend/node_modules --exclude=./frontend/dist --exclude=./.claude \
  --exclude=./backend/.mypy_cache --exclude=./backend/.ruff_cache --exclude=./backend/.pytest_cache \
  --exclude=./frontend/test-results --exclude=./frontend/playwright-report --exclude=__pycache__ .
tar -tzf ../gpu-util-src.tar.gz | grep -E 'samples/|data/app|\.env$|backups/' || echo "OK: không có dữ liệu nội bộ"
```
(~0,5 MB, khoảng 225 file. File `.xlsx` duy nhất bên trong là fixture tổng hợp `backend/tests/fixtures/synthetic_*` — IP 192.0.2.x,
không phải dữ liệu thật.)
Chép lên VM: `scp ../gpu-util-src.tar.gz <user>@<vm>:/opt/` rồi trên VM:
`mkdir -p /opt/gpu-util-admin && tar -xzf /opt/gpu-util-src.tar.gz -C /opt/gpu-util-admin`.
(Nếu sau này dùng git: `git clone` thay cho bước này — `.gitignore` đã loại dữ liệu nội bộ.)

### 5A. VM ra được Internet — build ngay trên VM (khuyến nghị)
```bash
cd /opt/gpu-util-admin
cp .env.example .env && nano .env        # đặt POSTGRES_PASSWORD, SECRET_KEY (mục 4)
docker compose up -d --build             # lần đầu 3–5 phút
docker compose ps                        # db, api: healthy · web, backup: running
```

### 5B. VM không ra Internet — build ở máy có mạng, mang image sang
Trên máy build (có Docker, chạy trong Git Bash / bash):
```bash
docker compose build                                         # tạo gpu-util-admin-api:local + gpu-util-admin-web:local
docker pull postgres:16-alpine
docker save -o gpu-util-images.tar gpu-util-admin-api:local gpu-util-admin-web:local postgres:16-alpine
```
Chép `gpu-util-images.tar` (~1,2 GB) + `gpu-util-src.tar.gz` lên VM, rồi trên VM:
```bash
docker load -i gpu-util-images.tar
cd /opt/gpu-util-admin && cp .env.example .env && nano .env
docker compose up -d --no-build           # dùng image vừa load, không build lại
```
Cập nhật phiên bản sau này: build + `docker save` lại 2 image `gpu-util-admin-*` (postgres không cần nếu không đổi).

---

## 6. Chuyển dữ liệu từ máy native sang server (1 lần, ngay sau lần `up` đầu tiên)

Nguyên tắc (PLAN ADR-9): **không chép bảng** — phát lại từng lô từ file gốc qua đúng luồng nhập → số liệu ở đích giống hệt nguồn.
Kèm theo: liên kết IP, cài đặt, tài khoản (giữ mật khẩu), nhật ký, ghi chú.

1. Trên máy Windows (Git Bash): dừng app native (Ctrl-C ở `task.sh run`/`dev`), rồi
   `bash scripts/task.sh backup` → `backups/gpu-util-data-<ngày-giờ>.zip` (chứa `data/app.db` + `data/uploads/`).
2. Chép zip lên VM: `scp backups/gpu-util-data-<ngày-giờ>.zip <user>@<vm>:/opt/gpu-util-admin/`.
3. Trên VM:
   ```bash
   cd /opt/gpu-util-admin
   mkdir -p gd1 && unzip gpu-util-data-<ngày-giờ>.zip -d gd1        # → gd1/data/app.db, gd1/data/uploads/
   GD1_DATA=./gd1/data docker compose run --rm replay
   ```
   Kết quả đúng: `Đã phát lại 5 lô (nguồn → đích): #1→#1, …` và
   `Kiểm: nguồn = đích (số lô, util_effective, inventory_current, reclaim_current, ip_link, app_setting, app_user, server_note, audit_log).`
4. Lỗi `CSDL đích đã có lô import` = đích không trống. Làm lại sạch: `docker compose down -v` (**XÓA** volume `pgdata` + `uploads`
   — hỏi người dùng trước), `docker compose up -d`, chạy lại bước 3.
5. Sau khi kiểm xong (mục 7), xóa `gd1/` và file zip trên VM (dữ liệu nội bộ), hoặc chuyển vào nơi lưu trữ an toàn.

Dữ liệu native hiện có (04/11/2026): 5 lô — thống kê 129 IP + VTNet T7, T8, T9, T10; chưa có tài khoản nào.

---

## 7. Sau khi `up`: tài khoản & kiểm tra

**Tạo admin đầu tiên** (in mật khẩu tạm 1 lần; lần đăng nhập đầu phải đổi, ≥ 10 ký tự, không chứa tên đăng nhập):
```bash
docker compose exec api python -m app.tools.users create-admin            # tên mặc định 'admin'
docker compose exec api python -m app.tools.users reset-password admin    # quên mật khẩu / bị khóa (sai 5 lần → khóa 15 phút)
```
Tài khoản khác tạo trên web (trang **Tài khoản**): *Đầu mối* (mã đầu mối = cột "Đầu mối sử dụng" trong file thống kê, vd
`kientt6`, `dungha7`; phạm vi *Chỉ server của mình*) hoặc *Chỉ xem*. Mật khẩu tạm gửi qua kênh an toàn.

**Kiểm tra sau deploy** (mở web qua đường hầm SSH nếu còn bind 127.0.0.1: `ssh -N -L 8080:127.0.0.1:8080 <user>@<vm>` rồi
mở http://localhost:8080 trên máy mình):

| Kiểm | Lệnh / thao tác | Kết quả đúng |
|---|---|---|
| Container | `docker compose ps` | db, api `healthy`; web, backup `running` |
| API sống | `curl -s http://127.0.0.1:8080/api/v1/healthz` | `{"db":"ok","gpu_core":"2.4.0"}` |
| Chưa đăng nhập bị chặn | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/api/v1/openapi.json` | `401` |
| Số liệu (sau replay) | Tổng quan, kỳ Tháng 10/2026, T = 40 | 92 server · Nguy hiểm 11 · Cảnh báo 46 · An toàn 35 · card Nguy hiểm 37 · GPU TB 38,7% |
| Xu hướng | So sánh: kỳ T7 (01–30/07) → T10 | 20 cải thiện · 5 xấu đi · 9 mới · 5 biến mất; Nguy hiểm 19 → 11 |
| Biểu đồ ngày | Tổng quan, tháng 10, điểm 01/10 | GPU 34,8% · VRAM 70,9% · 91 server |
| Báo cáo tháng | trang Báo cáo tháng → Tải (.pptx) | file `Bao_cao_GPU_thang_10_2026.pptx`, 7 slide |
| Xuất Excel | Cảnh báo → Xuất Excel | tải được `Danh_gia_tai_GPU_…xlsx` |
| Sao lưu | `docker compose run --rm backup now` | `Đã sao lưu: gpu-util-db-….dump + gpu-util-uploads-….tar.gz` trong `./backups` |
| Log | `docker compose logs --tail 50 api` | không có `ERROR`/traceback |

(Số golden đầy đủ: CONTEXT.md §7. Lệch số → **dừng**, không sửa số trong CSDL; báo người dùng.)

---

## 8. Mở cho người dùng trong mạng nội bộ (HTTPS)

Không mở HTTP thường ra mạng: mật khẩu và cookie phiên sẽ đi dạng rõ. Service `web` (nginx) có **2 chế độ**, cùng 1 image,
chọn lúc khởi động (`docker/nginx/40-gpu-mode.sh`):

| Chế độ | Khi nào | Cấu hình |
|---|---|---|
| **A. HTTPS tại nginx của app** (khuyến nghị — TTCN có sẵn file `.pem`) | người dùng vào thẳng VM, hoặc proxy hạ tầng chuyển tiếp TCP/TLS tới VM | `compose.tls.yaml`: cổng 443 dùng chứng chỉ của TTCN, cổng HTTP chỉ chuyển hướng 301 sang HTTPS, HSTS 180 ngày, api tự `COOKIE_SECURE=true` |
| **B. Proxy TLS của hạ tầng phía trước** | hạ tầng giữ chứng chỉ, chuyển HTTP vào VM | giữ chế độ HTTP: `HTTP_BIND=<IP nội bộ VM>`, `COOKIE_SECURE=true`, `TRUSTED_PROXIES=<IP proxy>`; firewall chỉ cho IP proxy |

### 8.1 Chế độ A — từng bước (trên VM)
1. **Chuẩn bị file `.pem`** — để **ngoài thư mục repo**, chỉ root/nhóm docker đọc được:
   ```bash
   sudo mkdir -p /etc/gpu-util/tls
   sudo cp fullchain.pem privkey.pem /etc/gpu-util/tls/       # tên file tùy, miễn khai đúng trong .env
   sudo chmod 644 /etc/gpu-util/tls/fullchain.pem && sudo chmod 600 /etc/gpu-util/tls/privkey.pem
   ```
   - `fullchain.pem` = chứng chỉ server **+ chuỗi trung gian** (nếu CA cấp riêng: `cat server.pem intermediate.pem > fullchain.pem`).
   - `privkey.pem` = khóa riêng **không passphrase** (có thì gỡ: `openssl pkey -in key.pem -out privkey.pem`).
   - Chỉ có 1 file `.pem` chứa cả chứng chỉ lẫn khóa → trỏ cả `TLS_CERT_FILE` và `TLS_KEY_FILE` vào nó (nên tách).
   - Chứng chỉ phải chứa đúng **tên miền / IP** người dùng sẽ gõ (trong SAN). CA nội bộ phải được cài trên máy người dùng.
2. **Kiểm file** (đọc file tại chỗ, không gửi đi đâu; chạy được cả trên máy Windows trong Git Bash):
   ```bash
   bash scripts/task.sh tls-check /etc/gpu-util/tls/fullchain.pem /etc/gpu-util/tls/privkey.pem <tên-miền-hoặc-IP>
   ```
   Kiểm: còn hạn (cảnh báo < 30 ngày) · khóa khớp chứng chỉ · khóa không passphrase · tên miền/IP có trong SAN · có chuỗi
   trung gian. Có `LỖI` → sửa trước (nginx sẽ không chạy hoặc trình duyệt sẽ chặn); `CẢNH BÁO` → đọc, quyết định.
   (`tls-check` chạy được với `sudo` khi file khóa chỉ root đọc được: `sudo bash scripts/tls_check.sh …`.)
3. **Thêm vào `.env`**:
   ```bash
   COMPOSE_FILE=compose.yaml:compose.tls.yaml     # mọi lệnh docker compose tự áp HTTPS (Windows: dấu ';')
   TLS_CERT_FILE=/etc/gpu-util/tls/fullchain.pem
   TLS_KEY_FILE=/etc/gpu-util/tls/privkey.pem
   HTTPS_BIND=0.0.0.0          # hoặc IP nội bộ của VM; mặc định 127.0.0.1 (chưa mở)
   HTTPS_PORT=443
   # TRUSTED_PROXIES=10.x.x.x  # nếu có proxy/load balancer hạ tầng đứng trước và gửi X-Forwarded-For
   ```
   Cổng HTTP (`HTTP_BIND`/`HTTP_PORT`) giờ chỉ chuyển hướng; muốn người dùng gõ `http://<tên>` cũng được chuyển sang HTTPS thì
   đặt `HTTP_BIND=0.0.0.0` + `HTTP_PORT=80`.
4. **Áp dụng**: `docker compose up -d` (image không đổi — chỉ tạo lại container `web`, `api`).
   `docker compose logs web | grep gpu-util` → `gpu-util: chế độ HTTPS (cổng công khai 443)`.
5. **Kiểm**:
   ```bash
   curl -sI http://127.0.0.1:${HTTP_PORT:-8080}/            # 301 → https://…
   curl -s --cacert <CA nội bộ>.pem https://<tên-miền>/api/v1/healthz   # {"db":"ok",…}
   curl -sI --cacert <CA nội bộ>.pem https://<tên-miền>/ | grep -i strict-transport   # HSTS
   ```
   Trên trình duyệt: `https://<tên-miền>` không cảnh báo chứng chỉ → đăng nhập được (cookie `gpu_session` có cờ *Secure*).
6. **Firewall**: chỉ mở 443 (và 80 nếu dùng chuyển hướng) cho dải IP nội bộ cần dùng.

**Gia hạn chứng chỉ**: thay file `.pem` tại chỗ (cùng đường dẫn) → `docker compose restart web`. Đặt lịch nhắc trước ngày hết
hạn (`tls-check` báo khi < 30 ngày).
**Quay về HTTP** (vd chứng chỉ lỗi): bỏ `COMPOSE_FILE` trong `.env` → `docker compose up -d`. Lưu ý HSTS: trình duyệt đã vào
HTTPS sẽ không chịu HTTP cùng tên miền trong 180 ngày — chỉ dùng HTTP qua đường hầm SSH (`localhost`).

### 8.2 IP người dùng trong Nhật ký
nginx gửi cho api đúng **1** địa chỉ (`X-Forwarded-For` = IP kết nối tới nginx), không nối thêm header do trình duyệt gửi (trước
04/11/2026 nối thêm → người dùng giả được IP ghi trong Nhật ký). Có proxy hạ tầng phía trước → đặt `TRUSTED_PROXIES` = IP/dải
của proxy để nginx lấy IP thật từ `X-Forwarded-For` của proxy đó (chỉ tin các địa chỉ này).

---

## 9. Vận hành hằng ngày

- **Nhập dữ liệu mỗi tháng**: VTNet gửi file qua Outlook nội bộ → admin tải về → trang **Nhập dữ liệu** (kéo thả .xlsx) → xem
  kiểm tra (lỗi chặn / cần xác nhận / thông tin) + xem trước tác động → **Xác nhận**. Không có nhập tự động. Nhập sai → **Hoàn tác** lô.
- **Sao lưu**: tự động `BACKUP_AT` mỗi ngày → `./backups`. **Chép thư mục này ra ngoài VM định kỳ** (VM hỏng = mất cả bản sao).
  Khôi phục: DEPLOY_VM §5.
- **Nâng cấp phiên bản**: `docker compose run --rm backup now` → thay mã nguồn (5A) hoặc `docker load` image mới (5B) →
  `docker compose up -d --build` (hoặc `--no-build`) → api tự chạy migration → kiểm mục 7. Quay lại bản cũ = mã cũ + khôi phục
  bản sao lưu vừa tạo (migration không lùi dữ liệu).
- **Log**: `docker compose logs -f api` · `docker compose logs web`.
- **Dừng / chạy lại**: `docker compose stop` / `docker compose start` (dữ liệu nằm trong volume, không mất).
  ⚠ `docker compose down -v` **xóa dữ liệu** — chỉ khi chủ động làm lại từ đầu.

---

## 10. Thư viện & phiên bản (khóa trong `backend/uv.lock`, `frontend/package-lock.json`)

| Thành phần | Phiên bản | Ghi chú |
|---|---|---|
| Python | 3.12 (image `python:3.12-slim-bookworm`) | native: Python 3.12 qua `uv` |
| uv | 0.13.0 (image `ghcr.io/astral-sh/uv:0.13.0`) | `uv sync --frozen` — đổi thư viện phải cập nhật `uv.lock` |
| FastAPI / uvicorn | 0.162.0 / 0.54.0 | |
| SQLAlchemy / Alembic | 2.1.6 / 1.20.1 | migration ở `backend/alembic/versions/` (0001, 0002) |
| pandas / openpyxl | 3.1.0 / 3.1.5 | đọc file VTNet & thống kê |
| python-pptx | 1.0.2 | báo cáo tháng (thêm 04/11/2026; đã có trong image build 04/11/2026) |
| psycopg (binary) | 3.3.7 | extra `pg` — chỉ khi dùng PostgreSQL |
| bcrypt / PyJWT | 5.0.0 / 2.15.1 | mật khẩu, phiên đăng nhập |
| Node | 22 (image `node:22-alpine`, chỉ để build) | native: Node LTS ≥ 22 |
| React / Ant Design / ECharts | 18.3 / 5.29 / 5.6 | ECharts 5 có cảnh báo XSS đã giảm thiểu bằng CSP (SECURITY_REVIEW §5) |
| Vite / TypeScript | 8.3 / 5.9 | |
| nginx | 1.27-alpine | |
| PostgreSQL | 16-alpine | test đã chạy trên PG 16.15 và PG 18 |

---

## 11. Hướng dẫn cho công cụ AI khi dẫn người dùng deploy

1. Đọc theo thứ tự: file này → `docs/DEPLOY_VM.md` → `compose.yaml` → `.env.example` → mục 12 bên dưới (biết cái gì đã/chưa kiểm).
2. Hỏi trước khi bắt đầu: VM có ra Internet không (5A/5B)? HTTPS theo chế độ A (file `.pem` gắn vào nginx) hay B (proxy
   hạ tầng giữ chứng chỉ) — mục 8? Tên miền/IP người dùng sẽ gõ? Ai cài Docker? Chạy `tls-check` trước khi bật HTTPS.
3. Mỗi bước: đưa **đúng 1 nhóm lệnh**, nói rõ chạy ở đâu (**máy Windows → Git Bash**; VM → shell Linux), kết quả mong đợi, rồi
   chờ người dùng dán kết quả trước khi sang bước tiếp. Đối chiếu với bảng mục 7.
4. Không bao giờ: in/ghi bí mật vào chat hay repo; commit `.env`, `samples/`, `data/`, `backups/`; mở `HTTP_BIND=0.0.0.0` khi chưa
   có HTTPS; chạy `docker compose down -v` hay xóa `backups/` khi người dùng chưa đồng ý rõ ràng; sửa số liệu trực tiếp trong CSDL
   (dữ liệu chỉ đổi qua nhập / hoàn tác lô).
5. Gặp lỗi: tra mục 9 của `docs/DEPLOY_VM.md` trước; lấy `docker compose ps` + `docker compose logs --tail 100 api`.
6. Xong việc: ghi kết quả vào mục 12 (ngày, môi trường, đã kiểm gì, lệch gì).

---

## 12. Trạng thái & nhật ký deploy (cập nhật mỗi khi có thay đổi / kiểm tra mới)

**Đã kiểm**
- 03/11/2026 — Docker Desktop (Windows): build 2 image, `up --wait` healthy, replay bản GĐ1 → "nguồn = đích", số qua nginx khớp
  golden, sao lưu `now` → xóa → khôi phục OK, upload > 20 MB → 413. Build lại sau G2-M4: healthy, header bảo mật đủ (PLAN §10.2).
- 04/11/2026 — CSDL native `data/app.db` có dữ liệu thật: migrate head, nhập 5 lô qua luồng nhập (thống kê 129 IP + VTNet T7→T10,
  không lỗi chặn/cảnh báo), golden CONTEXT §7 khớp; mọi trang chạy với dữ liệu thật; `replay` sang PostgreSQL 18 (cụm tạm) →
  "nguồn = đích", golden khớp trên PG. Bản sao lưu trước khi nhập: `backups/gpu-util-data-20261104-113311.zip`.

- 04/11/2026 — **HTTPS (chế độ A)** trên Docker Desktop, project thử `gpu-tls-test`, chứng chỉ thử do CA tự tạo ký: build lại
  2 image với code hiện tại (3 phút; api 1,02 GB có `python-pptx` 1.0.2, web 76 MB) → db/api/web/backup healthy; log
  `gpu-util: chế độ HTTPS`; HTTP → 301 `https://…` giữ đường dẫn; healthz qua HTTPS xác minh chuỗi CA (không có CA → bị từ chối);
  TLS 1.2/1.3 nhận, TLS 1.1 bị từ chối; HSTS + CSP + X-Frame-Options ở `/`, `/assets`, `/api`; đăng nhập → cookie
  `gpu_session`/`gpu_csrf` có `Secure`; `COOKIE_SECURE=true` trong api; header giả `X-Forwarded-For` bị bỏ qua (Nhật ký ghi IP kết
  nối — trên Docker Desktop là gateway 172.18.0.1 do NAT; VM Linux ghi IP người dùng); `TRUSTED_PROXIES=172.16.0.0/12` → ghi IP
  proxy gửi; sai đường dẫn chứng chỉ → log lỗi tiếng Việt, container khởi động lại; thiếu `TLS_CERT_FILE` → compose dừng kèm
  hướng dẫn; bỏ lớp TLS → chế độ HTTP như cũ (`COOKIE_SECURE=false`); `COMPOSE_FILE=compose.yaml;compose.tls.yaml` áp đúng.
  `task.sh tls-check` bắt được: thiếu chuỗi, sai cặp khóa, sai tên miền, khóa có passphrase, tự ký, sắp hết hạn.

- 05/11/2026 — Thêm cài đặt **`zone_metric`** ("Áp T cho", PLAN §14.9; gpu_core 2.5.0). Không đổi schema/migration: `seed`
  (tự chạy trong `setup/dev/run`; Docker: `api-entrypoint.sh` mỗi lần container api khởi động) thêm khóa còn thiếu với giá trị `both` = luật cũ → CSDL đã có (native,
  Docker, bản `replay`) vẫn ra số như trước. Deploy bản mới chỉ cần build lại image; không cần thao tác dữ liệu.

**Chưa kiểm / còn thiếu trước khi lên server thật**
- [ ] Chạy `replay` dữ liệu thật T7→T10 trong Docker (image đã build lại 04/11/2026) → kiểm đủ bảng mục 7, tải deck .pptx qua nginx.
- [ ] Chạy trên VM Linux thật (chưa từng làm).
- [ ] Service `backup` tự chạy đúng giờ `BACKUP_AT` (mới kiểm chế độ `now`).
- 05/11/2026 — **Sửa tay danh mục server** (PLAN §14.11): migration **0003** chỉ thêm bảng `inventory_override` (không đụng bảng
  / view cũ) — `setup`/`run`/`dev` và container api tự `migrate` khi khởi động, không cần thao tác dữ liệu. `replay` chép và kiểm
  bảng này (sửa tay ở native theo sang server). Không thêm thư viện, image không đổi ngoài code.
- [ ] HTTPS với **chứng chỉ thật** của TTCN trên VM (cấu hình đã có — mục 8; mới thử bằng chứng chỉ tự ký trên Docker Desktop).
- [ ] Bản native chưa có tài khoản admin (`bash scripts/task.sh create-admin`, chạy trong Git Bash) — nếu tạo ở native trước
      khi `replay` thì tài khoản được chép sang server; nếu không, tạo trên server (mục 7).
- [ ] File thống kê hiện tại (134 dòng) thiếu 11 IP có trong VTNet T10 (8 H200 `10.29.95.x` + 3 IP) → nhập file thống kê
      bản mới nhất khi có (CONTEXT §7).
