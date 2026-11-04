import { describe, expect, it } from 'vitest'
import { fmtDelta, MOVEMENT_META, MOVEMENT_ORDER, safeLabel, toggleServer } from './compare'

describe('toggleServer', () => {
  it('thêm / bớt, giữ thứ tự, tối đa 5', () => {
    expect(toggleServer([], 'a')).toEqual(['a'])
    expect(toggleServer(['a', 'b'], 'a')).toEqual(['b'])
    const five = ['a', 'b', 'c', 'd', 'e']
    expect(toggleServer(five, 'f')).toEqual(five)
    expect(toggleServer(five, 'c')).toEqual(['a', 'b', 'd', 'e'])
  })
})

describe('fmtDelta', () => {
  it('có dấu, vi-VN', () => {
    expect(fmtDelta(12.345)).toBe('+12,3')
    expect(fmtDelta(-40)).toBe('−40,0')
    expect(fmtDelta(0)).toBe('0,0')
    expect(fmtDelta(null)).toBe('—')
  })
})

describe('MOVEMENT_META', () => {
  it('đủ 5 trạng thái, không dùng đỏ (đỏ chỉ cho Nguy hiểm)', () => {
    expect(MOVEMENT_ORDER).toHaveLength(5)
    for (const m of MOVEMENT_ORDER) expect(MOVEMENT_META[m].tag).not.toMatch(/red|error/)
  })
})

describe('safeLabel', () => {
  it('bỏ ký tự HTML khỏi tên series', () => {
    expect(safeLabel('10.0.0.1 · <img src=x onerror=alert(1)>')).toBe('10.0.0.1 · img src=x onerror=alert(1)')
    expect(safeLabel(null)).toBe('')
  })
})
