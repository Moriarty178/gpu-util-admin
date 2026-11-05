import { CheckOutlined, DeleteOutlined, EditOutlined, LinkOutlined, PlusOutlined } from '@ant-design/icons'
import { Alert, App, Badge, Button, Card, Form, Input, Modal, Popconfirm, Space, Table, Tabs, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import { Link, useLocation } from 'react-router'
import { errorMessage } from '../api/client'
import { useGaps, useIpLinks, useLinkActions } from '../api/hooks'
import type { InventoryGapRow, IpLinkRow, MismatchRow, Suggestion, VtnetOnlyRow } from '../api/types'
import { useAuth } from '../auth/session'
import { ErrorState, Loading } from '../components/States'
import { ZoneTag } from '../components/Tags'
import { fmtDateTimeUtc, fmtPct } from '../lib/format'
import { VIETTEL_RED } from '../lib/theme'
import { vi } from '../lib/vi'
import { globalSearch } from '../store/filters'
import { useFilters, usePageParam } from '../store/useFilters'

const t = vi.gaps

function ServerLink({ ip }: { ip: string }) {
  const { search } = useLocation()
  return <Link to={`/servers/${ip}${globalSearch(new URLSearchParams(search))}`}>{ip}</Link>
}

interface LinkForm {
  inventory_ip: string
  vtnet_ip: string
  reason?: string
}

function LinkModal({ open, editing, initial, onClose }: {
  open: boolean
  editing: IpLinkRow | null
  initial: Partial<LinkForm> | null
  onClose: () => void
}) {
  const [form] = Form.useForm<LinkForm>()
  const act = useLinkActions()
  const { message } = App.useApp()
  const [error, setError] = useState<string | null>(null)
  const submit = async (v: LinkForm) => {
    setError(null)
    try {
      if (editing) {
        await act.update.mutateAsync({ ip: editing.inventory_ip, body: { vtnet_ip: v.vtnet_ip, reason: v.reason ?? null } })
        message.success(t.saved)
      } else {
        await act.create.mutateAsync({ inventory_ip: v.inventory_ip, vtnet_ip: v.vtnet_ip, reason: v.reason ?? null })
        message.success(t.created)
      }
      onClose()
    } catch (e) {
      setError(errorMessage(e))
    }
  }
  return (
    <Modal
      open={open}
      title={editing ? `${t.editPair}: ${editing.inventory_ip}` : t.addLink}
      okText={vi.users.ok}
      cancelText={vi.auth.cancel}
      confirmLoading={act.create.isPending || act.update.isPending}
      onOk={() => form.submit()}
      onCancel={onClose}
      destroyOnHidden
      afterClose={() => setError(null)}
    >
      {error && <Alert type="warning" showIcon style={{ marginBottom: 12 }} message={error} />}
      {editing && <Alert type="info" showIcon style={{ marginBottom: 12 }} message={t.unconfirmed} description={vi.gaps.linksHint} />}
      <Form<LinkForm>
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={(v) => void submit(v)}
        // Form dựng lại mỗi lần mở (destroyOnHidden) → initialValues luôn đúng, không phụ thuộc hiệu ứng mở hộp thoại
        initialValues={
          editing
            ? { inventory_ip: editing.inventory_ip, vtnet_ip: editing.vtnet_ip, reason: editing.reason ?? undefined }
            : { inventory_ip: initial?.inventory_ip, vtnet_ip: initial?.vtnet_ip, reason: initial?.reason }
        }
      >
        <Form.Item name="inventory_ip" label={t.inventoryIp} rules={[{ required: true, message: t.inventoryIp }]}>
          <Input disabled={Boolean(editing)} placeholder="10.207.188.1" />
        </Form.Item>
        <Form.Item name="vtnet_ip" label={t.vtnetIp} rules={[{ required: true, message: t.vtnetIp }]}>
          <Input placeholder="10.205.36.51" />
        </Form.Item>
        <Form.Item name="reason" label={t.reason}>
          <Input.TextArea rows={2} maxLength={500} />
        </Form.Item>
      </Form>
    </Modal>
  )
}

function LinksTab() {
  const me = useAuth()
  const admin = me.role === 'admin'
  const [f] = useFilters()
  const links = useIpLinks(f)
  const act = useLinkActions()
  const { message } = App.useApp()
  const [modal, setModal] = useState<{ editing: IpLinkRow | null } | null>(null)

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn()
      message.success(ok)
    } catch (e) {
      message.warning(errorMessage(e))
    }
  }

  const columns: ColumnsType<IpLinkRow> = [
    { title: t.inventoryIp, dataIndex: 'inventory_ip', render: (ip: string) => <ServerLink ip={ip} /> },
    { title: t.vtnetIp, dataIndex: 'vtnet_ip' },
    {
      title: vi.users.status,
      key: 'state',
      render: (_: unknown, r) => (
        <Space wrap size={4}>
          {r.pair_confirmed ? <Tag color="green">{t.confirmed}</Tag> : <Tag color="cyan">{t.unconfirmed}</Tag>}
          {!r.in_inventory && <Tag>{t.notInInventory}</Tag>}
          {!r.vtnet_has_data && <Tag>{t.noVtnetData}</Tag>}
        </Space>
      ),
    },
    { title: t.zone, dataIndex: 'zone', render: (z: IpLinkRow['zone']) => (z ? <ZoneTag zone={z} /> : '—') },
    { title: t.owner, dataIndex: 'owner', render: (v: string | null) => v ?? '—' },
    { title: t.service, dataIndex: 'service', ellipsis: true, render: (v: string | null) => v ?? '—' },
    { title: t.reason, dataIndex: 'reason', ellipsis: true, render: (v: string | null) => v ?? '—' },
    {
      title: t.history,
      key: 'by',
      render: (_: unknown, r) => (
        <Space direction="vertical" size={0} style={{ fontSize: 12 }}>
          <span>{t.by(r.created_by ?? '—', fmtDateTimeUtc(r.created_at))}</span>
          {r.confirmed_by && <span>✓ {t.by(r.confirmed_by, fmtDateTimeUtc(r.confirmed_at))}</span>}
        </Space>
      ),
    },
  ]
  if (admin) {
    columns.push({
      title: vi.users.actions,
      key: 'actions',
      render: (_: unknown, r) => (
        <Space wrap size={4}>
          {r.pair_confirmed ? (
            <Button size="small" onClick={() => void run(() => act.update.mutateAsync({ ip: r.inventory_ip, body: { pair_confirmed: false } }), t.saved)}>
              {t.unconfirm}
            </Button>
          ) : (
            <Popconfirm title={t.confirmConfirm} okText={vi.imports.confirmOk} cancelText={vi.imports.confirmCancel}
              onConfirm={() => void run(() => act.update.mutateAsync({ ip: r.inventory_ip, body: { pair_confirmed: true } }), t.saved)}>
              <Button size="small" icon={<CheckOutlined />}>{t.confirm}</Button>
            </Popconfirm>
          )}
          <Button size="small" icon={<EditOutlined />} onClick={() => setModal({ editing: r })}>{t.editPair}</Button>
          <Popconfirm title={t.confirmRemove} okText={vi.imports.confirmOk} cancelText={vi.imports.confirmCancel}
            onConfirm={() => void run(() => act.remove.mutateAsync(r.inventory_ip), t.removed)}>
            <Button size="small" icon={<DeleteOutlined />}>{t.remove}</Button>
          </Popconfirm>
        </Space>
      ),
    })
  }
  if (links.isError) return <ErrorState error={links.error} onRetry={() => void links.refetch()} />
  if (!links.data) return <Loading />
  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Alert type="info" showIcon message={t.linksHint} action={admin ? (
        <Button size="small" icon={<PlusOutlined />} onClick={() => setModal({ editing: null })}>{t.addLink}</Button>
      ) : undefined} />
      <Table<IpLinkRow> size="small" rowKey="inventory_ip" columns={columns} dataSource={links.data.items} pagination={false} />
      <LinkModal open={modal !== null} editing={modal?.editing ?? null} initial={null} onClose={() => setModal(null)} />
    </Space>
  )
}

