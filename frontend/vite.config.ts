import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// .env nằm ở gốc repo (dùng chung với backend): API_PORT, WEB_PORT.
// compose.dev.yaml (Vite trong container) đặt thêm VITE_HOST=0.0.0.0 và API_PROXY_TARGET=http://api:8000.
const rootDir = fileURLToPath(new URL('..', import.meta.url))

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, rootDir, '')
  const apiPort = Number(env.API_PORT || 8000)
  const webPort = Number(env.WEB_PORT || 5173)
  const host = env.VITE_HOST || '127.0.0.1' // GĐ1 không đăng nhập → chỉ nghe máy local
  const apiTarget = env.API_PROXY_TARGET || `http://127.0.0.1:${apiPort}`
  return {
    plugins: [react()],
    envDir: rootDir,
    server: {
      host,
      port: webPort,
      strictPort: true,
      proxy: { '/api': { target: apiTarget } },
    },
    preview: { host: '127.0.0.1', port: webPort, strictPort: true },
    build: { outDir: 'dist', chunkSizeWarningLimit: 2500 },
    test: { include: ['src/**/*.test.ts'] }, // e2e/ là của Playwright (task.sh e2e), không phải Vitest
  }
})
