# GPU Util Admin — TTCN-VTT

Công cụ quản trị theo dõi tải GPU các server của TTCN-VTT do VTNet giám sát: nhập file tải hàng tháng của VTNet và
file thống kê server vào CSDL riêng, xem biểu đồ tải toàn bộ / từng server theo khoảng ngày, bảng cảnh báo theo ngưỡng T%.

> Trạng thái: **GĐ1 xong (G1-M0 → G1-M3)** — giao diện 5 trang tại `http://localhost:8000` (`task.sh run`), đặc tả API tại
> `/api/v1/openapi.json` (Swagger `/docs` đã tắt — Q17). Lõi `backend/gpu_core` v2.3 + skill `gpu-util-vtnet`.
> **Giai đoạn 2**: G2-M1 (PostgreSQL + Docker Compose, `docs/DEPLOY_VM.md`) · G2-M2 (đăng nhập, tài khoản admin / đầu mối / chỉ xem)
> · G2-M3 (Đối soát + liên kết IP, So sánh kỳ / server, xu hướng vùng theo tháng, ghi chú · giải trình · miễn trừ)
> · G2-M4 (Cài đặt, Nhật ký, khôi phục, E2E, rà soát bảo mật — `docs/SECURITY_REVIEW.md`). **GĐ2 xong.**
> Roadmap §14.1 bước 1: kiểm tra + xem trước file VTNet trước khi nhập (lỗi chặn / cần xác nhận / thông tin).
> Roadmap §14.2: trang **Báo cáo tháng** — tải deck .pptx 7 slide phong cách TT.CN cho giao ban BGĐ.

## Có gì trong thư mục

| Đường dẫn | Nội dung |
|---|---|
| `DEPLOY.md` | **Sổ tay deploy lên server**: kiến trúc, chuẩn bị VM, `.env`, build/đóng gói image, chuyển dữ liệu, kiểm tra, trạng thái |
| `AGENTS.md` | Hướng dẫn cho công cụ AI khác (Codex, ZCode…): đọc gì trước, điều cấm, ghi chú vào đâu |
| `docs/AI_ONBOARDING.md` | Nhập môn cho AI agent mới: bối cảnh, tiến độ, thứ tự đọc, bản đồ code, quy trình, **prompt khởi động** |
| `CLAUDE.md` | Quy ước làm việc cho Claude Code (tự nạp mỗi phiên) — cũng là bộ quy tắc đầy đủ cho mọi công cụ AI |
| `PLAN.md` | Kế hoạch 2 giai đoạn: kiến trúc, CSDL, luồng nhập, phép tính, API, giao diện, milestone + nghiệm thu |
| `CONTEXT.md` | Bối cảnh nghiệp vụ, định dạng file VTNet/thống kê, phát hiện dữ liệu, số golden |
| `docs/KICKOFF_PROMPTS.md` | Prompt mẫu GĐ1 (lịch sử — prompt hiện hành ở `docs/AI_ONBOARDING.md` §9) |
| `docs/SETUP_WINDOWS_WSL.md` | Phương án WSL cũ (tham khảo cho GĐ2 / máy Linux) |
| `docs/SECURITY_REVIEW.md` | Rà soát bảo mật G2-M4: đã kiểm gì, đã sửa gì, khuyến nghị còn lại |
| `docs/DEPLOY_VM.md` | GĐ2: Docker Compose trên localhost → VM, chuyển dữ liệu GĐ1, sao lưu/khôi phục, nâng cấp |
| `compose.yaml` · `compose.dev.yaml` · `docker/` | GĐ2: web (nginx) · api · db (PostgreSQL 16) · backup; bản dev tự tải lại |
| `scripts/replay_batches.py` | GĐ2: phát lại các lô GĐ1 (SQLite + file gốc) sang PostgreSQL rồi kiểm nguồn = đích |
| `.claude/skills/gpu-util-vtnet/` | Skill (CLI + bản sao gpu_core 2.3 — đồng bộ bằng `task.sh sync-skill`) |
| `backend/gpu_core/` | Lõi: đọc file (schema t10 + t7), luật vùng, phép tính, liên kết IP, xuất Excel |
| `backend/app/` | FastAPI: `/imports`, `/fleet`, `/servers`, `/alerts` (+ export.xlsx), `/meta`, `/healthz`; phục vụ bản build frontend |
| `backend/tests/` | Test lõi (46: 40 chạy mọi nơi + 6 cần `samples/`) + test API (SQLite tạm) + golden dữ liệu thật + hiệu năng |
| `backend/alembic/` | Migration CSDL (`0001_initial`: bảng + 3 view) |
| `backend/seeds/ip_links.csv` | 9 liên kết IP server RTX6000 (thống kê `10.207.188.x` ↔ VTNet `10.205.36.x`) |
| `frontend/` | React 18 + TS + Vite + Ant Design 5 + ECharts 5 — 5 trang; Vitest (`src/**/*.test.ts`) |
| `samples/` | File thật (VTNet T7, T10; thống kê T7, T10) — **dữ liệu nội bộ, đã .gitignore** |
| `scripts/task.sh` | Mọi lệnh dự án (`Makefile` chỉ gọi lại file này) |