function SuggestionsTab({ items }: { items: Suggestion[] }) {
  const me = useAuth()
  const [initial, setInitial] = useState<Partial<LinkForm> | null>(null)
  if (!items.length) return <Alert type="success" showIcon message={t.noSuggestions} />
  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Alert type="info" showIcon message={t.suggestionsHint} />
      {items.map((g) => (
        <Card key={`${g.gpu_count}-${g.gpu_model}`} size="small" title={`${g.gpu_count}× ${g.gpu_model}`}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Text>
              {t.vtnetIp}: {g.vtnet_ips.join(', ')} · {t.inventoryIp}: {g.inventory_ips.join(', ')}
            </Typography.Text>
            {g.pairs.length ? (
              g.pairs.map((p) => (
                <Space key={p.inventory_ip} wrap>
                  <Typography.Text code>{p.inventory_ip} → {p.vtnet_ip}</Typography.Text>
                  {me.role === 'admin' && (
                    <Button size="small" icon={<LinkOutlined />}
                      onClick={() => setInitial({ ...p, reason: `Gợi ý: cùng ${g.gpu_count}× ${g.gpu_model}` })}>
                      {t.createLink}
                    </Button>
                  )}
                </Space>
              ))
            ) : (
              <Typography.Text type="secondary">{t.pickManually}</Typography.Text>
            )}
          </Space>
        </Card>
      ))}
      <LinkModal open={initial !== null} editing={null} initial={initial} onClose={() => setInitial(null)} />
    </Space>
  )
}

