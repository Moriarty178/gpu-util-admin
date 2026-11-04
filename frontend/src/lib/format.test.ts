import { describe, expect, it } from 'vitest'
import {
  csvNumber,
  fmtDate,
  fmtDateTimeUtc,
  fmtDec1,
  fmtInt,
  fmtPct,
  fmtPeriodLabel,
  fmtRange,
  fmtRatio,
  shortGpu,
} from './format'

describe('format vi-VN', () => {
  it('phần trăm 1 chữ số thập phân, dấu phẩy', () => {
    expect(fmtPct(38.7483)).toBe('38,7%')
    expect(fmtPct(72.3197)).toBe('72,3%')
    expect(fmtPct(0)).toBe('0,0%')
    expect(fmtPct(100)).toBe('100,0%')
  })
  it('giá trị thiếu → gạch ngang', () => {
    expect(fmtPct(null)).toBe('—')
    expect(fmtPct(undefined)).toBe('—')
    expect(fmtPct(Number.NaN)).toBe('—')
    expect(fmtInt(null)).toBe('—')
  })
  it('số nguyên có dấu chấm ngăn nghìn', () => {
    expect(fmtInt(2930)).toBe('2.930')
    expect(fmtInt(92)).toBe('92')
    expect(fmtDec1(0.65)).toBe('0,7')
    expect(fmtRatio(0.65625)).toBe('65,6%')
  })
  it('ngày dd/mm/yyyy, không lệch múi giờ', () => {
    expect(fmtDate('2026-10-01')).toBe('01/10/2026')
    expect(fmtDate('2026-11-01T00:00:00')).toBe('01/11/2026')
    expect(fmtDate(null)).toBe('—')
    expect(fmtRange('2026-10-01', '2026-11-01')).toBe('01/10/2026 – 01/11/2026')
  })
  it('thời điểm hệ thống (UTC) → giờ VN', () => {
    expect(fmtDateTimeUtc('2026-11-03T08:01:02.123456')).toBe('03/11/2026 15:01')
    expect(fmtDateTimeUtc('2026-11-03T20:30:00')).toBe('04/11/2026 03:30') // qua ngày
    expect(fmtDateTimeUtc(null)).toBe('—')
  })
  it('rút gọn tên GPU để hiển thị', () => {
    expect(shortGpu('4×NVIDIA L40S')).toBe('4×L40S')
    expect(shortGpu('8 x Quadro RTX 6000')).toBe('8 x RTX 6000')
    expect(shortGpu(null)).toBe('—')
  })
  it('nhãn kỳ và số CSV', () => {
    expect(fmtPeriodLabel('2026-10')).toBe('Tháng 10/2026')
    expect(fmtPeriodLabel('2026-W42')).toBe('Tuần 42/2026')
    expect(fmtPeriodLabel('2026-W05')).toBe('Tuần 5/2026')
    expect(csvNumber(72.3197)).toBe('72,3')
    expect(csvNumber(null)).toBe('')
  })
})
