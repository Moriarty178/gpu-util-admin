import { Alert, App, AutoComplete, Col, Form, Input, Modal, Row, Select, Typography } from 'antd'
import { useState } from 'react'
import { errorMessage } from '../api/client'
import { useManualInventory, useMeta } from '../api/hooks'
import type { EditableField, ManualField, VtnetOnlyRow } from '../api/types'
import { type ManualForm, manualBody } from '../lib/inventoryEdit'
import { vi } from '../lib/vi'
import { RECLAIM_META, RECLAIM_STATUSES } from '../lib/zones'

const col = vi.inventory.col
// Thứ tự cột như file thống kê (trừ STT, IP)
const FIELDS: { f: ManualField | EditableField; label: string }[] = [
  { f: 'server_class', label: col.serverClass },
  { f: 'config', label: col.config },
  { f: 'cpu', label: col.cpu },
  { f: 'ram', label: col.ram },
  { f: 'disk', label: col.disk },
  { f: 'hba', label: col.hba },
  { f: 'gpu_spec', label: col.gpu },
  { f: 'serial', label: col.serial },
  { f: 'owner', label: col.owner },
  { f: 'model', label: col.model },
  { f: 'input_load', label: col.input },
  { f: 'service', label: col.service },
  { f: 'managed_by', label: col.managed },
  { f: 'cluster', label: col.cluster },
]

/** Bổ sung thông tin 1 server "VTNet có – thống kê thiếu" (trang Đối soát, PLAN §14.12) — chỉ admin. */
export function InventoryManualModal({ row, onClose }: { row: VtnetOnlyRow | null; onClose: () => void }) {
  const [form] = Form.useForm<ManualForm>()
  const act = useManualInventory()
  const { data: meta } = useMeta()
  const { message } = App.useApp()
  const [error, setError] = useState<string | null>(null)
  const ip = row?.ip ?? ''
  const suggestions: Partial<Record<string, string[]>> = {
    owner: meta?.owners,
    managed_by: meta?.managed_by,
    cluster: meta?.clusters,
  }

  const submit = async (v: ManualForm) => {
    setError(null)
    try {
      await act.add.mutateAsync(manualBody(ip, v))
      message.success(vi.gaps.manualSaved(ip))
      onClose()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <Modal
      open={row !== null}
      title={vi.gaps.manualTitle(ip)}
      okText={vi.inventory.save}
      cancelText={vi.inventory.cancel}
      confirmLoading={act.add.isPending}
      onOk={() => form.submit()}
      onCancel={onClose}
      destroyOnHidden
      width={720}
      afterClose={() => setError(null)}
    >
      <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
        {vi.gaps.vtnetOnlyAdminHint}
      </Typography.Paragraph>
      {error && <Alert type="warning" showIcon style={{ marginBottom: 12 }} message={error} />}
      <Form<ManualForm>
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={(v) => void submit(v)}
        // GPU mặc định theo VTNet (vd '8×NVIDIA H200') — admin sửa lại cho đúng cách ghi của file thống kê nếu cần
        initialValues={{ gpu_spec: row?.gpu_type ?? undefined, reclaim_status: 'in_use' }}
      >
        <Row gutter={16}>
          {FIELDS.map(({ f, label }) => {
            const options = (suggestions[f] ?? []).map((o) => ({ value: o }))
            return (
              <Col key={f} xs={24} md={12}>
                <Form.Item
                  name={f}
                  label={f === 'owner' ? `${label} *` : label}
                  style={{ marginBottom: 12 }}
                  rules={f === 'owner' ? [{ required: true, whitespace: true, message: vi.gaps.ownerRequired }] : undefined}
                >
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
              </Col>
            )
          })}
          <Col xs={24} md={12}>
            <Form.Item name="reclaim_status" label={col.reclaim} style={{ marginBottom: 12 }}>
              <Select options={RECLAIM_STATUSES.map((s) => ({ value: s, label: RECLAIM_META[s].label }))} />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  )
}
