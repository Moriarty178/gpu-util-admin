import { DeleteOutlined, DownloadOutlined, PlusOutlined, UndoOutlined } from '@ant-design/icons'
import { Alert, App, Button, Card, Col, Empty, Input, Row, Select, Space, Tag, Typography } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { ApiError, apiDownload, errorMessage } from '../api/client'
import { useMonthlyReport } from '../api/hooks'
import type { MonthlyReportOut } from '../api/types'
import { Kpi } from '../components/Kpi'
import { ErrorState, Loading } from '../components/States'
import { downloadBlob } from '../lib/csv'
import { fmtDelta } from '../lib/compare'
import { fmtDate, fmtInt, fmtPct, fmtPeriodLabel, fmtRange } from '../lib/format'
import { draftErrors, REPORT_LIMITS, reportBody, type ReportDraft } from '../lib/report'
import { vi } from '../lib/vi'
import { thresholdLabel, ZONE_META } from '../lib/zones'

const t = vi.report

function toDraft(d: MonthlyReportOut): ReportDraft {
  return { message: d.suggestion.message, recommendations: d.suggestion.recommendations.map((r) => ({ ...r })) }
}

function Summary({ d }: { d: MonthlyReportOut }) {
  const k = d.kpi
  const p = d.previous
  const vs = p ? t.vsPrev(fmtPeriodLabel(p.month)) : ''
  const long = d.danger.filter((r) => r.streak_months >= 3).length
  return (
    <Row gutter={[12, 12]}>
      <Col xs={12} md={6}>
        <Kpi title={vi.kpi.gpuAvg} value={fmtPct(k.gpu_avg)}
          note={p && k.gpu_avg !== null && p.gpu_avg !== null ? `${fmtDelta(k.gpu_avg - p.gpu_avg)} ${vs}` : t.noPrev} />
      </Col>
      <Col xs={12} md={6}>
        <Kpi title={vi.kpi.memAvg} value={fmtPct(k.mem_avg)}
          note={`${fmtInt(k.n_servers)} server · ${fmtInt(k.cards)} card`} />
      </Col>
      <Col xs={12} md={6}>
        <Kpi title={ZONE_META.danger.label} color={ZONE_META.danger.color} value={fmtInt(k.zones.danger)}
          note={`${t.dangerCards(k.cards_total.danger)}${long ? ` · ${t.longStreak(long)}` : ''}`} />
      </Col>
      <Col xs={12} md={6}>
        <Kpi title={vi.compare.periods} value={d.movement ? t.movement(d.movement.counts.worsened ?? 0, d.movement.counts.improved ?? 0) : '—'}
          note={p ? vs : t.noPrev} />
      </Col>
    </Row>
  )
}

function Editor({ draft, onChange, onReset, edited }: {
  draft: ReportDraft
  onChange: (d: ReportDraft) => void
  onReset: () => void
  edited: boolean
}) {
  const recs = draft.recommendations
  const setRec = (i: number, patch: Partial<ReportDraft['recommendations'][number]>) =>
    onChange({ ...draft, recommendations: recs.map((r, j) => (j === i ? { ...r, ...patch } : r)) })
  return (
    <Card size="small" title={t.textTitle}
      extra={<Space>{edited && <Tag color="gold">{t.edited}</Tag>}<Button size="small" icon={<UndoOutlined />} onClick={onReset} disabled={!edited}>{t.reset}</Button></Space>}>
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <div>
          <Typography.Text strong>{t.message}</Typography.Text>
          <Input.TextArea value={draft.message} maxLength={REPORT_LIMITS.message} showCount autoSize={{ minRows: 2, maxRows: 4 }}
            onChange={(e) => onChange({ ...draft, message: e.target.value })} />
        </div>
        <Typography.Text strong>{t.recs}</Typography.Text>
        {recs.map((r, i) => (
          <Row gutter={8} key={i} align="top">
            <Col flex="none"><Tag color="red" style={{ marginTop: 4 }}>{i + 1}</Tag></Col>
            <Col flex="auto">
              <Space direction="vertical" style={{ width: '100%' }} size={4}>
                <Input value={r.title} placeholder={t.recTitle} maxLength={REPORT_LIMITS.recTitle} showCount
                  onChange={(e) => setRec(i, { title: e.target.value })} />
                <Input.TextArea value={r.detail} placeholder={t.recDetail} maxLength={REPORT_LIMITS.recDetail} showCount
                  autoSize={{ minRows: 1, maxRows: 3 }} onChange={(e) => setRec(i, { detail: e.target.value })} />
              </Space>
            </Col>
            <Col flex="none">
              <Button type="text" icon={<DeleteOutlined />} aria-label="Xóa"
                onClick={() => onChange({ ...draft, recommendations: recs.filter((_, j) => j !== i) })} />
            </Col>
          </Row>
        ))}
        {recs.length < REPORT_LIMITS.recs && (
          <Button icon={<PlusOutlined />} onClick={() => onChange({ ...draft, recommendations: [...recs, { title: '', detail: '' }] })}>
            {t.addRec}
          </Button>
        )}
      </Space>
    </Card>
  )
}

