# CLAUDE.md — GPU Util Admin (TTCN-VTT)

Web quản trị theo dõi tải GPU dài hạn cho TTCN-VTT: nhập file tải hàng tháng của VTNet + file thống kê server vào CSDL riêng,
xem biểu đồ tải toàn bộ / từng server theo khoảng ngày, bảng cảnh báo theo ngưỡng T%. Backend dùng lại logic skill `gpu-util-vtnet`.

## Đang ở đâu
- **Giai đoạn 1 (GĐ1) — XONG** (03/11/2026): chạy trực tiếp trên **Windows** (Git Bash), không Docker, **SQLite**, **không đăng nhập**.
  Milestone G1-M0 → G1-M3 trong `PLAN.md` §10.1. 5 trang: Tổng quan · Cảnh báo · Server · Danh mục server · Nhập dữ liệu.
- **Giai đoạn 2 (GĐ2)** — người dùng yêu cầu bắt đầu 03/11/2026. **G2-M1** (PostgreSQL + Docker Compose): `compose.yaml`,
  `compose.dev.yaml`, `docker/`, `app/tools/replay.py` (+ `scripts/replay_batches.py`), `docs/DEPLOY_VM.md`.
  **G2-M2** (tài khoản & phân quyền): `app/security.py` (bcrypt, JWT cookie httpOnly SameSite=Strict, CSRF double-submit),
  `services/auth_service.py`, `routers/auth.py` + `users.py`, migration 0002; frontend `src/auth/` + trang Tài khoản.
  **G2-M3**: `services/gaps_service.py` (đối soát + liên kết IP), `compare_service.py` (so sánh kỳ, xu hướng tháng, ≤ 5 server),
  `note_service.py` (ghi chú / giải trình / miễn trừ — **miễn trừ không đổi vùng**); frontend `pages/Gaps.tsx`, `Compare.tsx`,
  `components/ZoneTrend.tsx`, `NotesCard.tsx`. **G2-M4**: `services/ops_service.py` + trang Cài đặt / Nhật ký (admin),
  `tools/restore.py` (`task.sh restore`), E2E `frontend/e2e/` (`task.sh e2e`, Edge có sẵn, server `tests/e2e_server.py`),
  `docs/SECURITY_REVIEW.md`. GĐ2 xong; việc mới → PLAN §14 / hỏi người dùng. Roadmap §14.2 **báo cáo tháng** (.pptx):
  `services/report_service.py` (số) + `app/reports/` (dựng slide, phong cách skill `viettel-report-slides`) + `pages/Report.tsx`. Mọi cổng vẫn mặc định bind `127.0.0.1`;
  mở mạng chỉ khi có HTTPS: chế độ A `compose.tls.yaml` (nginx giữ `.pem`, `HTTPS_BIND`, tự `COOKIE_SECURE=true`) hoặc B proxy
  hạ tầng phía trước + `COOKIE_SECURE=true` (DEPLOY.md §8). nginx: `docker/nginx/` (phần chung `app.conf`; header thêm phải vào
  `headers.conf` vì location có add_header không kế thừa). Kiểm chứng chỉ: `task.sh tls-check`.
- **CSDL thật `data/app.db`** (04/11/2026): đã migrate head + nhập 5 lô qua luồng nhập (thống kê 129 IP, VTNet T7→T10,
  người nhập `local-admin`), golden §7 khớp; `replay` sang PG đã thử OK. Chưa có tài khoản → người dùng tự `create-admin`.
  Deploy = `task.sh backup` → chép zip lên VM → `replay` (DEPLOY_VM §3.1). Bản sao lưu trước khi nhập: `backups/gpu-util-data-20261104-113311.zip`.

