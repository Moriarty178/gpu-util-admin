import { DeleteOutlined } from '@ant-design/icons'
import { Alert, App, Button, Card, DatePicker, Empty, Flex, Form, Input, List, Popconfirm, Select, Space, Tag, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { errorMessage } from '../api/client'
import { useNoteActions, useNotes } from '../api/hooks'
import type { NoteKind } from '../api/types'
import { useAuth } from '../auth/session'
import { fmtDate, fmtDateTimeUtc } from '../lib/format'
import { vi } from '../lib/vi'
import type { GlobalFilters } from '../store/filters'
import { ErrorState, Loading } from './States'

const t = vi.notes
// Màu loại ghi chú (không dùng đỏ — đỏ chỉ dành cho vùng "Nguy hiểm")
const KIND_TAG: Record<NoteKind, string> = { explanation: 'blue', note: 'default', action: 'gold', exempt: 'purple' }

interface NoteForm {
  kind: NoteKind
  text: string
  valid_until?: Dayjs
}

/** Ghi chú / giải trình / miễn trừ / hành động của 1 server (G2-M3, PLAN §8.6). Quyền do API trả về (`can_add`). */
export function NotesCard({ ip, f }: { ip: string; f: GlobalFilters }) {
  const me = useAuth()
  const q = useNotes(ip, f)
  const act = useNoteActions(ip, f)
  const { message } = App.useApp()
  const [form] = Form.useForm<NoteForm>()
  const kind = Form.useWatch('kind', form)

  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />
  if (!q.data) return <Loading rows={3} />
  const { can_add: kinds, items } = q.data

  const submit = async (v: NoteForm) => {
    try {
      await act.add.mutateAsync({ kind: v.kind, text: v.text, valid_until: v.valid_until ? v.valid_until.format('YYYY-MM-DD') : null })
      message.success(t.added)
      form.resetFields(['text', 'valid_until'])
    } catch (e) {
      message.warning(errorMessage(e))
    }
  }
  const remove = async (id: number) => {
    try {
      await act.remove.mutateAsync(id)
    } catch (e) {
      message.warning(errorMessage(e))
    }
  }

  return (
    <Card title={`${t.title} (${items.length})`}>
      <Space direction="vertical" style={{ width: '100%' }}>
        {items.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t.empty} />
        ) : (
          <List
            size="small"
            dataSource={items}
            renderItem={(n) => (
              <List.Item
                actions={
                  n.can_delete
                    ? [
                        <Popconfirm key="del" title={t.confirmRemove} okText={vi.imports.confirmOk} cancelText={vi.imports.confirmCancel}
                          onConfirm={() => void remove(n.id)}>
                          <Button size="small" type="text" icon={<DeleteOutlined />}>{t.remove}</Button>
                        </Popconfirm>,
                      ]
                    : []
                }
              >
                <List.Item.Meta
                  title={
                    <Space wrap size={6}>
                      <Tag color={KIND_TAG[n.kind]}>{n.kind_label}</Tag>
                      {n.valid_until && (
                        <Typography.Text type={n.active ? undefined : 'secondary'} delete={!n.active}>
                          {t.validUntil}: {fmtDate(n.valid_until)}
                          {!n.active && ` (${t.expired})`}
                        </Typography.Text>
                      )}
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {n.created_by} · {fmtDateTimeUtc(n.created_at)}
                      </Typography.Text>
                    </Space>
                  }
                  description={<Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>{n.text}</Typography.Paragraph>}
                />
              </List.Item>
            )}
          />
        )}
        {kinds.length > 0 ? (
          <>
            {me.role === 'owner' && <Alert type="info" showIcon message={t.ownerHint} />}
            {kinds.includes('exempt') && <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t.exemptNote}</Typography.Text>}
            <Form<NoteForm> form={form} layout="vertical" requiredMark={false} initialValues={{ kind: kinds[0] }}
              onFinish={(v) => void submit(v)}>
              <Flex gap={8} wrap align="start">
                <Form.Item name="kind" label={t.kind} style={{ minWidth: 150, marginBottom: 8 }}>
                  <Select options={kinds.map((k) => ({ value: k, label: t.kinds[k] }))} />
                </Form.Item>
                {(kind === 'exempt' || kind === 'action') && (
                  <Form.Item
                    name="valid_until"
                    label={t.validUntil}
                    style={{ marginBottom: 8 }}
                    rules={kind === 'exempt' ? [{ required: true, message: t.exemptNeedsDate }] : []}
                  >
                    <DatePicker format="DD/MM/YYYY" disabledDate={(d) => d.isBefore(dayjs(), 'day') || d.isAfter(dayjs().add(366, 'day'))} />
                  </Form.Item>
                )}
              </Flex>
              <Form.Item name="text" label={t.text} rules={[{ required: true, whitespace: true, message: t.text }]} style={{ marginBottom: 8 }}>
                <Input.TextArea rows={3} maxLength={2000} showCount />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={act.add.isPending}>
                {t.add}
              </Button>
            </Form>
          </>
        ) : (
          me.role === 'viewer' && <Typography.Text type="secondary">{t.readOnly}</Typography.Text>
        )}
      </Space>
    </Card>
  )
}
