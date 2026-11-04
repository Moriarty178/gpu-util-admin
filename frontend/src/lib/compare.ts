import type { Movement } from '../api/types'

// Chuyển vùng giữa 2 kỳ (gpu_core.compare_periods). Không dùng đỏ — đỏ chỉ dành cho vùng "Nguy hiểm".
export const MOVEMENT_ORDER: readonly Movement[] = ['worsened', 'improved', 'new', 'gone', 'same']

export const MOVEMENT_META: Record<Movement, { label: string; tag: string }> = {
  worsened: { label: 'Xấu đi', tag: 'orange' },
  improved: { label: 'Cải thiện', tag: 'green' },
  new: { label: 'Mới', tag: 'blue' },
  gone: { label: 'Biến mất', tag: 'default' },
  same: { label: 'Giữ nguyên', tag: 'default' },
}

export const MAX_COMPARE_SERVERS = 5

/** Thêm/bớt server được chọn, giữ thứ tự, không quá 5 (khớp giới hạn của API). */
export function toggleServer(selected: readonly string[], ip: string): string[] {
  if (selected.includes(ip)) return selected.filter((x) => x !== ip)
  if (selected.length >= MAX_COMPARE_SERVERS) return [...selected]
  return [...selected, ip]
}

/** Chênh lệch điểm %: dấu + rõ ràng, 1 chữ số thập phân kiểu vi-VN. */
export function fmtDelta(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const s = new Intl.NumberFormat('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(Math.abs(v))
  return v > 0 ? `+${s}` : v < 0 ? `−${s}` : s
}

/** Màu đường cho tối đa 5 server (không có đỏ — đỏ dành cho "Nguy hiểm"). */
export const COMPARE_COLORS: readonly string[] = ['#1f3a68', '#13a8a8', '#722ed1', '#d48806', '#2f54eb']

/** Tên series lấy từ dữ liệu (vd dịch vụ trong file thống kê) → bỏ ký tự HTML trước khi đưa vào ECharts
 * (tooltip ECharts 5 hiển thị tên dạng HTML — GHSA-fgmj-fm8m-jvvx; CSP 'self' đã chặn script, đây là lớp thứ 2). */
export function safeLabel(s: string | null | undefined): string {
  return (s ?? '').replace(/[<>&"'`]/g, '')
}