## Đọc trước khi làm
1. `PLAN.md` — kiến trúc, schema, API, UI, milestone (làm theo thứ tự, tick checkbox khi xong).
2. `CONTEXT.md` — nghiệp vụ, định dạng file VTNet (schema `t10` hiện hành, `t7` cũ), phát hiện đã kiểm chứng, **số golden**.
3. `backend/gpu_core/` — lõi đã có & đã test. Đọc code trước khi viết service.
4. `DEPLOY.md` — sổ tay deploy lên server (môi trường, image, `.env`, chuyển dữ liệu, kiểm tra, trạng thái đã/chưa kiểm).
   `AGENTS.md` = bản tóm tắt cho công cụ AI khác (Codex, ZCode…), trỏ về file này; `docs/AI_ONBOARDING.md` = nhập môn cho
   agent mới (tiến độ, thứ tự đọc, bản đồ code, prompt khởi động) — cập nhật §2 khi tiến độ / mốc test đổi.
Người dùng là admin quy hoạch hạ tầng, nói tiếng Việt, cần câu trả lời gọn, có số liệu, có căn cứ.

## Môi trường của người dùng
- **GĐ1 chạy thẳng trên Windows** (người dùng chốt 03/11/2026, thay cho WSL): repo `D:\Downloads\gpu-util-admin`,
  Python 3.12 qua `uv`, Node LTS ≥ 22 cài phía Windows. Không có `make` → `bash scripts/task.sh <lệnh>` (Makefile chỉ gọi lại file này).
  WSL Ubuntu có sẵn nhưng chưa dùng; GĐ2 (Docker Compose/VM) vẫn chạy bằng `make` trên Linux.
- Lệnh chạy trong **Git Bash** (hoặc terminal Git Bash của VS Code). Trong PowerShell, `bash` là bash của **WSL** → không dùng.
  Thiếu công cụ thì hướng dẫn người dùng tự cài, không tự cài hệ thống.
- File luôn LF (`.gitattributes`); script chỉ bash; không viết script PowerShell; cổng cấu hình qua `.env`.
  Script đặt `PYTHONUTF8=1` (console Windows cp1252 làm lỗi khi in tiếng Việt). Không export `TZ` vào tiến trình Python trên Windows.
- Lệnh hướng dẫn người dùng ghi rõ **chạy trong Git Bash**.

## Stack & lệnh
- Backend: Python 3.12, FastAPI, SQLAlchemy 2 + Alembic (`render_as_batch=True`), Pydantic v2, pandas, openpyxl. CSDL: SQLite `data/app.db` (WAL).
- Frontend: React 18 + TypeScript (strict) + Vite + Ant Design 5 (`vi_VN`) + ECharts 5 + TanStack Query + React Router.
- Lệnh: `bash scripts/task.sh <lệnh>` (≡ `make <lệnh>` khi có make): `setup` · `dev` (API :8000 tự nạp lại qua watchfiles +
  Vite :5173) · `run` (build frontend, 1 tiến trình :8000) · `test` · `lint` · `fmt` · `migrate` · `seed` · `backup` · `sync-skill`
  · `create-admin [tên]` · `reset-password <tên>` · `restore <zip> --yes` · `e2e` · `tls-check <cert> [key] [tên-miền]` · GĐ2: `test-pg` (pytest trên SQLite + PostgreSQL, cần `TEST_PG_URL`) · `pg-temp start|stop` (cụm PG tạm 127.0.0.1:55432 từ
  PostgreSQL đã cài, dữ liệu `data/pg-temp`) · `replay` (phát lại lô GĐ1 sang CSDL mới, ADR-9).
- Docker (GĐ2, `docs/DEPLOY_VM.md`): `docker compose up -d --build` (web nginx :8080 → api → db PG16 + backup hằng đêm);
  `docker compose run --rm replay` chuyển dữ liệu GĐ1; `compose.dev.yaml` = tự tải lại, PG ở 127.0.0.1:15432 (máy đã có PostgreSQL 18 nghe ở 5433).
  Image không chứa `samples/ data/ .env` (`.dockerignore`). `/docs`, `/redoc` đã tắt (Q17 — Swagger tải CDN); đặc tả ở `/api/v1/openapi.json`.
