import { Card, Col, Flex, Row, Segmented, Space, Typography } from 'antd'
import { useLocation, useNavigate } from 'react-router'
import { useFleetSummary, useFleetTimeseries, useMeta } from '../api/hooks'
import type { Granularity, Weight } from '../api/types'
import { Kpi } from '../components/Kpi'
import { LoadChart } from '../components/LoadChart'
import { ErrorState, LimitationNote, Loading, NoData } from '../components/States'
import { ZoneOwnerMatrix } from '../components/ZoneOwnerMatrix'
import { ZoneTrend } from '../components/ZoneTrend'
import { fmtInt, fmtPct, fmtRange } from '../lib/format'
import { vi } from '../lib/vi'
import { ZONE_META } from '../lib/zones'
import { globalSearch } from '../store/filters'
import { useFilters, usePageParam } from '../store/useFilters'

const GRANS: Granularity[] = ['day', 'week', 'month']

export default function Dashboard() {
  const [f] = useFilters()
  const navigate = useNavigate()
  const location = useLocation()
  const [g, setG] = usePageParam('g')
  const [w, setW] = usePageParam('w')
  const granularity: Granularity = GRANS.includes(g as Granularity) ? (g as Granularity) : 'day'
  const weight: Weight = w === 'gpu' ? 'gpu' : 'server'
  const meta = useMeta()
  const summary = useFleetSummary(f)
  const ts = useFleetTimeseries(f, granularity, weight)

  if (meta.data && meta.data.periods.length === 0) return <NoData />
  if (summary.isError) return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />
  if (!summary.data) return <Loading />

  const s = summary.data
  const T = s.params.threshold
  const vtnetT = Number(meta.data?.settings.vtnet_low_load_t ?? 10)
  const toAlerts = (extra: Record<string, string>) => {
    const sp = new URLSearchParams(globalSearch(new URLSearchParams(location.search)))
    Object.entries(extra).forEach(([k, v]) => sp.set(k, v))
    navigate(`/alerts?${sp.toString()}`)
  }
  const dangerCards = Object.entries(s.cards_by_zone.danger)
    .slice(0, 3)
    .map(([m, n]) => `${m} ${fmtInt(n)}`)
    .join(' · ')

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Flex justify="space-between" align="baseline" wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          {vi.nav.dashboard}
        </Typography.Title>
        <Typography.Text type="secondary">{fmtRange(s.params.start, s.params.end)}</Typography.Text>
      </Flex>
      <LimitationNote />
      <Row gutter={[12, 12]}>
        <Col xs={12} md={8} xl={4}>
          <Kpi title={vi.kpi.gpuAvg} value={fmtPct(s.gpu_avg)} note={vi.kpi.avgNote} />
        </Col>
        <Col xs={12} md={8} xl={4}>
          <Kpi title={vi.kpi.memAvg} value={fmtPct(s.mem_avg)} note={vi.kpi.avgNote} />
        </Col>
        <Col xs={12} md={8} xl={4}>
          <Kpi
            title={vi.kpi.servers}
            value={fmtInt(s.n_servers)}
            note={vi.kpi.mappedNote(s.n_mapped, s.n_unmapped)}
          />
        </Col>
        <Col xs={12} md={8} xl={4}>
          <Kpi
            title={vi.kpi.danger(T)}
            value={fmtInt(s.zones.danger)}
            color={ZONE_META.danger.color}
            note={`${ZONE_META.warning.label} ${fmtInt(s.zones.warning)} · ${ZONE_META.safe.label} ${fmtInt(s.zones.safe)}`}
            onClick={() => toAlerts({ zones: 'danger' })}
          />
        </Col>
        <Col xs={12} md={8} xl={4}>
          <Kpi
            title={vi.kpi.vtnet}
            value={fmtInt(s.vtnet_low_load)}
            note={`gpu < ${vtnetT}% và VRAM < ${vtnetT}%`}
            onClick={() => toAlerts({ zones: 'danger,warning,safe', vtnet: '1' })}
          />
        </Col>
        <Col xs={12} md={8} xl={4}>
          <Kpi title={vi.kpi.dangerCards} value={fmtInt(s.cards_total.danger)} note={dangerCards || undefined} />
        </Col>
      </Row>

      <Card
        title={vi.chart.fleetTitle}
        extra={
          <Space wrap>
            <Segmented<Granularity>
              value={granularity}
              onChange={(v) => setG(v === 'day' ? null : v)}
              options={[
                { value: 'day', label: vi.chart.day },
                { value: 'week', label: vi.chart.week },
                { value: 'month', label: vi.chart.month },
              ]}
            />
            <Segmented<Weight>
              value={weight}
              onChange={(v) => setW(v === 'server' ? null : v)}
              options={[
                { value: 'server', label: vi.chart.byServer },
                { value: 'gpu', label: vi.chart.byCard },
              ]}
            />
          </Space>
        }
      >
        {ts.isError ? (
          <ErrorState error={ts.error} onRetry={() => ts.refetch()} />
        ) : !ts.data ? (
          <Loading rows={8} />
        ) : (
          <LoadChart
            points={ts.data.points}
            threshold={T}
            vtnetT={vtnetT}
            granularity={granularity}
            fileName={`tai_toan_bo_${s.params.start}_${s.params.end}`}
          />
        )}
      </Card>

      <Card title={vi.matrix.title} extra={<Typography.Text type="secondary">{vi.matrix.hint}</Typography.Text>}>
        <ZoneOwnerMatrix matrix={s.matrix} />
      </Card>

      <ZoneTrend f={f} />
    </Space>
  )
}
