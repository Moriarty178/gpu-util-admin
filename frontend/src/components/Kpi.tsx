import { Card, Statistic, Typography } from 'antd'
import type { ReactNode } from 'react'

interface Props {
  title: ReactNode
  value: ReactNode
  note?: ReactNode
  color?: string
  onClick?: () => void
}

export function Kpi({ title, value, note, color, onClick }: Props) {
  return (
    <Card size="small" hoverable={Boolean(onClick)} onClick={onClick} style={{ height: '100%' }}>
      <Statistic title={title} value={value as string} valueStyle={{ color, fontSize: 26 }} />
      {note && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {note}
        </Typography.Text>
      )}
    </Card>
  )
}
