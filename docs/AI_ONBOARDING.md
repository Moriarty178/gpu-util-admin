# AI_ONBOARDING.md — Nhập môn dự án cho AI agent nội bộ (ZCode / model tự host / bất kỳ công cụ nào)

> Mục đích: một AI agent **chưa từng làm dự án này** đọc file này (và các file nó chỉ tới) là nắm đủ bối cảnh, tiến độ, quy tắc
> để (1) phát triển tiếp tính năng và (2) dẫn người dùng deploy lên server thật.
> Người dùng: dán **prompt ở mục 9** vào cửa sổ chat của agent khi mở dự án lần đầu.
> Ảnh chụp trạng thái ở mục 2 ghi ngày 04/11/2026 — khi khác thực tế, **tin code + test + `DEPLOY.md` §12 + `PLAN.md`** hơn file này,
> rồi sửa lại file này.

---

## 1. Dự án là gì (đọc trong 1 phút)

- **GPU Util Admin** — web quản trị nội bộ của **TTCN-VTT** (Viettel) theo dõi tải GPU dài hạn của ~92–137 server GPU.
- Hằng tháng **VTNet** gửi file Excel tải GPU (sheet `server_raw`, mỗi dòng = 1 server × 1 ngày: % GPU util, % VRAM) qua
  **Outlook nội bộ** → admin tải về → **upload thủ công** vào app (không có API / nhập tự động). Kèm **file thống kê server**
  (IP, đầu mối sử dụng, dịch vụ, loại GPU…).
- App xếp mỗi server vào **vùng** theo ngưỡng **T%** (mặc định 40): `gpu<=T và mem<=T` → **Nguy hiểm**; đúng 1 trong 2 `<=T` →
  **Cảnh báo**; cả 2 `>T` → **An toàn**. Song song: **cờ VTNet** `gpu<10 và mem<10` (nguy cơ VTNet thu hồi GPU).
- Người dùng chính: **admin quy hoạch hạ tầng** (nói tiếng Việt, cần câu trả lời gọn, có số liệu, có căn cứ). Ngoài ra: **đầu mối**
  (owner — chỉ xem server của mình), **chỉ xem** (viewer). Báo cáo tháng trình **BGĐ TT.CN** ở giao ban.
- Stack: **Python 3.12 + FastAPI + SQLAlchemy 2 + Alembic + pandas** (backend), **React 18 + TypeScript + Vite + Ant Design 5 +
  ECharts 5** (frontend). CSDL: **SQLite** khi chạy native (máy Windows của admin) · **PostgreSQL 16** khi chạy Docker Compose (server).
- **Mọi phép tính nghiệp vụ nằm trong `backend/gpu_core/`** (thư viện Python thuần, có test golden). App không gọi AI / skill nào
  khi chạy; thư mục `.claude/` chỉ là công cụ phụ của Claude Code (mục 6).

---

## 2. Tiến độ hiện tại (ảnh chụp 04/11/2026)

| Giai đoạn / mục | Trạng thái |
|---|---|
| **GĐ1** (G1-M0 → M3): 5 trang Tổng quan · Cảnh báo · Server · Danh mục server · Nhập dữ liệu; SQLite; native Windows | ✅ xong |
| **GĐ2 G2-M1**: PostgreSQL + Docker Compose (`compose.yaml`: web nginx · api · db PG16 · backup), `replay` chuyển dữ liệu | ✅ |
| **G2-M2**: đăng nhập (bcrypt, JWT cookie httpOnly, CSRF), vai trò admin / đầu mối / chỉ xem, phạm vi dữ liệu | ✅ |
| **G2-M3**: Đối soát + liên kết IP, So sánh kỳ, xu hướng tháng, ghi chú / giải trình / miễn trừ | ✅ |
| **G2-M4**: Cài đặt, Nhật ký, sao lưu/khôi phục, E2E Playwright, rà soát bảo mật | ✅ |
| Roadmap §14.1: kiểm tra + xem trước file VTNet khi upload (lỗi chặn / cần xác nhận / thông tin; đối soát sheet theo ngày) | ✅ (tự nhận file: không làm — Outlook) |
| Roadmap §14.2: **Báo cáo tháng** `.pptx` 7 slide phong cách TT.CN (trang "Báo cáo tháng") | ✅ |
| Roadmap §14.6: **HTTPS** — nginx giữ chứng chỉ `.pem` (`compose.tls.yaml`), `task.sh tls-check` | ✅ cấu hình + thử chứng chỉ tự ký; ⏳ chứng chỉ thật trên VM |
| Roadmap §14.3 thông báo đầu mối · §14.4 CPU/RAM (chờ VTNet) · §14.5 kế hoạch cắt chuyển · §14.7 nâng ECharts 6 | ⏳ chưa làm |

