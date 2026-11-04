import { defineConfig } from '@playwright/test'

// E2E (G2-M4): luồng admin + đầu mối trên bản build thật (frontend/dist) và CSDL tạm dữ liệu tổng hợp.
// Dùng trình duyệt có sẵn trên máy (Edge mặc định trên Windows; đổi bằng E2E_CHANNEL=chrome) — không tải trình duyệt.
// Chạy (Git Bash): bash scripts/task.sh e2e
const PORT = Number(process.env.E2E_PORT || 8765)

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    channel: process.env.E2E_CHANNEL || 'msedge',
    locale: 'vi-VN',
    timezoneId: 'Asia/Ho_Chi_Minh',
    viewport: { width: 1366, height: 900 },
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `uv run --directory ../backend python tests/e2e_server.py ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/v1/healthz`,
    timeout: 120_000,
    reuseExistingServer: false,
    env: { PYTHONUTF8: '1', UV_LINK_MODE: 'copy' },
  },
})
