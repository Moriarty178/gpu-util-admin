import { describe, expect, it } from 'vitest'
import { readCookie, signalsAuthChange } from '../api/client'
import { canAccess, displayName, isOwnScope } from './access'

describe('canAccess', () => {
  it('chỉ admin vào Nhập dữ liệu / Tài khoản', () => {
    for (const key of ['imports', 'users', 'settings', 'audit']) {
      expect(canAccess(key, 'admin')).toBe(true)
      expect(canAccess(key, 'owner')).toBe(false)
      expect(canAccess(key, 'viewer')).toBe(false)
    }
  })
  it('Đối soát: admin + chỉ xem; đầu mối không thấy trong menu', () => {
    expect(canAccess('gaps', 'admin')).toBe(true)
    expect(canAccess('gaps', 'viewer')).toBe(true)
    expect(canAccess('gaps', 'owner')).toBe(false)
  })
  it('Báo cáo tháng (cho lãnh đạo): admin + chỉ xem; ẩn với đầu mối', () => {
    expect(canAccess('report', 'admin')).toBe(true)
    expect(canAccess('report', 'viewer')).toBe(true)
    expect(canAccess('report', 'owner')).toBe(false)
  })
  it('mọi vai trò xem được trang phân tích', () => {
    for (const key of ['dashboard', 'alerts', 'servers', 'inventory', 'compare']) {
      expect(canAccess(key, 'owner')).toBe(true)
      expect(canAccess(key, 'viewer')).toBe(true)
    }
  })
})

describe('isOwnScope', () => {
  it('chỉ đầu mối phạm vi own', () => {
    expect(isOwnScope({ role: 'owner', data_scope: 'own' })).toBe(true)
    expect(isOwnScope({ role: 'owner', data_scope: 'all' })).toBe(false)
    expect(isOwnScope({ role: 'admin', data_scope: 'all' })).toBe(false)
  })
})

describe('displayName', () => {
  it('có họ tên thì kèm tên đăng nhập', () => {
    expect(displayName({ username: 'kientt6', full_name: 'Trần Kiên' })).toBe('Trần Kiên (kientt6)')
    expect(displayName({ username: 'admin', full_name: null })).toBe('admin')
  })
})

describe('readCookie', () => {
  it('đọc đúng cookie, bỏ khoảng trắng, giải mã', () => {
    const c = 'a=1; gpu_csrf=abc%2Fdef ; gpu_csrf_x=no'
    expect(readCookie(c, 'gpu_csrf')).toBe('abc/def')
    expect(readCookie(c, 'a')).toBe('1')
    expect(readCookie(c, 'khong')).toBeNull()
    expect(readCookie('', 'gpu_csrf')).toBeNull()
  })
})

describe('signalsAuthChange', () => {
  it('hết phiên ở API dữ liệu → báo; ở chính /auth/* → không (tránh vòng lặp)', () => {
    expect(signalsAuthChange('/alerts', 'not_authenticated')).toBe(true)
    expect(signalsAuthChange('/alerts', 'password_change_required')).toBe(true)
    expect(signalsAuthChange('/auth/me', 'not_authenticated')).toBe(false)
    expect(signalsAuthChange('/auth/login', 'login_failed')).toBe(false)
    expect(signalsAuthChange('/users', 'forbidden')).toBe(false)
  })
})
