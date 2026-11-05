import { DownloadOutlined, MessageOutlined } from '@ant-design/icons'
import {
  Button,
  Card,
  Checkbox,
  Col,
  Flex,
  InputNumber,
  Row,
  Segmented,
  Select,
  Slider,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { ColumnsType, SorterResult } from 'antd/es/table/interface'
import { Link, useLocation } from 'react-router'
import { apiUrl } from '../api/client'
import { useAlerts, useMeta, useServerTimeseries } from '../api/hooks'
import type { ServerItem } from '../api/types'
import { LoadChart } from '../components/LoadChart'
import { GpuCell, ServerBadges } from '../components/ServerBadges'
import { ErrorState, LimitationNote, Loading, NoData } from '../components/States'
import { PatternTag, ZoneTag } from '../components/Tags'
import { fmtDate, fmtInt, fmtPct } from '../lib/format'
import { useDebouncedValue } from '../lib/useDebounced'
import { vi } from '../lib/vi'
import {
  isZoneMetric,
  PATTERN_META,
  PATTERN_ORDER,
  type Pattern,
  ZONE_META,
  ZONE_METRIC_META,
  ZONE_METRICS,
  ZONE_ORDER,
  type Zone,
  type ZoneMetric,
  zoneRuleText,
} from '../lib/zones'
import { apiParams, globalSearch, parseList } from '../store/filters'
import { useFilters, usePageParam } from '../store/useFilters'

const T_PRESETS = [10, 20, 30, 40, 50, 60]
const DEFAULT_SORT = 'zone,gpu_avg'
// cột bảng → khóa sắp xếp của API
const SORT_KEYS: Record<string, string> = {
  zone: 'zone',
  ip: 'ip',
  owner: 'owner',
  service: 'service',
  gpu_avg: 'gpu_avg',
  mem_avg: 'mem_avg',
  gpu_peak: 'gpu_peak',
  days: 'days',
  low_streak: 'low_streak',
  pattern: 'pattern',
}

function ExpandedRow({ item }: { item: ServerItem }) {
  const [f] = useFilters()
  const location = useLocation()
  const ts = useServerTimeseries(item.ip, f)
  const { data: meta } = useMeta()
  return (
    <Row gutter={16}>
      <Col xs={24} lg={12}>
        <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{item.assessment}</Typography.Paragraph>
        <ServerBadges s={item} />
        <div style={{ marginTop: 8 }}>
          <Link to={`/servers/${item.ip}${globalSearch(new URLSearchParams(location.search))}`}>
            <Button size="small" type="primary">
              {vi.alerts.openDetail}
            </Button>
          </Link>
        </div>
      </Col>
      <Col xs={24} lg={12}>
        {ts.data && (
          <LoadChart
            points={ts.data.points}
            threshold={ts.data.params.threshold}
            vtnetT={Number(meta?.settings.vtnet_low_load_t ?? 10)}
            granularity="day"
            zoneStrip
            height={200}
            fileName={`tai_${item.ip}`}
          />
        )}
      </Col>
    </Row>
  )
}

export default function Alerts() {
  const [f, setFilters] = useFilters()
  const meta = useMeta()
  const defaultT = Number(meta.data?.settings.default_threshold ?? 40)
  const sm = meta.data?.settings.zone_metric
  const defaultMetric: ZoneMetric = isZoneMetric(sm) ? sm : 'both'
  const metric = f.zone_metric ?? defaultMetric
  const [zonesParam, setZones] = usePageParam('zones')
  const [patternsParam, setPatterns] = usePageParam('patterns')
  const [vtnet, setVtnet] = usePageParam('vtnet')
  const [mapped, setMapped] = usePageParam('mapped')
  const [hideEx, setHideEx] = usePageParam('hide_exempt')
  const [sortParam, setSort] = usePageParam('sort')
  const [pageParam, setPage] = usePageParam('page')
  const [sizeParam, setSize] = usePageParam('size')

  const zones = zonesParam === null ? (['danger'] as Zone[]) : parseList(zonesParam, ZONE_ORDER)
  const patterns = parseList(patternsParam, PATTERN_ORDER)
  const sort = sortParam ?? DEFAULT_SORT
  const page = Math.max(1, Number(pageParam) || 1)
  const pageSize = [20, 50, 100, 200].includes(Number(sizeParam)) ? Number(sizeParam) : 50

  const [t, setT] = useDebouncedValue<number>(f.threshold ?? defaultT, (v) =>
    setFilters({ threshold: v === defaultT ? undefined : v }),
  )

  const q = useAlerts(f, {
    zones: zones.length === ZONE_ORDER.length ? undefined : zones,
    patterns,
    vtnet_flag: vtnet === '1',
    only_mapped: mapped === '1',
    hide_exempt: hideEx === '1',
    sort,
    page,
    page_size: pageSize,
  })

  if (meta.data && meta.data.periods.length === 0) return <NoData />

  const sortField = sort.split(',')[0] ?? ''
  const sortOrder = (key: string) =>
    sortField.replace('-', '') === key && sort !== DEFAULT_SORT
      ? sortField.startsWith('-')
        ? ('descend' as const)
        : ('ascend' as const)
      : null

  const columns: ColumnsType<ServerItem> = [
    {
      title: vi.alerts.col.zone,
      dataIndex: 'zone',
      key: 'zone',
      sorter: true,
      sortOrder: sortOrder('zone'),
      render: (z: Zone) => <ZoneTag zone={z} />,
      width: 120,
    },
    {
      title: vi.alerts.col.ip,
      dataIndex: 'ip',
      key: 'ip',
      sorter: true,
      sortOrder: sortOrder('ip'),
      render: (ip: string, r) => (
        <Space direction="vertical" size={2}>
          <Link to={`/servers/${ip}`}>{ip}</Link>
          {(r.reclaimed || r.thin_data || r.ip_linked) && <ServerBadges s={{ ...r, gpu_count_mismatch: false }} />}
          {(r.exempt_until || Boolean(r.notes_count)) && (
            <Space size={4} wrap>
              {r.exempt_until && <Tag color="purple">{vi.notes.exemptTag(fmtDate(r.exempt_until))}</Tag>}
              {Boolean(r.notes_count) && <Tag icon={<MessageOutlined />}>{vi.notes.count(r.notes_count ?? 0)}</Tag>}
            </Space>
          )}
        </Space>
      ),
    },
    {
      title: vi.alerts.col.owner,
      dataIndex: 'owner',
      key: 'owner',
      sorter: true,
      sortOrder: sortOrder('owner'),
      render: (o: string | null) => o ?? <Tag color="gold">{vi.badge.unmapped}</Tag>,
    },
    {
      title: vi.alerts.col.service,
      dataIndex: 'service',
      key: 'service',
      sorter: true,
      sortOrder: sortOrder('service'),
      ellipsis: { showTitle: true },
      render: (v: string | null) => v ?? '—',
    },
    {
      title: vi.alerts.col.gpu,
      key: 'gpu',
      render: (_: unknown, r) => <GpuCell s={r} />,
    },
    {
      title: vi.alerts.col.gpuAvg,
      dataIndex: 'gpu_avg',
      key: 'gpu_avg',
      align: 'right',
      sorter: true,
      sortOrder: sortOrder('gpu_avg'),
      render: fmtPct,
    },
    {
      title: vi.alerts.col.memAvg,
      dataIndex: 'mem_avg',
      key: 'mem_avg',
      align: 'right',
      sorter: true,
      sortOrder: sortOrder('mem_avg'),
      render: fmtPct,
    },
    {
      title: vi.alerts.col.peak,
      dataIndex: 'gpu_peak',
      key: 'gpu_peak',
      align: 'right',
      sorter: true,
      sortOrder: sortOrder('gpu_peak'),
      render: fmtPct,
    },
    {
      title: vi.alerts.col.days,
      dataIndex: 'days',
      key: 'days',
      align: 'right',
      sorter: true,
      sortOrder: sortOrder('days'),
      render: (d: number | null) => `${fmtInt(d)}/${fmtInt(q.data?.params.days_in_range)}`,
    },
    {
      title: vi.alerts.col.streak,
      dataIndex: 'low_streak',
      key: 'low_streak',
      align: 'right',
      sorter: true,
      sortOrder: sortOrder('low_streak'),
      render: (n: number | null) => (n ? vi.alerts.streakDays(n) : '—'),
    },
    {
      title: vi.alerts.col.pattern,
      dataIndex: 'pattern',
      key: 'pattern',
      sorter: true,
      sortOrder: sortOrder('pattern'),
      render: (p: Pattern) => <PatternTag pattern={p} />,
    },
    {
      title: vi.alerts.col.vtnet,
      dataIndex: 'vtnet_low_load',
      key: 'vtnet',
      align: 'center',
      render: (v: boolean) => (v ? <Tag color="gold">{vi.badge.vtnetFlag}</Tag> : null),
    },
    {
      title: vi.alerts.col.assessment,
      dataIndex: 'assessment',
      key: 'assessment',
      ellipsis: { showTitle: false },
      width: 320,
      render: (v: string) => (
        <Tooltip title={v} placement="topLeft">
          {v}
        </Tooltip>
      ),
    },
  ]

  const data = q.data
  const summaryParts: string[] = []
  if (data) {
    for (const z of ZONE_ORDER) {
      const n = data.summary.zones[z]
      if (!n) continue
      let part = `${fmtInt(n)} ${ZONE_META[z].label}`
      if (z === 'danger') {
        part += ` (${fmtInt(data.summary.patterns.idle)} idle thật · ${fmtInt(data.summary.patterns.bursty_idle)} bursty)`
      }
      summaryParts.push(part)
    }
    summaryParts.push(vi.alerts.cards(data.summary.cards))
    summaryParts.push(vi.alerts.vtnetCount(data.summary.vtnet_low_load))
    summaryParts.push(vi.alerts.thinCount(data.summary.thin_data))
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Typography.Title level={3} style={{ margin: 0 }}>
        {vi.nav.alerts}
      </Typography.Title>
      <LimitationNote />
      <Card size="small">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Flex wrap gap={12} align="center">
            <Typography.Text strong>{vi.alerts.slider}</Typography.Text>
            <Slider
              min={0}
              max={100}
              value={t}
              onChange={setT}
              style={{ flex: '1 1 220px', minWidth: 180 }}
              tooltip={{ formatter: (v) => `${v}%` }}
            />
            <InputNumber
              min={0}
              max={100}
              value={t}
              onChange={(v) => typeof v === 'number' && setT(v)}
              addonAfter="%"
              style={{ width: 100 }}
            />
            <Space.Compact>
              {T_PRESETS.map((p) => (
                <Button key={p} type={t === p ? 'primary' : 'default'} onClick={() => setT(p)}>
                  {p}
                </Button>
              ))}
            </Space.Compact>
          </Flex>
          <Flex wrap gap={12} align="center">
            <Typography.Text strong>{vi.filters.zoneMetric}:</Typography.Text>
            <Segmented<ZoneMetric>
              value={metric}
              onChange={(v) => setFilters({ zone_metric: v === defaultMetric ? undefined : v })}
              options={ZONE_METRICS.map((m) => ({
                value: m,
                label: ZONE_METRIC_META[m].label,
              }))}
            />
            <Typography.Text type="secondary">{zoneRuleText(t, metric)}</Typography.Text>
          </Flex>
          <Flex wrap gap={16} align="center">
            <Space>
              <Typography.Text strong>{vi.alerts.zones}:</Typography.Text>
              <Checkbox.Group<Zone>
                value={zones}
                onChange={(v) => v.length > 0 && setZones(v.length === 1 && v[0] === 'danger' ? null : v.join(','))}
                options={ZONE_ORDER.map((z) => ({
                  value: z,
                  label: ZONE_META[z].label,
                }))}
              />
            </Space>
            <Select<Pattern[]>
              mode="multiple"
              allowClear
              style={{ minWidth: 220 }}
              placeholder={`${vi.alerts.patterns}: ${vi.filters.all}`}
              value={patterns}
              onChange={(v) => setPatterns(v.length ? v.join(',') : null)}
              options={PATTERN_ORDER.map((p) => ({
                value: p,
                label: PATTERN_META[p].label,
              }))}
            />
            <Checkbox checked={vtnet === '1'} onChange={(e) => setVtnet(e.target.checked ? '1' : null)}>
              {vi.alerts.vtnetOnly}
            </Checkbox>
            <Checkbox checked={mapped === '1'} onChange={(e) => setMapped(e.target.checked ? '1' : null)}>
              {vi.alerts.mappedOnly}
            </Checkbox>
            <Checkbox checked={hideEx === '1'} onChange={(e) => setHideEx(e.target.checked ? '1' : null)}>
              {vi.notes.hideExempt}
              {data?.summary.exempt ? ` (${fmtInt(data.summary.exempt)})` : ''}
            </Checkbox>
            <Button icon={<DownloadOutlined />} href={apiUrl('/alerts/export.xlsx', apiParams(f))}>
              {vi.alerts.exportXlsx}
            </Button>
          </Flex>
        </Space>
      </Card>

      {q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !data ? (
        <Loading rows={10} />
      ) : (
        <Card
          size="small"
          title={
            <span>
              {vi.alerts.summary}: {summaryParts.join(' · ')}
            </span>
          }
        >
          <Table<ServerItem>
            size="small"
            rowKey="ip"
            loading={q.isFetching}
            columns={columns}
            dataSource={data.items}
            scroll={{ x: 1400 }}
            expandable={{ expandedRowRender: (r) => <ExpandedRow item={r} /> }}
            pagination={{
              current: page,
              pageSize,
              total: data.total,
              showSizeChanger: true,
              pageSizeOptions: [20, 50, 100, 200],
              showTotal: (n) => `${fmtInt(n)} server`,
            }}
            onChange={(pg, _filters, sorter) => {
              const s = (Array.isArray(sorter) ? sorter[0] : sorter) as SorterResult<ServerItem> | undefined
              const key = s?.columnKey ? SORT_KEYS[String(s.columnKey)] : undefined
              const nextSort = key && s?.order ? `${s.order === 'descend' ? '-' : ''}${key}` : null
              if ((nextSort ?? DEFAULT_SORT) !== sort) {
                setSort(nextSort)
                return
              }
              if (pg.pageSize !== pageSize) setSize(String(pg.pageSize))
              else if (pg.current !== page) setPage(pg.current && pg.current > 1 ? String(pg.current) : null)
            }}
          />
        </Card>
      )}
    </Space>
  )
}
