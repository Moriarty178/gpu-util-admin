import { Card, Empty, Segmented, Typography } from 'antd'
import { useState } from 'react'
import { useTrend } from '../api/hooks'
import { fmtPeriodLabel } from '../lib/format'
import { vi } from '../lib/vi'
import { ZONE_META, ZONE_ORDER } from '../lib/zones'
import type { GlobalFilters } from '../store/filters'
import { EChart, type EChartsOption } from './EChart'
import { ErrorState, Loading } from './States'

/** Xu hướng số server (hoặc số card) mỗi vùng theo tháng — cột chồng, màu/nhãn vùng từ zones.ts (B5b, G2-M3). */
export function ZoneTrend({ f }: { f: GlobalFilters }) {
  const q = useTrend(f)
  const [by, setBy] = useState<'zones' | 'cards'>('zones')
  const extra = (
    <Segmented<'zones' | 'cards'>
      value={by}
      onChange={setBy}
      options={[
        { value: 'zones', label: vi.trend.servers },
        { value: 'cards', label: vi.trend.cards },
      ]}
    />
  )
  let body
  if (q.isError) body = <ErrorState error={q.error} onRetry={() => void q.refetch()} />
  else if (!q.data) body = <Loading rows={4} />
  else if (q.data.months.length === 0) body = <Empty description={vi.empty} />
  else {
    const months = q.data.months
    const option: EChartsOption = {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { bottom: 0 },
      grid: { left: 48, right: 16, top: 16, bottom: 48 },
      xAxis: { type: 'category', data: months.map((m) => fmtPeriodLabel(m.month)) },
      yAxis: { type: 'value', minInterval: 1 },
      series: ZONE_ORDER.map((z) => ({
        name: ZONE_META[z].label,
        type: 'bar',
        stack: 'zones',
        itemStyle: { color: ZONE_META[z].color },
        label: { show: months.length <= 12, position: 'inside', color: '#fff', formatter: '{c}' },
        data: months.map((m) => m[by][z]),
      })),
    }
    body = <EChart option={option} height={300} />
  }
  return (
    <Card title={vi.trend.title} extra={extra}>
      <Typography.Paragraph type="secondary" style={{ marginTop: -8 }}>
        {vi.trend.hint}
      </Typography.Paragraph>
      {body}
    </Card>
  )
}