export default function Gaps() {
  const [f] = useFilters()
  const q = useGaps(f)
  const [tab, setTab] = usePageParam('tab')
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />
  if (!q.data) return <Loading />
  const g = q.data
  const c = g.counts

  const vtCols: ColumnsType<VtnetOnlyRow> = [
    { title: t.vtnetIp, dataIndex: 'ip', render: (ip: string) => <ServerLink ip={ip} /> },
    { title: t.vtnetSpec, dataIndex: 'gpu_type', render: (v: string | null) => v ?? '—' },
    { title: t.zone, dataIndex: 'zone', render: (z: VtnetOnlyRow['zone']) => <ZoneTag zone={z} /> },
    { title: vi.kpi.gpuAvg, dataIndex: 'gpu_avg', render: (v: number | null) => fmtPct(v) },
    { title: vi.kpi.memAvg, dataIndex: 'mem_avg', render: (v: number | null) => fmtPct(v) },
    { title: vi.server.days, dataIndex: 'days' },
  ]
  const invCols: ColumnsType<InventoryGapRow> = [
    { title: t.inventoryIp, dataIndex: 'inventory_ip', render: (ip: string) => <ServerLink ip={ip} /> },
    { title: t.owner, dataIndex: 'owner', render: (v: string | null) => v ?? '—' },
    { title: t.service, dataIndex: 'service', ellipsis: true, render: (v: string | null) => v ?? '—' },
    { title: t.spec, dataIndex: 'inventory_gpu_spec', render: (v: string | null) => v ?? '—' },
    { title: vi.server.cluster, dataIndex: 'cluster', render: (v: string | null) => v ?? '—' },
    { title: t.excelRow, dataIndex: 'excel_row', render: (v: number | null) => v ?? '—' },
  ]
  const mmCols: ColumnsType<MismatchRow> = [
    { title: t.inventoryIp, dataIndex: 'inventory_ip', render: (ip: string) => <ServerLink ip={ip} /> },
    { title: t.owner, dataIndex: 'owner', render: (v: string | null) => v ?? '—' },
    { title: t.spec, dataIndex: 'inventory_gpu_spec' },
    { title: t.vtnetSpec, dataIndex: 'gpu_type' },
    { title: t.zone, dataIndex: 'zone', render: (z: MismatchRow['zone']) => <ZoneTag zone={z} /> },
    { title: t.service, dataIndex: 'service', ellipsis: true, render: (v: string | null) => v ?? '—' },
  ]
  const label = (text: string, n: number) => (
    <Space size={6}>
      {text}
      <Badge count={n} showZero color={n ? VIETTEL_RED : '#d9d9d9'} overflowCount={999} />
    </Space>
  )

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Typography.Title level={3} style={{ margin: 0 }}>
        {t.title}
      </Typography.Title>
      <Card>
        <Tabs
          activeKey={tab ?? 'vtnet'}
          onChange={(k) => setTab(k === 'vtnet' ? null : k)}
          items={[
            {
              key: 'vtnet',
              label: label(t.vtnetOnly, c.vtnet_only),
              children: (
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Alert type="info" showIcon message={t.vtnetOnlyHint} />
                  <Table<VtnetOnlyRow> size="small" rowKey="ip" columns={vtCols} dataSource={g.vtnet_only} pagination={false} />
                </Space>
              ),
            },
            {
              key: 'nodata',
              label: label(t.noData, c.no_data),
              children: (
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Typography.Title level={5}>{t.unknown} ({c.unknown})</Typography.Title>
                  <Table<InventoryGapRow> size="small" rowKey="inventory_ip" columns={invCols} dataSource={g.unknown}
                    pagination={{ defaultPageSize: 50, hideOnSinglePage: true }} />
                  <Typography.Title level={5}>{t.reclaimed} ({c.reclaimed})</Typography.Title>
                  <Table<InventoryGapRow> size="small" rowKey="inventory_ip" columns={invCols} dataSource={g.reclaimed}
                    pagination={{ defaultPageSize: 50, hideOnSinglePage: true }} />
                </Space>
              ),
            },
            {
              key: 'mismatch',
              label: label(t.mismatch, c.gpu_count_mismatch),
              children: (
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Alert type="info" showIcon message={t.mismatchHint} />
                  <Table<MismatchRow> size="small" rowKey="inventory_ip" columns={mmCols} dataSource={g.gpu_count_mismatch} pagination={false} />
                </Space>
              ),
            },
            { key: 'links', label: label(t.links, c.links_unconfirmed), children: <LinksTab /> },
            { key: 'suggest', label: label(t.suggestions, g.suggestions.length), children: <SuggestionsTab items={g.suggestions} /> },
          ]}
        />
      </Card>
    </Space>
  )
}
