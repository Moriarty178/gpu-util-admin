import { CheckCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons'
import { Tag, Tooltip } from 'antd'
import type { ReactNode } from 'react'
import { DATA_STATUS_META, type DataStatus, PATTERN_META, type Pattern, ZONE_META, type Zone } from '../lib/zones'

const ZONE_ICON: Record<Zone, ReactNode> = {
  danger: <CloseCircleOutlined />,
  warning: <ExclamationCircleOutlined />,
  safe: <CheckCircleOutlined />,
}

/** Vùng luôn có biểu tượng + chữ (không chỉ màu). */
export function ZoneTag({ zone }: { zone: Zone | null | undefined }) {
  if (!zone) return <Tag>—</Tag>
  const m = ZONE_META[zone]
  return (
    <Tag color={m.tag} icon={ZONE_ICON[zone]} style={{ marginInlineEnd: 0 }}>
      {m.label}
    </Tag>
  )
}

export function PatternTag({ pattern, short = true }: { pattern: Pattern | null | undefined; short?: boolean }) {
  if (!pattern) return <span>—</span>
  const m = PATTERN_META[pattern]
  return (
    <Tooltip title={m.label}>
      <span>{short ? m.short : m.label}</span>
    </Tooltip>
  )
}

export function StatusTag({ status }: { status: DataStatus }) {
  const m = DATA_STATUS_META[status]
  return <Tag color={m.tag}>{m.label}</Tag>
}