- `test_gpu_core.py` có 64 test (phần cần `samples/` tự skip theo đúng file/sheet nó thiếu).
  Test API: `conftest.py` (CSDL tạm đã migrate + seed, `warm_cache=False`), dữ liệu thật qua `tests/realdata.py`;
  có `TEST_PG_URL` → mọi test dùng `settings/engine/client/new_database` chạy cả `[sqlite]` và `[postgresql]` (mỗi test PG
  = 1 database clone từ database mẫu); test riêng SQLite đánh dấu `@pytest.mark.sqlite_only`. Đổi gì ở tầng CSDL → chạy `test-pg`.
  `test_performance.py` (`slow`) đo API 12 tháng × 120 server. gpu_core hiện là **2.5.0** (`RuleParams` + `zone_metric`, `validate_daily`).
- Nhập VTNet: `import_checks.py` gắn mức error (chặn xác nhận) / warning (cần `acknowledge`) / info + xem trước tác động;
  thêm phép kiểm mới = thêm vào `run_checks` + test file lỗi dựng sẵn. "Hôm nay" qua `import_checks.today()` (test cố định).
  File VTNet đến qua Outlook nội bộ → admin upload thủ công (không có nhập tự động); cấu trúc chuẩn = file HSSD T7–T10.
- Báo cáo tháng: `app/reports/` chỉ trình bày số từ `report_service` (không tính gì); số thiếu → `[Cần bổ sung số liệu]`.
  Giới hạn chữ thông điệp/kiến nghị (220/60/150) giữ khớp giữa `schemas/report.py` và `frontend/src/lib/report.ts` (vừa khung slide).
  Đổi bố cục slide → render kiểm tra từng slide (PowerPoint/LibreOffice) trước khi giao.
- Phân tích: `analytics_service` — SQL chỉ lấy dữ liệu, tính qua gpu_core; cache theo `data_version` (kho mẫu hiệu lực trong bộ nhớ
  + LRU kết quả). Đổi gì ảnh hưởng dữ liệu (liên kết IP, cài đặt…) phải làm `data_version` đổi.
- CSDL: `task.sh migrate` (alembic upgrade head; `migrate down` = về base) · `task.sh seed` (idempotent). `setup/dev/run` tự chạy cả hai.
- Frontend: hàm thuần trong `lib/` và `store/filters.ts` (có Vitest); trang gọi API qua `api/hooks.ts`. Locale AntD nhập từ
  `antd/es/locale/vi_VN` (bản CJS bị Vite 8 nhập sai → rơi về tiếng Anh). Thử UI trên CSDL tạm: đặt `DATABASE_URL`/`UPLOAD_DIR` trước `task.sh run`.

## Bất biến nghiệp vụ — KHÔNG được phá
- **Mọi phép tính nghiệp vụ đi qua `backend/gpu_core`** (vùng, mẫu hình, cờ VTNet, trung bình, nhận xét, xuất Excel).
  Không viết lại công thức trong SQL, router hay frontend. SQL chỉ lọc/lấy dữ liệu.
- Luật vùng: `gpu<=T và mem<=T` → danger; đúng 1 trong 2 `<=T` → warning; cả 2 `>T` → safe. Biên là `<=`.
  Tùy chọn **"Áp T cho"** (PLAN §14.9, người dùng chốt 05/11/2026): `RuleParams.zone_metric` = `both` (mặc định, luật trên) /
  `gpu` / `mem` → 2 vùng: chỉ số đó `<=T` → danger, còn lại → safe. Nguồn: cài đặt `zone_metric`, ghi đè khi xem bằng tham số
  `zone_metric=` (URL). Ngày nguy hiểm / streak theo chế độ; mẫu hình vẫn theo cả 2 chỉ số.
- Cờ VTNet: `gpu<10 và mem<10` (biên `<` chặt). Hiển thị song song, không thay luật vùng.
- TB toàn bộ server theo ngày = mean đơn giản qua server có mẫu ngày đó (= sheet VTNet `HSSD theo ngay VTT`).
  TB 1 server = mean mẫu ngày trong khoảng (= `VTT_KPI_overview` khi khoảng = kỳ file). `end` tính trọn ngày.
