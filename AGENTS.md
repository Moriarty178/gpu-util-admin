# AGENTS.md — hướng dẫn cho mọi công cụ AI (Codex, Claude Code, Copilot, Cursor…)

Web quản trị theo dõi tải GPU dài hạn cho TTCN-VTT (FastAPI + React; SQLite native / PostgreSQL qua Docker Compose).
Người dùng là admin quy hoạch hạ tầng, nói tiếng Việt, cần câu trả lời gọn, có số liệu, có căn cứ.

## Đọc trước
| Cần | File |
|---|---|
| Quy tắc làm việc, bất biến nghiệp vụ, lệnh, quy ước code (**bộ quy tắc đầy đủ — áp dụng cho mọi công cụ, không riêng Claude**) | [CLAUDE.md](CLAUDE.md) |
| **Deploy lên server** (môi trường, thư viện, image, `.env`, chuyển dữ liệu, kiểm tra, trạng thái đã/chưa kiểm) | [DEPLOY.md](DEPLOY.md) → chi tiết [docs/DEPLOY_VM.md](docs/DEPLOY_VM.md) |
| Nghiệp vụ, định dạng file VTNet, **số golden** | [CONTEXT.md](CONTEXT.md) |
| Kiến trúc, schema, API, milestone, roadmap (§14) | [PLAN.md](PLAN.md) |
| Bảo mật | [docs/SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md) |
| Chạy trên Windows | [README.md](README.md) (`bash scripts/task.sh <lệnh>` **trong Git Bash**) |

## Điều không được làm
- Viết lại công thức nghiệp vụ ngoài `backend/gpu_core` (SQL / router / frontend chỉ lọc & trình bày).
- Tự đổi luật vùng, ngưỡng mặc định, ý nghĩa phép tính — phải hỏi người dùng.
- Commit / gửi ra ngoài `samples/`, `data/`, `backups/`, `.env`, IP / tên đầu mối thật.
- Mở cổng `0.0.0.0` khi chưa có HTTPS; chạy `sudo`, tự cài Docker / công cụ hệ thống (hướng dẫn người dùng tự cài).
- Xóa dữ liệu (`docker compose down -v`, xóa `backups/`, `migrate down`) khi người dùng chưa đồng ý rõ ràng.

## Luôn ghi chú (bắt buộc, mọi công cụ)
Mỗi việc làm xong mà có thông tin quan trọng → **tự cập nhật đúng tài liệu trong cùng việc đó**, không đợi người dùng nhắc:

| Loại thông tin | Ghi vào |
|---|---|
| Biến môi trường, thư viện/phiên bản, cổng, image, script, bước deploy / chuyển dữ liệu, kết quả kiểm tra deploy | `DEPLOY.md` (mục liên quan + mục 12 "Trạng thái & nhật ký deploy"); lệnh chi tiết → `docs/DEPLOY_VM.md` |
| Phát hiện về dữ liệu / file VTNet, số golden mới đã kiểm chứng | `CONTEXT.md` (§7 cho golden) |
| Milestone, checkbox, quyết định của người dùng, việc còn lại, ý tưởng | `PLAN.md` (§10 milestone, §14 roadmap) |
| Trạng thái dự án, lệnh mới, quy ước / bất biến mới | `CLAUDE.md` (mục "Đang ở đâu", "Stack & lệnh") |
| Cách chạy cho người dùng | `README.md` |
| Rủi ro / biện pháp bảo mật | `docs/SECURITY_REVIEW.md` |

Ghi ngắn, có ngày (dd/mm/yyyy), có số; không chép dữ liệu nội bộ ngoài những gì các file trên đã có sẵn.
