import { describe, expect, it } from 'vitest'
import { toCsv } from '../lib/csv'
import { apiParams, clampToData, EMPTY_FILTERS, globalSearch, parseFilters, parseList, presetRange, writeFilters } from './filters'

const sp = (s: string) => new URLSearchParams(s)

describe('bộ lọc toàn cục ⇄ URL', () => {
  it('đọc URL hợp lệ', () => {
    const f = parseFilters(sp('start=2026-10-01&end=2026-10-31&threshold=30&owner=kientt6&owner=_unmapped&gpu_model=A30'))
    expect(f).toEqual({
      start: '2026-10-01',
      end: '2026-10-31',
      threshold: 30,
      owner: ['kientt6', '_unmapped'],
      gpu_model: ['A30'],
      cluster: [],
      managed_by: [],
    })
  })
  it('bỏ giá trị sai: ngày lỗi, start > end, ngưỡng ngoài 0–100', () => {
    expect(parseFilters(sp('start=2026-13-01&end=2026-10-31')).start).toBeUndefined()
    expect(parseFilters(sp('start=2026-10-31&end=2026-10-01')).end).toBeUndefined()
    expect(parseFilters(sp('start=2026-10-01')).start).toBeUndefined() // thiếu end → dùng kỳ mặc định
    expect(parseFilters(sp('threshold=101')).threshold).toBeUndefined()
    expect(parseFilters(sp('threshold=abc')).threshold).toBeUndefined()
    expect(parseFilters(sp('threshold=0')).threshold).toBe(0)
    expect(parseFilters(sp(''))).toEqual(EMPTY_FILTERS)
  })
  it('ghi bộ lọc giữ tham số riêng của trang, xóa giá trị rỗng', () => {
    const out = writeFilters(sp('zones=danger&owner=a&threshold=30'), { owner: ['b', 'c'], threshold: undefined })
    expect(out.getAll('owner')).toEqual(['b', 'c'])
    expect(out.get('threshold')).toBeNull()
    expect(out.get('zones')).toBe('danger')
  })
  it('link menu chỉ mang khóa toàn cục', () => {
    expect(globalSearch(sp('start=2026-10-01&end=2026-10-31&zones=danger&page=2&owner=x'))).toBe(
      '?start=2026-10-01&end=2026-10-31&owner=x',
    )
    expect(globalSearch(sp('zones=danger'))).toBe('')
  })
  it('tham số API: lặp khóa danh sách, bỏ false/rỗng', () => {
    const f = parseFilters(sp('threshold=40&owner=a&owner=b'))
    const p = apiParams(f, { zones: ['danger', 'warning'], vtnet_flag: false, only_mapped: true, q: '', page: 2 })
    expect(p.toString()).toBe('threshold=40&owner=a&owner=b&zones=danger&zones=warning&only_mapped=true&page=2')
    expect(apiParams(EMPTY_FILTERS).toString()).toBe('') // không gửi start/end → API dùng 'Theo kỳ file'
  })
  it('preset khoảng ngày (end tính trọn ngày)', () => {
    expect(presetRange('this_month', '2026-11-03')).toEqual(['2026-11-01', '2026-11-30'])
    expect(presetRange('last_month', '2026-11-03')).toEqual(['2026-10-01', '2026-10-31'])
    expect(presetRange('3m', '2026-11-01')).toEqual(['2026-08-02', '2026-11-01'])
    expect(presetRange('12m', '2026-10-31')).toEqual(['2025-11-01', '2026-10-31'])
    expect(presetRange('4w', '2026-10-25')).toEqual(['2026-09-28', '2026-10-25']) // = default_range backend (28 ngày)
    expect(presetRange('last_month', '2026-03-31')).toEqual(['2026-02-01', '2026-02-28'])
  })
  it('danh sách trong URL chỉ giữ giá trị hợp lệ, theo thứ tự chuẩn', () => {
    expect(parseList('safe,danger,xx', ['danger', 'warning', 'safe'] as const)).toEqual(['danger', 'safe'])
    expect(parseList(null, ['danger'] as const)).toEqual([])
  })
})

describe('CSV cho Excel tiếng Việt', () => {
  it('BOM, phân cách ;, bọc ô có ký tự đặc biệt', () => {
    const s = toCsv(['IP', 'Dịch vụ'], [['10.0.0.1', 'OCR; KYC'], ['10.0.0.2', 'nói "xin chào"'], ['10.0.0.3', null]])
    expect(s.startsWith('﻿')).toBe(true)
    expect(s.slice(1).split('\r\n')).toEqual([
      'IP;Dịch vụ',
      '10.0.0.1;"OCR; KYC"',
      '10.0.0.2;"nói ""xin chào"""',
      '10.0.0.3;',
    ])
  })
})

describe('clampToData', () => {
  it('khoảng vượt ngày có dữ liệu → khoảng đã cắt; nằm trong / ngoài hẳn / thiếu → null', () => {
    expect(clampToData('2026-10-01', '2026-10-31', '2026-09-21', '2026-10-25')).toEqual(['2026-10-01', '2026-10-25'])
    expect(clampToData('2026-09-01', '2026-11-30', '2026-09-21', '2026-10-25')).toEqual(['2026-09-21', '2026-10-25'])
    expect(clampToData('2026-10-01', '2026-10-20', '2026-09-21', '2026-10-25')).toBeNull()
    expect(clampToData('2026-12-01', '2026-12-31', '2026-09-21', '2026-10-25')).toBeNull()
    expect(clampToData(undefined, undefined, '2026-09-21', '2026-10-25')).toBeNull()
    expect(clampToData('2026-10-01', '2026-10-31', null, null)).toBeNull()
  })
})

describe('áp ngưỡng T cho chỉ số nào (PLAN §14.9)', () => {
  it('đọc / ghi zone_metric qua URL, bỏ giá trị lạ', () => {
    expect(parseFilters(new URLSearchParams('zone_metric=gpu')).zone_metric).toBe('gpu')
    expect(parseFilters(new URLSearchParams('zone_metric=cpu')).zone_metric).toBeUndefined()
    expect(parseFilters(new URLSearchParams('')).zone_metric).toBeUndefined()
    const f = { ...EMPTY_FILTERS, threshold: 40, zone_metric: 'mem' as const }
    expect(apiParams(f).toString()).toBe('threshold=40&zone_metric=mem')
    expect(apiParams(EMPTY_FILTERS).has('zone_metric')).toBe(false)
    expect(globalSearch(new URLSearchParams('zone_metric=gpu&zones=danger'))).toBe('?zone_metric=gpu')
    expect(writeFilters(new URLSearchParams('zone_metric=gpu'), { zone_metric: undefined }).toString()).toBe('')
  })
})
