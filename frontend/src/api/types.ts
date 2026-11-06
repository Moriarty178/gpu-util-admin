// Kiểu dữ liệu API (khớp backend/app/schemas). Số % để nguyên, UI tự định dạng.
import type { DataStatus, Pattern, ReclaimStatus, Zone, ZoneMetric } from '../lib/zones'

export interface AnalyticsParams {
  start: string
  end: string
  threshold: number
  /** Áp T cho: both = 3 vùng · gpu / mem = 2 vùng (PLAN §14.9) */
  zone_metric: ZoneMetric
  days_in_range: number
  /** Khoảng chọn vượt ra ngoài ngày có dữ liệu → backend đã cắt về [start, end] (PLAN §14.8) */
  clamped?: boolean
  requested_start?: string | null
  requested_end?: string | null
}

export interface ZoneMatrix {
  owners: string[]
  rows: Record<Zone, Record<string, number>>
  totals: Record<Zone, number>
  mapped_total: number
}

export interface ServerItem {
  ip: string
  inventory_ip: string | null
  owner: string | null
  service: string | null
  model: string | null
  cluster: string | null
  managed_by: string | null
  gpu_type: string | null
  gpu_count: number | null
  gpu_model: string | null
  inventory_gpu_spec: string | null
  gpu_avg: number | null
  mem_avg: number | null
  gpu_peak: number | null
  gpu_p95: number | null
  mem_peak: number | null
  days: number | null
  coverage: number | null
  low_streak: number | null
  danger_days: number | null
  zone: Zone | null
  pattern: Pattern | null
  vtnet_low_load: boolean | null
  thin_data: boolean | null
  assessment: string | null
  reclaimed: boolean
  mapped: boolean
  ip_linked: boolean
  pair_confirmed: boolean | null
  gpu_count_mismatch: boolean
  cards: number | null
  notes_count?: number
  exempt_until?: string | null
}

export interface AlertsOut {
  params: AnalyticsParams
  matrix: ZoneMatrix
  pattern_counts: Record<Pattern, number>
  cards_by_zone: Record<Zone, Record<string, number>>
  summary: {
    zones: Record<Zone, number>
    patterns: Record<Pattern, number>
    cards: number
    vtnet_low_load: number
    thin_data: number
    exempt?: number
  }
  total: number
  page: number
  page_size: number
  items: ServerItem[]
}

export interface FleetPoint {
  date: string
  gpu: number
  mem: number
  n_servers: number
  n_days: number
}

export interface FleetTimeseriesOut {
  params: AnalyticsParams
  granularity: Granularity
  weight: Weight
  points: FleetPoint[]
  avg: { gpu: number | null; mem: number | null }
  n_servers: number
}

export interface FleetSummaryOut {
  params: AnalyticsParams
  gpu_avg: number | null
  mem_avg: number | null
  n_servers: number
  n_mapped: number
  n_unmapped: number
  zones: Record<Zone, number>
  patterns: Record<Pattern, number>
  vtnet_low_load: number
  thin_data: number
  cards_by_zone: Record<Zone, Record<string, number>>
  cards_total: Record<Zone, number>
  matrix: ZoneMatrix
}

export interface CatalogItem {
  row_type: 'inventory' | 'vtnet_only'
  data_status: DataStatus
  inventory_ip: string | null
  ip: string
  ip_linked: boolean
  pair_confirmed: boolean | null
  stt: string | null
  excel_row: number | null
  owner: string | null
  inventory_gpu_spec: string | null
  gpu_type: string | null
  gpu_count: number | null
  gpu_model: string | null
  gpu_count_mismatch: boolean
  model: string | null
  service: string | null
  input_load: string | null
  managed_by: string | null
  cluster: string | null
  zone: Zone | null
  pattern: Pattern | null
  gpu_avg: number | null
  mem_avg: number | null
  days: number | null
  coverage: number | null
  vtnet_low_load: boolean | null
  reclaimed: boolean
  /** Admin đặt (mặc định in_use); null với dòng VTNet-only */
  reclaim_status: ReclaimStatus | null
  /** Ô admin sửa tay khác file: cột → giá trị theo file; null với dòng VTNet-only */
  edited: Partial<Record<EditableField, string | null>> | null
  /** Server bổ sung trên web ở trang Đối soát (VTNet có log, file thống kê chưa có) */
  manual: boolean
}

export type EditableField = 'owner' | 'model' | 'input_load' | 'service' | 'managed_by' | 'cluster'
export const EDITABLE_FIELDS: EditableField[] = ['owner', 'model', 'input_load', 'service', 'managed_by', 'cluster']

/** PATCH /inventory/{ip}: chỉ gửi khóa cần đổi; null = về theo file; '' = để trống */
export type InventoryEditIn = Partial<Record<EditableField, string | null>> & { reclaim_status?: ReclaimStatus }

/** Cột phần cứng của 1 server bổ sung trên web (đủ cột như file thống kê, trừ STT) */
export type ManualField = 'server_class' | 'config' | 'cpu' | 'ram' | 'disk' | 'hba' | 'gpu_spec' | 'serial'
export const MANUAL_FIELDS: ManualField[] = ['server_class', 'config', 'cpu', 'ram', 'disk', 'hba', 'gpu_spec', 'serial']

