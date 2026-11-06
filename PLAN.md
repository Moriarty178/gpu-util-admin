# PLAN — GPU Util Admin (TTCN-VTT)

> Công cụ quản trị theo dõi tải GPU dài hạn: nhập file VTNet + file thống kê server vào CSDL riêng,
> xem biểu đồ tải toàn bộ / từng server theo khoảng ngày, bảng cảnh báo ngưỡng T% (backend = logic skill `gpu-util-vtnet`).
>
> Đọc kèm: `CONTEXT.md` (nghiệp vụ, định dạng file, số golden) · `CLAUDE.md` (quy ước làm việc).
> Lõi `backend/gpu_core` v2.1 đã có sẵn & đã test (39 test). Cập nhật checkbox `[ ]` → `[x]` khi xong từng việc.
>
> ## ▶ Làm theo 2 giai đoạn
> **Giai đoạn 1 (GĐ1) — ĐANG LÀM: trang quản trị đơn giản**, chạy trực tiếp trên Windows (Git Bash) của máy admin,
> **không Docker**, CSDL **SQLite** (1 file), **không đăng nhập** (chỉ nghe `127.0.0.1`). 5 trang: Tổng quan · Cảnh báo · Server ·
> Danh mục server · Nhập dữ liệu. Milestone **G1-M0 → G1-M3** (§10.1).
> **Giai đoạn 2 (GĐ2) — SAU**: PostgreSQL + Docker Compose (localhost rồi VM), tài khoản & phân quyền đầu mối, đối soát/liên kết IP
> trên UI, so sánh kỳ, ghi chú/giải trình/miễn trừ, cài đặt, nhật ký, sao lưu. Milestone **G2-M1 → G2-M4** (§10.2).
> Mục nào chỉ thuộc GĐ2 được gắn nhãn **[GĐ2]** — GĐ1 không làm, nhưng thiết kế GĐ1 không được chặn đường GĐ2.

**Đã chốt với người dùng (03/11/2026)**
1. 9 server RTX6000 `10.207.188.1–9` (thống kê) ≡ `10.205.36.51–59` (VTNet), ghép theo IP tăng dần, giữ cờ "chưa xác nhận cặp".
2. Phát triển trên **localhost: Windows + WSL2** (đã có Docker Desktop, nhưng GĐ1 **chưa dùng**); sau này lên **VM có Docker Compose**.
3. **Tài khoản riêng của công cụ** (không SSO) — [GĐ2].
4. **Đầu mối được đăng nhập** bằng tài khoản admin cấp, **mặc định chỉ thấy server của mình**, admin mở rộng từng tài khoản — [GĐ2].
5. **Hiện tại chỉ build trang quản trị đơn giản; deploy bằng Docker Compose để sau** → toàn bộ cấu trúc 2 giai đoạn ở trên.
6. **GĐ1 phát triển & chạy thẳng trên Windows** (Git Bash + uv + Node phía Windows), không dùng WSL — thay đổi ADR-7.

---

## 0. Tóm tắt

| | GĐ1 (đang làm) | GĐ2 (sau) |
|---|---|---|
| **Đầu vào** | File VTNet (`VTT_KPI_overview` + `server_raw`, tùy chọn `DS đã thu`) · File thống kê (`Thống kê chi tiết`) | như GĐ1 |
| **Lưu** | **SQLite** `data/app.db` — mỗi upload = 1 *lô import* xem lại / hoàn tác được; mẫu tải append-only | **PostgreSQL 16** (chuyển dữ liệu bằng cách phát lại các lô từ file gốc) |
| **Xem** | Biểu đồ tải TB toàn bộ server · biểu đồ từng server · bảng cảnh báo ngưỡng T chọn trên UI · danh mục server · xuất Excel | + đối soát, liên kết IP, so sánh kỳ, xu hướng vùng, ghi chú/giải trình |
| **Chạy** | Trong Ubuntu/WSL: `make dev` (uvicorn + Vite) hoặc `make run` (1 tiến trình, `http://localhost:8000`) | Docker Compose: localhost → VM |
| **Người dùng** | 1 admin trên máy mình, không đăng nhập | admin · đầu mối (tài khoản admin cấp) · viewer |
| **Stack** | FastAPI + SQLAlchemy 2 + Alembic · React 18 + TypeScript + Vite + Ant Design 5 + ECharts 5 | + PostgreSQL, nginx, Compose |
| **Nguyên tắc vàng** | Mọi phép tính nghiệp vụ đi qua `gpu_core` (1 nguồn chân lý cho UI, export, skill). Số liệu khớp golden CONTEXT §7 | như GĐ1 |

---

## 1. Mục tiêu & phạm vi

### 1.1 Mục tiêu

**A. Yêu cầu gốc** — tất cả thuộc GĐ1
- A1. Tải TB **toàn bộ server** trên khoảng `[date_start, date_end]` + **biểu đồ đường** (GPU% và VRAM%).
- A2. Tải TB **từng server** trên khoảng chọn + **biểu đồ đường**.
- A3. **Bảng cảnh báo** theo ngưỡng T% chọn trên UI — đúng luật skill; mặc định lọc **Nguy hiểm**.
- A4. **Nhập thủ công** file VTNet + file thống kê vào CSDL; mọi bảng/biểu đồ lấy từ CSDL.
- A5. **Danh mục server** (từ file thống kê) kèm dịch vụ/workload và tải VTNet đo được.

**B. Bổ sung**

| # | Nội dung | GĐ |
|---|---|---|
| B1 | Lọc theo **đầu mối, loại GPU, cụm, cách quản lý**; bảng vùng × đầu mối bấm được để drill-down | GĐ1 |
| B2 | **Cờ THẤP TẢI VTNet** (gpu<10 & mem<10) song song với vùng T | GĐ1 |
| B3 | **Mẫu hình** (idle / bursty / memory-bound / compute-bound) + **streak** thấp tải + **đỉnh / p95** | GĐ1 |
| B4 | Hai cách tính TB toàn bộ: **theo server** (mặc định = VTNet) và **theo số card** | GĐ1 |
| B5 | Gom ngày / tuần / tháng cho khoảng dài | GĐ1 |
| B9 | **Xuất Excel** đúng định dạng skill (thống kê + cột đánh giá + sheet tổng hợp) | GĐ1 |
| B10 | **Lô import có kiểm soát**: xem trước → xác nhận → hoàn tác; giữ file gốc; chống nhập trùng; đối soát overview | GĐ1 |
| B5b | Xu hướng số server từng vùng theo tháng | GĐ2 |
| B6 | **So sánh 2 kỳ**: xấu đi / cải thiện / mới / biến mất | GĐ2 |
| B7 | **Đối soát** trên UI + quản lý **liên kết IP** (GĐ1 chỉ nạp 9 liên kết RTX6000 từ seed, hiển thị badge) | GĐ2 |
| B8 | **Ghi chú, giải trình của đầu mối, miễn trừ** theo server | GĐ2 |
| B11 | Tài khoản, phân quyền admin / đầu mối / viewer, phạm vi theo đầu mối, nhật ký, sao lưu | GĐ2 |

### 1.2 Ngoài phạm vi (cả 2 giai đoạn)
CPU/RAM (VTNet chưa gửi) · tự động lấy file từ VTNet · gửi thông báo cho đầu mối · đơn vị khác VTT (VAI, VIC…) ·
dữ liệu theo giờ (chỉ cần *không vỡ* — §5.4) · báo cáo slide lãnh đạo (→ Roadmap §14).

### 1.3 Người dùng & vai trò
**GĐ1**: 1 người dùng (admin) trên máy của mình. Không màn đăng nhập. Server chỉ nghe `127.0.0.1` (trình duyệt Windows vẫn truy cập
qua `localhost` nhờ WSL2). Code vẫn có dependency `current_user()` trả `LocalAdmin` và đối tượng `Scope(all)` truyền vào mọi service
→ GĐ2 chỉ thay phần thân dependency, không sửa service.

**[GĐ2]**

| Vai trò | Phạm vi dữ liệu | Quyền |
|---|---|---|
| `admin` | Toàn bộ | Mọi thứ: import/hoàn tác, liên kết IP, ghi chú/miễn trừ, cài đặt, quản lý tài khoản, nhật ký |
| `owner` (đầu mối) | Gắn `owner_key` (vd `dungha7`). `data_scope = own` (mặc định): **chỉ server của mình**; `all`: toàn bộ | Xem Tổng quan / Cảnh báo / Server / Danh mục / So sánh trong phạm vi; xuất Excel trong phạm vi; **thêm giải trình** trên server của mình. Không import, không liên kết IP, không miễn trừ |
| `viewer` | Toàn bộ | Chỉ xem + xuất Excel (vd lãnh đạo) |

Tài khoản **do admin tạo**; mật khẩu tạm → **buộc đổi lần đầu**; admin khóa/mở, đặt lại mật khẩu, đổi vai trò/phạm vi.
Phạm vi áp **ở service layer** (qua `Scope`), không chỉ ẩn trên giao diện.

### 1.4 Tiêu chí thành công
- GĐ1: nhập file VTNet mới + xem bảng cảnh báo **< 2 phút**; số trên UI khớp golden CONTEXT §7 và sheet VTNet tự tính (≤ 1e-6);
  biểu đồ 12 tháng × ~100 server **< 1 giây**; khởi động lại máy → `make run` là dùng được, dữ liệu còn nguyên.
- GĐ2: đầu mối tự đăng nhập xem server của mình trên VM; chuyển dữ liệu GĐ1 sang không mất lô nào.

---

## 2. Kiến trúc

### 2.1 GĐ1 — chạy trực tiếp trong Ubuntu/WSL

