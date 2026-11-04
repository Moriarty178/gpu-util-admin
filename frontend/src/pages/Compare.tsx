import { SwapOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Col, DatePicker, Empty, Flex, Row, Segmented, Select, Space, Table, Tabs, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import { useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router'
import { ApiError } from '../api/client'
import { useCatalog, useCompare, useMeta, useMultiSeries } from '../api/hooks'
import type { CompareItem, Granularity, Movement, PeriodKpi } from '../api/types'
import { EChart, type EChartsOption } from '../components/EChart'
import { Kpi } from '../components/Kpi'
import { ErrorState, Loading } from '../components/States'
import { ZoneTag } from '../components/Tags'
import { COMPARE_COLORS, fmtDelta, MAX_COMPARE_SERVERS, MOVEMENT_META, MOVEMENT_ORDER, safeLabel } from '../lib/compare'
import { fmtDate, fmtInt, fmtPct, fmtPeriodLabel, fmtRange } from '../lib/format'
import { vi } from '../lib/vi'
import { SERIES, ZONE_META, ZONE_ORDER, zoneLabel } from '../lib/zones'
import { globalSearch } from '../store/filters'
import { useFilters, usePageParam, useSetPageParams } from '../store/useFilters'

const t = vi.compare
const DATE_FMT = 'DD/MM/YYYY'
type Range = [string, string] | null

function useRanges(): { a: Range; b: Range; set: (patch: { a?: Range; b?: Range }) => void } {
  const sp = new URLSearchParams(useLocation().search)
  const [as, ae, bs, be] = ['a_start', 'a_end', 'b_start', 'b_end'].map((k) => sp.get(k))
  const setParams = useSetPageParams()
  const a: Range = as && ae ? [as, ae] : null
  const b: Range = bs && be ? [bs, be] : null
  const set = (patch: { a?: Range; b?: Range }) => {
    const out: Record<string, string | null> = {}
    for (const k of ['a', 'b'] as const) {
      if (!(k in patch)) continue
      const r = patch[k] ?? null
      out[`${k}_start`] = r ? r[0] : null
      out[`${k}_end`] = r ? r[1] : null
    }
    setParams(out)
  }
  return { a, b, set }
}

function ServerLink({ ip }: { ip: string }) {
  const { search } = useLocation()
  return <Link to={`/servers/${ip}${globalSearch(new URLSearchParams(search))}`}>{ip}</Link>
}

function KpiPair({ a, b }: { a: PeriodKpi; b: PeriodKpi }) {
  const arrow = (x: string, y: string) => `${x} → ${y}`
  return (
    <Row gutter={[12, 12]}>
      <Col xs={24} md={8}>
        <Kpi title={t.kpiGpu} value={arrow(fmtPct(a.gpu_avg), fmtPct(b.gpu_avg))}
          note={fmtDelta(a.gpu_avg !== null && b.gpu_avg !== null ? b.gpu_avg - a.gpu_avg : null)} />
      </Col>
      <Col xs={24} md={8}>
        <Kpi title={t.kpiDanger} color={ZONE_META.danger.color}
          value={arrow(fmtInt(a.zones.danger), fmtInt(b.zones.danger))}
          note={`${vi.kpi.dangerCards}: ${fmtInt(a.cards_total.danger)} → ${fmtInt(b.cards_total.danger)}`} />
      </Col>
      <Col xs={24} md={8}>
        <Kpi title={t.kpiServers} value={arrow(fmtInt(a.n_servers), fmtInt(b.n_servers))} />
      </Col>
    </Row>
  )
}

function PeriodsTab() {
  const [f] = useFilters()
  const { data: meta } = useMeta()
  const { a, b, set } = useRanges()
  const setA = (r: Range) => set({ a: r })
  const setB = (r: Range) => set({ b: r })
  const [mv, setMv] = usePageParam('mv')
  const q = useCompare(f, { a_start: a?.[0], a_end: a?.[1], b_start: b?.[0], b_end: b?.[1] })
  const presets = (meta?.periods ?? [])
    .filter((p) => p.start && p.end)
    .map((p) => ({ label: fmtPeriodLabel(p.label), value: [dayjs(p.start), dayjs(p.end)] as [Dayjs, Dayjs] }))
  const picker = (r: Range, shown: PeriodKpi | undefined, set: (r: Range) => void) => (
    <DatePicker.RangePicker
      format={DATE_FMT}
      presets={presets}
      value={r ? [dayjs(r[0]), dayjs(r[1])] : shown ? [dayjs(shown.params.start), dayjs(shown.params.end)] : null}
      onChange={(v) => set(v && v[0] && v[1] ? [v[0].format('YYYY-MM-DD'), v[1].format('YYYY-MM-DD')] : null)}
    />
  )
  const data = q.data
  const header = (
    <Card size="small">
      <Flex wrap gap={12} align="center">
        <Typography.Text strong>{t.periodA}</Typography.Text>
        {picker(a, data?.a, setA)}
        <Button
          icon={<SwapOutlined />}
          disabled={!data}
          onClick={() => {
            if (!data) return
            set({ a: [data.b.params.start, data.b.params.end], b: [data.a.params.start, data.a.params.end] })
          }}
        >
          {t.swap}
        </Button>
        <Typography.Text strong>{t.periodB}</Typography.Text>
        {picker(b, data?.b, setB)}
      </Flex>
    </Card>
  )
  if (q.isError) {
    const need = q.error instanceof ApiError && q.error.status === 422
    return (
      <Space direction="vertical" style={{ width: '100%' }}>
        {header}
        {need ? <Alert type="info" showIcon message={t.needTwo} /> : <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      </Space>
    )
  }
  if (!data) return <Loading />

  const filtered = mv ? data.items.filter((i) => i.movement === mv) : data.items
  const columns: ColumnsType<CompareItem> = [
    { title: 'IP', dataIndex: 'ip', render: (ip: string) => <ServerLink ip={ip} /> },
    { title: vi.gaps.owner, dataIndex: 'owner', render: (v: string | null) => v ?? '—' },
    { title: vi.gaps.service, dataIndex: 'service', ellipsis: true, render: (v: string | null) => v ?? '—' },
    { title: t.movement, dataIndex: 'movement', render: (m: Movement) => <Tag color={MOVEMENT_META[m].tag}>{MOVEMENT_META[m].label}</Tag> },
    { title: t.zoneA, dataIndex: 'zone_prev', render: (z: CompareItem['zone_prev']) => (z ? <ZoneTag zone={z} /> : '—') },
    { title: t.zoneB, dataIndex: 'zone_cur', render: (z: CompareItem['zone_cur']) => (z ? <ZoneTag zone={z} /> : '—') },
    { title: t.gpuA, dataIndex: 'gpu_avg_prev', align: 'right', render: (v: number | null) => fmtPct(v) },
    { title: t.gpuB, dataIndex: 'gpu_avg_cur', align: 'right', render: (v: number | null) => fmtPct(v) },
    { title: t.dGpu, dataIndex: 'd_gpu', align: 'right', sorter: (x, y) => (x.d_gpu ?? 0) - (y.d_gpu ?? 0), render: (v: number | null) => fmtDelta(v) },
    { title: t.dMem, dataIndex: 'd_mem', align: 'right', sorter: (x, y) => (x.d_mem ?? 0) - (y.d_mem ?? 0), render: (v: number | null) => fmtDelta(v) },
  ]
  const rowsFrom = [...ZONE_ORDER, 'new'] as const
  const colsTo = [...ZONE_ORDER, 'gone'] as const
  const name = (k: string) => (k === 'new' ? t.newRow : k === 'gone' ? t.goneCol : zoneLabel(k))

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {header}
      <Typography.Text type="secondary">
        {fmtRange(data.a.params.start, data.a.params.end)} → {fmtRange(data.b.params.start, data.b.params.end)} ·{' '}
        {vi.filters.threshold} = {data.threshold}%
      </Typography.Text>
      <KpiPair a={data.a} b={data.b} />
      <Card size="small" title={t.movement}>
        <Space wrap>
          {MOVEMENT_ORDER.map((m) => (
            <Tag.CheckableTag key={m} checked={mv === m} onChange={(on) => setMv(on ? m : null)}>
              <Tag color={MOVEMENT_META[m].tag} style={{ margin: 0 }}>
                {MOVEMENT_META[m].label}: {fmtInt(data.counts[m])}
              </Tag>
            </Tag.CheckableTag>
          ))}
        </Space>
      </Card>
      <Card size="small" title={t.transition}>
        <Table
          size="small"
          pagination={false}
          rowKey="from"
          dataSource={rowsFrom.map((r) => ({ from: r, ...data.matrix[r] }))}
          columns={[
            { title: `${t.periodA} \\ ${t.periodB}`, dataIndex: 'from', render: (k: string) => <b>{name(k)}</b> },
            ...colsTo.map((c) => ({ title: name(c), dataIndex: c, align: 'right' as const, render: (n: number) => (n ? fmtInt(n) : '·') })),
          ]}
        />
      </Card>
      <Card size="small">
        <Table<CompareItem> size="small" rowKey="ip" columns={columns} dataSource={filtered}
          pagination={{ defaultPageSize: 50, hideOnSinglePage: true }} />
      </Card>
    </Space>
  )
}

function ServersTab() {
  const [f] = useFilters()
  const [ipsParam, setIps] = usePageParam('ips')
  const [metric, setMetric] = useState<'gpu' | 'mem'>('gpu')
  const [gParam, setG] = usePageParam('g')
  const g: Granularity = gParam === 'week' || gParam === 'month' ? gParam : 'day'
  const ips = useMemo(() => (ipsParam ? ipsParam.split(',').filter(Boolean).slice(0, MAX_COMPARE_SERVERS) : []), [ipsParam])
  const { data: cat } = useCatalog(f)
  const q = useMultiSeries(f, ips, g)
  const options = (cat?.items ?? [])
    .filter((r) => r.data_status === 'has_data' || r.row_type === 'vtnet_only')
    .map((r) => ({ value: r.ip, label: [r.ip, r.service, r.owner].filter(Boolean).join(' · ') }))

  let chart
  if (!ips.length) chart = <Empty description={t.noServers} />
  else if (q.isError) chart = <ErrorState error={q.error} onRetry={() => void q.refetch()} />
  else if (!q.data) chart = <Loading rows={8} />
  else {
    const dates = [...new Set(q.data.series.flatMap((s) => s.points.map((p) => p.date)))].sort()
    const option: EChartsOption = {
      tooltip: { trigger: 'axis', valueFormatter: (v: unknown) => fmtPct(typeof v === 'number' ? v : null) },
      legend: { bottom: 0 },
      grid: { left: 48, right: 24, top: 24, bottom: 56 },
      xAxis: { type: 'category', data: dates.map((d) => fmtDate(d)) },
      yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
      series: q.data.series.map((s, i) => {
        const byDate = new Map(s.points.map((p) => [p.date, p[metric]]))
        return {
          name: safeLabel([s.ip, s.service].filter(Boolean).join(' · ')),
          type: 'line',
          showSymbol: dates.length <= 40,
          connectNulls: false,
          itemStyle: { color: COMPARE_COLORS[i % COMPARE_COLORS.length] },
          data: dates.map((d) => byDate.get(d) ?? null),
          ...(i === 0
            ? { markLine: { silent: true, symbol: 'none', lineStyle: { color: SERIES.threshold, type: 'dashed' },
                data: [{ yAxis: q.data.params.threshold, name: `T=${q.data.params.threshold}%` }] } }
            : {}),
        }
      }),
    }
    chart = <EChart option={option} height={380} />
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card size="small">
        <Flex wrap gap={12} align="center">
          <Select
            mode="multiple"
            showSearch
            optionFilterProp="label"
            style={{ minWidth: 420, flex: 1 }}
            placeholder={t.pickServers}
            value={ips}
            maxCount={MAX_COMPARE_SERVERS}
            onChange={(v: string[]) => setIps(v.length ? v.slice(0, MAX_COMPARE_SERVERS).join(',') : null)}
            options={options}
          />
          <Typography.Text type="secondary">{t.maxServers}</Typography.Text>
          <Segmented<'gpu' | 'mem'> value={metric} onChange={setMetric}
            options={[{ value: 'gpu', label: t.gpu }, { value: 'mem', label: t.mem }]} />
          <Segmented<Granularity> value={g} onChange={(v) => setG(v === 'day' ? null : v)}
            options={[{ value: 'day', label: vi.chart.day }, { value: 'week', label: vi.chart.week }, { value: 'month', label: vi.chart.month }]} />
        </Flex>
      </Card>
      <Card>{chart}</Card>
      {q.data && (
        <Table
          size="small"
          rowKey="ip"
          pagination={false}
          dataSource={q.data.series}
          columns={[
            { title: 'IP', dataIndex: 'ip', render: (ip: string, _r, i) => (
              <Space><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 5, background: COMPARE_COLORS[i % COMPARE_COLORS.length] }} /><ServerLink ip={ip} /></Space>
            ) },
            { title: vi.gaps.owner, dataIndex: 'owner', render: (v: string | null) => v ?? '—' },
            { title: vi.gaps.service, dataIndex: 'service', render: (v: string | null) => v ?? '—' },
            { title: 'GPU', dataIndex: 'gpu_type', render: (v: string | null) => v ?? '—' },
            { title: vi.gaps.zone, dataIndex: 'zone', render: (z: CompareItem['zone_cur']) => <ZoneTag zone={z} /> },
            { title: vi.kpi.gpuAvg, dataIndex: 'gpu_avg', align: 'right', render: (v: number | null) => fmtPct(v) },
            { title: vi.kpi.memAvg, dataIndex: 'mem_avg', align: 'right', render: (v: number | null) => fmtPct(v) },
          ]}
        />
      )}
    </Space>
  )
}

export default function Compare() {
  const [tab, setTab] = usePageParam('tab')
  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Typography.Title level={3} style={{ margin: 0 }}>
        {t.title}
      </Typography.Title>
      <Tabs
        activeKey={tab === 'servers' ? 'servers' : 'periods'}
        onChange={(k) => setTab(k === 'periods' ? null : k)}
        items={[
          { key: 'periods', label: t.periods, children: <PeriodsTab /> },
          { key: 'servers', label: t.servers, children: <ServersTab /> },
        ]}
      />
    </Space>
  )
}
