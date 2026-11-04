import { describe, expect, it } from 'vitest'
import { fileNameFromDisposition } from '../api/client'
import { draftErrors, reportBody, type ReportDraft } from './report'

const sug: ReportDraft = { message: 'Gợi ý', recommendations: [{ title: 'A', detail: 'a' }] }

describe('reportBody', () => {
  it('không sửa → chỉ gửi tháng (backend dùng gợi ý)', () => {
    expect(reportBody('2026-10', { message: ' Gợi ý ', recommendations: [{ title: 'A ', detail: 'a' }] }, sug)).toEqual({ month: '2026-10' })
  })
  it('đã sửa → gửi bản sửa, bỏ kiến nghị trống', () => {
    const d = { message: 'Mới', recommendations: [{ title: 'B', detail: '' }, { title: ' ', detail: '' }] }
    expect(reportBody('2026-10', d, sug)).toEqual({ month: '2026-10', message: 'Mới', recommendations: [{ title: 'B', detail: '' }] })
  })
  it('xóa hết chữ → null = dùng gợi ý phía backend', () => {
    expect(reportBody('2026-10', { message: '', recommendations: [] }, sug)).toEqual({ month: '2026-10', message: null, recommendations: null })
  })
})

describe('draftErrors', () => {
  it('giới hạn = backend', () => {
    expect(draftErrors(sug)).toEqual([])
    expect(draftErrors({ message: 'x'.repeat(221), recommendations: [] })).toHaveLength(1)
    expect(draftErrors({ message: '', recommendations: [{ title: '', detail: 'chỉ có nội dung' }] })).toEqual(['Kiến nghị 1: cần tiêu đề.'])
    expect(draftErrors({ message: '', recommendations: Array(4).fill({ title: 'K', detail: '' }) })).toHaveLength(1)
  })
})

describe('fileNameFromDisposition', () => {
  it('ưu tiên filename* (UTF-8), rồi filename, rồi tên mặc định', () => {
    expect(fileNameFromDisposition(`attachment; filename="a.pptx"; filename*=UTF-8''B%C3%A1o_c%C3%A1o.pptx`, 'x')).toBe('Báo_cáo.pptx')
    expect(fileNameFromDisposition('attachment; filename="Bao_cao_GPU_thang_10_2026.pptx"', 'x')).toBe('Bao_cao_GPU_thang_10_2026.pptx')
    expect(fileNameFromDisposition(null, 'mac_dinh.pptx')).toBe('mac_dinh.pptx')
  })
})