export default function Report() {
  const { message } = App.useApp()
  const [month, setMonth] = useState<string | null>(null)
  const q = useMonthlyReport(month)
  const d = q.data
  const suggestion = useMemo(() => (d ? toDraft(d) : null), [d])
  const [draft, setDraft] = useState<ReportDraft | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => setDraft(suggestion), [suggestion]) // đổi tháng → lấy lại gợi ý của tháng đó

  if (q.isLoading) return <Loading />
  if (q.error && !(q.error instanceof ApiError && q.error.status === 422)) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  if (!d || !draft || !suggestion) return <Card><Empty description={q.error ? errorMessage(q.error) : vi.empty} /></Card>

  const c = d.completeness
  const incomplete = new Set(d.incomplete_months)
  const label = fmtPeriodLabel(d.month)
  const monthEnd = fmtDate(d.end)
  const errors = draftErrors(draft)
  const body = reportBody(d.month, draft, suggestion)
  const edited = Object.keys(body).length > 1
  const download = async () => {
    setBusy(true)
    try {
      const fallback = `Bao_cao_GPU_${d.month}.pptx`
      const { blob, fileName } = await apiDownload('/reports/monthly.pptx', body, fallback)
      downloadBlob(blob, fileName)
      message.success(t.downloaded(fileName))
    } catch (e) {
      message.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card size="small">
        <Space wrap align="center" style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space wrap>
            <Typography.Text strong>{t.month}</Typography.Text>
            <Select style={{ minWidth: 230 }} value={d.month} onChange={setMonth}
              options={d.available_months.map((m) => ({
                value: m,
                label: incomplete.has(m) ? `${fmtPeriodLabel(m)} — ${t.incompleteTag}` : fmtPeriodLabel(m),
              }))} />
            <Typography.Text type="secondary">{fmtRange(d.start, d.end)} · {thresholdLabel(d.threshold, d.zone_metric)}</Typography.Text>
          </Space>
          <Button type="primary" icon={<DownloadOutlined />} loading={busy} disabled={errors.length > 0 || !c.complete}
            onClick={download}>
            {t.download}
          </Button>
        </Space>
        <Typography.Paragraph type="secondary" style={{ margin: '8px 0 0' }}>{t.hint}</Typography.Paragraph>
      </Card>
      {!c.complete && (
        <Alert type="warning" showIcon
          message={t.incomplete(label, c.last ? t.uptoDay(fmtDate(c.last)) : t.noDataYet, c.days_with_data, c.days_in_month, monthEnd)} />
      )}
      {c.complete && c.missing_days.length > 0 && (
        <Alert type="info" showIcon message={t.missingDays(c.missing_days.length, c.missing_days.slice(0, 10).map((x) => fmtDate(x)).join(', ') + (c.missing_days.length > 10 ? ', …' : ''))} />
      )}
      {d.scope_owner && <Alert type="info" showIcon message={t.scopeOwn(d.scope_owner)} />}
      <Summary d={d} />
      <Row gutter={[12, 12]}>
        <Col xs={24} lg={15}>
          <Editor draft={draft} onChange={setDraft} onReset={() => setDraft(suggestion)} edited={edited} />
          {errors.length > 0 && <Alert style={{ marginTop: 8 }} type="warning" showIcon message={errors.join(' ')} />}
        </Col>
        <Col xs={24} lg={9}>
          <Card size="small" title={t.outline}>
            <ol style={{ margin: 0, paddingLeft: 20 }}>
              {t.slides.map((s) => <li key={s}>{s}</li>)}
            </ol>
          </Card>
        </Col>
      </Row>
    </Space>
  )
}
