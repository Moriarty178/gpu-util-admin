# Cài đặt môi trường — Windows + WSL2 (Ubuntu)

> **Cập nhật 03/11/2026: GĐ1 chạy thẳng trên Windows (Git Bash) — xem README mục "Chạy GĐ1" và PLAN ADR-7.**
> Tài liệu WSL dưới đây giữ lại để tham khảo (máy Linux/WSL, chuẩn bị GĐ2).

> **GĐ1 (đang làm) không cần Docker.** Công cụ chạy thẳng trong Ubuntu/WSL: Python (qua `uv`) + Node (qua `nvm`) + SQLite (có sẵn).
> Nguyên tắc: **project nằm trong filesystem của WSL (`~/projects/...`), mọi lệnh chạy trong terminal Ubuntu** (hoặc terminal của
> VS Code đang kết nối WSL). Không làm việc trên `C:\` (`/mnt/c/...`) — chậm và hot-reload không nhận thay đổi file.

## 1. Công cụ cơ bản (1 lần, trong Ubuntu)

```bash
sudo apt update && sudo apt install -y make unzip git curl build-essential sqlite3
git config --global core.autocrlf input     # không đổi LF -> CRLF
```

**Python + uv** (uv tự lo đúng phiên bản Python, không đụng Python hệ thống):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc            # hoặc mở terminal mới
uv --version
uv python install 3.12      # nếu python3 --version < 3.12
```

**Node LTS qua nvm** (bản nvm mới nhất xem ở github.com/nvm-sh/nvm/releases):
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.8/install.sh | bash
source ~/.bashrc
nvm install --lts && node --version && npm --version     # cần Node ≥ 22
```

## 2. Đặt project vào WSL

```bash
mkdir -p ~/projects && cd ~/projects
cp /mnt/c/Users/<tên-user-windows>/Downloads/gpu-util-admin.zip .
unzip gpu-util-admin.zip && cd gpu-util-admin      # giải nén TRONG WSL để giữ quyền thực thi script
git init && git add -A && git commit -m "Khởi tạo: kế hoạch + gpu_core + skill v2.1"   # samples/, data/ tự bị loại
```

Mở thư mục từ Windows khi cần (kéo thả file VTNet mới, mở file Excel kết quả): trong Ubuntu gõ `explorer.exe .`
— hoặc Explorer: `\\wsl$\Ubuntu\home\<user-ubuntu>\projects\gpu-util-admin`.

## 3. Mở bằng VS Code + Claude Code

1. Trong Ubuntu: `cd ~/projects/gpu-util-admin && code .` → góc dưới trái VS Code phải hiện **"WSL: Ubuntu"**.
2. Extensions → Claude Code → nếu có nút **"Install in WSL: Ubuntu"** thì bấm (có thể phải đăng nhập lại một lần).
3. Mở project là **folder duy nhất** của cửa sổ (không gộp vào workspace có folder khác) để Claude đọc `CLAUDE.md` và skill `.claude/skills/`.
4. Gõ `/skills` → thấy `gpu-util-vtnet`. Nếu thấy **2 bản**, bản trong tài khoản Claude của anh là v1 (lỗi với file T10) → nhắc Claude dùng bản trong project.
5. Dán prompt "Phiên đầu tiên" trong `docs/KICKOFF_PROMPTS.md`.

(Dùng terminal thay VS Code: `curl -fsSL https://claude.ai/install.sh | bash` trong Ubuntu rồi `claude` trong thư mục project.)

## 4. Kiểm tra lõi (trước khi có Makefile)

```bash
cd ~/projects/gpu-util-admin/backend
uv venv --python 3.12 && . .venv/bin/activate
uv pip install pandas openpyxl pytest
python -m pytest -q                      # 39 passed
deactivate
```

## 5. Sau G1-M0 — chạy công cụ

```bash
cd ~/projects/gpu-util-admin
cp .env.example .env
make setup        # 1 lần: cài thư viện backend (uv) + frontend (npm)
make dev          # đang phát triển: web http://localhost:5173 (tự tải lại khi sửa code), API :8000
make run          # dùng hằng ngày: build 1 lần, mở http://localhost:8000
make backup       # nén data/ (app.db + file gốc đã nhập) kèm ngày giờ
```
Mở các địa chỉ trên bằng trình duyệt **Windows** (WSL2 tự chuyển `localhost`). Dữ liệu nằm ở `data/` — sao lưu thư mục này là đủ.

## 6. Sự cố thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Sửa code mà web/API không tự tải lại; mọi thứ chậm | Project nằm ở `/mnt/c/...` | Chuyển vào `~/projects/...` (mục 2) |
| `bash: ./scripts/...: Permission denied` | Giải nén bằng Windows Explorer làm mất quyền thực thi | `chmod +x scripts/*.sh` hoặc `bash scripts/<tên>.sh` |
| `/usr/bin/env: 'bash\r': No such file` | File bị đổi sang CRLF khi sửa bằng công cụ phía Windows | `git config core.autocrlf input`; `git add --renormalize .` (`.gitattributes` đã ép LF) |
| `error: externally-managed-environment` khi `pip install` | Ubuntu khóa pip hệ thống (PEP 668) | Dùng `uv venv` / `uv pip` (mục 4) |
| `Address already in use` (8000, 5173) | Cổng đang bị dùng (tiến trình cũ hoặc dịch vụ Windows) | Dừng tiến trình cũ (`make dev` dùng Ctrl-C) hoặc đổi `API_PORT` / `WEB_PORT` trong `.env` |
| `node: command not found` trong terminal VS Code | nvm chưa nạp vào shell đó | Mở terminal mới hoặc `source ~/.bashrc` |
| Trình duyệt Windows không mở được `localhost:8000` | Server nghe sai địa chỉ hoặc WSL tắt chuyển localhost | Kiểm tra server nghe `127.0.0.1`; `wsl --shutdown` rồi mở lại Ubuntu |
| Không tải được gói pip/npm | Mạng công ty chặn/proxy | Đặt `HTTPS_PROXY`, hoặc mirror nội bộ: `UV_INDEX_URL`, `npm config set registry <mirror>` |

## 7. [GĐ2] Khi chuyển sang Docker Compose

Bật Docker Desktop → **Settings → Resources → WSL integration** → bật cho Ubuntu; kiểm tra `docker version`, `docker compose version`
trong Ubuntu. Giới hạn RAM WSL nếu cần: `C:\Users\<tên>\.wslconfig` với `[wsl2]` `memory=6GB`, rồi `wsl --shutdown`.
Hướng dẫn chi tiết sẽ nằm ở `docs/DEPLOY_VM.md` (tạo ở G2-M1).

Nguồn: [Claude Code — Advanced setup (Windows/WSL)](https://code.claude.com/docs/en/setup) ·
[Claude Code — VS Code](https://code.claude.com/docs/en/vs-code) ·
[Docker — WSL 2 best practices](https://docs.docker.com/desktop/features/wsl/best-practices/) ·
[nvm releases](https://github.com/nvm-sh/nvm/releases) · [Node.js releases](https://nodejs.org/en/about/previous-releases)