**Dữ liệu** (máy gốc của admin, có thể đã chép kèm): `data/app.db` (SQLite) đã nhập 5 lô — thống kê 129 IP + VTNet T7, T8, T9,
T10/2026; file gốc ở `data/uploads/<sha256>.xlsx`; **chưa có tài khoản** (tạo: `bash scripts/task.sh create-admin`).
File thống kê hiện tại thiếu 11 IP so với VTNet T10 (8 server H200 `10.29.95.x` + 3) → chờ bản thống kê mới (CONTEXT.md §7).

**Mốc test** (máy gốc, 04/11/2026, có `samples/`): `bash scripts/task.sh test` → backend **172 passed / 12 skipped** (SQLite),
Vitest **44 passed**; `task.sh lint` xanh; với PostgreSQL (`task.sh test-pg`) **279 passed**; E2E `task.sh e2e` **6/6**.
Thiếu `samples/` (dữ liệu thật) → nhiều test tự **skip**, không fail — đó là đúng thiết kế.

**Deploy lên server thật**: chưa làm. Mọi thứ cần biết + danh sách việc còn thiếu: `DEPLOY.md` (đặc biệt §12).

---

## 3. Đọc gì, theo thứ tự (model ngữ cảnh ngắn: đọc theo tầng, không nạp cả `PLAN.md` 800 dòng một lần)

**Tầng 1 — bắt buộc trước mọi việc** (~30 KB):
1. `AGENTS.md` — điều cấm + bảng "thông tin gì ghi vào file nào".
2. `CLAUDE.md` — **bộ quy tắc đầy đủ** (tên "CLAUDE" là lịch sử; áp dụng cho mọi agent): trạng thái, môi trường, lệnh, bất biến
   nghiệp vụ, quy ước code, cách làm việc.
3. File này.

**Tầng 2 — nghiệp vụ & kiến trúc** (đọc lướt rồi quay lại khi cần):
4. `CONTEXT.md` — nghiệp vụ, định dạng file VTNet (`t10` hiện hành, `t7` cũ), phát hiện dữ liệu đã kiểm chứng, **§7 số golden**.
5. `PLAN.md` — đọc theo mục: §0 tóm tắt · §2.3 ADR (quyết định kiến trúc) · §4 schema · §6 **định nghĩa phép tính** · §7 API ·
   §10.2 nghiệm thu GĐ2 (biết cái gì đã kiểm) · **§14 roadmap** (việc tiếp theo). Các mục khác đọc khi đụng tới.

**Tầng 3 — theo nhiệm vụ**:
| Nhiệm vụ | Đọc thêm |
|---|---|
| Deploy / vận hành server | `DEPLOY.md` (toàn bộ) → `docs/DEPLOY_VM.md` → `compose.yaml`, `compose.tls.yaml`, `.env.example`, `docker/` |
| Sửa / thêm phép tính | `backend/gpu_core/` (`rules.py` luật vùng & mẫu hình, `metrics.py` trung bình / so sánh kỳ, `parsing.py` đọc file, `export.py` xuất Excel) + `backend/tests/test_gpu_core.py` |
| Thêm API | `backend/app/main.py` (gắn quyền mức router), `routers/`, `services/`, `repo/`, `schemas/`, `tests/test_permissions.py` |
| Thêm trang / sửa UI | `frontend/src/routes.tsx`, `pages/`, `api/hooks.ts`, `lib/vi.ts` (chuỗi), `lib/zones.ts` (màu vùng), `auth/access.ts` |
| Nhập file VTNet | `backend/app/services/import_service.py`, `import_checks.py`, `tests/test_import_checks.py` |
| Báo cáo tháng | `services/report_service.py` (số), `app/reports/` (dựng slide), `pages/Report.tsx`, `tests/test_reports.py` |
| Bảo mật | `docs/SECURITY_REVIEW.md`, `app/security.py`, `app/deps.py`, `docker/nginx/` |

