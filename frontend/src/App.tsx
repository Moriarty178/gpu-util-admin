import { Alert, Layout, Menu, Result, Space, Typography } from 'antd'
import { Link, Route, Routes, useLocation } from 'react-router'
import { canAccess, isOwnScope } from './auth/access'
import { useAuth } from './auth/session'
import ChangePassword from './auth/ChangePassword'
import { UserMenu } from './auth/UserMenu'
import { ApiStatus } from './components/ApiStatus'
import { FilterBar } from './components/FilterBar'
import { NAVY_DARK } from './lib/theme'
import { vi } from './lib/vi'
import NotFound from './pages/NotFound'
import ServerDetail from './pages/ServerDetail'
import { activeRoute, navRoutes } from './routes'
import { globalSearch } from './store/filters'

function Forbidden() {
  return <Result status="403" title={vi.auth.forbiddenTitle} subTitle={vi.auth.forbidden} />
}

export default function App() {
  const me = useAuth()
  const { pathname, search } = useLocation()
  const keep = globalSearch(new URLSearchParams(search)) // giữ bộ lọc toàn cục khi chuyển trang
  const active = activeRoute(pathname)
  const items = navRoutes.filter((r) => canAccess(r.key, me.role)).map((r) => ({
    key: r.key,
    icon: r.icon,
    label: <Link to={`${r.path}${r.filters ? keep : ''}`}>{r.label}</Link>,
  }))

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Layout.Sider width={220} breakpoint="lg" collapsedWidth={0}>
        <div style={{ padding: '16px 20px', background: NAVY_DARK }}>
          <Typography.Text strong style={{ color: '#fff', fontSize: 16, display: 'block' }}>
            {vi.appName}
          </Typography.Text>
          <Typography.Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 12 }}>{vi.appUnit}</Typography.Text>
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={active ? [active.key] : []} items={items} />
      </Layout.Sider>
      <Layout>
        <Layout.Header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            gap: 12,
            padding: '0 24px',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <ApiStatus />
          <UserMenu />
        </Layout.Header>
        <Layout.Content style={{ padding: 24 }}>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {isOwnScope(me) && active?.filters && (
              <Alert
                type="info"
                showIcon
                message={vi.auth.ownScope(me.owner_key ?? '')}
                description={vi.auth.ownScopeHint}
              />
            )}
            {active?.filters && <FilterBar />}
            <Routes>
              {navRoutes.map((r) => (
                <Route key={r.key} path={r.path} element={canAccess(r.key, me.role) ? r.element : <Forbidden />} />
              ))}
              <Route path="/servers/:ip" element={<ServerDetail />} />
              <Route path="/account/password" element={<ChangePassword />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Space>
        </Layout.Content>
      </Layout>
    </Layout>
  )
}
