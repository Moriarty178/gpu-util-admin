import { DownOutlined, KeyOutlined, LogoutOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Dropdown, Space, Tag } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { INFO } from '../lib/theme'
import { vi } from '../lib/vi'
import { displayName } from './access'
import { logout, useAuth } from './session'

/** Góc phải header: tên + vai trò, menu Đổi mật khẩu / Đăng xuất. */
export function UserMenu() {
  const me = useAuth()
  const qc = useQueryClient()
  const navigate = useNavigate()
  return (
    <Dropdown
      trigger={['click']}
      menu={{
        items: [
          { key: 'pw', icon: <KeyOutlined />, label: vi.auth.changeTitle, onClick: () => navigate('/account/password') },
          { type: 'divider' },
          { key: 'logout', icon: <LogoutOutlined />, label: vi.auth.logout, onClick: () => void logout(qc) },
        ],
      }}
    >
      <Button type="text">
        <Space size={6}>
          <UserOutlined />
          {displayName(me)}
          <Tag color={me.role === 'admin' ? INFO : me.role === 'owner' ? 'cyan' : 'default'} style={{ margin: 0 }}>
            {vi.role[me.role]}
            {me.role === 'owner' && me.owner_key ? ` · ${me.owner_key}` : ''}
          </Tag>
          <DownOutlined style={{ fontSize: 10 }} />
        </Space>
      </Button>
    </Dropdown>
  )
}
