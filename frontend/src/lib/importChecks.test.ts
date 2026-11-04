import { describe, expect, it } from 'vitest'
import { CHECK_META, commitGate, countByLevel, readChecks } from './importChecks'

const c = (level: string, code = level) => ({ code, level, title: code })

describe('readChecks', () => {
  it('bỏ phần tử sai dạng / mức lạ', () => {
    expect(readChecks({ checks: [c('error'), c('warning'), c('khac'), null, 5] })).toHaveLength(2)
    expect(readChecks({})).toEqual([])
    expect(readChecks(null)).toEqual([])
  })
})

describe('commitGate', () => {
  it('lỗi chặn > cần xác nhận > tự do', () => {
    expect(commitGate(readChecks({ checks: [c('error'), c('warning')] }))).toEqual({ blocked: true, needsAck: false })
    expect(commitGate(readChecks({ checks: [c('warning'), c('info')] }))).toEqual({ blocked: false, needsAck: true })
    expect(commitGate(readChecks({ checks: [c('info')] }))).toEqual({ blocked: false, needsAck: false })
  })
  it('đếm theo mức', () => {
    expect(countByLevel(readChecks({ checks: [c('info'), c('info'), c('warning')] }))).toEqual({ error: 0, warning: 1, info: 2 })
  })
  it('không dùng đỏ cho mức kiểm tra (đỏ chỉ cho Nguy hiểm)', () => {
    for (const m of Object.values(CHECK_META)) expect(m.tag).not.toMatch(/red|error/)
  })
})