- **Khoảng xem** (người dùng chốt 04/11/2026, PLAN §14.8): mặc định = 4 tuần gần nhất có dữ liệu; khoảng vượt ngày có dữ liệu → cắt
  về [ngày đầu, ngày cuối có dữ liệu] (`resolve_context`, `params.clamped`). File VTNet tuần hoặc tháng đều nhận: nhãn lô `YYYY-Www`
  (≤ 10 ngày) / `YYYY-MM`. Báo cáo tháng chỉ xuất khi dữ liệu đã tới hết tháng (409 `month_incomplete`). Test golden dùng khoảng
  kỳ file tường minh, không dựa vào mặc định.
- Khóa server là **IP** (không dùng STT). Ghép inventory↔VTNet qua `COALESCE(ip_link.vtnet_ip, inventory.ip)` (= `gpu_core.apply_ip_links`).
  9 liên kết RTX6000 seed từ `backend/seeds/ip_links.csv` (ghép theo IP tăng dần, người dùng đã chốt) với `pair_confirmed=false` — code không tự đổi.
- Mẫu tải append-only theo lô; giá trị hiệu lực = lô committed mới nhất (VIEW `util_effective`). Không UPDATE/DELETE mẫu cũ để "sửa số".
  Luôn lưu file gốc vào `data/uploads/<sha256>.xlsx` — đó là nguồn để xuất Excel và để chuyển dữ liệu sang PostgreSQL ở GĐ2.
- **Sửa tay danh mục** (PLAN §14.11, người dùng chốt 05/11/2026): admin sửa đầu mối/model/đầu vào hệ thống/dịch vụ/quản lý bằng/cụm +
  "Trạng thái thu hồi" (mặc định Đang sử dụng) → bảng `inventory_override` (khóa IP thống kê) đè lên lô thống kê khi đọc
  (`inventory_repo.effective_frame` — mọi chỗ đọc thống kê để hiển thị/phạm vi phải đi qua đây), **giữ cả khi nhập file mới**
  (xem trước nhập báo ô khác). Chỉ là thông tin: không đổi phép tính; phép tính chỉ theo server có log VTNet trong khoảng xem.
- **Schema trung tính SQLite ↔ PostgreSQL** (PLAN §4): IP là TEXT, JSON qua `sa.JSON`, view thường (không materialized view), không dùng
  hàm/kiểu riêng của 1 dialect. Truy vấn qua SQLAlchemy Core/ORM.
- Mọi service nhận `Scope` (không nhận user). `deps.py`: cookie phiên → `CurrentUser` (đọc lại app_user mỗi request: khóa / đổi
  quyền có hiệu lực ngay) → `Scope.for_user` (owner + `data_scope=own` → chỉ server có owner = owner_key; còn lại toàn bộ).
  Vai trò: admin (mọi quyền) / owner (xem + xuất trong phạm vi) / viewer (xem + xuất toàn bộ). Ngoài phạm vi → **404**.
  Phân quyền gắn ở mức router trong `main.py` (mặc định chặn): dữ liệu `require_user`, `/imports` + `/users` `require_admin`;
  công khai chỉ `/healthz`, `/auth/login`, `/auth/logout`. Route mới phải được xếp mức trong `tests/test_permissions.py`
  (ma trận route × 6 loại người dùng tự lấy route từ OpenAPI). Xuất Excel cho owner-own: chỉ dòng của họ, bỏ sheet khác.
- Mật khẩu ≥ 10 ký tự, không chứa tên đăng nhập; tài khoản mới / đặt lại = mật khẩu tạm, buộc đổi. Sai 5 lần → khóa 15 phút.
  Tài khoản đầu tiên: `task.sh create-admin` (Docker: `docker compose exec api python -m app.tools.users create-admin`).
- Chạy native vẫn chỉ nghe `127.0.0.1`. Không mở `0.0.0.0`.
- Đổi gì trong `gpu_core` → `bash scripts/sync_skill.sh` (skill phải luôn khớp) + cập nhật test + CONTEXT nếu đổi nghĩa.
- Đổi luật/ngưỡng mặc định là **quyết định của người dùng** — hỏi trước, không tự đổi.

