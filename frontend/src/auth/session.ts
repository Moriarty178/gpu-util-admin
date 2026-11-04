import type { QueryClient } from '@tanstack/react-query'
import { createContext, useContext } from 'react'
import { apiPost } from '../api/client'
import type { Me } from '../api/types'

export const ME_KEY = ['/auth/me'] as const

export const AuthContext = createContext<Me | null>(null)

/** Tài khoản đang đăng nhập (chỉ dùng bên trong <AuthGate>). */
export function useAuth(): Me {
  const me = useContext(AuthContext)
  if (!me) throw new Error('useAuth() phải nằm trong <AuthGate>')
  return me
}

/** Đổi người dùng → bỏ mọi số liệu đã cache của phiên trước (không để lộ dữ liệu giữa 2 tài khoản). */
export function startSession(qc: QueryClient, me: Me) {
  qc.removeQueries({ predicate: (q) => q.queryKey[0] !== ME_KEY[0] })
  qc.setQueryData(ME_KEY, me)
}

export async function logout(qc: QueryClient) {
  try {
    await apiPost<void>('/auth/logout')
  } finally {
    qc.removeQueries({ predicate: (q) => q.queryKey[0] !== ME_KEY[0] })
    await qc.invalidateQueries({ queryKey: ME_KEY })
  }
}