**Không cần đọc / lỗi thời**: `docs/KICKOFF_PROMPTS.md` (prompt GĐ1 thời WSL — lịch sử), `docs/SETUP_WINDOWS_WSL.md` (phương án
WSL cũ, không dùng). Không mở `samples/`, `data/`, `backups/` trừ khi nhiệm vụ cần (dữ liệu nội bộ).

---

## 4. Bản đồ code

```
backend/
  gpu_core/            lõi tính toán (KHÔNG phụ thuộc web/DB) — mọi công thức nghiệp vụ ở đây, version 2.4.0
  app/
    main.py            create_app(): gắn router + mức quyền (mặc định chặn), phục vụ frontend/dist khi chạy native
    config.py          Settings (pydantic-settings, đọc .env)        deps.py   phiên → CurrentUser → Scope
    security.py        bcrypt, JWT cookie, CSRF                       scope.py  Scope / CurrentUser / LOCAL_ADMIN
    routers/           HTTP mỏng: auth users imports fleet servers alerts gaps compare reports ops meta
    services/          nghiệp vụ: analytics (cache theo data_version) · import + import_checks · compare · gaps · note ·
                       ops (cài đặt, nhật ký) · report · export · auth
    repo/              truy vấn SQLAlchemy (chỉ lọc / lấy dữ liệu)
    db/                models, views (util_effective, inventory_current, reclaim_current), migrate, seed
    schemas/           Pydantic I/O              reports/   dựng .pptx (python-pptx)
    tools/             CLI: users (create-admin, reset-password), backup, restore, replay
  alembic/versions/    0001 (GĐ1), 0002 (tài khoản, nhật ký, ghi chú) — mỗi đổi schema = 1 file mới có downgrade
  seeds/ip_links.csv   9 liên kết IP RTX6000 (người dùng đã chốt, pair_confirmed=false)
  tests/               pytest; conftest.py (CSDL tạm mỗi test, tham số hóa SQLite/PG); realdata.py (samples/, tự skip);
                       fixtures/make_synthetic.py (dữ liệu tổng hợp IP 192.0.2.x)
frontend/src/
  routes.tsx  pages/ (12 trang)  components/  api/ (client.ts, hooks.ts, types.ts)  auth/  lib/ (hàm thuần + Vitest)  store/
  e2e/        Playwright (Edge có sẵn, server tests/e2e_server.py)
docker/       api.Dockerfile · web.Dockerfile · nginx/ (http/https, header, 40-gpu-mode.sh) · backup.sh · api-entrypoint.sh
scripts/      task.sh (mọi lệnh) · lib.sh · dev.sh · sync_skill.sh · tls_check.sh · replay_batches.py
compose.yaml · compose.tls.yaml · compose.dev.yaml · .env.example · Makefile (vỏ gọi task.sh)
.claude/skills/gpu-util-vtnet/   bản sao gpu_core + CLI analyze_gpu_util.py cho Claude Code (xem mục 6)
```

---

## 5. Luật bất khả xâm phạm (tóm tắt — bản đầy đủ: `CLAUDE.md` "Bất biến nghiệp vụ")

1. **Mọi phép tính nghiệp vụ đi qua `backend/gpu_core`** — không viết lại công thức trong SQL, router, frontend.
2. **Không tự đổi** luật vùng (biên `<=`), cờ VTNet (`<10`, biên chặt), ngưỡng mặc định, ý nghĩa phép tính → **hỏi người dùng**.
3. TB toàn bộ server theo ngày = mean đơn giản qua server có mẫu ngày đó; TB 1 server = mean mẫu ngày trong khoảng; `end` trọn ngày.
4. Khóa server là **IP**; ghép thống kê ↔ VTNet qua liên kết IP (`gpu_core.apply_ip_links`).
5. Mẫu tải **append-only** theo lô, giá trị hiệu lực = lô committed mới nhất; **không UPDATE/DELETE số liệu để "sửa số"** — sai thì
   hoàn tác lô / nhập lại. Luôn giữ file gốc `data/uploads/<sha256>.xlsx`.
