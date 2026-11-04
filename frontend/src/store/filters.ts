// Bộ lọc toàn cục (PLAN §8.0): [Khoảng ngày + preset] [Đầu mối] [Loại GPU] [Cụm] [Quản lý bằng] [Ngưỡng T].
// Nguồn sự thật = URL query → giữ khi chuyển trang, chia sẻ link được. Hàm thuần ở đây (test bằng Vitest).
import dayjs from 'dayjs'

export interface GlobalFilters {
  start?: string // YYYY-MM-DD; bỏ trống = kỳ file VTNet mới nhất (API tự chọn)
  end?: string
  threshold?: number // bỏ trống = cài đặt default_threshold
  owner: string[]
  gpu_model: string[]
  cluster: string[]
  managed_by: string[]
}

export const GLOBAL_KEYS = ['start', 'end', 'threshold', 'owner', 'gpu_model', 'cluster', 'managed_by'] as const
const LIST_KEYS = ['owner', 'gpu_model', 'cluster', 'managed_by'] as const
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

export const EMPTY_FILTERS: GlobalFilters = { owner: [], gpu_model: [], cluster: [], managed_by: [] }

function validDate(v: string | null): string | undefined {
  return v && DATE_RE.test(v) && dayjs(v).isValid() ? v : undefined
}

export function parseFilters(sp: URLSearchParams): GlobalFilters {
  const t = sp.get('threshold')
  const n = t === null || t === '' ? NaN : Number(t)
  let start = validDate(sp.get('start'))
  let end = validDate(sp.get('end'))
  if (!start || !end || start > end) {
    start = undefined
    end = undefined
  }
  return {
    start,
    end,
    threshold: Number.isFinite(n) && n >= 0 && n <= 100 ? n : undefined,
    owner: sp.getAll('owner').filter(Boolean),
    gpu_model: sp.getAll('gpu_model').filter(Boolean),
    cluster: sp.getAll('cluster').filter(Boolean),
    managed_by: sp.getAll('managed_by').filter(Boolean),
  }
}

/** Ghi các khóa bộ lọc (giữ nguyên tham số riêng của trang). Giá trị rỗng → xóa khỏi URL. */
export function writeFilters(sp: URLSearchParams, patch: Partial<GlobalFilters>): URLSearchParams {
  const out = new URLSearchParams(sp)
  for (const [key, value] of Object.entries(patch)) {
    out.delete(key)
    if (Array.isArray(value)) value.forEach((v) => out.append(key, String(v)))
    else if (value !== undefined && value !== null && value !== '') out.set(key, String(value))
  }
  return out
}

/** Chỉ các khóa toàn cục — dùng cho link menu để giữ bộ lọc khi chuyển trang. */
export function globalSearch(sp: URLSearchParams): string {
  const out = new URLSearchParams()
  for (const key of GLOBAL_KEYS) sp.getAll(key).forEach((v) => out.append(key, v))
  const s = out.toString()
  return s ? `?${s}` : ''
}

type ParamValue = string | number | boolean | readonly string[] | undefined | null

/** Tham số gọi API = bộ lọc toàn cục + tham số riêng (vd zones, sort, page). */
export function apiParams(f: GlobalFilters, extra: Record<string, ParamValue> = {}): URLSearchParams {
  const out = new URLSearchParams()
  if (f.start && f.end) {
    out.set('start', f.start)
    out.set('end', f.end)
  }
  if (f.threshold !== undefined) out.set('threshold', String(f.threshold))
  for (const key of LIST_KEYS) f[key].forEach((v) => out.append(key, v))
  for (const [key, value] of Object.entries(extra)) {
    if (value === undefined || value === null || value === '' || value === false) continue
    if (Array.isArray(value)) value.forEach((v) => out.append(key, String(v)))
    else out.set(key, String(value))
  }
  return out
}

export function hasNarrowing(f: GlobalFilters): boolean {
  return LIST_KEYS.some((k) => f[k].length > 0)
}

export type Preset = '4w' | 'this_month' | 'last_month' | '3m' | '6m' | '12m'

/** Khoảng preset (YYYY-MM-DD, end tính trọn ngày). `anchor` = ngày tham chiếu (hôm nay hoặc ngày cuối có số liệu). */
export function presetRange(preset: Preset, anchor: string): [string, string] {
  const a = dayjs(anchor)
  const f = (d: dayjs.Dayjs) => d.format('YYYY-MM-DD')
  switch (preset) {
    case '4w': // = khoảng mặc định của backend (DEFAULT_WINDOW_DAYS = 28) khi anchor = ngày cuối có dữ liệu
      return [f(a.subtract(27, 'day')), f(a)]
    case 'this_month':
      return [f(a.startOf('month')), f(a.endOf('month'))]
    case 'last_month': {
      const p = a.subtract(1, 'month')
      return [f(p.startOf('month')), f(p.endOf('month'))]
    }
    case '3m':
      return [f(a.subtract(3, 'month').add(1, 'day')), f(a)]
    case '6m':
      return [f(a.subtract(6, 'month').add(1, 'day')), f(a)]
    case '12m':
      return [f(a.subtract(12, 'month').add(1, 'day')), f(a)]
  }
}

/** Khoảng chọn vượt ra ngoài [lo, hi] (ngày có dữ liệu) nhưng vẫn giao nhau → khoảng sau khi cắt (backend tính trên
 * khoảng này — PLAN §14.8); không vượt / không giao / thiếu dữ liệu → null. Chỉ để hiển thị ghi chú. */
export function clampToData(
  start: string | undefined,
  end: string | undefined,
  lo: string | null | undefined,
  hi: string | null | undefined,
): [string, string] | null {
  if (!start || !end || !lo || !hi || start > hi || end < lo) return null
  if (start >= lo && end <= hi) return null
  return [start < lo ? lo : start, end > hi ? hi : end]
}

/** Chuỗi danh sách trong URL: "danger,warning" ⇄ ['danger','warning'] (chỉ giữ giá trị hợp lệ). */
export function parseList<T extends string>(v: string | null, allowed: readonly T[]): T[] {
  if (!v) return []
  const set = new Set(v.split(',').map((x) => x.trim()))
  return allowed.filter((x) => set.has(x))
}
