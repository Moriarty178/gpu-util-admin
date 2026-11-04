import { CheckOutlined, DownloadOutlined, InboxOutlined, RollbackOutlined, StopOutlined } from '@ant-design/icons'
import { Alert, App, Button, Card, Popconfirm, Space, Table, Tag, Tooltip, Typography, Upload } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import { apiUrl, errorMessage } from '../api/client'
import { useBatchActions, useImports } from '../api/hooks'
import type { Batch, BatchStatus } from '../api/types'
import { BatchPreview } from '../components/BatchPreview'
import { ErrorState, Loading } from '../components/States'
import { fmtDateTimeUtc, fmtPeriodLabel, fmtRange } from '../lib/format'
import { commitGate, readChecks } from '../lib/importChecks'
import { vi } from '../lib/vi'

// Màu trạng thái lô — không dùng đỏ (đỏ chỉ dành cho vùng "Nguy hiểm")
const STATUS_TAG: Record<BatchStatus, string> = {
  staged: 'processing',
  committed: 'success',
  rolled_back: 'default',
  failed: 'warning',
  discarded: 'default',
}

/** Xác nhận nhập: lỗi chặn → khóa nút; có cảnh báo → phải xác nhận đã xem (backend kiểm lại `acknowledge`). */
function CommitButton({ batch, busy, onCommit }: { batch: Batch; busy: boolean; onCommit: (ack: boolean) => void }) {
  const checks = readChecks(batch.validation as Record<string, unknown>)
  const { blocked, needsAck } = commitGate(checks)
  const btn = (
    <Button size="small" type="primary" icon={<CheckOutlined />} disabled={busy || blocked}
      onClick={needsAck ? undefined : () => onCommit(false)}>
      {vi.imports.commit}
    </Button>
  )
  if (blocked) return <Tooltip title={vi.importChecks.blocked}>{btn}</Tooltip>
  if (!needsAck) return btn
  const warns = checks.filter((c) => c.level === 'warning')
  return (
    <Popconfirm
      title={vi.importChecks.ackTitle(warns.length)}
      description={<ul style={{ margin: 0, paddingLeft: 18, maxWidth: 420 }}>{warns.map((w) => <li key={w.code}>{w.title}</li>)}</ul>}
      okText={vi.importChecks.ackOk}
      cancelText={vi.imports.confirmCancel}
      onConfirm={() => onCommit(true)}
    >
      {btn}
    </Popconfirm>
  )
}

export default function Imports() {
  const { message } = App.useApp()
  const list = useImports()
  const act = useBatchActions()
  const [current, setCurrent] = useState<Batch | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const run = async (fn: () => Promise<Batch>, ok: (b: Batch) => string) => {
    try {
      const b = await fn()
      message.success(ok(b))
      setCurrent((c) => (c && c.id === b.id ? b : c))
    } catch (e) {
      message.warning(errorMessage(e))
    }
  }
  const commit = (id: number, acknowledge = false) =>
    run(() => act.commit.mutateAsync({ id, acknowledge }), (b) => vi.imports.committed(b.id))
  const discard = (id: number) => run(() => act.discard.mutateAsync(id), (b) => vi.imports.discarded(b.id))
  const rollback = (id: number) => run(() => act.rollback.mutateAsync(id), (b) => vi.imports.rolledBack(b.id))
  const busy = act.commit.isPending || act.discard.isPending || act.rollback.isPending

  const actions = (b: Batch) => (
    <Space wrap size={4}>
      {b.status === 'staged' && (
        <>
          <CommitButton batch={b} busy={busy} onCommit={(ack) => commit(b.id, ack)} />
          <Popconfirm
            title={vi.imports.confirmDiscard}
            okText={vi.imports.confirmOk}
            cancelText={vi.imports.confirmCancel}
            onConfirm={() => discard(b.id)}
          >
            <Button size="small" icon={<StopOutlined />} disabled={busy}>
              {vi.imports.discard}
            </Button>
          </Popconfirm>
        </>
      )}
      {b.status === 'committed' && (
        <Popconfirm
          title={vi.imports.confirmRollback}
          okText={vi.imports.confirmOk}
          cancelText={vi.imports.confirmCancel}
          onConfirm={() => rollback(b.id)}
        >
          <Button size="small" icon={<RollbackOutlined />} disabled={busy}>
            {vi.imports.rollback}
          </Button>
        </Popconfirm>
      )}
      <Button size="small" icon={<DownloadOutlined />} href={apiUrl(`/imports/${b.id}/file`)}>
        {vi.imports.download}
      </Button>
    </Space>
  )

  const columns: ColumnsType<Batch> = [
    { title: vi.imports.col.id, dataIndex: 'id', width: 56 },
    { title: vi.imports.col.kind, dataIndex: 'kind_label' },
    { title: vi.imports.col.file, dataIndex: 'file_name', ellipsis: true },
    {
      title: vi.imports.col.period,
      key: 'period',
      render: (_: unknown, b) =>
        b.period_start ? `${fmtRange(b.period_start, b.period_end)} (${fmtPeriodLabel(b.period_label)})` : '—',
    },
    {
      title: vi.imports.col.status,
      dataIndex: 'status',
      render: (s: BatchStatus, b) => <Tag color={STATUS_TAG[s]}>{b.status_label}</Tag>,
    },
    {
      title: vi.imports.col.time,
      key: 'time',
      render: (_: unknown, b) => fmtDateTimeUtc(b.rolled_back_at ?? b.committed_at ?? b.uploaded_at),
    },
    { title: vi.imports.col.actions, key: 'actions', render: (_: unknown, b) => actions(b) },
  ]

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Typography.Title level={3} style={{ margin: 0 }}>
        {vi.imports.title}
      </Typography.Title>
      <Upload.Dragger
        accept=".xlsx"
        multiple={false}
        showUploadList={false}
        disabled={act.upload.isPending}
        customRequest={async ({ file, onSuccess, onError }) => {
          setUploadError(null)
          try {
            const b = await act.upload.mutateAsync(file as File)
            setCurrent(b)
            onSuccess?.(b)
          } catch (e) {
            setUploadError(errorMessage(e))
            setCurrent(null)
            onError?.(e as Error)
          }
        }}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">{act.upload.isPending ? vi.imports.uploading : vi.imports.drop}</p>
        <p className="ant-upload-hint">{vi.imports.dropHint}</p>
      </Upload.Dragger>
      {uploadError && <Alert type="warning" showIcon message={uploadError} closable onClose={() => setUploadError(null)} />}

      {current && (
        <Card
          title={current.status === 'staged' ? vi.imports.preview(current.id, current.file_name) : `#${current.id} — ${current.file_name}`}
          extra={<Tag color={STATUS_TAG[current.status]}>{current.status_label}</Tag>}
        >
          <Space direction="vertical" style={{ width: '100%' }}>
            <BatchPreview batch={current} />
            {actions(current)}
          </Space>
        </Card>
      )}

      <Card title={vi.imports.history} size="small">
        {list.isError ? (
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        ) : !list.data ? (
          <Loading />
        ) : (
          <Table<Batch>
            size="small"
            rowKey="id"
            columns={columns}
            dataSource={list.data.items}
            expandable={{ expandedRowRender: (b) => <BatchPreview batch={b} /> }}
            pagination={{ defaultPageSize: 20 }}
          />
        )}
      </Card>
    </Space>
  )
}
