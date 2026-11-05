import { type CatalogItem, EDITABLE_FIELDS, type EditableField, type InventoryEditIn } from '../api/types'
import type { ReclaimStatus } from './zones'

/** Giá trị form sửa tay 1 server (Danh mục server, PLAN §14.11). */
export type InventoryForm = Partial<Record<EditableField, string>> & { reclaim_status: ReclaimStatus }

/** Giá trị theo file thống kê: ô đã sửa tay lấy từ `edited`, còn lại = giá trị đang hiện. */
export function fileValue(row: CatalogItem, f: EditableField): string | null {
  const e = row.edited ?? {}
  return f in e ? (e[f] ?? null) : row[f]
}

/** Thân PATCH: trùng file → null (về theo file); khác → giá trị mới ('' = để trống). Chỉ gửi ô thay đổi. */
export function editBody(row: CatalogItem, v: InventoryForm): InventoryEditIn {
  const body: InventoryEditIn = {}
  for (const f of EDITABLE_FIELDS) {
    const next = (v[f] ?? '').trim()
    if (next === (row[f] ?? '')) continue // không đổi so với đang hiện
    body[f] = next === (fileValue(row, f) ?? '') ? null : next
  }
  if (v.reclaim_status !== (row.reclaim_status ?? 'in_use')) body.reclaim_status = v.reclaim_status
  return body
}
