import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'
import { type GlobalFilters, parseFilters, writeFilters } from './filters'

/** Hook bộ lọc toàn cục đồng bộ URL. setFilters giữ nguyên tham số riêng của trang, trừ khi `resetPage`. */
export function useFilters(): [GlobalFilters, (patch: Partial<GlobalFilters>) => void] {
  const [sp, setSp] = useSearchParams()
  const filters = useMemo(() => parseFilters(sp), [sp])
  const setFilters = useCallback(
    (patch: Partial<GlobalFilters>) => {
      setSp(
        (prev) => {
          const next = writeFilters(prev, patch)
          next.delete('page') // đổi bộ lọc → về trang 1
          return next
        },
        { replace: true },
      )
    },
    [setSp],
  )
  return [filters, setFilters]
}

/** Đọc/ghi 1 tham số riêng của trang trên URL (vd zones, sort, page). */
export function usePageParam(key: string): [string | null, (v: string | null) => void] {
  const [sp, setSp] = useSearchParams()
  const set = useCallback(
    (v: string | null) => {
      setSp(
        (prev) => {
          const next = new URLSearchParams(prev)
          if (v === null || v === '') next.delete(key)
          else next.set(key, v)
          if (key !== 'page') next.delete('page')
          return next
        },
        { replace: true },
      )
    },
    [key, setSp],
  )
  return [sp.get(key), set]
}

/** Đặt nhiều tham số riêng của trang trong 1 lần cập nhật URL (null/'' = xóa). Gọi setSearchParams nhiều lần liên tiếp
 * có thể làm mất thay đổi trước → dùng hàm này cho các cặp start/end. */
export function useSetPageParams(): (patch: Record<string, string | null>) => void {
  const [, setSp] = useSearchParams()
  return useCallback(
    (patch: Record<string, string | null>) => {
      setSp(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const [k, v] of Object.entries(patch)) {
            if (v === null || v === '') next.delete(k)
            else next.set(k, v)
          }
          next.delete('page')
          return next
        },
        { replace: true },
      )
    },
    [setSp],
  )
}
