# Prompt mẫu cho Claude Code

Mở VS Code **kết nối WSL** tại `~/projects/gpu-util-admin` (xem `docs/SETUP_WINDOWS_WSL.md` mục 3), mở khung Claude Code rồi dán lần lượt.
Mỗi milestone nên là **1 cuộc hội thoại mới** để ngữ cảnh gọn; CLAUDE.md, PLAN.md, CONTEXT.md giữ mạch xuyên phiên.

> Hiện tại làm **GĐ1 — trang quản trị đơn giản** (không Docker, SQLite, không đăng nhập). GĐ2 chỉ làm khi tôi yêu cầu.

---

## 0. Phiên đầu tiên — làm quen & xác nhận kế hoạch (chưa code)

```
Đọc CLAUDE.md, PLAN.md, CONTEXT.md và toàn bộ backend/gpu_core.
Kiểm tra môi trường (không cài gì, không sudo): pwd không nằm dưới /mnt/c; python3 --version; uv --version;
node --version; npm --version. Thiếu gì thì liệt kê lệnh cài theo docs/SETUP_WINDOWS_WSL.md để tôi tự chạy.
Nếu có uv: tạo venv trong backend/, cài pandas openpyxl pytest, chạy `python -m pytest -q` — phải 39 passed.
Sau đó trả lời ngắn:
1) Tóm tắt kiến trúc GĐ1 & luồng dữ liệu trong 10 dòng.
2) Điểm trong PLAN thấy mâu thuẫn, thiếu, hoặc rủi ro (kèm đề xuất).
Chưa viết code.
```

## G1-M0 — Khung dự án chạy native trong WSL

```
Làm G1-M0 trong PLAN.md §10.1. Không Docker. Không sửa logic backend/gpu_core; 39 test phải xanh (chạy lại trên Python 3.12).
Backend: uv project trong backend/ (deps GĐ1 như pyproject.toml, nhóm pg/auth để GĐ2), FastAPI tối thiểu /api/v1/healthz,
pydantic-settings đọc .env, chỉ nghe 127.0.0.1.
Frontend: Vite + React 18 + TS strict + AntD 5 (vi_VN) + ECharts 5 + TanStack Query + React Router; layout menu 5 trang trống;
proxy /api sang API_PORT.
scripts/dev.sh chạy uvicorn --reload + vite cùng lúc (Ctrl-C dừng cả hai); make run build frontend rồi FastAPI phục vụ dist ở :8000.
.env.example, Makefile (setup, dev, run, test, lint, fmt, migrate, seed, backup, sync-skill), README mục "Chạy GĐ1".
Xong thì tự chạy make setup, make dev, gọi healthz, kiểm tra :5173 và :8000, make test + make lint, tick checkbox G1-M0 và tóm tắt.
```

## G1-M1 — CSDL + Nhập dữ liệu

```
Làm G1-M1: SQLAlchemy models + Alembic 0001_initial cho các bảng GĐ1 ở PLAN §4 (schema trung tính SQLite/PostgreSQL;
view util_effective dùng ROW_NUMBER, inventory_current, reclaim_current; render_as_batch; PRAGMA foreign_keys + WAL).
Seed idempotent: app_setting mặc định + 9 liên kết từ backend/seeds/ip_links.csv.
import_service theo PLAN §5 (staged → committed → rolled_back/discarded, 409 nhập trùng sha256, summary, validation, diff)
dùng gpu_core.read_vtnet_workbook / read_inventory; lưu file gốc vào data/uploads/<sha256>.xlsx.
Viết đủ test trong checklist G1-M1 (SQLite tạm mỗi test), gồm test dữ liệu thật (skip khi không có samples/):
T7 2.627 mẫu/88 IP; T10 2.930 mẫu/92 IP, overview ok, 30 thu hồi; inventory 137 dòng. Thêm fixture theo giờ.
```

## G1-M2 — API phân tích + xuất Excel

```
Làm G1-M2 theo PLAN §6, §7 (chỉ endpoint GĐ1). Mọi phép tính qua gpu_core (tham số hóa hằng số trong rules.py, giữ mặc định,
39 test cũ xanh, rồi bash scripts/sync_skill.sh). Mọi service nhận Scope (GĐ1 = Scope(all)).
/alerts/export.xlsx dùng gpu_core.export.write_assessed_inventory trên file inventory gốc + ip_links.
Test golden qua API đúng CONTEXT §7: fleet 01/10–31/10 khớp sheet "HSSD theo ngay VTT"; alerts T=40 kỳ file → 35/46/11;
ma trận map được có liên kết 34/45/10, không liên kết 33/38/9; T7 → 15/44/18; T=30 01/10–31/10 → 40/43/6;
danh mục T10: 89 có số liệu / 13 đã thu hồi / 35 không có. Test export (sheet GPU QHDC còn 280 công thức) và hiệu năng (slow).
```

## G1-M3 — Giao diện 5 trang

```
Làm G1-M3: bộ lọc toàn cục đồng bộ URL, các trang Tổng quan / Cảnh báo / Server / Danh mục server / Nhập dữ liệu theo wireframe
PLAN §8.1–8.5 và nguyên tắc §8.0 (tiếng Việt, vi-VN, đỏ chỉ cho Nguy hiểm, markLine T và 10%). Vitest cho format/zones/store.
Cuối cùng: tôi sẽ nhập T7 → T10 → thống kê qua UI; anh chụp ảnh màn hình từng trang (Playwright headless nếu cài được, không thì
mô tả) và đối chiếu số trên UI với phần nghiệm thu §8.1–8.5.
```

---

## Prompt dùng hằng tháng (sau khi công cụ chạy)

```
VTNet vừa gửi file <tên file>. Dùng skill gpu-util-vtnet (kèm --ip-links backend/seeds/ip_links.csv) kiểm nhanh
file này (schema, kỳ, số server, đối soát overview, IP mới/biến mất) trước khi tôi nhập vào công cụ.
Nếu format khác t10/t7 thì chỉ ra cột/sheet khác biệt và đề xuất sửa parser + fixture.
```

## Khi kết quả lạ

```
Số trên màn Cảnh báo (kỳ X, T=Y) khác kết quả skill gpu-util-vtnet chạy trên cùng file. Tìm nguyên nhân:
so từng IP giữa API và CLI, chỉ ra IP lệch và vì sao (khoảng ngày? ip_link? lô bị hoàn tác?). Viết test tái hiện trước khi sửa.
```

## Khi sẵn sàng sang GĐ2

```
Bắt đầu GĐ2 theo PLAN §10.2, milestone G2-M1 (PostgreSQL + Docker Compose + chuyển dữ liệu bằng phát lại lô).
Trước khi làm: rà lại PLAN GĐ2 với những gì đã xây ở GĐ1, đề xuất chỉnh sửa nếu cần, chờ tôi duyệt.
```
