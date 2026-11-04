import { LinkOutlined, WarningOutlined } from '@ant-design/icons'
import { Space, Tag, Tooltip } from 'antd'
import { shortGpu } from '../lib/format'
import { vi } from '../lib/vi'

interface BadgeSource {
  ip: string
  inventory_ip: string | null
  reclaimed: boolean
  gpu_count_mismatch: boolean
  thin_data?: boolean | null
  ip_linked: boolean
  pair_confirmed: boolean | null
  inventory_gpu_spec: string | null
  gpu_type: string | null
}

/** Badge PLAN §8.2: Đã thu hồi · Lệch số card · Dữ liệu mỏng · IP liên kết (chưa xác nhận cặp). */
export function ServerBadges({ s }: { s: BadgeSource }) {
  return (
    <Space size={[4, 4]} wrap>
      {s.reclaimed && <Tag color="purple">{vi.badge.reclaimed}</Tag>}
      {s.gpu_count_mismatch && (
        <Tooltip title={vi.badge.mismatchTip(s.inventory_gpu_spec ?? '—', shortGpu(s.gpu_type))}>
          <Tag color="gold" icon={<WarningOutlined />}>
            {vi.badge.mismatch}
          </Tag>
        </Tooltip>
      )}
      {s.thin_data && <Tag>{vi.badge.thin}</Tag>}
      {s.ip_linked && (
        <Tooltip title={vi.server.linkLine(s.inventory_ip ?? '—', s.ip)}>
          <Tag color="cyan" icon={<LinkOutlined />}>
            {s.pair_confirmed ? vi.badge.linked : vi.badge.linkedUnconfirmed}
          </Tag>
        </Tooltip>
      )}
    </Space>
  )
}

/** GPU theo VTNet (rút gọn) + ⚠ khi lệch số card với thống kê. */
export function GpuCell({ s }: { s: BadgeSource }) {
  return (
    <Space size={4}>
      <span>{shortGpu(s.gpu_type ?? s.inventory_gpu_spec)}</span>
      {s.gpu_count_mismatch && (
        <Tooltip title={vi.badge.mismatchTip(s.inventory_gpu_spec ?? '—', shortGpu(s.gpu_type))}>
          <WarningOutlined style={{ color: '#d48806' }} aria-label={vi.badge.mismatch} />
        </Tooltip>
      )}
    </Space>
  )
}
