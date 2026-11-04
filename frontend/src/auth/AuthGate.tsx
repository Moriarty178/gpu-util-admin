import { Button, Result, Spin } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, type ReactNode } from 'react'
import { ApiError, AUTH_EVENT, apiGet, errorMessage } from '../api/client'
import type { Me } from '../api/types'
import { vi } from '../lib/vi'
import ChangePassword from './ChangePassword'
import Login from './Login'
import { AuthContext, ME_KEY } from './session'

/**
 * Cổng đăng nhập bao toàn bộ app: chưa đăng nhập → trang Đăng nhập (giữ nguyên URL đang mở);
 * mật khẩu tạm → trang Đổi mật khẩu; xong mới hiện app. API báo hết phiên ở bất kỳ đâu → tải lại /auth/me.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const me = useQuery({
    queryKey: ME_KEY,
    queryFn: ({ signal }) => apiGet<Me>('/auth/me', undefined, signal),
    retry: false,
    staleTime: 5 * 60_000,
  })
  useEffect(() => {
    const onAuth = () => void qc.invalidateQueries({ queryKey: ME_KEY })
    window.addEventListener(AUTH_EVENT, onAuth)
    return () => window.removeEventListener(AUTH_EVENT, onAuth)
  }, [qc])

  if (me.isPending) return <Spin fullscreen />
  if (me.isError) {
    const err = me.error
    if (err instanceof ApiError && err.status === 401) {
      return <Login setupRequired={err.problem.type === 'setup_required'} expired={me.data !== undefined} />
    }
    return (
      <Result
        status="warning"
        title={vi.loadError}
        subTitle={errorMessage(err)}
        extra={<Button onClick={() => void me.refetch()}>{vi.retry}</Button>}
      />
    )
  }
  if (me.data.must_change_password) return <ChangePassword forced />
  return <AuthContext.Provider value={me.data}>{children}</AuthContext.Provider>
}
