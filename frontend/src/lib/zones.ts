// Màu & nhãn vùng / mẫu hình / trạng thái số liệu — TẬP TRUNG tại đây.
// Đỏ CHỈ dùng cho "Nguy hiểm"; vùng luôn hiển thị kèm chữ + biểu tượng (ZoneTag), không chỉ bằng màu.
// Luật phân vùng KHÔNG nằm ở frontend: vùng/mẫu hình luôn lấy từ API (gpu_core).

export type Zone = 'danger' | 'warning' | 'safe'
export type Pattern = 'idle' | 'bursty_idle' | 'memory_bound' | 'compute_bound' | 'high_load' | 'healthy'
export type DataStatus = 'has_data' | 'reclaimed' | 'no_data' | 'vtnet_only'

export const ZONE_ORDER: readonly Zone[] = ['danger', 'warning', 'safe']

export const ZONE_META: Record<Zone, { label: string; color: string; bg: string; tag: string }> = {
  danger: { label: 'Nguy hiểm', color: '#cf1322', bg: '#fff1f0', tag: 'red' },
  warning: { label: 'Cảnh báo', color: '#d46b08', bg: '#fff7e6', tag: 'orange' },
  safe: { label: 'An toàn', color: '#389e0d', bg: '#f6ffed', tag: 'green' },
}

export const PATTERN_ORDER: readonly Pattern[] = [
  'idle',
  'bursty_idle',
  'memory_bound',
  'compute_bound',
  'high_load',
  'healthy',
]

// Nhãn khớp gpu_core.rules.PATTERN_LABEL_VI (bản đầy đủ) + bản ngắn cho bảng
export const PATTERN_META: Record<Pattern, { label: string; short: string }> = {
  idle: { label: 'Idle thật', short: 'Idle' },
  bursty_idle: { label: 'Bursty (ngắt quãng)', short: 'Bursty' },
  memory_bound: { label: 'Memory-bound (giữ VRAM, ít tính toán)', short: 'Memory-bound' },
  compute_bound: { label: 'Compute-bound (dư VRAM)', short: 'Compute-bound' },
  high_load: { label: 'Tải cao ổn định', short: 'Tải cao' },
  healthy: { label: 'Dùng hiệu quả', short: 'Hiệu quả' },
}

export const DATA_STATUS_META: Record<DataStatus, { label: string; tag: string }> = {
  has_data: { label: 'Có số liệu', tag: 'blue' },
  reclaimed: { label: 'Đã thu hồi', tag: 'purple' },
  no_data: { label: 'Không có số liệu VTNet', tag: 'default' },
  vtnet_only: { label: 'Chưa có trong thống kê', tag: 'gold' },
}

// Biểu đồ: GPU% và VRAM% 2 màu trung tính phân biệt rõ (không đỏ/cam/xanh lá của vùng)
export const SERIES = {
  gpu: '#1f3a68',
  mem: '#13a8a8',
  threshold: '#595959',
  vtnet: '#8c8c8c',
} as const

export const UNMAPPED = '_unmapped'

export function isZone(v: unknown): v is Zone {
  return v === 'danger' || v === 'warning' || v === 'safe'
}

export function isPattern(v: unknown): v is Pattern {
  return typeof v === 'string' && (PATTERN_ORDER as readonly string[]).includes(v)
}

export function zoneLabel(z: string | null | undefined): string {
  return isZone(z) ? ZONE_META[z].label : '—'
}

export function patternLabel(p: string | null | undefined, short = false): string {
  if (!isPattern(p)) return '—'
  return short ? PATTERN_META[p].short : PATTERN_META[p].label
}

export function ownerLabel(owner: string | null | undefined): string {
  if (owner === UNMAPPED) return 'Chưa có trong thống kê'
  return owner ?? '—'
}

/** Sắp xếp vùng theo thứ tự hiển thị: Nguy hiểm → Cảnh báo → An toàn. */
export function compareZone(a: string | null | undefined, b: string | null | undefined): number {
  const ia = isZone(a) ? ZONE_ORDER.indexOf(a) : 99
  const ib = isZone(b) ? ZONE_ORDER.indexOf(b) : 99
  return ia - ib
}
