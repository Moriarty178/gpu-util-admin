import { Card, DatePicker, Flex, Input, Select, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { type AuditItem, useAudit } from '../api/hooks'
import { ErrorState } from '../components/States'
import { fmtDateTimeUtc } from '../lib/format'
import { useDebouncedValue } from '../lib/useDebounced'
import { vi } from '../lib/vi'
import { usePageParam, useSetPageParams } from '../store/useFilters'

const t = vi.audit
const PAGE_SIZE = 50
// Màu theo nhóm thao tác (không dùng đỏ — đỏ chỉ dành cho vùng "Nguy hiểm")
function actionColor(a: string): string {
  if (a === 'login_failed' || a === 'login_locked') return 'orange'
  if (a.startsWith('login') || a === 'logout' || a.startsWith('password')) return 'default'
  if (a.startsWith('import_')) return 'blue'
  if (a.startsWith('user_')) return 'geekblue'
  if (a.startsWith('link_')) return 'cyan'
  if (a.startsWith('note_')) return 'purple'
  return 'gold'
}

function payloadText(p: Record<string, unknown>): string {
  const entries = Object.entries(p).filter(([, v]) => v !== null && v !== undefined && v !== '')
  return entries.map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`).join(' · ')
}

/** Nhật ký thao tác (chỉ admin): lọc theo thao tác / tài khoản / ngày / đối tượng, mới nhất trước. */
export default function AuditPage() {
  const [action, setAction] = usePageParam('action')
  const [username, setUsername] = usePageParam('user')
  const [qParam, setQ] = usePageParam('q')
  const [start] = usePageParam('from')
  const [end] = usePageParam('to')
  const [pageParam, setPage] = usePageParam('page')
  const setParams = useSetPageParams()
  const page = Number(pageParam ?? 1) || 1
  const [qText, setQText] = useDebouncedValue<string | null>(qParam, (v) => setQ(v || null))
  const res = useAudit({ action: action ?? undefined, username: username ?? undefined, q: qParam ?? undefined,
    start: start ?? undefined, end: end ?? undefined, page, page_size: PAGE_SIZE })  // fmt: skip

  const columns: ColumnsType<AuditItem> = [
    { title: t.at, dataIndex: 'at', width: 160, render: (v: string) => fmtDateTimeUtc(v) },
    { title: t.user, dataIndex: 'username', width: 130, render: (v: string | null) => v ?? '—' },
    {
      title: t.action,
      dataIndex: 'action',
      width: 190,
      render: (a: string) => <Tag color={actionColor(a)}>{t.actions[a] ?? a}</Tag>,
    },
    { title: t.target, dataIndex: 'target', width: 180, render: (v: string | null) => v ?? '—' },
    {
      title: t.detail,
      dataIndex: 'payload',
      ellipsis: true,
      render: (p: Record<string, unknown>) => (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {payloadText(p)}
        </Typography.Text>
      ),
    },
  ]

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Typography.Title level={3} style={{ margin: 0 }}>
        {t.title}
      </Typography.Title>
      <Card size="small">
        <Flex wrap gap={8}>
          <Select
            allowClear
            style={{ minWidth: 220 }}
            placeholder={t.allActions}
            value={action ?? undefined}
            onChange={(v?: string) => setAction(v ?? null)}
            options={(res.data?.actions ?? []).map((a) => ({ value: a, label: t.actions[a] ?? a }))}
          />
          <Input allowClear style={{ width: 170 }} placeholder={t.user} defaultValue={username ?? ''}
            onPressEnter={(e) => setUsername((e.target as HTMLInputElement).value.trim() || null)}
            onBlur={(e) => setUsername(e.target.value.trim() || null)} />
          <Input.Search allowClear style={{ width: 280 }} placeholder={t.search} value={qText ?? ''}
            onChange={(e) => setQText(e.target.value || null)} />
          <DatePicker.RangePicker
            format="DD/MM/YYYY"
            value={start && end ? [dayjs(start), dayjs(end)] : null}
            onChange={(v) =>
              setParams(
                v && v[0] && v[1]
                  ? { from: v[0].format('YYYY-MM-DD'), to: v[1].format('YYYY-MM-DD') }
                  : { from: null, to: null },
              )
            }
          />
        </Flex>
      </Card>
      <Card size="small">
        {res.isError ? (
          <ErrorState error={res.error} onRetry={() => void res.refetch()} />
        ) : (
          <Table<AuditItem>
            size="small"
            rowKey="id"
            loading={!res.data}
            columns={columns}
            dataSource={res.data?.items ?? []}
            pagination={{
              current: page,
              pageSize: PAGE_SIZE,
              total: res.data?.total ?? 0,
              showSizeChanger: false,
              onChange: (p) => setPage(p === 1 ? null : String(p)),
            }}
          />
        )}
      </Card>
    </Space>
  )
}
