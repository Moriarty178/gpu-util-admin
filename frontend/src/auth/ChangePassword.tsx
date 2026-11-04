import { Alert, App, Button, Card, Flex, Form, Input, Space, Typography } from 'antd'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { apiPost, errorMessage } from '../api/client'
import type { Me } from '../api/types'
import { vi } from '../lib/vi'
import { logout, ME_KEY } from './session'

interface PwForm {
  current_password: string
  new_password: string
  confirm: string
}

/** Đổi mật khẩu. `forced`: mật khẩu tạm — trang đứng riêng, chưa vào được app; còn lại là 1 trang trong app. */
export default function ChangePassword({ forced = false }: { forced?: boolean }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { message } = App.useApp()
  const change = useMutation({
    mutationFn: (v: PwForm) =>
      apiPost<Me>('/auth/change-password', { current_password: v.current_password, new_password: v.new_password }),
    onSuccess: (me) => {
      qc.setQueryData(ME_KEY, me)
      message.success(vi.auth.changed)
      if (!forced) navigate(-1)
    },
  })

  const form = (
    <Card title={vi.auth.changeTitle} style={{ width: 420, maxWidth: '100%' }}>
      {forced && <Alert type="info" showIcon style={{ marginBottom: 16 }} message={vi.auth.mustChange} />}
      {change.isError && (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }} message={errorMessage(change.error)} />
      )}
      <Form<PwForm> layout="vertical" requiredMark={false} onFinish={(v) => change.mutate(v)} disabled={change.isPending}>
        <Form.Item name="current_password" label={vi.auth.current} rules={[{ required: true, message: vi.auth.current }]}>
          <Input.Password autoComplete="current-password" autoFocus />
        </Form.Item>
        <Form.Item
          name="new_password"
          label={vi.auth.next}
          extra={vi.auth.policy}
          rules={[{ required: true, message: vi.auth.next }]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="confirm"
          label={vi.auth.confirm}
          dependencies={['new_password']}
          rules={[
            { required: true, message: vi.auth.confirm },
            ({ getFieldValue }) => ({
              validator: (_r, v) =>
                !v || v === getFieldValue('new_password') ? Promise.resolve() : Promise.reject(new Error(vi.auth.mismatch)),
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Space>
          <Button type="primary" htmlType="submit" loading={change.isPending}>
            {vi.auth.save}
          </Button>
          {forced ? (
            <Button onClick={() => void logout(qc)}>{vi.auth.logout}</Button>
          ) : (
            <Button onClick={() => navigate(-1)}>{vi.auth.cancel}</Button>
          )}
        </Space>
      </Form>
    </Card>
  )

  if (!forced) return form
  return (
    <Flex vertical justify="center" align="center" gap={12} style={{ minHeight: '100vh', background: '#f0f2f5', padding: 16 }}>
      <Typography.Text strong style={{ fontSize: 18 }}>
        {vi.appName} · {vi.appUnit}
      </Typography.Text>
      {form}
    </Flex>
  )
}
