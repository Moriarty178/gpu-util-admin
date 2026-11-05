import { LinkOutlined } from '@ant-design/icons'
import {
  Alert,
  AutoComplete,
  Card,
  Col,
  Descriptions,
  Empty,
  Flex,
  Input,
  Result,
  Row,
  Segmented,
  Space,
  Statistic,
  Tag,
  Typography,
} from 'antd'
import { useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router'
import { ApiError } from '../api/client'
import { useCatalog, useMeta, useServerDetail, useServerTimeseries } from '../api/hooks'
import type { Granularity } from '../api/types'
import { LoadChart } from '../components/LoadChart'
import { NotesCard } from '../components/NotesCard'
import { ServerBadges } from '../components/ServerBadges'
import { ErrorState, Loading, NoData } from '../components/States'
import { PatternTag, ReclaimTag, StatusTag, ZoneTag } from '../components/Tags'
import { fmtInt, fmtPct, fmtRange, shortGpu } from '../lib/format'
import { vi } from '../lib/vi'
import type { ReclaimStatus } from '../lib/zones'
import { globalSearch } from '../store/filters'
import { useFilters, usePageParam } from '../store/useFilters'

const GRANS: Granularity[] = ['day', 'week', 'month']

function ServerSearch({ current }: { current?: string }) {
  const [f] = useFilters()
  const navigate = useNavigate()
  const location = useLocation()
  const { data } = useCatalog(f)
  const [text, setText] = useState('')
  const options = useMemo(() => {
    const needle = text.trim().toLowerCase()
    return (data?.items ?? [])
      .map((r) => {
        const target = r.data_status === 'has_data' || r.row_type === 'vtnet_only' ? r.ip : (r.inventory_ip ?? r.ip)
        const label = [target, r.service, r.model, r.owner].filter(Boolean).join(' · ')
        return { value: target, label, hay: `${label} ${r.inventory_ip ?? ''} ${r.ip}`.toLowerCase() }
      })
      .filter((o) => !needle || o.hay.includes(needle))
      .slice(0, 50)
      .map(({ value, label }) => ({ value, label }))
  }, [data, text])
  return (
    <AutoComplete
      style={{ width: '100%', maxWidth: 560 }}
      options={options}
      value={text}
      onChange={setText}
      onSelect={(ip: string) => {
        setText('')
        navigate(`/servers/${ip}${globalSearch(new URLSearchParams(location.search))}`)
      }}
    >
      <Input.Search placeholder={current ? `${vi.server.search} (${current})` : vi.server.search} allowClear />
    </AutoComplete>
  )
}

export default function ServerDetail() {
  const { ip } = useParams()
  const [f] = useFilters()
  const [g, setG] = usePageParam('g')
  const granularity: Granularity = GRANS.includes(g as Granularity) ? (g as Granularity) : 'day'
  const meta = useMeta()
  const detail = useServerDetail(ip, f)
  const ts = useServerTimeseries(ip, f, granularity)

  if (meta.data && meta.data.periods.length === 0 && !meta.data.inventory) return <NoData />

  const header = (
    <Flex justify="space-between" align="center" wrap gap={12}>
      <Typography.Title level={3} style={{ margin: 0 }}>
        {vi.nav.servers}
      </Typography.Title>
      <ServerSearch current={ip} />
    </Flex>
  )
  if (!ip) {
    return (
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        {header}
        <Card>
          <Empty description={vi.server.pick} />
        </Card>
      </Space>
    )
  }
  if (detail.isError) {
    const notFound = detail.error instanceof ApiError && detail.error.status === 404
    return (
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        {header}
        {notFound ? (
          <Result status="404" title={vi.server.notFound} subTitle={ip} />
        ) : (
          <ErrorState error={detail.error} onRetry={() => detail.refetch()} />
        )}
      </Space>
    )
  }
  if (!detail.data) return <Loading />

  const d = detail.data
  const s = d.stats
  const inv = d.inventory
  const vtnetT = Number(meta.data?.settings.vtnet_low_load_t ?? 10)
  const gpuLabel = shortGpu(s?.gpu_type ?? (inv?.inventory_gpu_spec as string | null))
  const owner = (inv?.owner as string | null) ?? s?.owner ?? null

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {header}
      <Row gutter={[12, 12]}>
        <Col xs={24} xl={14}>
          <Card
            style={{ height: '100%' }}
            title={
              <Space wrap>
                <span>{d.ip}</span>
                <span>· {gpuLabel}</span>
                <span>· {owner ?? vi.badge.unmapped}</span>
              </Space>
            }
          >
            <Space direction="vertical" style={{ width: '100%' }}>
              {d.link && (
                <Space wrap>
                  <LinkOutlined />
                  <Typography.Text>{vi.server.linkLine(d.link.inventory_ip, d.link.vtnet_ip)}</Typography.Text>
                  {!d.link.pair_confirmed && <Tag color="cyan">{vi.badge.linkedUnconfirmed}</Tag>}
                </Space>
              )}
              <Space wrap>
                {s && <ZoneTag zone={s.zone} />}
                {s && <PatternTag pattern={s.pattern} short={false} />}
                <StatusTag status={d.data_status} />
                {s && (
                  <Tag color={s.vtnet_low_load ? 'gold' : 'default'}>
                    {vi.server.vtnetFlag}: {s.vtnet_low_load ? vi.server.yes : vi.server.no}
                  </Tag>
                )}
              </Space>
              {s && <ServerBadges s={{ ...s, ip_linked: false }} /* liên kết đã hiện ở dòng trên */ />}
              {inv ? (
                <Descriptions size="small" column={{ xs: 1, md: 2 }} bordered>
                  <Descriptions.Item label={vi.server.service}>{(inv.service as string) ?? '—'}</Descriptions.Item>
                  <Descriptions.Item label={vi.server.model}>{(inv.model as string) ?? '—'}</Descriptions.Item>
                  <Descriptions.Item label={vi.server.cluster}>{(inv.cluster as string) ?? '—'}</Descriptions.Item>
                  <Descriptions.Item label={vi.server.managedBy}>{(inv.managed_by as string) ?? '—'}</Descriptions.Item>
                  <Descriptions.Item label={vi.server.inputLoad}>{(inv.input_load as string) ?? '—'}</Descriptions.Item>
                  <Descriptions.Item label={vi.inventory.col.reclaim}>
                    <ReclaimTag status={(inv.reclaim_status as ReclaimStatus | null) ?? 'in_use'} />
                  </Descriptions.Item>
                  <Descriptions.Item label={vi.server.gpuInventory}>
                    {(inv.inventory_gpu_spec as string) ?? '—'}
                  </Descriptions.Item>
                  <Descriptions.Item label={vi.server.gpuVtnet}>{s?.gpu_type ?? '—'}</Descriptions.Item>
                  <Descriptions.Item label="">
                    {inv.excel_row ? vi.server.excelRow(inv.excel_row) : '—'}
                  </Descriptions.Item>
                </Descriptions>
              ) : (
                <Alert type="warning" showIcon message={vi.server.vtnetOnly} />
              )}
              {!s && <Alert type="info" showIcon message={vi.server.noVtnet} />}
              {d.reclaim && (
                <Alert
                  type="info"
                  showIcon
                  message={vi.server.reclaimInfo}
                  description={[d.reclaim.gpu_type, d.reclaim.beneficiary, d.reclaim.owner_dcim, d.reclaim.status]
                    .filter(Boolean)
                    .join(' · ')}
                />
              )}
            </Space>
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card title={`${vi.server.metrics} (${fmtRange(d.params.start, d.params.end)})`} style={{ height: '100%' }}>
            {s ? (
              <Row gutter={[12, 16]}>
                <Col span={8}>
                  <Statistic title={vi.kpi.gpuAvg} value={fmtPct(s.gpu_avg)} />
                </Col>
                <Col span={8}>
                  <Statistic title={vi.kpi.memAvg} value={fmtPct(s.mem_avg)} />
                </Col>
                <Col span={8}>
                  <Statistic title={vi.server.peak} value={fmtPct(s.gpu_peak)} />
                </Col>
                <Col span={8}>
                  <Statistic title={vi.server.p95} value={fmtPct(s.gpu_p95)} />
                </Col>
                <Col span={8}>
                  <Statistic title={vi.server.days} value={`${fmtInt(s.days)}/${fmtInt(d.params.days_in_range)}`} />
                </Col>
                <Col span={8}>
                  <Statistic title={vi.server.streak} value={fmtInt(s.low_streak)} />
                </Col>
                <Col span={8}>
                  <Statistic title={vi.server.dangerDays} value={fmtInt(s.danger_days)} />
                </Col>
              </Row>
            ) : (
              <Empty description={vi.server.noVtnet} />
            )}
          </Card>
        </Col>
      </Row>

      {s && (
        <Card
          title={vi.chart.serverTitle}
          extra={
            <Segmented<Granularity>
              value={granularity}
              onChange={(v) => setG(v === 'day' ? null : v)}
              options={[
                { value: 'day', label: vi.chart.day },
                { value: 'week', label: vi.chart.week },
                { value: 'month', label: vi.chart.month },
              ]}
            />
          }
        >
          {ts.data ? (
            <LoadChart
              points={ts.data.points}
              threshold={d.params.threshold}
              vtnetT={vtnetT}
              granularity={granularity}
              zoneStrip
              fileName={`tai_${d.ip}_${d.params.start}_${d.params.end}`}
            />
          ) : (
            <Loading rows={8} />
          )}
        </Card>
      )}
      {s?.assessment && (
        <Card title={vi.server.assessment}>
          <Typography.Paragraph style={{ marginBottom: 0 }}>{s.assessment}</Typography.Paragraph>
        </Card>
      )}
      <NotesCard ip={d.ip} f={f} />
    </Space>
  )
}
