import { Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useLocation, useNavigate } from 'react-router'
import type { ZoneMatrix } from '../api/types'
import { fmtInt } from '../lib/format'
import { vi } from '../lib/vi'
import { ownerLabel, ZONE_ORDER, type Zone } from '../lib/zones'
import { globalSearch } from '../store/filters'
import { ZoneTag } from './Tags'

interface Row {
  zone: Zone
  [owner: string]: number | string
}

/** Bảng vùng × đầu mối; bấm ô → trang Cảnh báo đã lọc (vùng + đầu mối), giữ bộ lọc toàn cục. */
export function ZoneOwnerMatrix({ matrix }: { matrix: ZoneMatrix }) {
  const navigate = useNavigate()
  const location = useLocation()

  const open = (zone: Zone, owner?: string) => {
    const sp = new URLSearchParams(globalSearch(new URLSearchParams(location.search)))
    sp.set('zones', zone)
    if (owner) {
      sp.delete('owner')
      sp.append('owner', owner)
    }
    navigate(`/alerts?${sp.toString()}`)
  }

  const cell = (zone: Zone, n: number, owner?: string) => (
    <Typography.Link onClick={() => open(zone, owner)} disabled={n === 0}>
      {fmtInt(n)}
    </Typography.Link>
  )

  const rows: Row[] = ZONE_ORDER.map((z) => ({ zone: z, ...matrix.rows[z], _total: matrix.totals[z] }))
  const columns: ColumnsType<Row> = [
    { title: vi.matrix.zone, dataIndex: 'zone', render: (z: Zone) => <ZoneTag zone={z} /> },
    ...matrix.owners.map((o) => ({
      title: ownerLabel(o),
      dataIndex: o,
      align: 'right' as const,
      render: (n: number, r: Row) => cell(r.zone, n ?? 0, o),
    })),
    {
      title: vi.matrix.total,
      dataIndex: '_total',
      align: 'right' as const,
      render: (n: number, r: Row) => <strong>{cell(r.zone, n ?? 0)}</strong>,
    },
  ]
  return <Table<Row> size="small" rowKey="zone" pagination={false} columns={columns} dataSource={rows} />
}
