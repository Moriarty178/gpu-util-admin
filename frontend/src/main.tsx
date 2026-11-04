import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp, ConfigProvider } from 'antd'
import viVN from 'antd/es/locale/vi_VN' // bản ES module — bản CJS bị Vite 8 nhập sai, rơi về tiếng Anh
import dayjs from 'dayjs'
import 'dayjs/locale/vi'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import App from './App'
import { shouldRetry } from './api/client'
import { AuthGate } from './auth/AuthGate'
import { theme } from './lib/theme'

dayjs.locale('vi')

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, retry: shouldRetry, refetchOnWindowFocus: false } },
})

const rootEl = document.getElementById('root')
if (!rootEl) throw new Error('Không thấy phần tử #root')

createRoot(rootEl).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ConfigProvider locale={viVN} theme={theme}>
        <AntApp>
          <BrowserRouter>
            <AuthGate>
              <App />
            </AuthGate>
          </BrowserRouter>
        </AntApp>
      </ConfigProvider>
    </QueryClientProvider>
  </StrictMode>,
)
