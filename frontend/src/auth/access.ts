import type { Me, Role } from '../api/types'

/** Trang chỉ dành cho quản trị (backend cũng chặn — đây chỉ để ẩn menu / hiện trang "Không có quyền"). */
export const ADMIN_ONLY_ROUTES: ReadonlySet<string> = new Set(['imports', 'users', 'settings', 'audit'])

/** Ẩn với đầu mối (menu rút gọn PLAN §8.6: Tổng quan · Cảnh báo · Server · Danh mục · So sánh kỳ; báo cáo tháng là cho lãnh đạo). API vẫn áp phạm vi. */
export const HIDDEN_FOR_OWNER: ReadonlySet<string> = new Set(['gaps', 'report'])

export function canAccess(routeKey: string, role: Role): boolean {
  if (role === 'admin') return true
  if (ADMIN_ONLY_ROUTES.has(routeKey)) return false
  return !(role === 'owner' && HIDDEN_FOR_OWNER.has(routeKey))
}

/** Đầu mối với phạm vi "chỉ server của mình" → khóa bộ lọc đầu mối, hiện thông điệp đầu mối. */
export function isOwnScope(me: Pick<Me, 'role' | 'data_scope'>): boolean {
  return me.role === 'owner' && me.data_scope === 'own'
}

export function displayName(me: Pick<Me, 'username' | 'full_name'>): string {
  return me.full_name ? `${me.full_name} (${me.username})` : me.username
}