6. Schema **trung tính SQLite ↔ PostgreSQL** (không hàm riêng 1 dialect); đổi tầng CSDL → chạy `task.sh test-pg`.
7. Phân quyền mức router, mặc định chặn; route mới phải được xếp mức trong `tests/test_permissions.py`; ngoài phạm vi → **404**.
8. Mặc định chỉ nghe **127.0.0.1**; mở mạng chỉ khi có **HTTPS** (DEPLOY.md §8).
9. **Golden độc lập** (CONTEXT §7): không sinh số kỳ vọng từ chính code đang test. Số trên API/UI phải khớp golden.
10. Không commit / gửi ra ngoài `samples/`, `data/`, `backups/`, `.env`, IP / tên đầu mối thật. Không CDN, không tải tài nguyên ngoài
    lúc chạy. Không `sudo`, không tự cài công cụ hệ thống (hướng dẫn người dùng tự cài).
11. Đổi `gpu_core` → `bash scripts/sync_skill.sh` + cập nhật test (+ CONTEXT nếu đổi nghĩa).

---

## 6. Về `.claude/` và skill `gpu-util-vtnet` (agent không phải Claude Code)

- `.claude/skills/gpu-util-vtnet/` = **bản sao** `backend/gpu_core` + CLI `scripts/analyze_gpu_util.py`, dùng để Claude Code kiểm nhanh
  1 file VTNet. App **không** đọc thư mục này; image Docker **không** chứa nó (`.dockerignore`).
- Agent khác vẫn dùng được như công cụ dòng lệnh (đối chiếu kết quả API với file VTNet mới):
  `PYTHONUTF8=1 uv run --directory backend python ../.claude/skills/gpu-util-vtnet/scripts/analyze_gpu_util.py --vtnet <file> --inventory <file> --out <KetQua.xlsx>`
  (thêm `--threshold`, `--start/--end`, `--ip-links` khi cần; `--help` xem đủ; thiếu `PYTHONUTF8=1` trên Windows → lỗi in tiếng Việt)
  (kết quả là dữ liệu nội bộ — để ngoài repo hoặc trong `data/`).
- `scripts/sync_skill.sh --check` (nằm trong `task.sh lint`) báo lệch khi `gpu_core` đổi mà chưa đồng bộ.

---

## 7. Môi trường & lệnh

**Máy Windows (cách đang dùng)** — mọi lệnh chạy trong **Git Bash** (không phải PowerShell: `bash` trong PowerShell là của WSL):
| Cần | Kiểm |
|---|---|
| Python 3.12 qua `uv` | `uv --version` |
| Node LTS ≥ 22 + npm | `node --version` |
| Git Bash | `bash --version` |
| (tùy) Docker Desktop — chỉ khi thử bản Docker | `docker version` |
| (tùy) PostgreSQL cài sẵn — chỉ cho `test-pg` qua `pg-temp` | `ls "/c/Program Files/PostgreSQL"` |

**Máy nội bộ không ra Internet**: `task.sh setup` cần tải thư viện từ PyPI (`uv sync`) và npm registry (`npm ci`); Docker build
cần Docker Hub + `ghcr.io`. Không có mạng → hỏi người dùng về **mirror nội bộ** (biến `UV_INDEX_URL` / `UV_DEFAULT_INDEX`,
`npm config set registry …`) hoặc mang sẵn `backend/.venv` / `frontend/node_modules` / image Docker (`docker save`, DEPLOY.md §5B)
từ máy có mạng. **Không tự cài** — liệt kê cho người dùng.

**Lệnh chính** (`bash scripts/task.sh <lệnh>`, ≡ `make <lệnh>` nếu có make):
`setup` (cài thư viện + migrate + seed) · `dev` (API :8000 tự nạp lại + Vite :5173) · `run` (build frontend, 1 tiến trình :8000) ·
`test` (pytest + Vitest) · `lint` (sync skill? + ruff + mypy + eslint + tsc) · `fmt` · `migrate` · `seed` · `backup` · `restore <zip> --yes` ·
`create-admin [tên]` · `reset-password <tên>` · `e2e` · `test-pg` · `pg-temp start|stop` · `replay` · `tls-check <cert> [key] [tên-miền]` · `sync-skill`.
Thử UI trên CSDL tạm (không đụng `data/`): đặt `DATABASE_URL` / `UPLOAD_DIR` trước `task.sh run`.