## Chạy GĐ1 (Windows)

Cần: **Git for Windows** (Git Bash), **uv** (tự lo Python 3.12), **Node LTS ≥ 22**. Mọi lệnh dưới đây **chạy trong Git Bash**
(hoặc terminal "Git Bash" của VS Code) tại thư mục repo. Không gõ `bash` trong PowerShell — đó là bash của WSL.

```bash
bash scripts/task.sh setup    # 1 lần: tạo .env, cài backend (uv sync) + frontend (npm ci)
bash scripts/task.sh dev      # phát triển: http://localhost:5173 (tự tải lại), API http://127.0.0.1:8000
bash scripts/task.sh run      # dùng hằng ngày: build 1 lần rồi mở http://localhost:8000
bash scripts/task.sh create-admin   # 1 lần: tạo tài khoản quản trị (in mật khẩu tạm, đăng nhập lần đầu phải đổi)
bash scripts/task.sh test     # pytest backend + Vitest frontend
bash scripts/task.sh lint     # skill đồng bộ + ruff + mypy + eslint + tsc
bash scripts/task.sh backup   # nén data/ (app.db + file gốc đã nhập) vào backups/
bash scripts/task.sh restore backups/gpu-util-data-<ngày>.zip --yes   # khôi phục (dừng app trước)
bash scripts/task.sh e2e      # kiểm thử đầu-cuối bằng Playwright + Edge có sẵn (CSDL tạm)
bash scripts/task.sh help     # danh sách lệnh
```
GĐ2: `bash scripts/task.sh test-pg` (test cả trên PostgreSQL; `pg-temp start` dựng cụm PG tạm), `replay`, và Docker Compose —
xem `docs/DEPLOY_VM.md`.
Có GNU make (Linux/WSL/VM) thì `make setup`, `make dev`… tương đương. Dữ liệu nằm ở `data/` — sao lưu thư mục này là đủ.
Cổng đổi trong `.env` (`API_PORT`, `WEB_PORT`). Server chỉ nghe `127.0.0.1` (GĐ1 không có đăng nhập).

## Kiểm tra lõi bằng skill (không cần web)

```bash
cd backend
uv run python ../.claude/skills/gpu-util-vtnet/scripts/analyze_gpu_util.py \
  --vtnet ../samples/HSSD_GPU_Thang_10_2026_-_VTT.xlsx \
  --inventory ../samples/Thong_ke_toan_bo_server_TTCN_VTT.xlsx \
  --ip-links seeds/ip_links.csv --out KetQua_T10.xlsx        # Map được: 89 (qua liên kết IP: 9)
```
