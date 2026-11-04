import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Flex, Form, Input, Typography } from 'antd'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiPost, errorMessage } from '../api/client'
import type { Me } from '../api/types'
import { NAVY_DARK } from '../lib/theme'
import { vi } from '../lib/vi'
import { startSession } from './session'

interface LoginForm {
  username: string
  password: string
}

/** Trang đăng nhập (hiện ở đúng URL người dùng đang mở → đăng nhập xong ở lại trang đó). */
export default function Login({ setupRequired = false, expired = false }: { setupRequired?: boolean; expired?: boolean }) {
  const qc = useQueryClient()
  const login = useMutation({
    mutationFn: (body: LoginForm) => apiPost<Me>('/auth/login', body),
    onSuccess: (me) => startSession(qc, me),
  })

  return (
    <Flex justify="center" align="center" style={{ minHeight: '100vh', background: '#f0f2f5', padding: 16 }}>
      <Card style={{ width: 380, maxWidth: '100%' }} styles={{ header: { background: NAVY_DARK } }}
        title={
          <div style={{ padding: '8px 0' }}>
            <Typography.Text strong style={{ color: '#fff', fontSize: 18, display: 'block' }}>
              {vi.appName}
            </Typography.Text>
            <Typography.Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 12 }}>{vi.appUnit}</Typography.Text>
          </div>
        }
      >
        <Typography.Title level={4} style={{ marginTop: 0 }}>
          {vi.auth.loginTitle}
        </Typography.Title>
        {setupRequired && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={vi.auth.setupTitle}
            description={
              <>
                <div>{vi.auth.setupHint}</div>
                <Typography.Text code copyable>
                  {vi.auth.setupCmd}
                </Typography.Text>
                <div style={{ marginTop: 4, fontSize: 12 }}>{vi.auth.setupDocker}</div>
              </>
            }
          />
        )}
        {expired && !login.isError && (
          <Alert type="info" showIcon style={{ marginBottom: 16 }} message={vi.auth.sessionExpired} />
        )}
        {login.isError && (
          <Alert type="warning" showIcon style={{ marginBottom: 16 }} message={errorMessage(login.error)} />
        )}
        <Form<LoginForm> layout="vertical" requiredMark={false} onFinish={(v) => login.mutate(v)} disabled={login.isPending}>
          <Form.Item name="username" label={vi.auth.username} rules={[{ required: true, message: vi.auth.required }]}>
            <Input prefix={<UserOutlined />} autoComplete="username" autoFocus />
          </Form.Item>
          <Form.Item name="password" label={vi.auth.password} rules={[{ required: true, message: vi.auth.required }]}>
            <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={login.isPending}>
            {login.isPending ? vi.auth.loggingIn : vi.auth.login}
          </Button>
        </Form>
        <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0, fontSize: 12 }}>
          {vi.auth.forgot}
        </Typography.Paragraph>
      </Card>
    </Flex>
  )
}
