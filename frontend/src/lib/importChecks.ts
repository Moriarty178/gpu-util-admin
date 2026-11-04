// Kiểm tra lô VTNet trước khi nhập (Roadmap §14.1). Mức + màu tập trung ở đây; không dùng đỏ (đỏ chỉ cho "Nguy hiểm").
export type CheckLevel = 'error' | 'warning' | 'info'

export interface ImportCheck {
  code: string
  level: CheckLevel
  title: string
  detail?: string
  items?: string[]
  n_items?: number
}

export const CHECK_LEVELS: readonly CheckLevel[] = ['error', 'warning', 'info']

export const CHECK_META: Record<CheckLevel, { label: string; tag: string }> = {
  error: { label: 'Lỗi — không nhập được', tag: 'orange' },
  warning: { label: 'Cần xác nhận', tag: 'gold' },
  info: { label: 'Thông tin', tag: 'blue' },
}

export function readChecks(validation: Record<string, unknown> | null | undefined): ImportCheck[] {
  const v = validation?.checks
  if (!Array.isArray(v)) return []
  return v.filter(
    (x): x is ImportCheck =>
      !!x && typeof x === 'object' && typeof (x as ImportCheck).title === 'string' &&
      CHECK_LEVELS.includes((x as ImportCheck).level),
  )
}

export function countByLevel(checks: readonly ImportCheck[]): Record<CheckLevel, number> {
  const out: Record<CheckLevel, number> = { error: 0, warning: 0, info: 0 }
  for (const c of checks) out[c.level] += 1
  return out
}

/** Xác nhận nhập được không: lỗi → không; có cảnh báo → cần người dùng xác nhận đã xem (backend kiểm lại). */
export function commitGate(checks: readonly ImportCheck[]): { blocked: boolean; needsAck: boolean } {
  const n = countByLevel(checks)
  return { blocked: n.error > 0, needsAck: n.error === 0 && n.warning > 0 }
}
