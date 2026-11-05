import { DownloadOutlined, EditOutlined, LinkOutlined, WarningOutlined } from '@ant-design/icons'
import { App, Button, Card, Flex, Input, Select, Space, Table, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import { Link, useLocation } from 'react-router'
import { errorMessage } from '../api/client'
import { useCatalog, useEditInventory, useMeta } from '../api/hooks'
import type { CatalogItem, EditableField } from '../api/types'
import { useAuth } from '../auth/session'
import { InventoryEditModal } from '../components/InventoryEditModal'
import { ErrorState, Loading, NoData } from '../components/States'
import { ReclaimTag, StatusTag, ZoneTag } from '../components/Tags'
import { downloadText, toCsv } from '../lib/csv'
import { csvNumber, fmtInt, fmtPct, shortGpu } from '../lib/format'
import { useDebouncedValue } from '../lib/useDebounced'
import { vi } from '../lib/vi'
import {
  compareZone,
  DATA_STATUS_META,
  type DataStatus,
  RECLAIM_META,
  RECLAIM_STATUSES,
  type ReclaimStatus,
  ZONE_META,
} from '../lib/zones'
import { globalSearch } from '../store/filters'
import { useFilters, usePageParam } from '../store/useFilters'

const txt = (a: string | null, b: string | null) => (a ?? '').localeCompare(b ?? '', 'vi')
const num = (a: number | null, b: number | null) => (a ?? -1) - (b ?? -1)
const ipNum = (ip: string | null) => (ip ?? '').split('.').reduce((acc, p) => acc * 256 + (Number(p) || 0), 0)

export default function Inventory() {
  const [f] = useFilters()
  const location = useLocation()
  const [qParam, setQ] = usePageParam('q')
  const [statusParam, setStatus] = usePageParam('status')
  const [reclaimParam, setReclaim] = usePageParam('reclaim')
  const isAdmin = useAuth().role === 'admin'
  const [editing, setEditing] = useState<CatalogItem | null>(null)
  const edit = useEditInventory()
  const { message } = App.useApp()
  const [q, setLocalQ] = useDebouncedValue<string>(qParam ?? '', (v) => setQ(v || null))
  const meta = useMeta()
  const cat = useCatalog(f, qParam ?? undefined)

  if (meta.data && !meta.data.inventory && meta.data.periods.length === 0) return <NoData />
  if (cat.isError) return <ErrorState error={cat.error} onRetry={() => cat.refetch()} />
  if (!cat.data) return <Loading rows={10} />

  const keep = location.search ? globalSearch(new URLSearchParams(location.search)) : ''
  const status = (statusParam && statusParam in DATA_STATUS_META ? statusParam : null) as DataStatus | null
  const all = cat.data.items
  const reclaim = (reclaimParam && reclaimParam in RECLAIM_META ? reclaimParam : null) as ReclaimStatus | null
  const invRows = all.filter(
    (r) =>
      r.row_type === 'inventory' &&
      (!status || r.data_status === status) &&
      (!reclaim || (r.reclaim_status ?? 'in_use') === reclaim),
  )
  // dòng VTNet-only không có trạng thái thu hồi → ẩn khi đang lọc theo trạng thái thu hồi
  const vtRows = all.filter((r) => r.row_type === 'vtnet_only' && (!status || status === 'vtnet_only') && !reclaim)
  const c = cat.data.counts

  const ipCell = (_: unknown, r: CatalogItem) => {
    const target = r.data_status === 'has_data' || r.row_type === 'vtnet_only' ? r.ip : (r.inventory_ip ?? r.ip)
    return (
      <Space direction="vertical" size={0}>
        <Link to={`/servers/${target}${keep}`}>{r.inventory_ip ?? r.ip}</Link>
        {r.ip_linked && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            <LinkOutlined /> VTNet {r.ip}
          </Typography.Text>
        )}
      </Space>
    )
  }
  const gpuVt = (_: unknown, r: CatalogItem) => (
    <Space size={4}>
      <span>{shortGpu(r.gpu_type)}</span>
      {r.gpu_count_mismatch && (
        <Tooltip title={vi.badge.mismatchTip(r.inventory_gpu_spec ?? '—', shortGpu(r.gpu_type))}>
          <WarningOutlined style={{ color: '#d48806' }} aria-label={vi.badge.mismatch} />
        </Tooltip>
      )}
    </Space>
  )
  const statusCell = (s: DataStatus, r: CatalogItem) => (
    <Space size={4} wrap>
      <StatusTag status={s} />
      {r.ip_linked && (
        <Tag color="cyan" icon={<LinkOutlined />}>
          {r.pair_confirmed ? vi.badge.linked : vi.badge.linkedUnconfirmed}
        </Tag>
      )}
    </Space>
  )

  // ô admin sửa tay khác file: chữ + biểu tượng bút, di chuột xem giá trị theo file
  const editable = (f: EditableField) => (v: string | null, r: CatalogItem) => {
    const e = r.edited ?? {}
    if (!(f in e)) return v ?? '—'
    const tip = vi.inventory.editedTip(e[f] ?? null)
    return (
      <Tooltip title={tip}>
        <span>
          {v ?? '—'} <EditOutlined style={{ color: '#8c8c8c', fontSize: 12 }} aria-label={tip} />
        </span>
      </Tooltip>
    )
  }
  const setReclaimStatus = async (r: CatalogItem, v: ReclaimStatus) => {
    const ip = r.inventory_ip ?? r.ip
    try {
      await edit.mutateAsync({ ip, body: { reclaim_status: v } })
      message.success(vi.inventory.reclaimSaved(ip, RECLAIM_META[v].label))
    } catch (e) {
      message.warning(errorMessage(e))
    }
  }
  const reclaimCell = (v: ReclaimStatus | null, r: CatalogItem) =>
    isAdmin && r.row_type === 'inventory' ? (
      <Select<ReclaimStatus>
        size="small"
        value={v ?? 'in_use'}
        style={{ width: 150 }}
        disabled={edit.isPending}
        onChange={(nv) => void setReclaimStatus(r, nv)}
        options={RECLAIM_STATUSES.map((s) => ({ value: s, label: RECLAIM_META[s].label }))}
        aria-label={vi.inventory.col.reclaim}
      />
    ) : (
      <ReclaimTag status={v} />
    )

  const columns: ColumnsType<CatalogItem> = [
    { title: vi.inventory.col.stt, dataIndex: 'stt', width: 64, sorter: (a, b) => num(a.excel_row, b.excel_row) },
    { title: vi.inventory.col.ip, key: 'ip', render: ipCell, sorter: (a, b) => ipNum(a.inventory_ip) - ipNum(b.inventory_ip) },
    { title: vi.inventory.col.owner, dataIndex: 'owner', render: editable('owner'),
      sorter: (a, b) => txt(a.owner, b.owner) },
    { title: vi.inventory.col.gpuInv, dataIndex: 'inventory_gpu_spec', render: (v: string | null) => v ?? '—' },
    { title: vi.inventory.col.gpuVt, key: 'gpu_vt', render: gpuVt },
    { title: vi.inventory.col.model, dataIndex: 'model', ellipsis: true, render: editable('model'),
      sorter: (a, b) => txt(a.model, b.model) },
    { title: vi.inventory.col.service, dataIndex: 'service', ellipsis: true, render: editable('service'),
      sorter: (a, b) => txt(a.service, b.service) },
    { title: vi.inventory.col.input, dataIndex: 'input_load', ellipsis: true, render: editable('input_load') },
    { title: vi.inventory.col.managed, dataIndex: 'managed_by', render: editable('managed_by'),
      sorter: (a, b) => txt(a.managed_by, b.managed_by) },
    { title: vi.inventory.col.cluster, dataIndex: 'cluster', render: editable('cluster'),
      sorter: (a, b) => txt(a.cluster, b.cluster) },
    { title: vi.inventory.col.reclaim, dataIndex: 'reclaim_status', render: reclaimCell, width: 170,
      sorter: (a, b) => txt(a.reclaim_status, b.reclaim_status) },
    { title: vi.inventory.col.zone, dataIndex: 'zone', render: (z) => (z ? <ZoneTag zone={z} /> : '—'),
      sorter: (a, b) => compareZone(a.zone, b.zone) },
    { title: vi.inventory.col.gpuAvg, dataIndex: 'gpu_avg', align: 'right', render: fmtPct,
      sorter: (a, b) => num(a.gpu_avg, b.gpu_avg) },
    { title: vi.inventory.col.memAvg, dataIndex: 'mem_avg', align: 'right', render: fmtPct,
      sorter: (a, b) => num(a.mem_avg, b.mem_avg) },
    { title: vi.inventory.col.status, dataIndex: 'data_status', render: statusCell,
      sorter: (a, b) => txt(a.data_status, b.data_status) },
    ...(isAdmin
      ? [{ title: vi.inventory.col.action, key: 'action', fixed: 'right' as const, width: 80,
          render: (_: unknown, r: CatalogItem) => (
            <Button size="small" icon={<EditOutlined />} onClick={() => setEditing(r)}>{vi.inventory.edit}</Button>
          ) }]
      : []),
  ]
  const vtColumns = columns.filter((col) =>
    ['ip', 'gpu_vt', 'zone', 'gpu_avg', 'mem_avg', 'data_status'].includes(String(col.key ?? (col as { dataIndex?: string }).dataIndex)),
  )

  const exportCsv = () => {
    const header = [
      vi.inventory.col.stt, vi.inventory.col.ip, 'IP VTNet', vi.inventory.col.owner, vi.inventory.col.gpuInv,
      vi.inventory.col.gpuVt, vi.badge.mismatch, vi.inventory.col.model, vi.inventory.col.service,
      vi.inventory.col.input, vi.inventory.col.managed, vi.inventory.col.cluster, vi.inventory.col.zone,
      vi.inventory.col.gpuAvg, vi.inventory.col.memAvg, vi.inventory.col.status, vi.inventory.col.reclaim,
    ]
    const rows = [...invRows, ...vtRows].map((r) => [
      r.stt, r.inventory_ip ?? '', r.ip, r.owner, r.inventory_gpu_spec, r.gpu_type, r.gpu_count_mismatch ? 'x' : '',
      r.model, r.service, r.input_load, r.managed_by, r.cluster, r.zone ? ZONE_META[r.zone].label : '',
      csvNumber(r.gpu_avg), csvNumber(r.mem_avg), DATA_STATUS_META[r.data_status].label,
      r.reclaim_status ? RECLAIM_META[r.reclaim_status].label : '',
    ])
    downloadText(toCsv(header, rows), `Danh_muc_server_${cat.data.params.start}_${cat.data.params.end}.csv`)
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Typography.Title level={3} style={{ margin: 0 }}>
        {vi.nav.inventory}
      </Typography.Title>
      <Card size="small">
        <Flex wrap gap={12} align="center" justify="space-between">
          <Space wrap>
            <Typography.Text strong>{vi.inventory.counts(c)}</Typography.Text>
            <Tag color="gold" icon={<WarningOutlined />}>{vi.inventory.mismatch(c.gpu_count_mismatch)}</Tag>
            <Tag color="cyan" icon={<LinkOutlined />}>{vi.inventory.linked(c.linked)}</Tag>
            <Tag color="purple">{vi.inventory.reclaimMarked(c.reclaim_marked)}</Tag>
            {c.edited > 0 && <Tag icon={<EditOutlined />}>{vi.inventory.editedCount(c.edited)}</Tag>}
          </Space>
          <Space wrap>
            <Input.Search
              allowClear
              placeholder={vi.inventory.searchPlaceholder}
              value={q}
              onChange={(e) => setLocalQ(e.target.value)}
              style={{ width: 280 }}
            />
            <Select<DataStatus | 'all'>
              style={{ width: 210 }}
              value={status ?? 'all'}
              onChange={(v) => setStatus(v === 'all' ? null : v)}
              options={[
                { value: 'all', label: vi.inventory.allStatus },
                ...(Object.keys(DATA_STATUS_META) as DataStatus[]).map((k) => ({
                  value: k,
                  label: DATA_STATUS_META[k].label,
                })),
              ]}
            />
            <Select<ReclaimStatus | 'all'>
              style={{ width: 200 }}
              value={reclaim ?? 'all'}
              onChange={(v) => setReclaim(v === 'all' ? null : v)}
              options={[
                { value: 'all', label: vi.inventory.allReclaim },
                ...RECLAIM_STATUSES.map((k) => ({ value: k, label: RECLAIM_META[k].label })),
              ]}
              aria-label={vi.inventory.col.reclaim}
            />
            <Button icon={<DownloadOutlined />} onClick={exportCsv}>
              {vi.inventory.exportCsv}
            </Button>
          </Space>
        </Flex>
      </Card>
      <Table<CatalogItem>
        size="small"
        rowKey={(r) => r.inventory_ip ?? r.ip}
        loading={cat.isFetching}
        columns={columns}
        dataSource={invRows}
        scroll={{ x: isAdmin ? 1750 : 1650 }}
        pagination={{ defaultPageSize: 50, showSizeChanger: true, pageSizeOptions: [50, 100, 200],
          showTotal: (n) => `${fmtInt(n)} dòng` }}
      />
      {vtRows.length > 0 && (
        <Card size="small" title={vi.inventory.vtnetOnlyTitle(vtRows.length)}>
          <Table<CatalogItem> size="small" rowKey="ip" columns={vtColumns} dataSource={vtRows} pagination={false} />
        </Card>
      )}
      <InventoryEditModal row={editing} onClose={() => setEditing(null)} />
    </Space>
  )
}
