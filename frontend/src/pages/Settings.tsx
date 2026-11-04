import { UndoOutlined } from '@ant-design/icons'
import { Alert, App, Button, Card, InputNumber, Popconfirm, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import { errorMessage } from '../api/client'
import { type SettingItem, useSaveSettings, useSettingsList } from '../api/hooks'
import { ErrorState, Loading } from '../components/States'
import { fmtDateTimeUtc } from '../lib/format'
import { vi } from '../lib/vi'

const t = vi.settings

/** Cài đặt các hằng §4 (chỉ admin). Giới hạn hợp lệ do API trả về; backend kiểm lại khi lưu. */
export default function SettingsPage() {
  const q = useSettingsList()
  const save = useSaveSettings()
  const { message } = App.useApp()
  const [draft, setDraft] = useState<Record<string, number>>({})

  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />
  if (!q.data) return <Loading />
  const items = q.data.items
  const changed = Object.fromEntries(
    Object.entries(draft).filter(([k, v]) => items.find((i) => i.key === k)?.value !== v),
  )
  const n = Object.keys(changed).length

  const submit = async () => {
    try {
      await save.mutateAsync(changed)
      setDraft({})
      message.success(t.saved)
    } catch (e) {
      message.warning(errorMessage(e))
    }
  }

  const columns: ColumnsType<SettingItem> = [
    {
      title: t.name,
      key: 'label',
      render: (_: unknown, r) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{r.label}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {r.hint}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: t.value,
      key: 'value',
      width: 180,
      render: (_: unknown, r) => (
        <InputNumber
          min={r.min}
          max={r.max}
          step={r.integer ? 1 : r.max <= 1 ? 0.05 : 1}
          precision={r.integer ? 0 : undefined}
          value={draft[r.key] ?? r.value}
          onChange={(v) => typeof v === 'number' && setDraft((d) => ({ ...d, [r.key]: v }))}
          addonAfter={r.unit || undefined}
          style={{ width: 150 }}
          aria-label={r.label}
        />
      ),
    },
    {
      title: t.default,
      key: 'default',
      width: 160,
      render: (_: unknown, r) => (
        <Space>
          <span>
            {r.default}
            {r.unit}
          </span>
          {(draft[r.key] ?? r.value) !== r.default && (
            <Button size="small" icon={<UndoOutlined />} onClick={() => setDraft((d) => ({ ...d, [r.key]: r.default }))}>
              {t.reset}
            </Button>
          )}
        </Space>
      ),
    },
    {
      title: t.lastChange,
      key: 'updated',
      render: (_: unknown, r) =>
        r.updated_by && r.updated_by !== 'seed' ? t.updated(r.updated_by, fmtDateTimeUtc(r.updated_at)) : t.neverUpdated,
    },
  ]

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Typography.Title level={3} style={{ margin: 0 }}>
        {t.title}
      </Typography.Title>
      <Alert type="info" showIcon message={t.hint} />
      <Card size="small">
        <Table<SettingItem> size="small" rowKey="key" columns={columns} dataSource={items} pagination={false} />
      </Card>
      <Space>
        <Popconfirm title={t.confirm} okText={vi.imports.confirmOk} cancelText={vi.imports.confirmCancel}
          onConfirm={() => void submit()} disabled={!n}>
          <Button type="primary" disabled={!n} loading={save.isPending}>
            {t.save} {n ? `(${n})` : ''}
          </Button>
        </Popconfirm>
        {!n && <Typography.Text type="secondary">{t.noChange}</Typography.Text>}
      </Space>
    </Space>
  )
}