/** POST /inventory/manual — bổ sung server VTNet-only (bắt buộc đầu mối) */
export type InventoryManualIn = { ip: string; owner: string; reclaim_status?: ReclaimStatus } & Partial<
  Record<Exclude<EditableField, 'owner'> | ManualField, string | null>
>

export interface InventoryStateOut {
  inventory_ip: string
  manual: boolean
  values: Record<EditableField, string | null>
  file_values: Record<EditableField, string | null>
  edited: Partial<Record<EditableField, string | null>>
  reclaim_status: ReclaimStatus
  updated_by: string | null
  updated_at: string | null
}

export interface CatalogOut {
  params: AnalyticsParams
  counts: {
    inventory_rows: number
    has_data: number
    reclaimed: number
    no_data: number
    vtnet_only: number
    linked: number
    gpu_count_mismatch: number
    reclaim_marked: number
    edited: number
    manual: number
  }
  items: CatalogItem[]
}

export interface ServerDetailOut {
  params: AnalyticsParams
  ip: string
  inventory_ip: string | null
  data_status: DataStatus
  inventory: Record<string, string | number | null> | null
  link: { inventory_ip: string; vtnet_ip: string; pair_confirmed: boolean; reason: string | null } | null
  reclaim: Record<string, string | null> | null
  stats: ServerItem | null
}

export interface ServerPoint {
  date: string
  gpu: number
  mem: number
  zone: Zone
  vtnet_low_load: boolean
  n_days: number
}

export interface ServerTimeseriesOut {
  params: AnalyticsParams
  ip: string
  granularity: Granularity
  points: ServerPoint[]
}

export interface Period {
  batch_id: number
  label: string | null
  start: string | null
  end: string | null
  file_name: string
  committed_at: string | null
}

export interface MetaOut {
  gpu_core: string
  data_range: { start: string | null; end: string | null }
  default_range: { start: string | null; end: string | null } | null
  periods: Period[]
  inventory: { batch_id: number; file_name: string; committed_at: string | null } | null
  owners: string[]
  gpu_models: string[]
  clusters: string[]
  managed_by: string[]
  settings: Record<string, number | string | boolean | null>
}

export type BatchStatus = 'staged' | 'committed' | 'rolled_back' | 'failed' | 'discarded'

export interface Batch {
  id: number
  kind: 'vtnet_util' | 'inventory'
  kind_label: string
  file_name: string
  file_sha256: string
  schema_version: string | null
  status: BatchStatus
  status_label: string
  period_start: string | null
  period_end: string | null
  period_label: string | null
  summary: Record<string, unknown>
  validation: Record<string, unknown>
  uploaded_by: string
  uploaded_at: string
  committed_by: string | null
  committed_at: string | null
  rolled_back_by: string | null
  rolled_back_at: string | null
  note: string | null
}

export type Granularity = 'day' | 'week' | 'month'
export type Weight = 'server' | 'gpu'

// ------------------------------------------------------------------ tài khoản (G2-M2)

export type Role = 'admin' | 'owner' | 'viewer'
export type DataScope = 'own' | 'all'

export interface Me {
  username: string
  full_name: string | null
  role: Role
  role_label: string
  owner_key: string | null
  data_scope: DataScope
  must_change_password: boolean
}

export interface User {
  id: number
  username: string
  full_name: string | null
  email: string | null
  role: Role
  role_label: string
  owner_key: string | null
  data_scope: DataScope
  must_change_password: boolean
  active: boolean
  locked: boolean
  locked_until: string | null
  last_login_at: string | null
  created_by: string | null
  created_at: string
}

export interface UserWithPassword {
  user: User
  temp_password: string
}

export interface UserInput {
  username?: string
  role?: Role
  owner_key?: string | null
  data_scope?: DataScope
  full_name?: string | null
  email?: string | null
  active?: boolean
  unlock?: boolean
}

// ------------------------------------------------------------------ G2-M3: đối soát, liên kết, so sánh, ghi chú

export interface VtnetOnlyRow {
  ip: string
  gpu_type: string | null
  gpu_count: number | null
  gpu_model: string | null
  zone: Zone | null
  pattern: string | null
  gpu_avg: number | null
  mem_avg: number | null
  days: number | null
  vtnet_low_load: boolean | null
}

export interface InventoryGapRow {
  inventory_ip: string
  ip: string
  owner: string | null
  service: string | null
  model: string | null
  cluster: string | null
  inventory_gpu_spec: string | null
  gpu_count: number | null
  gpu_model: string | null
  data_status: string
  excel_row: number | null
}

export interface MismatchRow {
  inventory_ip: string
  ip: string
  owner: string | null
  service: string | null
  inventory_gpu_spec: string | null
  gpu_type: string | null
  gpu_count: number | null
  gpu_model: string | null
  zone: Zone | null
  ip_linked: boolean
}

export interface LinkPair {
  inventory_ip: string
  vtnet_ip: string
}