**Đặc thù Windows đã gặp** (máy gốc): file phải **LF** (Python `Path.write_text` ghi CRLF → dùng `write_bytes` / `newline="\n"`);
script đặt `PYTHONUTF8=1` (console cp1252); **không export `TZ`** vào tiến trình Python; `pg_ctl start` giữ stdout → chuyển hướng
`</dev/null >/dev/null 2>&1`; `python3 -` trong Git Bash chờ stdin; `OPENSSL_CONF` có thể trỏ file không tồn tại → `unset`;
curl của Git Bash (Schannel) cần `--ssl-no-revoke` với CA tự tạo; PostgreSQL 18 cài sẵn trên máy gốc nghe cổng 5433.

---

## 8. Quy trình làm việc chuẩn

**Tính năng mới** (theo `CLAUDE.md` "Cách làm việc"):
1. Tóm tắt ngắn sẽ làm gì; hỏi người dùng các điểm **thuộc quyết định của họ** (luật, ngưỡng, ai được xem, bố cục báo cáo…).
2. Làm từng phần; tính toán mới → thêm vào `gpu_core` (+ `sync_skill.sh`), service gọi gpu_core, router mỏng, schema Pydantic.
3. Test: endpoint phân tích mới phải có test so với golden hoặc fixture có kết quả **tính tay**; bug fix → test tái hiện trước;
   route mới → xếp mức trong `test_permissions.py`; đổi schema → migration Alembic mới có `downgrade` (không sửa migration cũ).
4. `bash scripts/task.sh test` + `bash scripts/task.sh lint` xanh (đổi tầng CSDL → thêm `test-pg`; đổi luồng UI → `e2e`).
5. **Ghi chú** theo bảng trong `AGENTS.md` (PLAN tick checkbox + nghiệm thu, CLAUDE trạng thái, DEPLOY nếu ảnh hưởng deploy…).
6. Báo cáo: đã làm gì, số test, đã ghi vào file nào, việc còn lại. Không mở rộng phạm vi ngoài yêu cầu; ý tưởng → PLAN §14.

**Gặp điều tài liệu không nói hoặc mâu thuẫn với dữ liệu**: dừng, nêu phát hiện + số liệu, đề xuất phương án, hỏi.

**Quy ước**: tên biến/hàm/bảng tiếng Anh; chuỗi UI, thông báo lỗi API (`detail`), comment nghiệp vụ **tiếng Việt**; ngày UI
`dd/mm/yyyy`; số `Intl.NumberFormat('vi-VN')` (1 chữ số thập phân cho %); đỏ chỉ dùng cho "Nguy hiểm".

**Lời khuyên cho model tự host**: đọc từng mục thay vì cả file lớn; **kiểm chứng bằng cách chạy test / đọc code**, không đoán API
hay tên hàm; trích dẫn `file:dòng` khi giải thích; không bịa số liệu (thiếu → nói thiếu).

---

## 9. Prompt khởi động — dán vào ZCode khi mở dự án lần đầu

