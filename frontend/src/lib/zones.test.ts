import { describe, expect, it } from 'vitest'
import {
  compareZone,
  DATA_STATUS_META,
  isPattern,
  isZone,
  ownerLabel,
  PATTERN_META,
  PATTERN_ORDER,
  patternLabel,
  SERIES,
  ZONE_META,
  ZONE_ORDER,
  zoneLabel,
} from './zones'

describe('zones', () => {
  it('nhãn tiếng Việt khớp luật vùng (gpu_core)', () => {
    expect(ZONE_ORDER).toEqual(['danger', 'warning', 'safe'])
    expect(zoneLabel('danger')).toBe('Nguy hiểm')
    expect(zoneLabel('warning')).toBe('Cảnh báo')
    expect(zoneLabel('safe')).toBe('An toàn')
    expect(zoneLabel('khac')).toBe('—')
  })
  it('đỏ CHỈ dùng cho Nguy hiểm', () => {
    expect(ZONE_META.danger.tag).toBe('red')
    const others = [
      ZONE_META.warning.tag,
      ZONE_META.safe.tag,
      ...Object.values(DATA_STATUS_META).map((m) => m.tag),
    ]
    expect(others).not.toContain('red')
    expect(others).not.toContain('error')
    const colors = [ZONE_META.warning.color, ZONE_META.safe.color, ...Object.values(SERIES)]
    expect(colors).not.toContain(ZONE_META.danger.color)
  })
  it('mỗi vùng có màu khác nhau (kèm chữ — không chỉ màu)', () => {
    const c = ZONE_ORDER.map((z) => ZONE_META[z].color)
    expect(new Set(c).size).toBe(3)
    ZONE_ORDER.forEach((z) => expect(ZONE_META[z].label.length).toBeGreaterThan(0))
  })
  it('sắp xếp: Nguy hiểm → Cảnh báo → An toàn → không rõ', () => {
    const arr = ['safe', null, 'danger', 'warning']
    expect([...arr].sort(compareZone)).toEqual(['danger', 'warning', 'safe', null])
  })
  it('mẫu hình đủ 6 loại, nhãn khớp gpu_core.PATTERN_LABEL_VI', () => {
    expect(PATTERN_ORDER).toHaveLength(6)
    expect(PATTERN_META.memory_bound.label).toBe('Memory-bound (giữ VRAM, ít tính toán)')
    expect(PATTERN_META.bursty_idle.label).toBe('Bursty (ngắt quãng)')
    expect(patternLabel('idle')).toBe('Idle thật')
    expect(patternLabel('idle', true)).toBe('Idle')
    expect(isPattern('healthy')).toBe(true)
    expect(isPattern('xyz')).toBe(false)
    expect(isZone('danger')).toBe(true)
  })
  it('đầu mối chưa map', () => {
    expect(ownerLabel('_unmapped')).toBe('Chưa có trong thống kê')
    expect(ownerLabel('kientt6')).toBe('kientt6')
  })
})