```
 Trình duyệt Windows
   │  http://localhost:5173 (make dev)  hoặc  http://localhost:8000 (make run)
   ▼
 ┌──────────────────────────── Ubuntu (WSL2) — ~/projects/gpu-util-admin ────────────────────────────┐
 │  Vite dev server :5173 ── proxy /api ──┐        (make run: FastAPI tự phục vụ frontend/dist)       │
 │                                        ▼                                                          │
 │  FastAPI (uvicorn, 127.0.0.1:8000)                                                                │
 │   ├─ routers/   imports · fleet · servers · alerts · meta · healthz                               │
 │   ├─ services/  import_service · analytics_service (gọi gpu_core) · export_service                │
 │   ├─ repo/      SQLAlchemy (util_effective, inventory_current, ip_link …)                          │
 │   └─ gpu_core/  parsing · rules · metrics · export   ◄── NGUỒN CHÂN LÝ (đồng bộ sang skill)        │
 │                                                                                                    │
 │  data/app.db (SQLite, WAL)        data/uploads/<sha256>.xlsx (file gốc mọi lô)                     │
 └────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 [GĐ2] — Docker Compose (localhost rồi VM)
`compose.yaml`: `web` (nginx phục vụ SPA + proxy `/api`) · `api` (cùng code GĐ1) · `db` (PostgreSQL 16, volume `pgdata`) ·
`backup` (pg_dump hằng đêm). `compose.dev.yaml` cho localhost (hot-reload, cổng bind 127.0.0.1). Lên VM = cùng file + `.env` khác.
Dữ liệu GĐ1 chuyển sang bằng **phát lại các lô** từ `data/uploads/` theo đúng thứ tự & trạng thái (ADR-9).

### 2.3 Quyết định kiến trúc (ADR — đổi được, ghi lý do khi đổi)

| # | Quyết định | Lý do | Phương án bị loại |
|---|---|---|---|
| ADR-1 | **Python/FastAPI** | Dùng lại nguyên `gpu_core` (pandas/openpyxl) | Node/Go: viết lại parser & luật → 2 nguồn chân lý |
| ADR-2 | GĐ1 **SQLite** (1 file, WAL) qua SQLAlchemy với **schema trung tính** (§4); GĐ2 **PostgreSQL 16** | GĐ1 không cần cài/chạy dịch vụ DB; dữ liệu nhỏ (~36,5k mẫu/năm). Schema trung tính để chạy được cả 2 | PG ngay từ GĐ1: phải cài dịch vụ hoặc Docker — trái yêu cầu "đơn giản". SQLite mãi mãi: yếu khi nhiều người dùng (GĐ2) |
| ADR-3 | **Tính toán bằng pandas trong `gpu_core`**, SQL chỉ lọc & lấy dữ liệu | UI = export = skill = test golden; tránh lệch nghĩa giữa 2 dialect SQL | Viết công thức bằng SQL: lệch biên `<=`, bursty… và khác nhau giữa SQLite/PG |
| ADR-4 | **Mẫu tải append-only theo lô** + **VIEW** `util_effective` (ROW_NUMBER, lô committed mới nhất thắng) | Hoàn tác lô không mất dữ liệu cũ; truy vết nguồn. VIEW thường chạy cả SQLite & PG (GĐ2 có thể đổi sang materialized view nếu cần) | Upsert ghi đè: không hoàn tác được |
| ADR-5 | **Inventory theo snapshot** (mỗi upload = 1 snapshot) | Giữ lịch sử đổi đầu mối / dịch vụ | Ghi đè: mất lịch sử |
| ADR-6 | **React + Ant Design 5 + ECharts 5** | Bảng lọc/sắp xếp, RangePicker `vi_VN`, Upload, Slider sẵn có; ECharts có dataZoom, markLine ngưỡng. Giữ nguyên sang GĐ2, không viết lại UI | Trang server-render (Jinja/HTMX): không cần Node nhưng UI admin nghèo hơn, GĐ2 dễ phải làm lại |
| ADR-7 | **(đổi 03/11/2026)** GĐ1 **chạy native trên Windows**: Git Bash chạy `scripts/*.sh`, `scripts/task.sh` thay `make` (Makefile là vỏ gọi lại), `concurrently` dừng trọn cây tiến trình, API tự nạp lại bằng `watchfiles` (không dùng `uvicorn --reload`: trên Windows reloader gửi CTRL_C_EVENT, worker không nhận được → treo). GĐ2 Docker Compose | Người dùng chọn làm trên Windows (máy đã có uv, Python 3.12, Node; WSL thiếu công cụ). Script vẫn bash → lên Linux/VM không phải viết lại | WSL `~/projects` (phương án cũ): cần cài thêm uv/node/make trong WSL. Script PowerShell: 2 bộ script, trái quy ước |
| ADR-8 | GĐ1 **không đăng nhập** (chỉ 127.0.0.1) nhưng có `current_user()` + `Scope`; GĐ2 tài khoản riêng (bcrypt + JWT cookie httpOnly), RBAC 3 vai trò | Đơn giản cho 1 người dùng; GĐ2 thêm auth không phải sửa service | Làm auth ngay: tốn công khi chỉ admin dùng trên máy mình |
| ADR-9 | Chuyển SQLite → PostgreSQL ở GĐ2 bằng **phát lại lô** (`scripts/replay_batches.py`: đọc `import_batch` + file gốc trong `data/uploads/`, nhập lại vào PG theo thứ tự, giữ trạng thái committed/rolled_back) + copy `ip_link`, `app_setting` | Mọi dữ liệu tải đều sinh ra từ file gốc đã lưu theo sha256 → tái tạo được chính xác, kiểm bằng golden | Dump SQL chéo dialect: dễ lệch kiểu |

---

## 3. Cấu trúc repo (mục tiêu GĐ1; GĐ2 thêm file đánh dấu ⓶)

```
gpu-util-admin/
├── CLAUDE.md  PLAN.md  CONTEXT.md  README.md  .gitattributes  .gitignore
├── .claude/skills/gpu-util-vtnet/      # ✅ skill v2.1 (CLI + bản sao gpu_core)
├── docs/KICKOFF_PROMPTS.md             # ✅ prompt mẫu từng milestone
├── docs/SETUP_WINDOWS_WSL.md           # ✅ cài môi trường Windows + WSL2
├── samples/                            # ✅ dữ liệu THẬT (gitignored) — test golden
├── scripts/sync_skill.sh               # ✅ đồng bộ backend/gpu_core -> skill
├── scripts/dev.sh                      # chạy uvicorn --reload + Vite cùng lúc, Ctrl-C dừng cả hai
├── Makefile  .env.example
├── data/                               # (gitignored) app.db + uploads/ — tạo tự động
├── compose.yaml  compose.dev.yaml  scripts/replay_batches.py  docs/DEPLOY_VM.md   ⓶
├── backend/
│   ├── pyproject.toml                  # ✅ (uv)
│   ├── gpu_core/                       # ✅ parsing.py rules.py metrics.py export.py
│   ├── seeds/ip_links.csv              # ✅ 9 liên kết RTX6000
│   ├── app/
│   │   ├── main.py  config.py  deps.py (current_user, get_scope)  scope.py
│   │   ├── db/ (base.py, session.py, models.py)
│   │   ├── repo/ (util_repo.py, inventory_repo.py, batch_repo.py, link_repo.py)
│   │   ├── services/ (import_service.py, analytics_service.py, export_service.py)
│   │   ├── routers/ (meta.py, imports.py, fleet.py, servers.py, alerts.py)    ⓶ auth, users, gaps, compare, notes, settings, audit
│   │   └── schemas/ (pydantic I/O)
│   ├── alembic/ (env.py — render_as_batch cho SQLite, versions/)
│   └── tests/
│       ├── test_gpu_core.py            # ✅ 39 test
│       ├── fixtures/make_synthetic.py  # ✅ IP giả 192.0.2.x
│       └── test_import_api.py  test_analytics_api.py  test_export_api.py  conftest.py (SQLite tạm cho mỗi test)
└── frontend/
    ├── package.json  vite.config.ts (proxy /api)  tsconfig.json
    └── src/
        ├── main.tsx  App.tsx  routes.tsx
        ├── api/ (client.ts, hooks.ts – TanStack Query)
        ├── store/filters.ts            # bộ lọc toàn cục, đồng bộ URL query
        ├── components/ (FilterBar, ZoneTag, PatternTag, KpiCard, LoadChart, ZoneOwnerMatrix, …)
        ├── pages/ (Dashboard, Alerts, ServerDetail, Inventory, Imports)        ⓶ Gaps, Compare, Settings, Users, Audit, Login, ChangePassword
        └── lib/ (vi.ts – chuỗi UI, format.ts – vi-VN, zones.ts – màu/nhãn)
```

---

## 4. Mô hình dữ liệu (schema trung tính SQLite ↔ PostgreSQL)

Hiện thực bằng SQLAlchemy models + Alembic (`render_as_batch=True` để ALTER chạy trên SQLite). Quy ước kiểu:

| Logic | SQLAlchemy | SQLite (GĐ1) | PostgreSQL (GĐ2) |
|---|---|---|---|
| IP | `String(15)` (+ kiểm tra IPv4 ở tầng app; sắp xếp bằng `ipaddress` trong Python) | TEXT | VARCHAR(15) (có thể đổi INET) |
| JSON | `JSON` | TEXT JSON | JSONB |
| Thời điểm mẫu | `DateTime` không timezone, quy ước giờ VN, mẫu ngày = 00:00 | TEXT ISO | TIMESTAMP |
| Thời điểm hệ thống | `DateTime` lưu UTC | TEXT ISO | TIMESTAMP |
| Khóa tự tăng | `Integer, primary_key` | INTEGER | BIGINT identity |

SQLite: bật `PRAGMA foreign_keys=ON`, `journal_mode=WAL` mỗi kết nối.

```sql
-- 4.1 Lô import (GĐ1)
CREATE TABLE import_batch (
  id              INTEGER PRIMARY KEY,
  kind            TEXT NOT NULL CHECK (kind IN ('vtnet_util','inventory')),
  file_name       TEXT NOT NULL,
  file_sha256     TEXT NOT NULL,                     -- 64 hex
  file_path       TEXT NOT NULL,                     -- data/uploads/<sha256>.xlsx (bản gốc, để xuất Excel & phát lại GĐ2)
  schema_version  TEXT,                              -- 't10' | 't7' | 'inventory_v1'
  status          TEXT NOT NULL CHECK (status IN ('staged','committed','rolled_back','failed','discarded')),
  period_start    DATE, period_end DATE, period_label TEXT,      -- '2026-10'
  summary         JSON NOT NULL DEFAULT '{}',        -- số dòng, IP, IP mới/biến mất, ngày chồng lấn, số mẫu bị thay…
  validation      JSON NOT NULL DEFAULT '{}',        -- validate_overview(), warnings, ignored_sheets
  uploaded_by     TEXT NOT NULL,                     -- GĐ1: 'local-admin'
  uploaded_at     DATETIME NOT NULL,
  committed_by    TEXT, committed_at DATETIME,
  rolled_back_by  TEXT, rolled_back_at DATETIME,
  note            TEXT
);
CREATE UNIQUE INDEX uq_batch_committed_file ON import_batch(kind, file_sha256) WHERE status = 'committed';  -- partial index: SQLite & PG

-- 4.2 Mẫu tải — append-only theo lô (GĐ1)
CREATE TABLE util_sample (
  batch_id  INTEGER NOT NULL REFERENCES import_batch(id) ON DELETE CASCADE,
  ip        TEXT NOT NULL,
  ts        DATETIME NOT NULL,
  gpu       REAL NOT NULL,  mem REAL NOT NULL,     -- %
  gpu_type  TEXT,                                  -- nguyên văn VTNet: '4×NVIDIA L40S'
  don_vi    TEXT,
  PRIMARY KEY (batch_id, ip, ts)
);
CREATE INDEX ix_sample_ip_ts ON util_sample(ip, ts);
CREATE INDEX ix_sample_ts ON util_sample(ts);

-- 4.3 Giá trị hiệu lực: mỗi (ip, ts) lấy mẫu của lô COMMITTED mới nhất — VIEW thường, chạy cả SQLite (≥3.25) & PG
CREATE VIEW util_effective AS
SELECT ip, ts, gpu, mem, gpu_type, batch_id FROM (
  SELECT s.ip, s.ts, s.gpu, s.mem, s.gpu_type, s.batch_id,
         ROW_NUMBER() OVER (PARTITION BY s.ip, s.ts ORDER BY b.committed_at DESC, b.id DESC) AS rn
  FROM util_sample s JOIN import_batch b ON b.id = s.batch_id AND b.status = 'committed'
) t WHERE rn = 1;

-- 4.4 Overview VTNet — chỉ để đối soát (GĐ1)
CREATE TABLE vtnet_overview (batch_id INTEGER REFERENCES import_batch(id) ON DELETE CASCADE,
  ip TEXT, gpu REAL, mem REAL, PRIMARY KEY (batch_id, ip));

-- 4.5 Danh sách VTNet đã thu hồi (sheet 'DS đã thu') (GĐ1)
CREATE TABLE vtnet_reclaim (batch_id INTEGER REFERENCES import_batch(id) ON DELETE CASCADE,
  ip TEXT, gpu_type TEXT, beneficiary TEXT, owner_dcim TEXT, service_manager TEXT, status TEXT,
  PRIMARY KEY (batch_id, ip));
-- view reclaim_current: hợp các lô committed, mỗi IP lấy bản mới nhất + first_seen

-- 4.6 Inventory theo snapshot (GĐ1)
CREATE TABLE inventory_item (
  batch_id   INTEGER REFERENCES import_batch(id) ON DELETE CASCADE,
  ip         TEXT NOT NULL,  excel_row INTEGER,
  stt TEXT, server_class TEXT, config TEXT, cpu TEXT, ram TEXT, disk TEXT, hba TEXT,
  gpu_spec TEXT, gpu_count INTEGER, gpu_model TEXT, serial TEXT,
  owner TEXT,                                       -- đã casefold: 'dungha7'
  model TEXT, input_load TEXT, service TEXT, managed_by TEXT, cluster TEXT,
  extra JSON NOT NULL DEFAULT '{}',
  PRIMARY KEY (batch_id, ip)
);
-- view inventory_current: dòng của lô inventory committed mới nhất

-- 4.7 Liên kết IP (GĐ1: chỉ nạp từ seed & đọc; GĐ2: sửa/xác nhận trên UI)
CREATE TABLE ip_link (
  inventory_ip   TEXT PRIMARY KEY,
  vtnet_ip       TEXT NOT NULL UNIQUE,
  pair_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
  reason TEXT, created_by TEXT NOT NULL, created_at DATETIME NOT NULL,
  confirmed_by TEXT, confirmed_at DATETIME,
  CHECK (inventory_ip <> vtnet_ip)
);
-- Join: effective_ip = COALESCE(ip_link.vtnet_ip, inventory.ip)   (= gpu_core.apply_ip_links)
-- Seed: backend/seeds/ip_links.csv — 10.207.188.1–9 ↔ 10.205.36.51–59, pair_confirmed=false, created_by='seed'

-- 4.8 Cài đặt (GĐ1: chỉ đọc mặc định; GĐ2: sửa trên UI)
CREATE TABLE app_setting (key TEXT PRIMARY KEY, value JSON NOT NULL, updated_by TEXT, updated_at DATETIME);

-- 4.9 [GĐ2] — tạo bằng migration riêng của GĐ2
CREATE TABLE server_note (id INTEGER PRIMARY KEY, ip TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('note','explanation','exempt','action')),
  text TEXT NOT NULL, valid_until DATE, created_by TEXT NOT NULL, created_at DATETIME NOT NULL, deleted_at DATETIME);
CREATE TABLE app_user (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, full_name TEXT, email TEXT,
  password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK (role IN ('admin','owner','viewer')),
  owner_key TEXT, data_scope TEXT NOT NULL DEFAULT 'own' CHECK (data_scope IN ('own','all')),
  must_change_password BOOLEAN NOT NULL DEFAULT TRUE, failed_attempts INTEGER NOT NULL DEFAULT 0, locked_until DATETIME,
  active BOOLEAN NOT NULL DEFAULT TRUE, last_login_at DATETIME, created_by TEXT, created_at DATETIME NOT NULL,
  CHECK (role <> 'owner' OR owner_key IS NOT NULL));
CREATE TABLE audit_log (id INTEGER PRIMARY KEY, at DATETIME NOT NULL, username TEXT, action TEXT NOT NULL,
  target TEXT, payload JSON NOT NULL DEFAULT '{}');
```

`app_setting` mặc định: `default_threshold=40`, `vtnet_low_load_t=10`, `bursty_peak=70`, `high_load=80`, `thin_coverage=0.8`,
`max_upload_mb=20`. Các hằng này hiện nằm trong `gpu_core/rules.py` → G1-M2 chuyển thành tham số hàm (giữ mặc định) để đọc từ settings.

---

## 5. Luồng nhập dữ liệu (GĐ1)

### 5.1 Trạng thái lô
```
 upload ──► [staged] ──xác nhận──► [committed] ──hoàn tác──► [rolled_back]
              │                   (util_effective là VIEW → tự cập nhật, chỉ cần xóa cache phân tích)
              ├─ parse/validate lỗi ─► [failed]
              └─ hủy ─► [discarded]   (lô staged > 24h tự discard khi khởi động)
```

### 5.2 File VTNet (`kind = vtnet_util`)
1. **Nhận file**: chỉ `.xlsx`, ≤ `max_upload_mb`; tính `sha256`; lưu `data/uploads/<sha256>.xlsx`. Đã có lô *committed* cùng sha → **409** "File đã được nhập (lô #id, ngày…)".
2. **Nhận diện loại**: có sheet `server_raw`/`VTT_GPU_Server_RAW` → VTNet; có `Thống kê chi tiết` → inventory; khác → 422.
3. **Parse** bằng `gpu_core.read_vtnet_workbook` (t7 + t10, header lệch dòng, Grand Total, NBSP).
4. **Validate** → `validation`: `validate_overview()` (lệch > 0,01 → cảnh báo vàng, không chặn); cảnh báo parser; `ignored_sheets`.
5. **Tóm tắt** → `summary`: kỳ (start, end, nhãn), số dòng, số IP, `gpu_type` theo model, **IP mới**, **IP biến mất** so với lô committed gần nhất,
   **ngày chồng lấn** + **số mẫu sẽ bị thay** (vd file T10 có 01/11 sẽ chồng với file T11).
6. Ghi `util_sample`, `vtnet_overview`, `vtnet_reclaim` với `batch_id` (**staged** → chưa ảnh hưởng số liệu).
7. **Xác nhận** → `committed` (+ `committed_at`), xóa cache. **Hoàn tác** → `rolled_back`; giá trị cũ của ngày chồng lấn tự "sống lại".

### 5.3 File thống kê (`kind = inventory`)
`gpu_core.read_inventory` (cột theo header). Bỏ IP rỗng/không hợp lệ (cảnh báo); **IP trùng trong file → chặn**; thiếu `IP` hoặc
`Đầu mối sử dụng` → chặn. Tóm tắt: số dòng, theo đầu mối, số IP thêm/bớt so với snapshot hiện tại (diff chi tiết từng trường: [GĐ2]).
Commit → snapshot mới thành `inventory_current`. File gốc giữ lại để xuất Excel đúng định dạng.

### 5.4 Quy tắc dữ liệu
- Khóa mẫu `(ip, ts)`. Trùng trong 1 file → giữ dòng cuối + cảnh báo (parser đã làm).
- Dữ liệu theo giờ (giờ ≠ 00:00): **vẫn nhập**; trước khi đưa vào `gpu_core` gom về ngày (mean trong ngày, làm trong pandas). Có fixture theo giờ.
- Chỉ nhập `don_vi = 'VTT'` hoặc rỗng; khác → bỏ + cảnh báo.

---

## 6. Định nghĩa phép tính (bắt buộc dùng đúng)

| Đại lượng | Định nghĩa | Hàm `gpu_core` | Đối soát |
|---|---|---|---|
| TB 1 server trong khoảng | mean các mẫu ngày của IP trong `[start, end]` (end tính cả ngày) | `server_stats` | `VTT_KPI_overview` khi khoảng = kỳ file |
| TB toàn bộ server theo ngày | mean đơn giản qua các server có mẫu trong ngày; kèm `n_servers` | `fleet_daily(weight="server")` | sheet `HSSD theo ngay VTT` |
| TB toàn bộ — theo card | trung bình trọng số số card (`gpu_type` VTNet → inventory → 1) | `fleet_daily(weight="gpu")` | — |
| TB toàn khoảng (KPI) | mean chuỗi ngày ở trên. **Khác** `Grand Total` VTNet (trọng số theo mẫu): T10 = 38,75% vs 38,74% | (từ chuỗi) | — |
| Gom tuần/tháng | mean giá trị ngày trong bucket (tuần ISO từ thứ Hai; tháng dương lịch) | analytics_service | — |
| Vùng / mẫu hình / cờ VTNet | CONTEXT §4 | `classify_zone`, `classify_pattern`, `vtnet_low_load` | golden §7 |
| Đỉnh / p95 | max / quantile 0.95 mẫu ngày `gpu` | `server_stats` | — |
| Coverage / dữ liệu mỏng | ngày có mẫu / ngày lịch trong khoảng; mỏng nếu < 0.8 | `server_stats` | — |
| Streak thấp tải · Số ngày nguy hiểm | `low_load_streak` · `danger_days` | `server_stats` | — |
| Card trong vùng | Σ số card server thuộc vùng (theo model) | analytics_service | — |
| [GĐ2] Xu hướng vùng theo tháng · So sánh 2 kỳ | `server_stats` theo từng tháng · `compare_periods` | — | — |

Phạm vi server mặc định: **mọi IP VTNet đo**. Lọc theo đầu mối/cụm/dịch vụ → chỉ server map được (qua `ip_link`).
Bảng vùng × đầu mối có cột **"Chưa có trong thống kê"** cho IP VTNet-only.

**Phạm vi theo tài khoản** — GĐ1 luôn `Scope(all)`. [GĐ2] `owner` + `own` → tập IP = `effective_ip` của `inventory_current`
có `owner = owner_key`; không thấy VTNet-only/đầu mối khác; Tổng quan ghi "Server của tôi (N)"; ngoài phạm vi → 404; export cắt theo phạm vi.

**Preset khoảng ngày**: 4 tuần gần nhất (= mặc định từ 04/11/2026, §14.8), "Theo kỳ file VTNet" (khớp tuyệt đối overview, vd
01/10–01/11; file tuần: "Tuần 42/2026"), Tháng này, Tháng trước, 3/6/12 tháng, Tùy chọn.
Ghi chú UI: chọn "Tháng 10" dương lịch (01–31/10) lệch nhẹ so với overview vì VTNet tính cả 01/11.

**Hiệu năng**: lấy `util_effective` theo khoảng (+ lọc IP) → DataFrame → `gpu_core`. Cache LRU trong tiến trình theo
`(endpoint, params, data_version)`, `data_version` = max(committed_at, rolled_back_at) của các lô.

---

## 7. API (`/api/v1`, JSON; lỗi `{type,title,detail}` tiếng Việt)

Tham số chung: `start`, `end` (YYYY-MM-DD), `threshold` (0–100, mặc định setting), `owner`, `gpu_model`, `cluster`, `managed_by` (lặp được), `q`.

| GĐ | Method | Path | Mô tả |
|---|---|---|---|
| 1 | GET | `/healthz` | DB ok + phiên bản `gpu_core` |
| 1 | GET | `/meta` | Khoảng dữ liệu, danh sách kỳ (lô VTNet committed), đầu mối/model/cụm cho bộ lọc, settings |
| 1 | POST | `/imports` (multipart `file`) | Upload → lô **staged** + `summary` + `validation` |
| 1 | GET | `/imports` · `/imports/{id}` · `/imports/{id}/file` | Lịch sử lô, chi tiết, tải file gốc |
| 1 | POST | `/imports/{id}/commit` · `/rollback` · `/discard` | Đổi trạng thái lô |
| 1 | GET | `/fleet/timeseries` (+`granularity` = day / week / month, `weight` = server / gpu) | Chuỗi TB toàn bộ server |
| 1 | GET | `/fleet/summary` | KPI: TB GPU/VRAM, số server có số liệu, số server mỗi vùng, dưới ngưỡng VTNet, card theo vùng |
| 1 | GET | `/servers` | Danh mục: inventory ⟗ VTNet + chỉ số trong khoảng + trạng thái số liệu; phân trang/sắp xếp |
| 1 | GET | `/servers/{ip}` · `/servers/{ip}/timeseries` | Chi tiết 1 server (inventory, liên kết IP, thu hồi, chỉ số, nhận xét) + chuỗi ngày |
| 1 | GET | `/alerts` (+`zones`, `patterns`, `vtnet_flag`, `only_mapped`, `sort`, `page`, `page_size`) | **Bảng cảnh báo** + `matrix` + `pattern_counts` + `cards_by_zone` |
| 1 | GET | `/alerts/export.xlsx` | Excel định dạng skill (`gpu_core.export.write_assessed_inventory` trên file inventory gốc của snapshot hiện tại + `ip_links`) |
| 2 | POST/GET | `/auth/login` · `/auth/logout` · `/auth/me` · `/auth/change-password` | Cookie httpOnly + CSRF; buộc đổi mật khẩu lần đầu |
| 2 | GET/POST/PATCH | `/users` · `/users/{id}/reset-password` | Quản lý tài khoản (role, owner_key, data_scope, mật khẩu tạm) |
| 2 | GET | `/servers/timeseries?ips=…` (≤ 5) · `/trend/zones` · `/compare` · `/gaps` | So sánh server, xu hướng vùng, so sánh kỳ, đối soát |
| 2 | GET/POST/PATCH/DELETE | `/ip-links` · `/servers/{ip}/notes` · `/settings` · `/audit` | Liên kết IP (sửa/xác nhận cặp), ghi chú/giải trình/miễn trừ, cài đặt, nhật ký |

Ví dụ `GET /alerts?start=2026-10-01&end=2026-11-01&threshold=40&zones=danger` (số thật T10, đã nạp 9 liên kết RTX6000):

```json
{
  "params": {"start": "2026-10-01", "end": "2026-11-01", "threshold": 40, "days_in_range": 32},
  "matrix": {"owners": ["dungha7", "kientt6", "_unmapped"],
             "rows": {"safe": {"dungha7": 18, "kientt6": 16, "_unmapped": 1},
                      "warning": {"dungha7": 18, "kientt6": 27, "_unmapped": 1},
                      "danger": {"dungha7": 5, "kientt6": 5, "_unmapped": 1}}},
  "pattern_counts": {"memory_bound": 46, "healthy": 18, "high_load": 17, "idle": 7, "bursty_idle": 4},
  "cards_by_zone": {"danger": {"A30": 14, "L40": 12, "RTX 6000": 8, "L4": 3}},
  "total": 11,
  "items": [{
    "ip": "10.207.163.82", "inventory_ip": "10.207.163.82", "owner": "kientt6", "service": "OCR, KYC",
    "model": "OCR", "cluster": "Server độc lập", "managed_by": "Server độc lập",
    "gpu_type": "1×NVIDIA A30", "gpu_count": 1, "gpu_model": "A30", "inventory_gpu_spec": "3*A30",
    "gpu_avg": 1.2, "mem_avg": 23.9, "gpu_peak": 37.2, "gpu_p95": 0.0, "days": 32, "coverage": 1.0,
    "low_streak": 20, "danger_days": 20, "zone": "danger", "pattern": "idle", "vtnet_low_load": false,
    "thin_data": false,
    "assessment": "[util TB 1% / VRAM TB 24% (đỉnh util 37%)] NGUY HIỂM – idle thật: compute+VRAM đều thấp cả kỳ. Ứng viên thu hồi/tái phân bổ NGAY.",
    "reclaimed": false, "ip_linked": false, "pair_confirmed": null, "gpu_count_mismatch": true
  }]
}
```
`_unmapped` = 3 server VTNet-only (1/1/1); không có liên kết thì kientt6 = 15/20/4 và `_unmapped` = 2/8/2.
`gpu_count` theo VTNet (1), thống kê ghi `3*A30` → `gpu_count_mismatch: true`. [GĐ2] thêm `exempt_until`, `notes_count`.

---

## 8. Giao diện

### 8.0 Nguyên tắc chung
- **Tiếng Việt**; ngày `dd/mm/yyyy`; số `vi-VN` (`38,7%`); giờ VN. Tên biến/code tiếng Anh.
- **Màu**: ~~primary navy; đỏ chỉ dành cho "Nguy hiểm"~~ → từ 05/11/2026 **phong cách Viettel** (§14.10). Vùng: An toàn xanh lá, Cảnh báo cam, Nguy hiểm đỏ — luôn kèm **chữ/biểu tượng**.
  GPU% và VRAM% 2 màu trung tính phân biệt rõ; ngưỡng nét đứt.
- **Bộ lọc toàn cục** (thanh trên cùng, giữ khi chuyển trang, đồng bộ URL): `[Khoảng ngày + preset] [Đầu mối] [Loại GPU] [Cụm] [Quản lý bằng] [Ngưỡng T]`.
- Biểu đồ: dataZoom, tooltip đủ số + `n_servers`, markLine **T** (nét đứt) và **10% VTNet** (chấm), nút tải PNG.
- Trạng thái rỗng ("Chưa có dữ liệu" + nút "Nhập file"), đang tải (skeleton), lỗi (thông báo + thử lại).
- Chú thích cố định ở Tổng quan & Cảnh báo: "Chỉ có số liệu GPU, chưa có CPU/RAM — là xấp xỉ luật thu hồi của VTNet".

Menu GĐ1: **Tổng quan · Cảnh báo · Server · Danh mục server · Nhập dữ liệu**. [GĐ2] thêm: Đối soát · So sánh kỳ · Cài đặt · Tài khoản · Nhật ký.

### 8.1 Tổng quan — A1 (+B1, B4, B5)
```
┌ Bộ lọc toàn cục ───────────────────────────────────────────────────────────────────────────────┐
│ [01/10/2026 – 01/11/2026 ▾ Theo kỳ file VTNet] [Đầu mối: Tất cả▾] [GPU▾] [Cụm▾] [T: 40%]      │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
┌ GPU TB ──┐┌ VRAM TB ─┐┌ Server có số liệu ┐┌ Nguy hiểm (T) ┐┌ Dưới ngưỡng VTNet ┐┌ Card nguy hiểm ┐
│ 38,7%    ││ 72,3%    ││ 92                ││ 11             ││ 1                 ││ 37 (A30 14…)   │
└──────────┘└──────────┘└───────────────────┘└────────────────┘└───────────────────┘└────────────────┘
┌ Tải trung bình toàn bộ server ──────────────── [Ngày|Tuần|Tháng] [Theo server|Theo card] [⤓] ┐
│ 100 ┤      GPU% ───   VRAM% ───   T=40% - - -   VTNet 10% · · ·                              │
│   0 ┼──────────────────────────────────────────────────────────── (dataZoom) ───────────────│
└──────────────────────────────────────────────────────────────────────────────────────────────┘
┌ Vùng × đầu mối (bấm ô → Cảnh báo đã lọc) ┐
│        dungha7 kientt6 Chưa map  Tổng    │      [GĐ2] bên phải: xu hướng vùng theo tháng +
│ An toàn   18     16      1       35      │      biến động so với kỳ trước; KPI có "▼8 vs kỳ trước"
│ Cảnh báo  18     27      1       46      │
│ Nguy hiểm  5      5      1       11      │
└──────────────────────────────────────────┘
```
Nghiệm thu: khoảng 01/10–31/10, theo server, theo ngày → 31 điểm khớp sheet `HSSD theo ngay VTT` (≤ 1e-6).

### 8.2 Cảnh báo — A3 (+B2, B3, B9)
```
┌ Ngưỡng T: [──────●─────] 40%  [10][20][30][40][50][60]   Vùng: [☑Nguy hiểm ☐Cảnh báo ☐An toàn] ┐
│ Mẫu hình [▾]  ☐ Chỉ cờ VTNet  ☐ Chỉ server có trong thống kê                         [⤓ Excel] │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
 Tóm tắt: 11 Nguy hiểm (7 idle thật · 4 bursty) · 37 card · 1 dưới ngưỡng VTNet · 1 dữ liệu mỏng
┌────────┬───────────────┬─────────┬──────────────┬────────┬──────┬──────┬──────┬──────┬────────┬────────┬─────┬──────────────┐
│ Vùng   │ IP            │ Đầu mối │ Dịch vụ      │ GPU    │GPU TB│VRAM TB│ Đỉnh │ Ngày │ Streak │ Mẫu hình│ VTNet│ Nhận xét ▸  │
├────────┼───────────────┼─────────┼──────────────┼────────┼──────┼──────┼──────┼──────┼────────┼────────┼─────┼──────────────┤
│🔴Nguy h│ 10.207.163.82 │ kientt6 │ OCR, KYC     │ 1×A30⚠ │ 1,2% │23,9% │37,2% │32/32 │ 20 ngày│ Idle   │      │ NGUY HIỂM – …│
└────────┴───────────────┴─────────┴──────────────┴────────┴──────┴──────┴──────┴──────┴────────┴────────┴─────┴──────────────┘
```
- Kéo ngưỡng → bảng cập nhật (debounce 300 ms). Sắp xếp mặc định: Vùng ↑, GPU TB ↑.
- Dòng mở rộng: nhận xét đầy đủ + sparkline + nút "Mở chi tiết". [GĐ2] ghi chú/giải trình/miễn trừ.
- Badge: "Đã thu hồi", "Lệch số card", "Dữ liệu mỏng", "IP liên kết (chưa xác nhận cặp)". [GĐ2] "Miễn trừ đến dd/mm", 💬 giải trình.
- Nghiệm thu (có 9 liên kết): T=40, kỳ 01/10–01/11 → 11 Nguy hiểm / 46 Cảnh báo / 35 An toàn (mọi server VTNet);
  ma trận map được (89 server) 34/45/10. T=30, 01/10–31/10 → map được 40/43/6.
  Không liên kết: 80 server, 33/38/9 và 36/38/6.

### 8.3 Server (chi tiết) — A2
```
[Tìm server: IP / dịch vụ / model ▾]                                   [GĐ2: + So sánh tối đa 5 server]
┌ 10.254.135.36 · 2×A30 · dungha7 ──────────────────────┐┌ Chỉ số trong khoảng ─────────────────┐
│ Dịch vụ: n8n, dify test lab · Model: mineru · Cụm:     ││ GPU TB 17,9% · VRAM TB 38,3%          │
│ Server độc lập · Inventory dòng Excel #4                ││ Đỉnh 100% · p95 100% · 32/32 ngày     │
│ [🔴 Nguy hiểm · Bursty]  [Cờ VTNet: không]              ││ Streak thấp tải 12 · Ngày nguy hiểm 20│
└─────────────────────────────────────────────────────────┘└───────────────────────────────────────┘
┌ Tải theo ngày ─────────────────────────────── [Ngày|Tuần|Tháng] ┐
│ GPU% ───  VRAM% ───  T - - -  10% · · ·                          │
│ dải vùng theo ngày: ■■■■■■■■■■■■                                  │
└──────────────────────────────────────────────────────────────────┘
┌ Nhận xét (gpu_core.assessment_text) ┐      [GĐ2] Ghi chú & giải trình · Lịch sử đầu mối/dịch vụ theo snapshot
```
Server VTNet-only vẫn xem được ("Chưa có trong thống kê"). Server inventory-only: "Không có số liệu VTNet" (+ "Đã thu hồi" nếu có).
Server liên kết hiển thị cả 2 IP ("10.207.188.1 → VTNet 10.205.36.51", badge "chưa xác nhận cặp").

### 8.4 Danh mục server — A5
Bảng `inventory_current` ⟕ chỉ số tải khoảng đang chọn: STT, IP (+ IP VTNet nếu liên kết), Đầu mối, GPU (thống kê) / GPU (VTNet),
Model, Dịch vụ, Đầu vào hệ thống, Quản lý bằng, Cụm, Vùng, GPU TB, VRAM TB, **Trạng thái số liệu** (Có / Không có / Đã thu hồi / Liên kết).
Thêm nhóm "VTNet có – thống kê thiếu" ở cuối bảng (T10 sau seed: 3 server). Lọc + tìm kiếm + xuất CSV.
Nghiệm thu T10: 137 dòng thống kê = 89 có số liệu + 13 đã thu hồi + 35 không có; lệch số card 8 server.

### 8.5 Nhập dữ liệu — A4
```
┌ Kéo thả file .xlsx (VTNet hoặc Thống kê server) ┐
└──────────────────────────────────────────────────┘
Xem trước lô #2 (staged) — HSSD GPU Thang 10 2026 - VTT.xlsx
  Loại: File tải VTNet · Schema: t10 · Kỳ: 01/10/2026 → 01/11/2026 (2026-10) · 2.930 dòng · 92 server
  ✓ Đối soát overview: khớp 92/92 (lệch lớn nhất 0)          ⚠ Sheet bỏ qua: VAI, VIC, pivot_value, …
  Server mới: 9 · Biến mất so với kỳ trước: 5 · Ngày chồng lấn: 0 · Danh sách thu hồi: 30
  [Xác nhận nhập]  [Hủy]
Lịch sử lô: # · Loại · File · Kỳ · Trạng thái · Thời điểm · [Tải file gốc] [Hoàn tác]
```
(Số "mới 9 / biến mất 5" là khi đã nhập T7 trước.)

### 8.6 [GĐ2] Đối soát · So sánh kỳ · Cài đặt · Tài khoản · Nhật ký · Trải nghiệm đầu mối
- **Đối soát**: tab VTNet-only (3) · thống kê không có số liệu (48 = 13 đã thu hồi + 35 chưa rõ) · lệch số card (8) · **liên kết IP**
  (9 đã seed: sửa cặp, "Xác nhận cặp", xóa; gợi ý liên kết mới theo nhóm `(gpu_count, gpu_model)` — admin duyệt, không tự áp).
- **So sánh kỳ**: kỳ A/B (preset 2 kỳ file gần nhất), ma trận chuyển vùng, danh sách xấu đi/cải thiện.
  Nghiệm thu T7→T10 (T=40): 20 cải thiện, 5 xấu đi, 9 mới, 5 biến mất.
- **Cài đặt**: các hằng ở §4. **Tài khoản**: tạo (vai trò, đầu mối, phạm vi mặc định "Chỉ server của mình"), mật khẩu tạm hiện 1 lần,
  khóa/mở, đặt lại. **Nhật ký**: login, import, commit, rollback, link, note, settings, user_*.
- **Đầu mối**: buộc đổi mật khẩu lần đầu; menu rút gọn (Tổng quan · Cảnh báo · Server · Danh mục · So sánh kỳ); bộ lọc đầu mối khóa;
  "Server của tôi (N)"; nút "Thêm giải trình"; thông điệp "Server vùng Nguy hiểm có nguy cơ bị thu hồi — hãy tối ưu hoặc giải trình".

---

## 9. Yêu cầu phi chức năng

| Nhóm | GĐ1 | [GĐ2] |
|---|---|---|
| Môi trường | Windows (ADR-7 đổi 03/11/2026): Git Bash; Python ≥ 3.12 qua `uv`; Node LTS ≥ 22. Hướng dẫn: README mục "Chạy GĐ1" | Docker Compose trên localhost rồi VM |
| Chạy | `bash scripts/task.sh dev` (≡ `make dev`): `scripts/dev.sh` chạy API `127.0.0.1:8000` (watchfiles tự nạp lại) + Vite `:5173` (proxy `/api`), Ctrl-C dừng cả hai. `task.sh run`: build frontend → FastAPI phục vụ `frontend/dist` tại `http://localhost:8000` | `compose.yaml` (+ `compose.dev.yaml`), chỉ mở cổng web |
| Cấu hình | `.env`: `DATABASE_URL=sqlite:///./data/app.db`, `UPLOAD_DIR=./data/uploads`, `API_PORT=8000`, `WEB_PORT=5173`, `TZ=Asia/Ho_Chi_Minh`; thư mục `data/` tự tạo | `DATABASE_URL=postgresql+psycopg://…`, secret, cookie |
| Bảo mật | Chỉ nghe `127.0.0.1`; upload chỉ `.xlsx`, giới hạn dung lượng, cài `defusedxml`; không log nội dung file | Đăng nhập bắt buộc, bcrypt, JWT cookie httpOnly + SameSite=Strict + CSRF, khóa 5 lần sai/15 phút, mật khẩu ≥ 10 ký tự, buộc đổi lần đầu; RBAC + `Scope` ở service, ngoài phạm vi → 404 |
| Dữ liệu nội bộ | `samples/`, `data/` không vào git; repo không chứa IP thật ngoài tài liệu/test golden/`backend/seeds/` | + dump DB, backups |
| Hiệu năng | API phân tích ≤ 1 s cho 12 tháng × 100 server (fixture tổng hợp 3 năm); import 3k dòng ≤ 5 s | như GĐ1 trên PG |
| Ngoại tuyến | Không CDN; font tự host; mirror cấu hình bằng `PIP_INDEX_URL`/`npm config` nếu mạng công ty chặn | + image build qua mirror |
| Tệp & dòng | Mọi file LF (`.gitattributes`); script chỉ bash, gọi `bash scripts/...` | — |
| Sao lưu | Copy `data/` (app.db + uploads) là đủ; `task.sh backup` nén `data/` vào `backups/` có ngày giờ (API backup của `sqlite3` trong Python — an toàn khi đang chạy, không cần cài `sqlite3` CLI) | pg_dump hằng đêm giữ 30 bản |
| Chất lượng | ruff + mypy (backend), eslint + tsc strict (frontend); test backend ≥ 85% cho `gpu_core` & services | + E2E Playwright, ma trận test quyền |
| i18n | Chuỗi UI tập trung `src/lib/vi.ts`; `Intl.NumberFormat('vi-VN')`, `dayjs` locale `vi` | — |

---

## 10. Kế hoạch triển khai

> Mỗi milestone: đọc mục liên quan → làm → `task.sh test` + `task.sh lint` xanh → tick checkbox → tóm tắt thay đổi. Không nhảy milestone.

### 10.1 GĐ1 — Trang quản trị đơn giản (ĐANG LÀM)

#### G1-M0 — Khung dự án chạy native (Windows — ADR-7 đổi 03/11/2026)
- [x] Kiểm tra công cụ (Windows): Python 3.12.10, uv 0.13.0, Node 26.3.0 (LTS), npm 11.16.0; không có `make` → `scripts/task.sh`
- [x] Backend: `uv` project trong `backend/` (deps GĐ1 + `uv.lock`; `pg`/`auth` là nhóm tùy chọn GĐ2), FastAPI tối thiểu `/api/v1/healthz`, `pydantic-settings` đọc `.env`, log ra stdout; test `gpu_core` chạy lại trên Python 3.12.10 (real-data skip theo từng file thiếu)
- [x] Frontend: Vite 8 + React 18 + TS 5.9 strict + AntD 5 (`vi_VN`) + ECharts 5 + TanStack Query 5 + React Router 7; layout menu 5 trang trống; Vite proxy `/api` → `127.0.0.1:${API_PORT}`
- [x] `scripts/dev.sh` (API watchfiles + Vite qua `concurrently`), `scripts/task.sh` + `Makefile` (vỏ): `setup` (uv sync + npm ci), `dev`, `run`, `test`, `lint`, `fmt`, `migrate`/`seed` (chờ G1-M1), `backup`, `sync-skill`; `.env.example`
- [x] `task.sh run`: build frontend, FastAPI mount `frontend/dist` (SPA fallback về `index.html`), một cổng `8000`
- [x] README mục "Chạy GĐ1"; `scripts/sync_skill.sh --check` nằm trong `lint`
- **Nghiệm thu** (Windows, Git Bash): `bash scripts/task.sh setup && bash scripts/task.sh dev` → `http://localhost:5173` thấy layout;
  sửa 1 file `.tsx` (HMR) và 1 file `.py` (API nạp lại ~2 s) → tự tải lại; `http://localhost:8000/api/v1/healthz` trả
  `{"db":"ok","gpu_core":"2.1.0"}` (từ G1-M1: `2.2.0`); `task.sh run` → `http://localhost:8000` chạy bản build; `task.sh test` + `lint` xanh.
  Đã kiểm 03/11/2026 — trừ Ctrl-C trong terminal tương tác (người dùng kiểm) và `make` (máy chưa có make).

#### G1-M1 — CSDL + Nhập dữ liệu
- [x] SQLAlchemy models + Alembic `0001_initial` cho các bảng GĐ1 ở §4 (kể cả view `util_effective`, `inventory_current`, `reclaim_current`); `render_as_batch=True`; PRAGMA foreign_keys/WAL
- [x] Seed idempotent: `app_setting` mặc định, 9 liên kết từ `backend/seeds/ip_links.csv` (`created_by='seed'`)
- [x] `import_service` theo §5 (staged → committed → rolled_back/discarded, 409 nhập trùng, summary, validation, diff IP mới/biến mất, ngày chồng lấn, số mẫu bị thay); router `/imports*`
- [x] Test API (SQLite tạm mỗi test): fixture t10, t7, inventory tổng hợp; nhập trùng → 409; nhập lại file sửa 1 giá trị → `replaced=1`, rollback khôi phục giá trị cũ; file theo giờ → nhập được + cảnh báo; seed chạy 2 lần không nhân đôi
- [x] Test thật (skip theo đúng file/sheet thiếu): T7 → 2.627 mẫu/88 IP; T10 → 2.930 mẫu/92 IP, overview ok, 30 thu hồi; inventory → 137 dòng
  — 03/11/2026 chạy được: T10 (2.930/92, overview ok) và thống kê T7 (Q13). **Chưa kiểm** (thiếu file): T7, thống kê T10, 30 thu hồi (file T10 hiện thiếu sheet `DS đã thu`)
- [x] `gpu_core` 2.2 (Q13, Q15 đã duyệt): bỏ dòng `don_vi` khác VTT; `to_daily` gom giờ→ngày trong `server_stats`/`fleet_daily`; `read_inventory` bỏ IP sai định dạng trước khi kiểm trùng; đã `sync_skill`
- **Nghiệm thu**: `task.sh migrate && task.sh seed` sạch (seed lần 2 thêm 0); `task.sh migrate down` (= `alembic downgrade base`) sạch; test xanh (68 passed, 7 skipped do thiếu dữ liệu thật). Đã kiểm 03/11/2026.
- Ghi chú triển khai: `task.sh setup/dev/run` tự `migrate` + `seed` (idempotent); app tự hủy lô staged > 24h khi khởi động;
  lô bị hủy được xóa mẫu chi tiết (chưa từng có hiệu lực); lô failed được ghi lại kèm `validation.error`.

#### G1-M2 — API phân tích + xuất Excel
- [x] `analytics_service`: fleet timeseries (day/week/month, server/gpu), fleet summary, server list (danh mục), server detail + timeseries, alerts (+matrix, pattern_counts, cards_by_zone); join `ip_link`; `Scope(all)` truyền qua mọi hàm; thêm `/meta`
- [x] Tham số hóa hằng số `gpu_core.rules` (`RuleParams`, mặc định giữ nguyên → test cũ xanh) rồi `bash scripts/sync_skill.sh` — gpu_core **2.3.0**
- [x] Cache theo `data_version` (lô committed/rolled_back, `ip_link`, `app_setting`): kho mẫu hiệu lực trong bộ nhớ (đọc CSDL 1 lần / phiên bản, làm nóng nền khi khởi động & sau xác nhận/hoàn tác lô) + LRU kết quả theo (khoảng, T, tham số luật)
- [x] `/alerts/export.xlsx` dùng `gpu_core.export.write_assessed_inventory` trên file inventory gốc + `ip_links` (+ danh sách thu hồi); test parity với CLI skill
- [x] **Test golden qua API** (CONTEXT §7): fleet 01/10–31/10 khớp sheet `HSSD theo ngay VTT`; alerts T=40 kỳ file → 35/46/11; ma trận map được
      có liên kết 34/45/10, không liên kết 33/38/9; T7 → 15/44/18; T=30 01/10–31/10 → 40/43/6 (có liên kết); danh mục T10: 89 có số liệu / 13 đã thu hồi / 35 không có
      — 03/11/2026 **đạt** phần chỉ cần file VTNet T10: 31 điểm khớp sheet (≤ 1e-6, 01/10 = 34,761/70,878/91), KPI = mean sheet, 35/46/11,
      mẫu hình 46/18/17/7/4, cờ VTNet 1, mỏng 1, ví dụ `10.207.163.82`, card Nguy hiểm 37 (A30 14 · L40 12 · RTX 6000 8 · L4 3).
      **Chưa kiểm** (thiếu file thống kê T10 / VTNet T7 / sheet `DS đã thu`): ma trận theo đầu mối, T7, danh mục — test đã viết sẵn, tự chạy khi đủ file
- [x] Test export: fixture → sheet tổng hợp + cột đánh giá; liên kết `.9↔.6` làm số map tăng 5→6; dữ liệu thật → sheet `GPU QHDC` giữ nguyên mọi công thức
      (đã kiểm với thống kê T7; số 280 kiểm khi có thống kê T10)
- [x] Test hiệu năng: fixture tổng hợp 3 năm × 120 server ≤ 1 s (đánh dấu `slow`) — 12 tháng: 0,11–0,30 s/endpoint (trung vị, chưa có kết quả tính sẵn);
      đọc sẵn 3 năm: ~2,6 s, 1 lần / phiên bản dữ liệu, chạy nền
- **Nghiệm thu**: OpenAPI (`/api/v1/openapi.json`) đầy đủ (test kiểm đủ 15 endpoint GĐ1 + summary); mọi test xanh (95 passed, 13 skipped do thiếu dữ liệu thật). Đã kiểm 03/11/2026.
- Ghi chú: `/docs` và `/redoc` đã tắt (Q17, 03/11/2026 — Swagger UI tải từ CDN); đặc tả tại `/api/v1/openapi.json`. Khoảng ngày mặc định = kỳ file VTNet mới nhất (từ 04/11/2026: 4 tuần gần nhất có dữ liệu, §14.8); `zones` để trống = mọi vùng
  (UI mặc định chọn Nguy hiểm); `owner=_unmapped` lọc server VTNet chưa có trong thống kê.

#### G1-M3 — Giao diện 5 trang
- [x] Bộ lọc toàn cục (`store/filters.ts` hàm thuần + `useFilters` đồng bộ URL; link menu giữ bộ lọc), `lib/vi.ts`, `lib/format.ts`, `lib/zones.ts`, `lib/csv.ts`
- [x] Tổng quan (§8.1), Cảnh báo (§8.2), Server (§8.3), Danh mục server (§8.4), Nhập dữ liệu (§8.5)
- [x] Vitest cho `format.ts`, `zones.ts` (kể cả "đỏ chỉ cho Nguy hiểm"), store bộ lọc, CSV — 21 test; nằm trong `task.sh test`
- [x] Kiểm thủ công 03/11/2026 (CSDL tạm, không đụng `data/app.db`), ảnh chụp trong phiên:
  - nhập T10 + thống kê T7 (kéo thả qua UI → xem trước → Xác nhận); nhập trùng → "File đã được nhập (lô #1…)"; Hoàn tác qua UI; nhập lại file đã hoàn tác được
  - §8.1 Tổng quan (kỳ file T10): GPU 38,7% · VRAM 72,3% · 92 server · 11 Nguy hiểm (46/35) · 1 dưới ngưỡng VTNet · 37 card (A30 14 · L40 12 · RTX 6000 8) ✓
  - §8.2 Cảnh báo: "11 Nguy hiểm (7 idle thật · 4 bursty) · 37 card · 1 dưới ngưỡng VTNet · 1 dữ liệu mỏng" ✓; dòng `10.207.163.82` 1,2/23,9/37,2/32·32/20 ngày ✓;
    ngưỡng T đồng bộ URL, menu giữ bộ lọc, ô ma trận → Cảnh báo lọc sẵn ✓
  - §8.3 Server `10.254.135.36`: 17,9/38,3/100/100/32·32/streak 12/20 ngày nguy hiểm, dòng Excel #4 ✓; `10.207.188.1 → VTNet 10.205.36.51` + "chưa xác nhận cặp" ✓
  - §8.4 Danh mục (thống kê T7): 129 = 81 + 0 + 48, lệch số card 8, nhóm "VTNet có – thống kê thiếu" ở cuối; CSV đủ dòng ✓
  - Xuất Excel mở được trong **Excel 16** trên Windows; sheet `GPU QHDC` còn 280 công thức, 0 lỗi sau khi tính lại ✓
  - Khởi động lại (`task.sh run`) → dữ liệu còn nguyên ✓
  - **Chưa kiểm** (thiếu file): nhập VTNet T7; số §8.4 137 = 89/13/35 và ma trận 34/45/10 với thống kê T10 (API đã có test golden chờ sẵn)
- **Nghiệm thu GĐ1**: luồng trên chạy trọn trên máy admin; số trên UI = API = golden; khởi động lại máy → `make run`, dữ liệu còn nguyên.
  — Đạt với dữ liệu hiện có (T10 + thống kê T7). Cần chạy lại phần T7 / thống kê T10 khi có đủ file.

### 10.2 GĐ2 — Triển khai & mở rộng (người dùng yêu cầu bắt đầu 03/11/2026)

#### G2-M1 — PostgreSQL + Docker Compose
- [x] `compose.yaml` (web nginx, api, db PG16, backup) + `compose.dev.yaml` (hot-reload, bind 127.0.0.1); deps nhóm `pg`
  — `docker/` (api.Dockerfile Python 3.12 + uv `--extra pg`, entrypoint tự `alembic upgrade head` + seed; web.Dockerfile Node 22 →
  nginx 1.27, proxy `/api`, CSP chỉ `'self'`; backup.sh: `pg_dump -Fc` + nén uploads lúc `BACKUP_AT`, giữ `BACKUP_KEEP`=30).
  Chỉ `web` mở cổng `${HTTP_BIND:-127.0.0.1}:${HTTP_PORT:-8080}` — **chưa có đăng nhập → không mở 0.0.0.0 trước G2-M2**.
  `.dockerignore` loại `samples/ data/ .env`. Dev: Vite + `uvicorn --reload` trong container (polling), PG ở 127.0.0.1:15432
  (máy admin đã có PostgreSQL 18 nghe 5433). `psycopg[binary]` thêm vào nhóm dev (test) và extra `pg` (image)
- [x] Chạy toàn bộ test API trên cả SQLite và PostgreSQL (tham số hóa fixture DB) — `TEST_PG_URL` → mọi test dùng
  `settings/engine/client/new_database` chạy `[sqlite]` + `[postgresql]`; mỗi test PG = 1 database clone từ database mẫu
  (migrate + seed 1 lần), xóa khi xong. `task.sh test-pg`, `task.sh pg-temp start|stop` (cụm PG tạm 127.0.0.1:55432)
- [x] `scripts/replay_batches.py` (ADR-9): SQLite → PG, kiểm bằng golden sau khi phát lại — logic `app/tools/replay.py`
  (stage → commit → [rollback] qua đúng import_service, giữ người làm + mốc thời gian gốc; chép `ip_link`, `app_setting`;
  bỏ qua lô staged/failed/discarded; từ chối đích đã có lô; kiểm sha256 file gốc) + `verify()` so số lô, 3 view hiệu lực,
  liên kết, cài đặt. Chạy: `task.sh replay` hoặc `docker compose run --rm replay`
- [x] `docs/DEPLOY_VM.md`: localhost → VM (`.env` VM, `docker compose up -d`, sao lưu, nâng cấp) + khôi phục, đường hầm SSH, sự cố
- **Nghiệm thu (03/11/2026)**:
  - pytest: SQLite 103 passed / 13 skipped; SQLite + PostgreSQL **158 passed** / 23 skipped trên **PG 18** (cụm tạm) và
    **PG 16.15** (db của compose.dev.yaml). Skip = thiếu file `samples/` + 1 test riêng SQLite (PRAGMA). Lint xanh
  - `test_replay.py`: đủ trạng thái lô (committed, rolled_back, nhập lại file đã hoàn tác, failed, discarded, liên kết/cài đặt
    đã sửa) → `verify()` khớp, API đích = API nguồn; dữ liệu thật T10 phát lại sang PG → golden `HSSD theo ngay VTT` 31 ngày,
    vùng T=40 35/46/11, card Nguy hiểm 37 đều đạt
  - Docker Desktop 29.6 (Windows): build 2 image (api 673 MB, web 50 MB; không chứa `.xlsx`/`.env`/`app.db`, chạy user `app`);
    `up --wait` → db/api healthy; `run --rm replay` bản GĐ1 (T10 + thống kê T7) → "nguồn = đích"; qua nginx 127.0.0.1:
    01/10 = 34,761 / 70,878 / 91, vùng 35/46/11, card Nguy hiểm A30 14 · L40 12 · RTX 6000 8 · L4 3; UI chạy dưới CSP không lỗi
    console; upload trùng → 409, > 20 MB → 413 (thông báo tiếng Việt từ API); xuất Excel 200
  - Sao lưu `run --rm backup now` → xóa dữ liệu → khôi phục theo DEPLOY_VM §5 → số như trên. Dev: API tự nạp lại khi sửa file,
    Vite proxy `/api` → api
  - Sửa kèm: `gpu_core` đọc Excel không đóng file (`pd.ExcelFile` chờ gc) → Windows không xóa/ghi đè được file vừa đọc; nay
    `with pd.ExcelFile(...)` (không đổi phép tính; test `test_readers_close_file`; đã sync skill)
  - **Chưa kiểm**: chạy trên VM Linux thật; service `backup` tự chạy đúng giờ `BACKUP_AT` (đã kiểm chế độ `now`)
#### G2-M2 — Tài khoản & phân quyền
- [x] Migration `server_note`, `app_user`, `audit_log`; auth (§9); `current_user()`/`Scope` thật; trang Đăng nhập, Đổi mật khẩu, Tài khoản
  — migration `0002` (+ cột `app_user.session_version`: đổi/đặt lại mật khẩu, khóa tài khoản → phiên cũ hết hiệu lực);
  `app/security.py`: bcrypt (12 vòng), JWT HS256 trong cookie `gpu_session` httpOnly + SameSite=Strict (12 giờ), CSRF double-submit
  (`gpu_csrf` + header `X-CSRF-Token`); sai 5 lần → khóa 15 phút (423); mật khẩu ≥ 10 ký tự, không chứa tên đăng nhập; mật khẩu tạm
  14 ký tự hiện 1 lần, buộc đổi (403 `password_change_required`). `/auth/login|logout|me|change-password`, `/users` (+ `PATCH`,
  `reset-password`, `unlock`); chặn tự hạ quyền / khóa admin cuối cùng. Phân quyền mức router (mặc định chặn): dữ liệu → đăng nhập,
  `/imports` + `/users` → admin; công khai chỉ `/healthz`, `/auth/login`, `/auth/logout`. `audit_log`: login*, logout, password_*,
  user_*, import_*. Admin đầu tiên: `task.sh create-admin` / `docker compose exec api python -m app.tools.users create-admin`.
  Compose bắt buộc `SECRET_KEY`; native tự tạo `data/secret_key`. Frontend: `src/auth/` (cổng đăng nhập giữ nguyên URL, menu theo
  vai trò, trang "Không có quyền", menu người dùng), trang Tài khoản; đầu mối phạm vi own: bộ lọc đầu mối khóa + thông điệp §8.6
- [x] Test phạm vi: owner `kientt6` scope own → `/alerts` T=40 chỉ 48 server (16/27/5); server dungha7 → 404; scope all → như admin;
      ma trận quyền mọi route × (admin, owner-own, owner-all, viewer, chưa đăng nhập, phải đổi mật khẩu)
  — `test_permissions.py`: fixture tổng hợp (kientt6 = 0/2/1, server ngoài phạm vi / VTNet-only / chỉ-thống-kê → 404, meta + ma trận
  chỉ còn kientt6, Excel chỉ dòng của họ); ma trận 24 route × 6 loại người dùng (route lấy từ OpenAPI → route mới buộc phải xếp mức);
  golden thật 48 server (16/27/5) viết sẵn, **tự skip** vì thiếu thống kê T10. `test_auth.py` (9), `test_schema.py` (model ≡ migration)
- **Nghiệm thu (03/11/2026)**:
  - pytest SQLite + PostgreSQL **186 passed** / 25 skipped (skip = thiếu `samples/` + test riêng SQLite); Vitest 27; lint xanh
  - Kiểm tay (bản GĐ1 T10 + thống kê T7, nâng cấp 0001 → 0002 tại chỗ): trang đăng nhập báo "chưa có tài khoản" → `create-admin` →
    đăng nhập sai báo lỗi, đúng → buộc đổi mật khẩu → vào đúng URL ban đầu; tạo đầu mối kientt6 trên UI (mật khẩu tạm hiện 1 lần) →
    đầu mối thấy 10/27/5 = đúng cột kientt6 trong ma trận của admin; server dungha7 → 404; `/imports` → trang "Không có quyền";
    Excel chỉ 2 sheet, toàn dòng kientt6
  - Docker (build lại image): `exec … create-admin`, đăng nhập qua nginx → cookie HttpOnly/SameSite=Strict; thiếu CSRF → 403
  - Quyết định trong milestone (chưa có trong PLAN): (1) Excel của đầu mối phạm vi own **bỏ dòng của người khác và mọi sheet khác**
    của file gốc (vd 'GPU QHDC' chứa số toàn bộ) — tránh lộ dữ liệu ngoài phạm vi; (2) ma trận vùng × đầu mối của owner-own không có
    cột `_unmapped`; (3) phát lại lô (ADR-9) chép thêm `app_user`, `audit_log`, `server_note` (giữ tài khoản trùng tên đã có ở đích)
  - Lỗi phát hiện khi kiểm tay & đã sửa: `/auth/me` 401 → phát sự kiện "hết phiên" → gọi lại `/auth/me` vô hạn (đăng xuất không về
    trang đăng nhập); đăng nhập sai cùng `type` với hết phiên → mất thông báo lỗi (nay `login_failed`)
  - **Chưa làm** (G2-M4): trang Nhật ký (đã ghi `audit_log`), Cài đặt. Mở mạng VM cần HTTPS phía trước + `COOKIE_SECURE=true`
#### G2-M3 — Đối soát, so sánh, ghi chú
- [x] Đối soát + liên kết IP trên UI, So sánh kỳ, xu hướng vùng theo tháng, server so sánh ≤ 5, ghi chú/giải trình/miễn trừ (§8.6)
  — API: `/gaps` (dựng lại từ Danh mục: VTNet-only · đã thu hồi / chưa rõ · lệch số card · gợi ý theo (số card, model GPU), ghép
  theo IP tăng dần khi 2 bên cùng số máy), `/ip-links` (GET mọi tài khoản theo phạm vi; POST/PATCH/DELETE chỉ admin; kiểm IPv4,
  trùng IP, `gpu_core.apply_ip_links` chặn 2 dòng thống kê cùng trỏ 1 máy; đổi cặp → bỏ xác nhận), `/compare` (mặc định 2 kỳ file
  gần nhất, `gpu_core.compare_periods`, KPI 2 kỳ, ma trận chuyển vùng + new/gone), `/trend/zones` (mỗi tháng 1 Bundle → số server
  / card mỗi vùng, tối đa 36 tháng), `/servers/timeseries?ips=` (1–5 server, ngoài phạm vi → 404), `/servers/{ip}/notes`
  (GET; POST admin mọi loại, đầu mối chỉ `explanation` trên server có owner = mình; DELETE mềm: admin hoặc người viết).
  `/alerts` thêm `notes_count`, `exempt_until`, `summary.exempt`, `hide_exempt`. **Miễn trừ không đổi vùng** (bất biến luật vùng);
  bắt buộc `valid_until` (hôm nay → ≤ 366 ngày). Ghi chú không vào cache (đọc mỗi request). Nhật ký: link_*, note_*.
  `data_version` nay gồm toàn bộ nội dung `ip_link` (trước chỉ count/max thời điểm → sửa cặp không làm cache đổi — đã có test).
  Frontend: trang **Đối soát** (admin + chỉ xem; ẩn với đầu mối), **So sánh** (tab So sánh kỳ: chọn kỳ A/B, đổi A↔B, KPI, lọc theo
  chuyển vùng, ma trận; tab So sánh server: ≤ 5 server, GPU/VRAM, ngày/tuần/tháng), **Xu hướng vùng theo tháng** trên Tổng quan,
  khung **Ghi chú & giải trình** trên trang Server, nhãn miễn trừ / số ghi chú + "Ẩn server đang miễn trừ" ở Cảnh báo.
  Kèm: `gpu_core.compare_periods` bỏ `join(lsuffix, rsuffix)` (pandas 4 bỏ) → `add_suffix` (kết quả giống hệt; đã sync skill)
- **Nghiệm thu (03/11/2026)**:
  - pytest SQLite + PostgreSQL **203 passed** / 29 skipped; Vitest 31; lint xanh. `test_g2m3.py`: dữ liệu tổng hợp 2 kỳ biết trước
    (xấu đi / cải thiện / giữ / mới / biến mất = 1/1/3/1/1; KPI GPU kỳ A = 36,17% tính tay; xu hướng 2/2/2 → 3/1/2; đối soát
    1 VTNet-only, 2 chưa rõ, 1 lệch card, gợi ý .7↔.6; vòng đời liên kết làm ma trận đổi ngay; quyền ghi chú từng vai trò)
  - Golden thật viết sẵn, **tự skip** (thiếu file): T7→T10 20 cải thiện / 5 xấu đi / 9 mới / 5 biến mất (cần VTNet T7);
    đối soát T10 3 VTNet-only, 48 = 13 + 35, 8 lệch card (cần thống kê T10)
  - Kiểm tay (CSDL tạm, dữ liệu tổng hợp 2 kỳ): So sánh kỳ hiện 36,2% → 41,7%, Nguy hiểm 2 → 3, ma trận đúng; so sánh 3 server;
    Đối soát → "Tạo liên kết" từ gợi ý (điền sẵn cặp) → VTNet-only 1 → 0, liên kết 9 → 10; ghi chú + miễn trừ trên trang Server →
    Cảnh báo: `.5` vẫn Nguy hiểm, nhãn "Miễn trừ đến 03/12/2026", ẩn được; đầu mối: menu 5 mục (không Đối soát), chỉ thêm giải trình
  - Lỗi phát hiện khi kiểm tay & đã sửa: hộp "Tạo liên kết" không điền sẵn (điền trong `afterOpenChange` → đổi sang `initialValues`);
    nhật ký không ghi được ngày (`valid_until`) → `audit()` chuyển payload sang JSON
  - **Chưa kiểm**: build lại image Docker với G2-M3 (chỉ đổi code, compose không đổi)
  - Bổ sung dữ liệu (03/11/2026, CONTEXT §7): golden thật **T7→T10 = 20 cải thiện / 5 xấu đi / 9 mới / 5 biến mất, Nguy hiểm
    19 → 11 — đạt**; T7 15/44/18 đạt; T8, T9 nhập được, TB khớp overview VTNet (thêm alias tiêu đề overview, sync skill). Thống kê
    dùng 1 file (bản T7); golden "thống kê T10" chờ bản 137 dòng (tự skip)
#### G2-M4 — Vận hành
- [x] Cài đặt, Nhật ký, backup + khôi phục, E2E Playwright (admin + đầu mối), rà soát bảo mật; dựng mới trên máy sạch ≤ 30 phút
  — `/settings` (GET/PATCH, admin; giới hạn từng khóa, ghi `settings_updated`, `updated_at` → `data_version` đổi → phân tích tính lại)
  + trang **Cài đặt** (về mặc định từng mục); `/audit` (lọc thao tác / tài khoản / ngày giờ VN / đối tượng, phân trang) + trang
  **Nhật ký**. Khôi phục native `task.sh restore <zip> --yes` (`tools/restore.py`: kiểm zip + integrity_check, tự sao lưu hiện
  trạng `truoc-khoi-phuc-*.zip`); Docker: pg_restore (DEPLOY_VM §5, đã thử ở G2-M1). E2E `frontend/e2e/flows.spec.ts`
  (Playwright 1.64 + Edge có sẵn — không tải trình duyệt; server CSDL tạm `tests/e2e_server.py`; `task.sh e2e`).
  Rà soát bảo mật `docs/SECURITY_REVIEW.md` — sửa: header bảo mật khi chạy native, openapi cần đăng nhập, đăng xuất làm hết hạn
  mọi phiên, chặn chèn công thức trong CSV, lọc HTML ở tên series biểu đồ
- **Nghiệm thu (03/11/2026)**:
  - pytest SQLite + PostgreSQL **224 passed** / 22 skipped; Vitest 34; lint xanh; **E2E 4/4** (admin: đăng nhập sai/đúng, Cảnh báo 3 server Nguy hiểm,
    tạo đầu mối + mật khẩu tạm; đầu mối: buộc đổi mật khẩu, banner phạm vi, menu 5 mục, chỉ .7, `/imports` → Không có quyền,
    server ngoài phạm vi → không tìm thấy, thêm giải trình; admin thấy trong Nhật ký) — 57 giây
  - Dựng mới native từ bản sao sạch (không `.venv`/`node_modules`/`data`): `setup` + build + `create-admin` + chạy → healthz
    trong **6 phút 36 giây** (cache uv/npm của máy có sẵn; máy mới thêm thời gian tải thư viện) — đạt ≤ 30 phút
  - Quét thư viện: Python không lỗ hổng; npm: ECharts 5 XSS mức trung bình → giảm thiểu (CSP + `safeLabel`), **khuyến nghị nâng
    ECharts 6** ở đợt riêng (đổi stack PLAN — cần người dùng duyệt)
  - Docker: build lại image (G2-M3 + G2-M4) → `up --wait` healthy; qua nginx: web 200, openapi chưa đăng nhập 401, đủ header bảo mật

---

## 11. Chiến lược kiểm thử

| Tầng | Công cụ | Nội dung | GĐ |
|---|---|---|---|
| Lõi | pytest | `test_gpu_core.py` (đã có): luật biên, parser 2 schema, liên kết IP, golden thật | 1 |
| Service/API | pytest + FastAPI TestClient + **SQLite tạm** | import state machine, golden qua API (có/không liên kết), export | 1 |
| Parity | pytest | `/alerts/export.xlsx` vs CLI skill trên cùng dữ liệu → cùng vùng từng IP | 1 |
| Hiệu năng | pytest (`slow`) | fixture tổng hợp 3 năm | 1 |
| Frontend | Vitest | `format.ts`, `zones.ts`, store bộ lọc | 1 |
| Đa CSDL | pytest | cùng bộ test API trên SQLite **và** PostgreSQL | 2 |
| Quyền | pytest | ma trận vai trò × route | 2 |
| E2E | Playwright | luồng admin + đầu mối | 2 |

Golden **độc lập**: chỉ so với (a) sheet VTNet tự tính, (b) kết quả skill v1 tháng 7, (c) số trong CONTEXT §7. Không sinh golden từ chính code đang test.

---

## 12. Rủi ro & giảm thiểu

| Rủi ro | Ảnh hưởng | Giảm thiểu |
|---|---|---|
| VTNet đổi format file lần nữa (như T7→T10) | Import vỡ | Parser theo alias + dò header; fixture từng schema; lỗi rõ "thiếu cột X, có các cột …" |
| Hiểu sai luật thu hồi VTNet (suy luận, chưa có CPU/RAM) | Cảnh báo sai | Hiển thị cả 2 luật + chú thích hạn chế; hỏi VTNet công thức chính thức (Q6) |
| Thiết kế GĐ1 chặn đường GĐ2 (SQLite-only, không có chỗ cắm auth) | Phải viết lại | Schema trung tính (§4), view thường, `Scope` + `current_user()` từ GĐ1, file gốc giữ để phát lại (ADR-9); G2-M1 chạy test trên cả 2 CSDL |
| Liên kết IP sai | Gán nhầm dịch vụ | `pair_confirmed=false` + badge ở mọi nơi; GĐ2 mới cho sửa/xác nhận, có audit |
| File chồng ngày giữa 2 tháng (01/11) | Đếm trùng / lệch | Khóa (ip, ts) + lô mới nhất thắng + báo số mẫu bị thay khi xem trước |
| Lệch nghĩa giữa UI, export, skill | Mất tin cậy | Mọi phép tính qua `gpu_core`; `sync_skill.sh --check` trong `make lint`; test parity |
| Mất dữ liệu trên máy cá nhân (GĐ1) | Mất lịch sử | `make backup`; mọi lô tái tạo được từ file gốc trong `data/uploads/` |
| Dữ liệu nội bộ lọt ra ngoài | An ninh | `.gitignore` sẵn (`samples/`, `data/`); fixture tổng hợp; không gửi dữ liệu ra dịch vụ ngoài |

---

## 13. Câu hỏi

**Đã trả lời (03/11/2026)**

| # | Câu hỏi | Trả lời → đã áp vào |
|---|---|---|
| Q1 | `10.207.188.1–9` ≡ `10.205.36.51–59` (9 server RTX6000)? | **Đúng** → seed `ip_link` (§4.7, G1-M1), golden có liên kết |
| Q2 | Triển khai ở đâu? | **VM có Docker + Compose**, trước mắt localhost → GĐ2 (§2.2, G2-M1) |
| Q3 | Đăng nhập local hay SSO? | **Tài khoản riêng của công cụ** → GĐ2 (ADR-8, G2-M2) |
| Q4 | Đầu mối có đăng nhập không? | **Có, tài khoản do admin cấp** → GĐ2 (§1.3, G2-M2) |
| Q9 | 9 cặp RTX6000: máy nào ↔ máy nào? | **Ghép theo IP tăng dần**, giữ `pair_confirmed=false` + badge tới khi admin kiểm thực tế và xác nhận (GĐ2) |
| Q10 | Đầu mối thấy server của mình hay toàn bộ? | **Mặc định chỉ của mình**; admin mở rộng từng tài khoản → GĐ2 |
| Q11 | Hệ điều hành máy localhost? | **Windows, Docker Desktop + WSL2** → ADR-7, §9, `docs/SETUP_WINDOWS_WSL.md` |
| Q12 | Làm gì trước? | **Trang quản trị đơn giản trước, Docker Compose để sau** → chia GĐ1/GĐ2 (toàn bộ PLAN) |

**Còn mở** (không chặn GĐ1)

| # | Câu hỏi | Mặc định |
|---|---|---|
| Q5 | VTNet có gửi dữ liệu theo giờ không (cột `date_hour`)? | Nhập được, gom về ngày khi tính |
| Q6 | VTNet có công thức thu hồi chính thức (kèm CPU/RAM)? | Dùng luật suy luận gpu<10 & mem<10 |
| Q7 | Có cần ngưỡng **riêng** cho GPU và VRAM? | 1 ngưỡng T; hàm thiết kế nhận được `t_gpu`, `t_mem` sau này |
| Q8 | `pivot_value` là kỳ nào — cần nhập lịch sử đơn vị khác? | Bỏ qua |
| Q13 | Thống kê T7: dòng Excel 131–135 có IP `10.29.95.16/17` (sai định dạng, trùng 5 lần, 2 đầu mối). §5.3 "bỏ IP lỗi" vs "IP trùng → chặn" | **Đã duyệt 03/11/2026, đã làm (gpu_core 2.2)**: bỏ IP lỗi (cảnh báo kèm số dòng) **trước** khi kiểm trùng; không tự tách thành 2 IP |
| Q14 | Golden T7 15/44/18 tính **không** liên kết; app luôn seed 9 liên kết `10.205.36.51–59` | **Đã làm (G1-M2)**: test API T7 chạy ở CSDL chưa seed liên kết; số T7 có liên kết chốt khi có file T7 |
| Q15 | Lọc `don_vi` và gom giờ→ngày (§5.4) chưa có trong `gpu_core` | **Đã duyệt 03/11/2026, đã làm (gpu_core 2.2)**: parser bỏ `don_vi` khác VTT; `to_daily` dùng trong `server_stats`/`fleet_daily`; DB lưu nguyên mẫu giờ |
| Q16 | KPI "TB toàn khoảng": §6 = mean chuỗi ngày (T10 kỳ file 38,748%); CONTEXT §7 "38,8%" là TB các server (38,751%); "theo card 44,8%" (CONTEXT §3.3) không tái lập được (ra 44,75% / 44,56%) | **Đã áp (G1-M2)**: KPI theo §6, test so với mean sheet `HSSD theo ngay VTT`; không dùng 44,8 làm golden |
| Q17 | `/docs` (Swagger UI mặc định của FastAPI) tải JS/CSS từ CDN — trái quy tắc "không CDN" | **Chốt 03/11/2026:** tắt `/docs` + `/redoc` (`docs_url=None`, `redoc_url=None`); giữ `/api/v1/openapi.json`. Test `test_no_cdn_docs_pages` |
| Q18 | G2-M1 có Docker nhưng chưa có đăng nhập (G2-M2) — mở web ra mạng VM lúc nào? | Mặc định `HTTP_BIND=127.0.0.1`, truy cập VM qua đường hầm SSH; chỉ mở mạng sau G2-M2 (DEPLOY_VM §4) |

---

## 14. Roadmap sau GĐ2
1. Tự động nhận file VTNet (thư mục chia sẻ/SFTP/email) → lô staged chờ admin duyệt.
   - **[x] Bước 1 — kiểm tra + xem trước khi upload (người dùng chốt 04/11/2026; file vẫn do admin upload thủ công)**:
     `services/import_checks.py` gắn mức cho từng phát hiện — **lỗi chặn** (ngày ở tương lai theo giờ VN; không tính được server
     nào) → API từ chối xác nhận (409 `import_blocked`), phải hủy lô · **cần xác nhận** (giá trị ngoài 0–100, kỳ > 45 ngày, tháng
     trên tên file ≠ tháng dữ liệu, ngày thiếu số liệu, 1 IP nhiều loại GPU, lệch overview VTNet, sẽ thay mẫu đã nhập, số server
     giảm > 20%, ghi chú khi đọc file) → `POST /imports/{id}/commit {"acknowledge": true}` (thiếu → 409 `ack_required`; nhật ký
     ghi các cảnh báo đã xác nhận) · **thông tin** (server mới / biến mất, dữ liệu mỏng, TB GPU lệch > 15 điểm, nhập bù kỳ cũ,
     thiếu overview). Xem trước tác động (qua gpu_core): vùng theo T mặc định, TB GPU/VRAM, chuỗi theo ngày, so với kỳ trước.
     Giao diện: khung "Xem trước tác động" + danh sách kiểm tra (cam / vàng / xanh — không đỏ); nút Xác nhận khóa khi có lỗi,
     có cảnh báo thì hỏi "đã xem và vẫn nhập?". Test `test_import_checks.py` (17: file lỗi dựng sẵn + T7–T10 thật không báo lỗi
     giả) + E2E bước upload có cảnh báo. File thật T7–T10: chỉ có mục "thông tin"
   - [x] Bước 1b — kiểm cấu trúc theo file chuẩn (người dùng chốt 04/11/2026: cấu trúc sheet/bảng = các file HSSD GPU T7–T10
     trong `samples/`): server_raw thiếu cột chuẩn `don_vi`/`gpu_type` → **cần xác nhận** (`missing_columns`); sheet
     `HSSD theo ngay VTT` (từ T8) đối soát với TB theo ngày tự tính (gpu_core **2.4.0** `validate_daily`, lệch > 0,01 điểm hoặc
     khác số server → **cần xác nhận** `daily_mismatch`; không có sheet → thông tin `daily_missing`); thiếu overview chỉ còn
     1 mục thông tin (trước bắt xác nhận trùng); file không còn dòng hợp lệ → nêu rõ lý do bỏ dòng. T8/T9/T10 thật khớp sheet
     theo ngày ~1e-14, số server khớp từng ngày (T10 thừa ngày tràn 01/11 — không tính là lệch)
   - [~] Bước 2 — tự nhận file: **không làm** (người dùng 04/11/2026: VTNet gửi qua Outlook nội bộ, không có API → admin tải
     file đính kèm và upload thủ công; mọi file đi qua bộ kiểm tra bước 1)
2. Báo cáo tháng cho lãnh đạo: deck theo phong cách TTCN (skill `viettel-report-slides`) từ `/fleet/summary`, `/alerts`, `/compare`.
   - **[x] Làm 04/11/2026** (người dùng chốt: nút trong app · BGĐ TT.CN giao ban tháng · 7 slide). `services/report_service.py`
     gom số 1 tháng dương lịch qua hàm phân tích sẵn có (không công thức mới): KPI, xu hướng ≤ 6 tháng (chỉ tháng có lô VTNet —
     ngày tràn 01/11 không thành "tháng 11"), so với tháng trước (`compare`), vùng × đầu mối, server Nguy hiểm + số tháng liên
     tiếp (`≥` khi chạm tháng đầu có dữ liệu), thông điệp + ≤ 3 kiến nghị **gợi ý từ số** (admin sửa được). Deck:
     `app/reports/ttcn_style.py` (bản Python của `deck_helpers.js`: màu/font/thẻ/icon/dải chốt, biểu đồ native, nhãn số kiểu VN) +
     `monthly_deck.py` (bìa · tổng quan · xu hướng · so với tháng trước · theo đầu mối · server Nguy hiểm · kết luận & kiến nghị).
     API `GET /reports/monthly?month=` + `POST /reports/monthly.pptx` (mức `user`, áp phạm vi; nhật ký `report_exported`).
     Trang "Báo cáo tháng" (admin + chỉ xem; ẩn với đầu mối): chọn tháng, xem nhanh số, sửa thông điệp/kiến nghị, tải .pptx.
     Phụ thuộc mới `python-pptx` (offline). Test `test_reports.py` (fixture 3 tháng tính tay + golden T7 21/48/19, Nguy hiểm
     19 → 11) + Vitest + E2E tải file. Đã render kiểm tra 7 slide bằng PowerPoint trên dữ liệu thật T7–T10
3. Thông báo đầu mối hằng tuần: server Nguy hiểm / streak ≥ N ngày / sắp bị VTNet thu hồi.
4. CPU/RAM khi VTNet cung cấp → luật thu hồi đầy đủ.
5. Liên kết kế hoạch cắt chuyển: card idle → nguồn nạp vùng đệm L40S (1 L40S = 2 A30 theo VRAM), xếp đợt cuốn chiếu.
6. HTTPS nội bộ cho VM; SSO/LDAP chỉ khi chính sách yêu cầu; K8s nội bộ nếu cần.
   - **[x] HTTPS — làm 04/11/2026** (người dùng chốt: nginx của app làm cổng vào, TTCN có sẵn chứng chỉ `.pem`, hạ tầng có proxy).
     `web` 2 chế độ cùng 1 image (`docker/nginx/`: `app.conf` chung · `http.conf` · `https.conf` · `40-gpu-mode.sh` chọn lúc khởi
     động): **A** `compose.tls.yaml` gắn `TLS_CERT_FILE`/`TLS_KEY_FILE` → 443 (TLS 1.2/1.3, Mozilla intermediate, http2), cổng
     HTTP → 301, HSTS 180 ngày, api `COOKIE_SECURE=true`; `HTTPS_BIND` mặc định 127.0.0.1. **B** proxy hạ tầng giữ TLS (HTTP +
     `COOKIE_SECURE=true`). `TRUSTED_PROXIES` (realip) cho cả hai. Sửa kèm: nginx ghi đè `X-Forwarded-For` (trước nối thêm → giả
     được IP trong Nhật ký). `task.sh tls-check` (scripts/tls_check.sh). Hướng dẫn DEPLOY.md §8. Còn: thử chứng chỉ thật trên VM
   - [ ] SSO/LDAP (chỉ khi chính sách yêu cầu) · K8s nội bộ (nếu cần)
7. **Nâng ECharts 5 → 6** (vá XSS GHSA-fgmj-fm8m-jvvx; thay đổi lớn) — người dùng chọn "để sau" 03/11/2026. Hiện đã giảm thiểu bằng CSP + `safeLabel` (docs/SECURITY_REVIEW.md §5). Khi làm: chạy lại Vitest + E2E + kiểm tay các biểu đồ.
8. **File VTNet theo chu kỳ TUẦN** (người dùng dự định đề nghị VTNet 04/11/2026) — **[x] làm 04/11/2026**. Phân tích: thử 3 file tuần
   tổng hợp (28/09–04/10 vắt 2 tháng, 05–11/10, 12–18/10): nhập được, không cảnh báo giả, lô mới thắng ngày trùng (không cần đổi
   schema / gpu_core / luật vùng). Chỗ phải sửa: (a) nhãn kỳ = tháng chiếm nhiều ngày nhất → 3 lô cùng "Tháng 10/2026" ở bộ lọc /
   So sánh, banner "Đang xem kỳ file Tháng 10/2026" khi chỉ là 1 tuần; (b) báo cáo tháng lấy tháng từ nhãn lô → tháng 9 có 3 ngày dữ
   liệu nhưng `/reports/monthly?month=2026-09` 404; tháng 10 mới có 18/31 ngày vẫn ghi "tháng 10/2026" không báo thiếu; (c) xem cả
   tháng khi mới có 18 ngày → **6/6 server bị gắn "dữ liệu mỏng"** (độ phủ 18/31 < 0,8), khoảng 01–18/10 thì 0/6; (d) không có phép
   kiểm khoảng trống giữa 2 lô (thiếu 1 tuần không ai biết); (e) kiểm tên file chỉ hiểu "tháng N", chưa hiểu "tuần N".
   Câu hỏi chờ người dùng: khoảng xem mặc định (tuần mới nhất / 4 tuần / tháng đến nay); báo cáo tháng chưa đủ ngày (tạm tính hay
   chặn); khoảng xem vượt quá dữ liệu có cắt về ngày có dữ liệu không (đổi mẫu số độ phủ — quyết định của người dùng); có cần xu
   hướng / so sánh theo tuần, báo cáo tuần. Thỏa thuận với VTNet: giữ nguyên cấu trúc sheet, tuần thứ 2 → CN, ngày trùng cùng giá trị.
   - **Người dùng chốt**: (1) mặc định **4 tuần gần nhất**; (2) tháng chưa đủ → **chặn xuất** báo cáo tháng + cảnh báo; (3) **cắt**
     khoảng xem về ngày có dữ liệu; (4) chỉ làm **xu hướng theo tuần**, không làm báo cáo tuần.
   - Đã làm: nhãn kỳ lô = tuần ISO `YYYY-Www` khi file ≤ 10 ngày (`import_checks.period_label`, hòa → tuần sớm hơn), file dài hơn giữ
     `YYYY-MM`; UI "Tuần 42/2026". Phép kiểm mới: `filename_week` (cần xác nhận; "tuần N tháng M" = tuần của tháng → không so),
     `filename_month` không báo khi file tuần vắt tháng có tháng ghi trên tên, `coverage_gap` (cần xác nhận: khoảng ngày chưa có lô nào
     giữa file mới và lô gần nhất trước/sau; file nhập lại không thêm ngày mới → không báo). Mặc định `resolve_context` = [ngày cuối có
     dữ liệu − 27, ngày cuối] (`DEFAULT_WINDOW_DAYS`); khoảng vượt dữ liệu → cắt, `params.clamped` + `requested_start/end`; UI ghi chú
     "Số liệu tính trên …". Báo cáo: tháng lấy từ ngày có dữ liệu (`util_repo.data_days`), `completeness` (đủ tháng = dữ liệu đã tới
     ngày cuối tháng; tháng đã qua thiếu ngày lẻ vẫn xuất + ghi chú — vd T7 thiếu 31/07), mặc định = tháng đủ mới nhất, POST .pptx
     tháng chưa đủ → 409 `month_incomplete`, nút tải khóa. `/trend/zones?granularity=week` (tuần ISO cắt theo dữ liệu, `period`,
     `n_days`, tối đa 156 tuần) + nút "Theo tháng / Theo tuần" ở Tổng quan. Preset "4 tuần gần nhất".
   - Nghiệm thu: `test_weekly.py` (15: nhãn, tên file, khoảng trống tính tay, mặc định 4 tuần, cắt khoảng — không cắt thì 6/6 server
     "mỏng"; thật: T8 sau T7 báo đúng 1 ngày trống 31/07), `test_reports` (tháng chưa đủ → 409, tháng đã qua thiếu 26 ngày vẫn xuất),
     `test_g2m3` (xu hướng tuần tính tay W40–W45: 2/2/2 · 1/3/2 · 0 · 0 · 3/1/2 · 3/1/2). Dữ liệu thật T7–T10: mặc định 05/10–01/11
     (10 Nguy hiểm / 47 Cảnh báo / 35 An toàn); 18 tuần W27–W44; báo cáo T10 giữ nguyên số (38,9% · 11 Nguy hiểm), T11 (chỉ ngày tràn
     01/11) bị chặn. Golden §7 giữ nguyên khi gọi đúng khoảng kỳ file.
9. **Áp ngưỡng T cho 1 chỉ số** (người dùng yêu cầu 05/11/2026) — **[x] làm 05/11/2026**. Luật gốc (cả 2 chỉ số, 3 vùng) giữ
   nguyên, thêm tùy chọn chỉ xét compute hoặc chỉ memory. Ví dụ người dùng: 10.224.58.73 compute 15% / memory 75%, T = 40 → luật cả 2
   = Cảnh báo; chỉ compute = **Nguy hiểm**.
   - **Người dùng chốt**: (1) chế độ 1 chỉ số chỉ có **2 vùng**: chỉ số đó ≤ T → Nguy hiểm, còn lại → An toàn, bỏ qua hẳn chỉ số kia
     (vd 60/20 chỉ compute → An toàn; vùng Cảnh báo luôn = 0); (2) đặt ở **Cài đặt** (mặc định) **và chọn khi xem** trên thanh bộ lọc
     (giống ô Ngưỡng T); (3) "Ngày nguy hiểm" và chuỗi ngày thấp tải **đếm theo chỉ số đã chọn**. Biên vẫn `<=`. Cờ VTNet không đổi.
   - Đã làm: gpu_core **2.5.0** — `RuleParams.zone_metric` (`both`/`gpu`/`mem`, mặc định `both` → kết quả y như trước, golden không
     đổi), `classify_zone(..., metric)`, `is_danger` (đếm ngày), `zone_rule_text`; nhận xét memory/compute-bound ghi đúng vùng
     ("NGUY HIỂM (theo compute) – memory-bound"), mẫu hình vẫn mô tả theo cả 2 chỉ số; Excel ghi luật đang áp, tên file thêm `_gpu`/`_mem`;
     skill: `--zone-metric`. App: cài đặt `zone_metric` (kiểu lựa chọn, seed `both`), tham số `zone_metric=` trên mọi API phân tích,
     so sánh, xu hướng, báo cáo tháng (GET + POST .pptx); `params.zone_metric` trả về; slide ghi "T = 40% · chỉ compute". UI: ô
     "Áp T cho" ở thanh bộ lọc (URL `zone_metric=`), nút chọn + câu mô tả luật ở trang Cảnh báo, ô chọn ở Cài đặt. Báo cáo tháng dùng
     cài đặt (như T).
   - Nghiệm thu: `test_gpu_core` (+9, 55 → 64: ví dụ 15/75, 60/20, biên 40/40; server_stats tổng hợp tính tay — chỉ compute Nguy hiểm .3 .5 .6,
     chỉ memory .4 .5 .6; .6 ngày nguy hiểm 4/4/5), `test_zone_metric.py` (5: ghi đè khi xem, cài đặt + kiểm hợp lệ + nhật ký, xem trước
     khi nhập, so sánh / xu hướng, Excel), `test_reports` (+1: chỉ compute T8/T9/T10 Nguy hiểm 1/3/3, chuỗi .5 ≥3 tháng).
10. **Giao diện phong cách Viettel** (người dùng yêu cầu 05/11/2026, ảnh tham khảo VOffice `anh_ui_tham_khao.png` + `viettel-logo.png`)
   — **[x] làm 05/11/2026**. Header trắng trên cùng: khối "GPU Util" nền đỏ `#ee0033` cạnh phải cắt chéo (rộng = sidebar), logo Viettel,
   dòng "Theo dõi tải GPU · TTCN-VTT"; sidebar `#241d1e`, mục menu chữ trắng in hoa, mục đang chọn nền đỏ, hover `#3a3132`; nền nội
   dung `#e6e6e6`. AntD `colorPrimary`/`colorLink` = đỏ Viettel (nút, tab, checkbox, slider, link, hover); thông báo info = navy
   `#1f2433` trên nền xám sáng (không xanh dương); nhãn vai trò admin navy; favicon đỏ; trang đăng nhập đầu thẻ đỏ + logo. Màn hẹp:
   thu khối tên, ẩn dòng phụ/logo/trạng thái API (header không tràn ở 375 px). Bỏ quy ước cũ "đỏ chỉ cho Nguy hiểm" — màu vùng giữ
   nguyên (`lib/zones.ts`), luôn có chữ + biểu tượng. Biểu đồ giữ màu chuỗi navy/teal. Logo: `frontend/src/assets/viettel-logo.png`
   (Vite đóng gói, không tải ngoài; CSP `img-src 'self'` đã đủ). Kiểm: lint, Vitest 47, E2E 6/6, xem tay Tổng quan / Cảnh báo / Cài
   đặt / đăng nhập ở 1366 px và 375 px. Bổ sung cùng ngày: `src/index.css` bỏ lề 8px mặc định của `body` (header + sidebar
   sát mép); số đếm tab Đối soát đỏ; sidebar `position: sticky` ngay dưới header (cao `100vh − 52px`, menu dài tự cuộn trong
   div con để không cắt nút mở sidebar ở màn hẹp).
11. **Sửa tay danh mục server + "Trạng thái thu hồi"** (người dùng yêu cầu 05/11/2026: server bị thu hồi / đổi đầu mối / đổi
   model, dịch vụ, CCU… mà file thống kê chưa cập nhật) — **[x] làm 05/11/2026**. Người dùng chốt: (1) **giữ sửa tay** cả khi nhập
   file thống kê mới — màn xem trước nhập liệt kê ô file mới khác giá trị đã sửa (cảnh báo không chặn, `summary.edit_conflicts`);
   (2) trạng thái thu hồi **chỉ là nhãn + bộ lọc**, không đổi phép tính (đã kiểm: mọi phép tính TB / số server / vùng / cảnh báo
   chỉ dùng server có log VTNet trong khoảng xem — server không có log, kể cả đã thu hồi, không vào mẫu số); (3) mặc định luôn
   **"Đang sử dụng"** (không suy từ sheet 'DS đã thu' — trạng thái số liệu "Đã thu hồi" theo sheet đó vẫn giữ riêng).
   Backend: bảng `inventory_override` (migration **0003**, khóa = IP trong file thống kê; cột NULL = theo file, '' = để trống;
   `reclaim_status` NULL = in_use) · `inventory_repo.apply_overrides/effective_frame` đè lên snapshot hiện hành cho phân tích,
   danh mục, chi tiết, bộ lọc (meta), xuất Excel (đầu mối/phạm vi) · `services/inventory_service.py`
   (chuẩn hóa như file: đầu mối chữ thường; trùng file → không lưu; nhật ký `inventory_edited`) · `PATCH /inventory/{inventory_ip}`
   (chỉ admin, `require_admin` ở main.py) · `data_version` gồm (IP, mốc sửa) → phân tích tính lại; đổi đầu mối → phạm vi tài khoản
   đầu mối đổi ngay · `replay` chép + kiểm bảng mới. Catalog thêm `reclaim_status`, `edited` (cột → giá trị theo file), đếm
   `reclaim_marked`, `edited`. Frontend (Danh mục server): cột "Trạng thái thu hồi" (admin đổi ngay trong bảng; người khác xem nhãn),
   bộ lọc trạng thái thu hồi (`?reclaim=`), nút **Sửa** mở hộp thoại 6 cột + trạng thái (mỗi ô hiện "Theo file: …" + "Về theo
   file"), ô sửa tay có biểu tượng bút (di chuột xem giá trị file), CSV thêm cột; chi tiết server hiện trạng thái thu hồi.
   Hàm thuần `lib/inventoryEdit.ts` (Vitest). Test `test_inventory_edit.py` (10) + replay + ma trận quyền. Kiểm: SQLite 215/12,
   SQLite + PG 346/22, Vitest 52, E2E 6/6, thử tay trên server E2E (sửa, lọc, đổi trạng thái); CSDL thật đã migrate 0003
   (sao lưu trước: `backups/gpu-util-data-20261105-155857.zip`).
   **Xuất Excel** (làm tiếp cùng ngày, người dùng đồng ý): `export_service._apply_edits` (tầng app, gpu_core/skill không đổi) ghi
   giá trị sửa tay vào đúng ô của sheet "Thống kê chi tiết" (chỉ ô khác file; nền vàng nhạt `FFF2CC` + ghi chú "Sửa tay trên web —
   theo file: …") và thêm cột cuối **"Trạng thái thu hồi"** cho mọi dòng; đầu mối phạm vi own nhận file theo đầu mối đã sửa.
   Công thức sheet GPU QHDC vẫn giữ (test dữ liệu thật). Chưa làm (đề xuất): lọc theo trạng thái thu hồi ở trang Cảnh báo.
12. **Đối soát: bổ sung server "VTNet có – thống kê thiếu" + "Sửa cặp" đổi được IP thống kê** (người dùng yêu cầu 06/11/2026;
   chốt: không thêm chỗ sửa ở trang Cảnh báo — sửa đúng trang chuyên trách: đối soát ở Đối soát, thông tin ở Danh mục server)
   — **[x] làm 06/11/2026**.
   - Bổ sung: nút **Cập nhật** (admin) ở mục "VTNet có – thống kê thiếu" → hộp thoại đủ cột như file thống kê (Loại server,
     Cấu hình, CPU, RAM, Disk, HBA, GPU — mặc định theo VTNet, Serial, **Đầu mối (bắt buộc)**, Model, Đầu vào hệ thống, Dịch vụ,
     Quản lý bằng, Tên cụm, Trạng thái thu hồi; không STT). Người dùng chốt: server đã bổ sung **rời mục đó** và **được tính cho
     đầu mối và tổng thể như server chuẩn** (ma trận vùng × đầu mối, bộ lọc, phạm vi tài khoản đầu mối, xuất Excel). TB toàn bộ
     / tổng vùng vốn đã gồm server này → không đổi; chỉ "chưa map" giảm. Danh mục: nhãn "Bổ sung trên web", đếm, sửa như dòng
     thường (không có "theo file"), nút **Bỏ bổ sung** → quay về mục VTNet-only. Chi tiết server có nhãn.
   - Lưu: `inventory_override.is_manual` + 8 cột phần cứng (migration **0004**, chỉ thêm cột); `inventory_repo.manual_rows`
     ghép vào `effective_frame` (khóa = IP VTNet; GPU đọc qua `gpu_core.parse_gpu_spec`). Dòng bổ sung "ngủ" khi file thống kê đã
     có IP (từ đó theo file, 6 cột sửa tay vẫn giữ — xem trước nhập báo `manual_in_file`) hoặc IP đã là đích 1 liên kết. API
     `POST /inventory/manual` (409 nếu đã có trong file / đã liên kết, 404 nếu VTNet chưa có số liệu, 422 thiếu đầu mối) ·
     `DELETE /inventory/manual/{ip}`; nhật ký `inventory_manual_added/removed`. Xuất Excel: thêm dòng bổ sung cuối sheet thống
     kê chi tiết (ô IP nền vàng + ghi chú) trước khi gpu_core đánh giá → có cột đánh giá như dòng thường.
   - Sửa cặp: `PATCH /ip-links/{inventory_ip}` nhận `inventory_ip` mới (phải có trong file thống kê hiện hành, chưa có liên kết
     khác → 409/422); khóa đổi → tạo dòng mới, cặp mới **chưa xác nhận**; nhật ký ghi IP thống kê trước/sau.
   - Test `test_inventory_manual.py` (12). Kiểm: SQLite 227/12, SQLite + PG 346 → 370/22, Vitest 53, E2E 6/6, thử tay trên server E2E (bổ sung .6 → mục
     VTNet-only còn 0; đổi IP thống kê 10.207.188.1 → 192.0.2.7; Danh mục hiện "Bổ sung trên web" + "Bỏ bổ sung"). CSDL thật
     đã migrate 0004 (sao lưu trước: `backups/gpu-util-data-20261106-101456.zip`).
