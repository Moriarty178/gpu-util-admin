import { KeyOutlined, LockOutlined, PlusOutlined, UnlockOutlined } from '@ant-design/icons'
import { Alert, App, AutoComplete, Button, Card, Flex, Form, Input, Modal, Popconfirm, Radio, Select, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import { errorMessage } from '../api/client'
import { useMeta, useUserActions, useUsers } from '../api/hooks'
import type { DataScope, Role, User, UserInput, UserWithPassword } from '../api/types'
import { useAuth } from '../auth/session'
import { ErrorState, Loading } from '../components/States'
import { fmtDateTimeUtc } from '../lib/format'
import { INFO } from '../lib/theme'
import { vi } from '../lib/vi'

const ROLE_COLOR: Record<Role, string> = { admin: INFO, owner: 'cyan', viewer: 'default' }

interface UserForm {
  username?: string
  full_name?: string
  email?: string
  role: Role
  owner_key?: string
  data_scope: DataScope
}

function UserFormModal({
  open,
  editing,
  onClose,
  onDone,
}: {
  open: boolean
  editing: User | null
  onClose: () => void
  onDone: (r: UserWithPassword | null) => void
}) {
  const [form] = Form.useForm<UserForm>()
  const role = Form.useWatch('role', form)
  const { data: meta } = useMeta()
  const act = useUserActions()
  const { message } = App.useApp()
  const [error, setError] = useState<string | null>(null)
  const busy = act.create.isPending || act.update.isPending

  const submit = async (v: UserForm) => {
    setError(null)
    const body: UserInput = {
      role: v.role,
      owner_key: v.role === 'owner' ? (v.owner_key ?? null) : null,
      data_scope: v.role === 'owner' ? v.data_scope : 'all',
      full_name: v.full_name ?? null,
      email: v.email ?? null,
    }
    try {
      if (editing) {
        await act.update.mutateAsync({ id: editing.id, body })
        message.success(vi.users.saved)
        onDone(null)
      } else {
        const r = await act.create.mutateAsync({ ...body, username: v.username })
        message.success(vi.users.created(r.user.username))
        onDone(r)
      }
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <Modal
      open={open}
      title={editing ? `${vi.users.edit}: ${editing.username}` : vi.users.create}
      okText={vi.users.ok}
      cancelText={vi.auth.cancel}
      confirmLoading={busy}
      onOk={() => form.submit()}
      onCancel={onClose}
      destroyOnHidden
      afterOpenChange={(o) => {
        if (!o) return
        setError(null)
        form.setFieldsValue(
          editing
            ? {
                full_name: editing.full_name ?? undefined,
                email: editing.email ?? undefined,
                role: editing.role,
                owner_key: editing.owner_key ?? undefined,
                data_scope: editing.data_scope,
              }
            : { role: 'owner', data_scope: 'own' },
        )
      }}
    >
      {error && <Alert type="warning" showIcon style={{ marginBottom: 12 }} message={error} />}
      <Form<UserForm> form={form} layout="vertical" requiredMark={false} onFinish={(v) => void submit(v)}>
        {!editing && (
          <Form.Item
            name="username"
            label={vi.auth.username}
            extra={vi.users.usernameHint}
            rules={[{ required: true, message: vi.auth.username }]}
          >
            <Input autoComplete="off" />
          </Form.Item>
        )}
        <Form.Item name="full_name" label={vi.users.fullName}>
          <Input />
        </Form.Item>
        <Form.Item name="email" label={vi.users.email}>
          <Input type="email" />
        </Form.Item>
        <Form.Item name="role" label={vi.users.role}>
          <Select
            options={(['owner', 'viewer', 'admin'] as Role[]).map((r) => ({ value: r, label: vi.role[r] }))}
          />
        </Form.Item>
        {role === 'owner' && (
          <>
            <Form.Item
              name="owner_key"
              label={vi.users.ownerKey}
              extra={vi.users.ownerKeyHint}
              rules={[{ required: true, message: vi.users.ownerKey }]}
            >
              <AutoComplete
                options={(meta?.owners ?? []).map((o) => ({ value: o }))}
                filterOption={(input, o) => String(o?.value ?? '').includes(input.trim().toLowerCase())}
              />
            </Form.Item>
            <Form.Item name="data_scope" label={vi.users.dataScope}>
              <Radio.Group
                options={[
                  { value: 'own', label: vi.scope.own },
                  { value: 'all', label: vi.scope.all },
                ]}
              />
            </Form.Item>
          </>
        )}
      </Form>
    </Modal>
  )
}

function TempPasswordModal({ result, onClose }: { result: UserWithPassword | null; onClose: () => void }) {
  return (
    <Modal
      open={result !== null}
      title={`${vi.users.tempTitle}: ${result?.user.username ?? ''}`}
      onCancel={onClose}
      footer={<Button type="primary" onClick={onClose}>{vi.users.close}</Button>}
      maskClosable={false}
    >
      <Alert type="info" showIcon message={vi.users.tempWarn} style={{ marginBottom: 12 }} />
      <Typography.Paragraph
        copyable={{ text: result?.temp_password, tooltips: [vi.users.copy, vi.users.copied] }}
        style={{ fontSize: 20, fontFamily: 'monospace', marginBottom: 0 }}
      >
        {result?.temp_password}
      </Typography.Paragraph>
    </Modal>
  )
}

export default function Users() {
  const me = useAuth()
  const list = useUsers()
  const act = useUserActions()
  const { message } = App.useApp()
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<User | null>(null)
  const [temp, setTemp] = useState<UserWithPassword | null>(null)

  const run = async (fn: () => Promise<unknown>) => {
    try {
      await fn()
      message.success(vi.users.saved)
    } catch (e) {
      message.warning(errorMessage(e))
    }
  }
  const reset = async (u: User) => {
    try {
      setTemp(await act.reset.mutateAsync(u.id))
    } catch (e) {
      message.warning(errorMessage(e))
    }
  }

  const columns: ColumnsType<User> = [
    {
      title: vi.auth.username,
      key: 'username',
      render: (_: unknown, u) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{u.username}</Typography.Text>
          {u.full_name && <Typography.Text type="secondary">{u.full_name}</Typography.Text>}
        </Space>
      ),
      sorter: (a, b) => a.username.localeCompare(b.username),
    },
    {
      title: vi.users.role,
      key: 'role',
      render: (_: unknown, u) => <Tag color={ROLE_COLOR[u.role]}>{vi.role[u.role]}</Tag>,
      filters: (['admin', 'owner', 'viewer'] as Role[]).map((r) => ({ text: vi.role[r], value: r })),
      onFilter: (v, u) => u.role === v,
    },
    { title: vi.users.ownerKey, dataIndex: 'owner_key', render: (v: string | null) => v ?? '—' },
    {
      title: vi.users.dataScope,
      key: 'scope',
      render: (_: unknown, u) => (u.role === 'owner' ? vi.scope[u.data_scope] : vi.scope.all),
    },
    {
      title: vi.users.status,
      key: 'status',
      render: (_: unknown, u) => (
        <Space wrap size={4}>
          <Tag color={u.active ? 'success' : 'default'}>{u.active ? vi.users.active : vi.users.inactive}</Tag>
          {u.locked && <Tag color="warning">{vi.users.locked}</Tag>}
          {u.must_change_password && <Tag color="gold">{vi.users.mustChange}</Tag>}
        </Space>
      ),
    },
    {
      title: vi.users.lastLogin,
      dataIndex: 'last_login_at',
      render: (v: string | null) => (v ? fmtDateTimeUtc(v) : vi.users.never),
    },
    {
      title: vi.users.actions,
      key: 'actions',
      render: (_: unknown, u) => {
        const self = u.username === me.username
        return (
          <Space wrap size={4}>
            <Button size="small" onClick={() => { setEditing(u); setFormOpen(true) }}>
              {vi.users.edit}
            </Button>
            <Popconfirm title={vi.users.confirmReset} okText={vi.imports.confirmOk} cancelText={vi.imports.confirmCancel}
              onConfirm={() => void reset(u)}>
              <Button size="small" icon={<KeyOutlined />}>{vi.users.resetPassword}</Button>
            </Popconfirm>
            {u.locked && (
              <Button size="small" icon={<UnlockOutlined />}
                onClick={() => void run(() => act.update.mutateAsync({ id: u.id, body: { unlock: true } }))}>
                {vi.users.unlock}
              </Button>
            )}
            {!self &&
              (u.active ? (
                <Popconfirm title={vi.users.confirmLock} okText={vi.imports.confirmOk} cancelText={vi.imports.confirmCancel}
                  onConfirm={() => void run(() => act.update.mutateAsync({ id: u.id, body: { active: false } }))}>
                  <Button size="small" icon={<LockOutlined />}>{vi.users.lock}</Button>
                </Popconfirm>
              ) : (
                <Button size="small"
                  onClick={() => void run(() => act.update.mutateAsync({ id: u.id, body: { active: true } }))}>
                  {vi.users.unlockAccount}
                </Button>
              ))}
          </Space>
        )
      },
    },
  ]

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Flex justify="space-between" align="center">
        <Typography.Title level={3} style={{ margin: 0 }}>
          {vi.users.title}
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); setFormOpen(true) }}>
          {vi.users.create}
        </Button>
      </Flex>
      <Card size="small">
        {list.isError ? (
          <ErrorState error={list.error} onRetry={() => void list.refetch()} />
        ) : !list.data ? (
          <Loading />
        ) : (
          <Table<User> size="small" rowKey="id" columns={columns} dataSource={list.data.items} pagination={false} />
        )}
      </Card>
      <UserFormModal
        open={formOpen}
        editing={editing}
        onClose={() => setFormOpen(false)}
        onDone={(r) => {
          setFormOpen(false)
          if (r) setTemp(r)
        }}
      />
      <TempPasswordModal result={temp} onClose={() => setTemp(null)} />
    </Space>
  )
}