export interface Suggestion {
  gpu_count: number
  gpu_model: string
  vtnet_ips: string[]
  inventory_ips: string[]
  pairs: LinkPair[]
}

export interface GapsOut {
  params: AnalyticsParams
  counts: {
    vtnet_only: number
    no_data: number
    reclaimed: number
    unknown: number
    gpu_count_mismatch: number
    links: number
    links_unconfirmed: number
    manual: number
  }
  vtnet_only: VtnetOnlyRow[]
  reclaimed: InventoryGapRow[]
  unknown: InventoryGapRow[]
  gpu_count_mismatch: MismatchRow[]
  suggestions: Suggestion[]
}

export interface IpLinkRow {
  inventory_ip: string
  vtnet_ip: string
  pair_confirmed: boolean
  reason: string | null
  owner: string | null
  service: string | null
  inventory_gpu_spec: string | null
  in_inventory: boolean
  vtnet_has_data: boolean
  zone: Zone | null
  created_by: string | null
  created_at: string | null
  confirmed_by: string | null
  confirmed_at: string | null
}

export type Movement = 'worsened' | 'improved' | 'same' | 'new' | 'gone'

export interface PeriodKpi {
  params: AnalyticsParams
  gpu_avg: number | null
  mem_avg: number | null
  n_servers: number
  zones: Record<Zone, number>
  cards_total: Record<string, number>
}

export interface CompareItem {
  ip: string
  inventory_ip: string | null
  owner: string | null
  service: string | null
  model: string | null
  gpu_type: string | null
  gpu_model: string | null
  cards: number | null
  mapped: boolean | null
  zone_prev: Zone | null
  zone_cur: Zone | null
  gpu_avg_prev: number | null
  gpu_avg_cur: number | null
  mem_avg_prev: number | null
  mem_avg_cur: number | null
  d_gpu: number | null
  d_mem: number | null
  movement: Movement
}

export interface CompareOut {
  a: PeriodKpi
  b: PeriodKpi
  threshold: number
  zone_metric: ZoneMetric
  counts: Record<Movement, number>
  matrix: Record<string, Record<string, number>>
  items: CompareItem[]
}

export type TrendGranularity = 'month' | 'week'

export interface TrendMonth {
  /** 'YYYY-MM' hoặc 'YYYY-Www' (tuần ISO, thứ 2 → CN) */
  period: string
  month: string | null
  start: string
  end: string
  n_days: number
  n_servers: number
  zones: Record<Zone, number>
  cards: Record<Zone, number>
  gpu_avg: number | null
  mem_avg: number | null
}

export interface TrendOut {
  threshold: number | null
  zone_metric: ZoneMetric | null
  granularity: TrendGranularity
  months: TrendMonth[]
}

export interface ServerSeries {
  ip: string
  inventory_ip: string | null
  owner: string | null
  service: string | null
  gpu_type: string | null
  zone: Zone | null
  gpu_avg: number | null
  mem_avg: number | null
  points: ServerPoint[]
}

export interface MultiSeriesOut {
  params: AnalyticsParams
  granularity: Granularity
  series: ServerSeries[]
}

export type NoteKind = 'note' | 'explanation' | 'exempt' | 'action'

export interface Note {
  id: number
  ip: string
  kind: NoteKind
  kind_label: string
  text: string
  valid_until: string | null
  active: boolean
  created_by: string
  created_at: string
  can_delete: boolean
}

export interface NoteList {
  ip: string
  can_add: NoteKind[]
  items: Note[]
}

// ------------------------------------------------------------------ báo cáo tháng (Roadmap §14.2)

export interface ZoneCount {
  danger: number
  warning: number
  safe: number
}

export interface ReportDangerRow {
  ip: string
  owner: string | null
  service: string | null
  gpu_model: string | null
  cards: number | null
  gpu_avg: number | null
  mem_avg: number | null
  pattern: string | null
  vtnet_low_load: boolean
  mapped: boolean
  streak_months: number
  streak_open: boolean
}

export interface ReportCompleteness {
  days_in_month: number
  days_with_data: number
  first: string | null
  last: string | null
  /** false → chưa đủ tháng: không xuất được .pptx (409 month_incomplete) */
  complete: boolean
  missing_days: string[]
}

export interface MonthlyReportOut {
  month: string
  label: string
  start: string
  end: string
  threshold: number
  zone_metric: ZoneMetric
  vtnet_t: number
  scope_owner: string | null
  available_months: string[]
  completeness: ReportCompleteness
  incomplete_months: string[]
  kpi: {
    gpu_avg: number | null
    mem_avg: number | null
    n_servers: number
    n_mapped: number
    n_unmapped: number
    cards: number
    zones: ZoneCount
    cards_total: ZoneCount
  }
  trend: { month: string; n_servers: number; zones: ZoneCount; gpu_avg: number | null; mem_avg: number | null }[]
  previous: { month: string; gpu_avg: number | null; mem_avg: number | null; zones: ZoneCount } | null
  movement: { counts: Record<string, number>; matrix: Record<string, Record<string, number>> } | null
  danger: ReportDangerRow[]
  suggestion: { message: string; recommendations: { title: string; detail: string }[] }
}
