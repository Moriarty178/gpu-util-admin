// Định dạng hiển thị (vi-VN): số `38,7%`, ngày `dd/mm/yyyy`, giờ VN. Chỉ trình bày — không tính toán nghiệp vụ.

const pct1 = new Intl.NumberFormat('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const int0 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 })
const dec1 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 })
const VN_TZ = 'Asia/Ho_Chi_Minh'
export const DASH = '—'

const isNum = (v: number | null | undefined): v is number => typeof v === 'number' && Number.isFinite(v)

/** 38.75 → "38,8%" (1 chữ số thập phân). */
export function fmtPct(v: number | null | undefined): string {
  return isNum(v) ? `${pct1.format(v)}%` : DASH
}

/** 2930 → "2.930". */
export function fmtInt(v: number | null | undefined): string {
  return isNum(v) ? int0.format(v) : DASH
}

/** 0.656 → "0,7"; 12 → "12". */
export function fmtDec1(v: number | null | undefined): string {
  return isNum(v) ? dec1.format(v) : DASH
}

/** Tỷ lệ 0..1 → "65,6%". */
export function fmtRatio(v: number | null | undefined): string {
  return isNum(v) ? fmtPct(v * 100) : DASH
}

/** "2026-10-01" (hoặc ISO có giờ) → "01/10/2026". Không qua Date để tránh lệch múi giờ. */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return DASH
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}/${m[1]}` : DASH
}

/** "01/10/2026 – 01/11/2026". */
export function fmtRange(start: string | null | undefined, end: string | null | undefined): string {
  return `${fmtDate(start)} – ${fmtDate(end)}`
}

/** Thời điểm hệ thống (UTC, không timezone, vd "2026-11-03T08:01:02.123") → giờ VN "03/11/2026 15:01". */
export function fmtDateTimeUtc(iso: string | null | undefined): string {
  if (!iso) return DASH
  const withZone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`
  const d = new Date(withZone)
  if (Number.isNaN(d.getTime())) return DASH
  const parts = new Intl.DateTimeFormat('vi-VN', {
    timeZone: VN_TZ,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(d)
  const get = (t: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === t)?.value ?? ''
  return `${get('day')}/${get('month')}/${get('year')} ${get('hour')}:${get('minute')}`
}

/** "4×NVIDIA L40S" → "4×L40S"; "8 x Quadro RTX 6000" → "8 x RTX 6000" (chỉ rút gọn để hiển thị). */
export function shortGpu(spec: string | null | undefined): string {
  if (!spec) return DASH
  return spec.replace(/\b(NVIDIA|Quadro)\s+/gi, '').replace(/\s+/g, ' ').trim()
}

/** Kỳ 'YYYY-MM' → 'Tháng 10/2026'. */
export function fmtPeriodLabel(label: string | null | undefined): string {
  const m = label ? /^(\d{4})-(\d{2})$/.exec(label) : null
  return m ? `Tháng ${Number(m[2])}/${m[1]}` : (label ?? DASH)
}

/** Giá trị CSV kiểu Excel tiếng Việt: dấu thập phân ',' (dùng với dấu phân cách ';'). */
export function csvNumber(v: number | null | undefined, digits = 1): string {
  return isNum(v) ? v.toFixed(digits).replace('.', ',') : ''
}
