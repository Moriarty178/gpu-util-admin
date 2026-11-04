// Báo cáo tháng (Roadmap §14.2): giới hạn chữ (= backend schemas/report.py, vừa khung slide) + dựng body tải .pptx.
export const REPORT_LIMITS = { message: 220, recTitle: 60, recDetail: 150, recs: 3 } as const

export interface Rec {
  title: string
  detail: string
}

export interface ReportDraft {
  message: string
  recommendations: Rec[]
}

/** Lỗi nhập (chuỗi tiếng Việt) — rỗng = hợp lệ. Thông điệp trống = dùng gợi ý; kiến nghị trống tiêu đề bị bỏ. */
export function draftErrors(d: ReportDraft): string[] {
  const out: string[] = []
  if (d.message.trim().length > REPORT_LIMITS.message) out.push(`Thông điệp tối đa ${REPORT_LIMITS.message} ký tự.`)
  const recs = d.recommendations.filter((r) => r.title.trim() || r.detail.trim())
  if (recs.length > REPORT_LIMITS.recs) out.push(`Tối đa ${REPORT_LIMITS.recs} kiến nghị.`)
  recs.forEach((r, i) => {
    if (!r.title.trim()) out.push(`Kiến nghị ${i + 1}: cần tiêu đề.`)
    if (r.title.trim().length > REPORT_LIMITS.recTitle) out.push(`Kiến nghị ${i + 1}: tiêu đề tối đa ${REPORT_LIMITS.recTitle} ký tự.`)
    if (r.detail.trim().length > REPORT_LIMITS.recDetail) out.push(`Kiến nghị ${i + 1}: nội dung tối đa ${REPORT_LIMITS.recDetail} ký tự.`)
  })
  return out
}

const same = (a: ReportDraft, b: ReportDraft) =>
  a.message.trim() === b.message.trim() &&
  JSON.stringify(a.recommendations.map((r) => [r.title.trim(), r.detail.trim()])) ===
    JSON.stringify(b.recommendations.map((r) => [r.title.trim(), r.detail.trim()]))

/** Body POST /reports/monthly.pptx: giữ nguyên gợi ý → không gửi chữ (nhật ký ghi "không sửa"); đã sửa → gửi bản sửa. */
export function reportBody(month: string, draft: ReportDraft, suggestion: ReportDraft): Record<string, unknown> {
  if (same(draft, suggestion)) return { month }
  const recs = draft.recommendations
    .map((r) => ({ title: r.title.trim(), detail: r.detail.trim() }))
    .filter((r) => r.title)
  return { month, message: draft.message.trim() || null, recommendations: recs.length ? recs : null }
}
