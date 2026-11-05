import { Card, Col, Collapse, Row, Space, Statistic, Tag, Typography } from 'antd'
import { useMeta } from '../api/hooks'
import type { Batch } from '../api/types'
import { fmtDelta } from '../lib/compare'
import { fmtInt, fmtPct, fmtPeriodLabel } from '../lib/format'
import { CHECK_LEVELS, CHECK_META, countByLevel, readChecks } from '../lib/importChecks'
import { vi } from '../lib/vi'
import { ZONE_META, ZONE_ORDER } from '../lib/zones'
import { LoadChart, type LoadPoint } from './LoadChart'

type Dict = Record<string, unknown>
const obj = (v: unknown): Dict | null => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Dict) : null)
const num = (v: unknown): number | null => (typeof v === 'number' ? v : null)
const t = vi.importChecks

/** Danh sách kiểm tra của lô VTNet (lỗi chặn · cần xác nhận · thông tin). */
export function CheckList({ batch }: { batch: Batch }) {
  const checks = readChecks(batch.validation as Dict)
  if (!checks.length) return <Typography.Text type="success">{t.allClear}</Typography.Text>
  const n = countByLevel(checks)
  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Space wrap>
        {CHECK_LEVELS.filter((lv) => n[lv]).map((lv) => (
          <Tag key={lv} color={CHECK_META[lv].tag}>
            {CHECK_META[lv].label}: {n[lv]}
          </Tag>
        ))}
      </Space>
      <Collapse
        size="small"
        defaultActiveKey={checks.filter((c) => c.level !== 'info').map((c) => c.code)}
        items={checks.map((c) => ({
          key: c.code,
          label: (
            <Space wrap>
              <Tag color={CHECK_META[c.level].tag}>{CHECK_META[c.level].label}</Tag>
              <span>{c.title}</span>
            </Space>
          ),
          children: (
            <Space direction="vertical" size={4}>
              {c.detail && <Typography.Text type="secondary">{c.detail}</Typography.Text>}
              {c.items?.length ? (
                <Typography.Paragraph style={{ marginBottom: 0 }} copyable={{ text: c.items.join(', ') }}>
                  {c.items.join(', ')}
                  {c.n_items && c.n_items > c.items.length ? ` … (+${c.n_items - c.items.length})` : ''}
                </Typography.Paragraph>
              ) : null}
            </Space>
          ),
        }))}
      />
    </Space>
  )
}

/** Xem trước tác động: vùng theo T mặc định, TB toàn bộ server, so với kỳ trước + chuỗi theo ngày của file. */
export function ImpactPreview({ batch }: { batch: Batch }) {
  const { data: meta } = useMeta()
  const vtnetT = Number(meta?.settings.vtnet_low_load_t ?? 10)
  const sm = batch.summary as Dict
  const pv = obj(sm.preview)
  if (!pv) return null
  const prev = obj(sm.previous)
  const zones = obj(pv.zones) ?? {}
  const pz = prev ? (obj(prev.zones) ?? {}) : null
  const gpu = num(pv.gpu_avg)
  const pg = prev ? num(prev.gpu_avg) : null
  const daily = (Array.isArray(pv.daily) ? pv.daily : []) as LoadPoint[]
  const T = num(pv.threshold) ?? 40
  return (
    <Card size="small" title={t.previewTitle(T, typeof pv.zone_metric === 'string' ? pv.zone_metric : undefined)} extra={prev ? <Typography.Text type="secondary">{t.vsPrev(fmtPeriodLabel(prev.label as string))}</Typography.Text> : null}>
      <Row gutter={[12, 12]}>
        <Col xs={12} md={6}>
          <Statistic title={vi.kpi.gpuAvg} value={fmtPct(gpu)} />
          {pg !== null && gpu !== null && <Typography.Text type="secondary">{fmtDelta(gpu - pg)} {t.points}</Typography.Text>}
        </Col>
        <Col xs={12} md={6}>
          <Statistic title={vi.kpi.memAvg} value={fmtPct(num(pv.mem_avg))} />
        </Col>
        {ZONE_ORDER.map((z) => (
          <Col xs={8} md={4} key={z}>
            <Statistic title={ZONE_META[z].label} value={fmtInt(num(zones[z]))} valueStyle={{ color: ZONE_META[z].color }} />
            {pz && <Typography.Text type="secondary">{t.prevValue(fmtInt(num(pz[z])))}</Typography.Text>}
          </Col>
        ))}
      </Row>
      {daily.length > 1 && (
        <div style={{ marginTop: 12 }}>
          <LoadChart points={daily} threshold={T} vtnetT={vtnetT} granularity="day" height={240}
            fileName={`xem_truoc_lo_${batch.id}`} />
        </div>
      )}
    </Card>
  )
}