## Test
- Golden **độc lập**: sheet VTNet tự tính, kết quả skill v1 tháng 7, số trong CONTEXT §7. Không sinh golden từ chính code đang test.
- Test API dùng SQLite tạm cho mỗi test. Test dữ liệu thật đọc `samples/` và tự `skip` khi thiếu; fixture tổng hợp
  `backend/tests/fixtures/make_synthetic.py` (IP 192.0.2.x) chạy mọi nơi.
- Mỗi endpoint phân tích mới phải có test so số với golden hoặc fixture có kết quả biết trước. Bug fix: viết test tái hiện trước.

## Quy ước code
- Tên biến/hàm/bảng: tiếng Anh. Chuỗi hiển thị, thông báo lỗi API (`detail`), comment nghiệp vụ: **tiếng Việt**.
- Python: type hints đầy đủ, ruff (format + lint), mypy cho `app/`. Router mỏng → service → repo. Pydantic schema cho mọi I/O.
- Giờ mẫu: `DateTime` không timezone, quy ước giờ VN; ngày trên UI `dd/mm/yyyy`; số `Intl.NumberFormat('vi-VN')` (1 chữ số thập phân cho %).
- Frontend: chuỗi UI tập trung `src/lib/vi.ts`; màu/nhãn vùng tập trung `src/lib/zones.ts`; bộ lọc toàn cục đồng bộ URL.
  **Phong cách Viettel** (người dùng chốt 05/11/2026, PLAN §14.10): đỏ `#ee0033` cho thương hiệu, nút, tab, hover; sidebar
  `#241d1e`; nền `#e6e6e6`; token ở `src/lib/theme.ts`, khối "GPU Util" + logo ở `components/Brand.tsx`. Vì đỏ đã dùng cho giao diện,
  vùng "Nguy hiểm" **luôn** kèm chữ + biểu tượng (ZoneTag), không bao giờ chỉ bằng màu.
- Migration: mỗi thay đổi schema = 1 file Alembic có `downgrade`. Không sửa migration đã merge.
- Không CDN, không tải tài nguyên ngoài lúc chạy.

## Dữ liệu nội bộ
- `samples/`, `data/`, `*.dump`, `.env` nằm trong `.gitignore` — không commit, không dán nội dung file thật vào issue/PR.
  Ngoại lệ được commit: `backend/seeds/` và các IP đã có sẵn trong CONTEXT.md/test golden.
- Không gửi dữ liệu (IP, tên đầu mối, dịch vụ) ra dịch vụ bên ngoài.

## Cách làm việc
- Bắt đầu milestone: tóm tắt ngắn sẽ làm gì → làm từng checkbox → `task.sh test` + `task.sh lint` xanh → tick PLAN → tóm tắt thay đổi và việc còn lại.
- Gặp điều PLAN/CONTEXT không nói hoặc mâu thuẫn với dữ liệu: dừng, nêu rõ phát hiện + số liệu, đề xuất phương án, hỏi.
- Không mở rộng phạm vi ngoài milestone; không làm mục [GĐ2] khi chưa được yêu cầu; ý tưởng hay → PLAN §14.
- Skill `gpu-util-vtnet` (trong `.claude/skills/`) dùng để kiểm nhanh 1 file VTNet mới hoặc đối chiếu kết quả API.
- **Tự ghi chú (người dùng yêu cầu 04/11/2026)**: xong mỗi việc có thông tin quan trọng → cập nhật ngay tài liệu đúng danh mục,
  không đợi nhắc: deploy (env, thư viện, image, script, kết quả kiểm) → `DEPLOY.md` (+ mục 12 nhật ký); dữ liệu/golden →
  `CONTEXT.md`; milestone/quyết định/việc còn lại → `PLAN.md`; trạng thái/lệnh/quy ước → file này; cách chạy → `README.md`;
  bảo mật → `docs/SECURITY_REVIEW.md`. Bảng đầy đủ ở `AGENTS.md`. Báo cuối việc đã ghi vào đâu.
