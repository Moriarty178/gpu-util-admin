import { DeleteOutlined } from '@ant-design/icons'
import { Alert, App, AutoComplete, Button, Form, Input, Modal, Popconfirm, Select, Space, Typography } from 'antd'
import { useState } from 'react'
import { errorMessage } from '../api/client'
import { useEditInventory, useManualInventory, useMeta } from '../api/hooks'
import { type CatalogItem, EDITABLE_FIELDS, type EditableField } from '../api/types'
import { editBody, fileValue, type InventoryForm } from '../lib/inventoryEdit'
import { vi } from '../lib/vi'
import { RECLAIM_META, RECLAIM_STATUSES } from '../lib/zones'

const LABEL: Record<EditableField, string> = {
  owner: vi.inventory.col.owner,
  model: vi.inventory.col.model,
  input_load: vi.inventory.col.input,
  service: vi.inventory.col.service,
  managed_by: vi.inventory.col.managed,
  cluster: vi.inventory.col.cluster,
}

export function InventoryEditModal({ row, onClose }: { row: CatalogItem | null; onClose: () => void }) {
  const [form] = Form.useForm<InventoryForm>()
  const edit = useEditInventory()
  const manualAct = useManualInventory()
  const manual = row?.manual ?? false // server bổ sung trên web: không có giá trị "theo file"
  const { data: meta } = useMeta()
  const { message } = App.useApp()
  const [error, setError] = useState<string | null>(null)
  const ip = row?.inventory_ip ?? ''

  const suggestions: Partial<Record<EditableField, string[]>> = {
    owner: meta?.owners,
    managed_by: meta?.managed_by,
    cluster: meta?.clusters,
  }

  const submit = async (v: InventoryForm) => {
    if (!row) return
    setError(null)
    const body = editBody(row, v)
    if (Object.keys(body).length === 0) return onClose()
    try {
      await edit.mutateAsync({ ip, body })
      message.success(vi.inventory.saved(ip))
      onClose()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  const removeManual = async () => {
    try {
      await manualAct.remove.mutateAsync(ip)
      message.success(vi.inventory.manualRemoved(ip))
      onClose()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <Modal
      open={row !== null}
      title={vi.inventory.editTitle(ip)}
      okText={vi.inventory.save}
      cancelText={vi.inventory.cancel}
      confirmLoading={edit.isPending}
      onOk={() => form.submit()}
      onCancel={onClose}
      destroyOnHidden
      width={560}
      footer={(_, { OkBtn, CancelBtn }) => (
        <Space>
          {manual && (
            <Popconfirm title={vi.inventory.confirmRemoveManual} okText={vi.imports.confirmOk}
              cancelText={vi.imports.confirmCancel} onConfirm={() => void removeManual()}>
              <Button danger icon={<DeleteOutlined />} loading={manualAct.remove.isPending}>{vi.inventory.removeManual}</Button>
            </Popconfirm>
          )}
          <CancelBtn />
          <OkBtn />
        </Space>
      )}
      afterOpenChange={(o) => {
        if (!o || !row) return
        setError(null)
        form.setFieldsValue({
          ...Object.fromEntries(EDITABLE_FIELDS.map((f) => [f, row[f] ?? ''])),
          reclaim_status: row.reclaim_status ?? 'in_use',
        })
      }}
    >
      <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
        {manual ? vi.inventory.manualHint : vi.inventory.editHint}
      </Typography.Paragraph>
      {error && <Alert type="warning" showIcon style={{ marginBottom: 12 }} message={error} />}
      <Form<InventoryForm> form={form} layout="vertical" requiredMark={false} onFinish={(v) => void submit(v)}>
        <Form.Item name="reclaim_status" label={vi.inventory.col.reclaim}>
          <Select options={RECLAIM_STATUSES.map((s) => ({ value: s, label: RECLAIM_META[s].label }))} />
        </Form.Item>
        {row &&
          EDITABLE_FIELDS.map((f) => {
            const file = fileValue(row, f)
            const options = (suggestions[f] ?? []).map((o) => ({ value: o }))
            return (
              <Form.Item
                key={f}
                label={LABEL[f]}
                style={{ marginBottom: 12 }}
                extra={manual ? undefined : (
                  <span>
                    {vi.inventory.fileValue(file)}{' '}
                    <Button type="link" size="small" style={{ padding: 0 }} onClick={() => form.setFieldValue(f, file ?? '')}>
                      {vi.inventory.resetToFile}
                    </Button>
                  </span>
                )}
              >
                <Form.Item name={f} noStyle>
                  {options.length > 0 ? (
                    <AutoComplete
                      options={options}
                      filterOption={(input, o) =>
                        String(o?.value ?? '').toLowerCase().includes(input.trim().toLowerCase())
                      }
                    />
                  ) : (
                    <Input maxLength={f === 'owner' ? 64 : 500} />
                  )}
                </Form.Item>
              </Form.Item>
            )
          })}
      </Form>
    </Modal>
  )
}
