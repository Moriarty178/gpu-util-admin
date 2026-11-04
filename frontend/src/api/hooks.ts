import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiParams, type GlobalFilters } from '../store/filters'
import { apiGet, apiPost, apiSend, apiUpload } from './client'
import type {
  AlertsOut,
  Batch,
  CatalogOut,
  CompareOut,
  GapsOut,
  IpLinkRow,
  MultiSeriesOut,
  NoteKind,
  NoteList,
  TrendOut,
  FleetSummaryOut,
  FleetTimeseriesOut,
  Granularity,
  MetaOut,
  MonthlyReportOut,
  ServerDetailOut,
  ServerTimeseriesOut,
  User,
  UserInput,
  UserWithPassword,
  Weight,
} from './types'

export interface Health {
  db: 'ok'
  gpu_core: string
}

type Extra = Record<string, string | number | boolean | readonly string[] | undefined | null>

function useApi<T>(path: string, params: URLSearchParams, enabled = true) {
  const qs = params.toString()
  return useQuery({
    queryKey: [path, qs],
    queryFn: ({ signal }) => apiGet<T>(path, params, signal),
    placeholderData: keepPreviousData, // giữ số cũ khi đổi bộ lọc/ngưỡng → không nháy trắng
    enabled,
  })
}

export function useHealth() {
  return useQuery({
    queryKey: ['healthz'],
    queryFn: ({ signal }) => apiGet<Health>('/healthz', undefined, signal),
    refetchInterval: 30_000,
  })
}

export function useMeta() {
  return useApi<MetaOut>('/meta', new URLSearchParams())
}

export function useFleetSummary(f: GlobalFilters) {
  return useApi<FleetSummaryOut>('/fleet/summary', apiParams(f))
}

export function useFleetTimeseries(f: GlobalFilters, granularity: Granularity, weight: Weight) {
  return useApi<FleetTimeseriesOut>('/fleet/timeseries', apiParams(f, { granularity, weight }))
}

export function useAlerts(f: GlobalFilters, extra: Extra) {
  return useApi<AlertsOut>('/alerts', apiParams(f, extra))
}

export function useCatalog(f: GlobalFilters, q?: string) {
  return useApi<CatalogOut>('/servers', apiParams(f, { q }))
}

export function useServerDetail(ip: string | undefined, f: GlobalFilters) {
  return useApi<ServerDetailOut>(`/servers/${ip ?? ''}`, apiParams(f), Boolean(ip))
}

export function useServerTimeseries(ip: string | undefined, f: GlobalFilters, granularity: Granularity = 'day') {
  return useApi<ServerTimeseriesOut>(`/servers/${ip ?? ''}/timeseries`, apiParams(f, { granularity }), Boolean(ip))
}

export function useImports() {
  return useQuery({
    queryKey: ['/imports'],
    queryFn: ({ signal }) => apiGet<{ items: Batch[] }>('/imports', undefined, signal),
  })
}

/** Nhập / xác nhận / hoàn tác / hủy lô → dữ liệu đổi → làm mới MỌI truy vấn. */
export function useBatchActions() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries()
  return {
    upload: useMutation({ mutationFn: (file: File) => apiUpload<Batch>('/imports', file), onSettled: refresh }),
    commit: useMutation({
      mutationFn: ({ id, acknowledge }: { id: number; acknowledge: boolean }) =>
        apiPost<Batch>(`/imports/${id}/commit`, { acknowledge }),
      onSettled: refresh,
    }),
    rollback: useMutation({ mutationFn: (id: number) => apiPost<Batch>(`/imports/${id}/rollback`), onSettled: refresh }),
    discard: useMutation({ mutationFn: (id: number) => apiPost<Batch>(`/imports/${id}/discard`), onSettled: refresh }),
  }
}

// ------------------------------------------------------------------ tài khoản (G2-M2, chỉ admin)

export function useUsers() {
  return useQuery({
    queryKey: ['/users'],
    queryFn: ({ signal }) => apiGet<{ items: User[] }>('/users', undefined, signal),
  })
}

export function useUserActions() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: ['/users'] })
  return {
    create: useMutation({
      mutationFn: (body: UserInput) => apiPost<UserWithPassword>('/users', body),
      onSettled: refresh,
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: UserInput }) => apiSend<User>('PATCH', `/users/${id}`, body),
      onSettled: refresh,
    }),
    reset: useMutation({
      mutationFn: (id: number) => apiPost<UserWithPassword>(`/users/${id}/reset-password`),
      onSettled: refresh,
    }),
  }
}

