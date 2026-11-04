import { Alert, Descriptions, Space, Tag, Tooltip, Typography } from 'antd'
import type { Batch } from '../api/types'
import { fmtInt, fmtPeriodLabel, fmtRange } from '../lib/format'
import { vi } from '../lib/vi'
import { CheckList, ImpactPreview } from './ImportChecks'

type Dict = Record<string, unknown>
const arr = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : [])
const n = (v: unknown): number | null => (typeof v === 'number' ? v : null)
const obj = (v: unknown): Dict | null => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Dict) : null)

function ListCount({ items, empty }: { items: string[]; empty?: string }) {
  if (items.length === 0) return <span>{empty ?? '0'}</span>
  return (
    <Tooltip title={items.join(', ')}>
      <Typography.Text underline style={{ cursor: 'help' }}>
        {fmtInt(items.length)}
      </Typography.Text>
    </Tooltip>
  )
}

function maxDiff(v: unknown): string {
  const x = n(v)
  if (x === null) return '—'
  return x < 5e-5 ? '0' : new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 4 }).format(x)
}

/** Tóm tắt + kiểm tra của 1 lô (PLAN §5, §8.5). */
export function BatchPreview({ batch }: { batch: Batch }) {
  const sm = batch.summary as Dict
  const val = batch.validation as Dict
  const warnings = arr(val.warnings)
  const ignored = arr(val.ignored_sheets)
  const error = typeof val.error === 'string' ? val.error : null

  if (batch.status === 'failed') {
    return <Alert type="warning" showIcon message={batch.status_label} description={error} />
  }

  const common = (
    <>
      <Descriptions.Item label={vi.imports.kind}>{batch.kind_label}</Descriptions.Item>
      <Descriptions.Item label={vi.imports.schema}>{batch.schema_version ?? '—'}</Descriptions.Item>
    </>
  )

  if (batch.kind === 'vtnet_util') {
    const ov = obj(val.overview)
    const hasPrev = n(sm.prev_batch_id) !== null
    return (
      <Space direction="vertical" style={{ width: '100%' }}>
        <Descriptions size="small" bordered column={{ xs: 1, md: 2, xl: 3 }}>
          {common}
          <Descriptions.Item label={vi.imports.period}>
            {fmtRange(batch.period_start, batch.period_end)} ({fmtPeriodLabel(batch.period_label)})
          </Descriptions.Item>
          <Descriptions.Item label={vi.imports.rows}>{fmtInt(n(sm.rows))}</Descriptions.Item>
          <Descriptions.Item label={vi.imports.servers}>{fmtInt(n(sm.n_ips))}</Descriptions.Item>
          <Descriptions.Item label={vi.imports.reclaimed}>
            {sm.reclaimed === null || sm.reclaimed === undefined ? '—' : fmtInt(n(sm.reclaimed))}
          </Descriptions.Item>
          <Descriptions.Item label={vi.imports.newIps}>
            <ListCount items={arr(sm.new_ips)} empty={hasPrev ? '0' : vi.imports.noPrevious} />
          </Descriptions.Item>
          <Descriptions.Item label={vi.imports.goneIps}>
            <ListCount items={arr(sm.gone_ips)} empty={hasPrev ? '0' : vi.imports.noPrevious} />
          </Descriptions.Item>
          <Descriptions.Item label={vi.imports.overlapDays}>
            <ListCount items={arr(sm.overlap_days)} />
          </Descriptions.Item>
          <Descriptions.Item label={vi.imports.replaced}>{fmtInt(n(sm.replaced))}</Descriptions.Item>
        </Descriptions>
        {ov ? (
          ov.ok ? (
            <Alert
              type="success"
              showIcon
              message={vi.imports.overviewOk(
                Number(ov.n_overview ?? 0),
                maxDiff(Math.max(n(ov.max_abs_diff_gpu) ?? 0, n(ov.max_abs_diff_mem) ?? 0)),
              )}
            />
          ) : (
            <Alert
              type="warning"
              showIcon
              message={vi.imports.overviewBad(arr(ov.mismatched_ips).length, Number(ov.n_overview ?? 0))}
              description={arr(ov.mismatched_ips).slice(0, 10).join(', ')}
            />
          )
        ) : (
          <Alert type="info" showIcon message={vi.imports.overviewMissing} />
        )}
        {sm.granularity === 'hour' && <Alert type="info" showIcon message={vi.imports.granularityHour} />}
        {ignored.length > 0 && (
          <Space wrap>
            <Typography.Text type="secondary">{vi.imports.ignoredSheets}:</Typography.Text>
            {ignored.map((s) => (
              <Tag key={s}>{s}</Tag>
            ))}
          </Space>
        )}
        {Array.isArray(val.checks) ? (
          <>
            {batch.status === 'staged' && <ImpactPreview batch={batch} />}
            <CheckList batch={batch} />
          </>
        ) : (
          warnings.length > 0 && ( // lô nhập trước khi có kiểm tra chi tiết
            <Alert type="warning" showIcon message={vi.imports.warnings} description={<ul style={{ margin: 0 }}>{warnings.map((w) => <li key={w}>{w}</li>)}</ul>} />
          )
        )}
      </Space>
    )
  }

  const byOwner = obj(sm.by_owner) ?? {}
  const invalid = Array.isArray(val.invalid_ip_rows) ? (val.invalid_ip_rows as Array<{ excel_row: number; ip: string }>) : []
  const hasPrev = n(sm.prev_batch_id) !== null
  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Descriptions size="small" bordered column={{ xs: 1, md: 2, xl: 3 }}>
        {common}
        <Descriptions.Item label={vi.imports.rows}>{fmtInt(n(sm.rows))}</Descriptions.Item>
        <Descriptions.Item label={vi.imports.byOwner}>
          {Object.entries(byOwner)
            .map(([o, c]) => `${o}: ${fmtInt(Number(c))}`)
            .join(' · ') || '—'}
        </Descriptions.Item>
        <Descriptions.Item label={vi.imports.added}>
          <ListCount items={arr(sm.added_ips)} empty={hasPrev ? '0' : vi.imports.noPrevious} />
        </Descriptions.Item>
        <Descriptions.Item label={vi.imports.removed}>
          <ListCount items={arr(sm.removed_ips)} empty={hasPrev ? '0' : vi.imports.noPrevious} />
        </Descriptions.Item>
        <Descriptions.Item label={vi.imports.linkedIps}>{fmtInt(n(sm.linked_ips))}</Descriptions.Item>
        <Descriptions.Item label={vi.imports.invalidRows}>
          {invalid.length ? invalid.map((x) => `#${x.excel_row} (${x.ip})`).join(', ') : '0'}
        </Descriptions.Item>
      </Descriptions>
      {warnings.length > 0 && (
        <Alert type="warning" showIcon message={vi.imports.warnings} description={<ul style={{ margin: 0 }}>{warnings.map((w) => <li key={w}>{w}</li>)}</ul>} />
      )}
    </Space>
  )
}