```
Bạn là AI agent hỗ trợ tôi (admin quy hoạch hạ tầng TTCN-VTT) phát triển tiếp và deploy dự án "GPU Util Admin" trong thư mục
này. Trả lời tiếng Việt, gọn, có số liệu, có căn cứ (trích file:dòng). Phiên này CHỈ đọc và báo cáo — chưa sửa file, chưa cài gì,
không sudo, không chạy lệnh xóa dữ liệu.

1) Đọc theo thứ tự: AGENTS.md → CLAUDE.md → docs/AI_ONBOARDING.md → CONTEXT.md → PLAN.md (§0, §2.3, §4, §6, §7, §10.2, §14;
   phần khác khi cần) → DEPLOY.md (toàn bộ, chú ý §12). Lướt cấu trúc backend/gpu_core, backend/app, frontend/src.
   PLAN.md dài ~800 dòng: đọc theo mục, đừng nạp một lần.
2) Kiểm môi trường máy này (chỉ đọc): hệ điều hành; đang chạy trong Git Bash hay shell nào; uv --version; node --version;
   npm --version; docker version (nếu có); có Internet / mirror PyPI-npm nội bộ không (thử `curl -sI -m 5 https://pypi.org/simple/`
   và `curl -sI -m 5 https://registry.npmjs.org/`, hoặc hỏi tôi địa chỉ mirror). Có các thư mục samples/, data/ (data/app.db, data/uploads/), backend/.venv, frontend/node_modules không.
   Thiếu công cụ → liệt kê cách cài để TÔI tự làm.
3) Nếu đủ công cụ và thư viện: chạy `bash scripts/task.sh test` và `bash scripts/task.sh lint`, so với mốc ở
   docs/AI_ONBOARDING.md §2 (172 passed / 12 skipped + Vitest 44 khi có samples/; thiếu samples/ thì skip nhiều hơn, không được fail).
   Chưa có thư viện thì DỪNG ở bước này, báo tôi cần chạy `bash scripts/task.sh setup` (cần mạng/mirror).
4) Báo cáo ngắn:
   a. Dự án làm gì, kiến trúc & luồng dữ liệu (≤ 10 dòng).
   b. 5–8 bất biến nghiệp vụ / quy tắc quan trọng nhất bạn sẽ tuân thủ (luật vùng, gpu_core, append-only, phân quyền, golden…).
   c. Tiến độ: phần đã xong, phần còn lại (PLAN §14 + DEPLOY.md §12), dữ liệu đang có trên máy này.
   d. Kết quả kiểm môi trường + test (số passed/skipped/failed) và điểm khác so với máy gốc.
   e. Những gì tài liệu nói mâu thuẫn với code/máy này, hoặc chỗ bạn chưa rõ — liệt kê để tôi trả lời.
   f. Đề xuất 3 việc tiếp theo (tính năng hoặc deploy), mỗi việc: lợi ích, phụ thuộc, câu hỏi cần tôi chốt.
Từ phiên sau: mỗi việc làm xong có thông tin quan trọng → tự ghi vào đúng file theo bảng "Luôn ghi chú" trong AGENTS.md
và báo đã ghi vào đâu.
```

**Prompt mẫu cho các phiên sau** (mỗi việc lớn nên là 1 phiên mới để ngữ cảnh gọn):

- *Tính năng*:
  ```
  Đọc AGENTS.md, CLAUDE.md, docs/AI_ONBOARDING.md (§5, §8) và PLAN.md §14 mục <số>. Làm "<tên việc>".
  Trước khi code: tóm tắt cách làm (file sẽ sửa, API/UI mới, test sẽ viết, kỳ vọng tính tay) và hỏi tôi các điểm cần chốt.
  Làm xong: task.sh test + lint xanh, ghi chú theo AGENTS.md, báo cáo số test và việc còn lại.
  ```
- *Deploy*:
  ```
  Đọc DEPLOY.md (toàn bộ, đặc biệt §11 hướng dẫn cho AI và §12 trạng thái) và docs/DEPLOY_VM.md. Dẫn tôi deploy lên VM <mô tả VM:
  OS, có Internet không, có proxy/HTTPS của hạ tầng không, tên miền>. Mỗi bước: 1 nhóm lệnh, nói rõ chạy ở máy nào, kết quả mong
  đợi, chờ tôi dán kết quả rồi mới sang bước sau; đối chiếu bảng kiểm tra DEPLOY.md §7. Xong: ghi kết quả vào DEPLOY.md §12.
  ```
- *Nhập dữ liệu tháng mới*:
  ```
  Tôi vừa nhận file VTNet tháng <MM/YYYY>. Đọc CONTEXT.md (định dạng file) và import_checks.py. Hướng dẫn tôi upload trên trang
  Nhập dữ liệu, giải thích từng mục kiểm tra (lỗi chặn / cần xác nhận / thông tin) và so số với tháng trước. Không sửa CSDL trực tiếp.
  ```