// ------------------------------------------------------------------ G2-M3

export function useGaps(f: GlobalFilters) {
  return useApi<GapsOut>('/gaps', apiParams(f))
}

export function useIpLinks(f: GlobalFilters) {
  return useApi<{ items: IpLinkRow[] }>('/ip-links', apiParams(f))
}

type LinkPatch = { vtnet_ip?: string; pair_confirmed?: boolean; reason?: string | null }

/** Đổi liên kết IP → mọi số liệu phân tích đổi theo → làm mới mọi truy vấn. */
export function useLinkActions() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries()
  return {
    create: useMutation({
      mutationFn: (body: { inventory_ip: string; vtnet_ip: string; reason?: string | null }) =>
        apiPost<IpLinkRow>('/ip-links', body),
      onSettled: refresh,
    }),
    update: useMutation({
      mutationFn: ({ ip, body }: { ip: string; body: LinkPatch }) => apiSend<IpLinkRow>('PATCH', `/ip-links/${ip}`, body),
      onSettled: refresh,
    }),
    remove: useMutation({
      mutationFn: (ip: string) => apiSend<void>('DELETE', `/ip-links/${ip}`),
      onSettled: refresh,
    }),
  }
}

export interface ComparePeriods {
  a_start?: string
  a_end?: string
  b_start?: string
  b_end?: string
}

/** So sánh kỳ / xu hướng dùng khoảng riêng — bỏ start/end của bộ lọc toàn cục. */
function withoutRange(f: GlobalFilters): GlobalFilters {
  return { ...f, start: undefined, end: undefined }
}

export function useCompare(f: GlobalFilters, p: ComparePeriods) {
  return useApi<CompareOut>('/compare', apiParams(withoutRange(f), { ...p }))
}

export function useMonthlyReport(month: string | null) {
  return useApi<MonthlyReportOut>('/reports/monthly', new URLSearchParams(month ? { month } : {}))
}

export function useTrend(f: GlobalFilters) {
  return useApi<TrendOut>('/trend/zones', apiParams(withoutRange(f)))
}

export function useMultiSeries(f: GlobalFilters, ips: string[], granularity: Granularity) {
  return useApi<MultiSeriesOut>('/servers/timeseries', apiParams(f, { ips, granularity }), ips.length > 0)
}

export function useNotes(ip: string | undefined, f: GlobalFilters) {
  return useApi<NoteList>(`/servers/${ip ?? ''}/notes`, apiParams(f), Boolean(ip))
}

export function useNoteActions(ip: string, f: GlobalFilters) {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries()
  const qs = apiParams(f).toString()
  const suffix = qs ? `?${qs}` : ''
  return {
    add: useMutation({
      mutationFn: (body: { kind: NoteKind; text: string; valid_until?: string | null }) =>
        apiPost<unknown>(`/servers/${ip}/notes${suffix}`, body),
      onSettled: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: number) => apiSend<void>('DELETE', `/servers/${ip}/notes/${id}${suffix}`),
      onSettled: refresh,
    }),
  }
}

// ------------------------------------------------------------------ G2-M4: cài đặt, nhật ký (chỉ admin)

export interface SettingItem {
  key: string
  value: number
  default: number
  label: string
  hint: string
  min: number
  max: number
  integer: boolean
  unit: string
  updated_by: string | null
  updated_at: string | null
}

export interface AuditItem {
  id: number
  at: string
  username: string | null
  action: string
  target: string | null
  payload: Record<string, unknown>
}

export interface AuditOut {
  total: number
  page: number
  page_size: number
  actions: string[]
  items: AuditItem[]
}

export function useSettingsList() {
  return useQuery({
    queryKey: ['/settings'],
    queryFn: ({ signal }) => apiGet<{ items: SettingItem[] }>('/settings', undefined, signal),
  })
}

/** Đổi cài đặt → mọi phân tích tính lại → làm mới mọi truy vấn. */
export function useSaveSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (values: Record<string, number>) => apiSend<{ items: SettingItem[] }>('PATCH', '/settings', { values }),
    onSettled: () => qc.invalidateQueries(),
  })
}

export function useAudit(params: Record<string, string | number | undefined>) {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') sp.set(k, String(v))
  return useApi<AuditOut>('/audit', sp)
}
