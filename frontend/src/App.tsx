import { Alert, Divider, Grid, Layout, Menu, Result, Space, Typography } from 'antd'
import { Link, Route, Routes, useLocation } from 'react-router'
import { canAccess, isOwnScope } from './auth/access'
import { useAuth } from './auth/session'
import ChangePassword from './auth/ChangePassword'
import { UserMenu } from './auth/UserMenu'
import { ApiStatus } from './components/ApiStatus'
import { BrandBlock, ViettelLogo } from './components/Brand'
import { FilterBar } from './components/FilterBar'
import { HEADER_H, SIDER_W } from './lib/theme'
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
  const screens = Grid.useBreakpoint() // màn hẹp: thu khối tên, ẩn dòng phụ (không tràn ngang)
  const items = navRoutes.filter((r) => canAccess(r.key, me.role)).map((r) => ({
    key: r.key,
    icon: r.icon,
    label: <Link to={`${r.path}${r.filters ? keep : ''}`}>{r.label}</Link>,
  }))

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* Phong cách Viettel (ảnh tham khảo VOffice): tên đỏ cắt chéo góc trái, logo, header trắng; sidebar tối bên dưới */}
      <Layout.Header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          paddingRight: 20,
          borderBottom: '1px solid #d9d9d9',
          position: 'sticky',
          top: 0,
          zIndex: 10,
          lineHeight: 'normal',
        }}
      >
        <BrandBlock width={screens.md ? SIDER_W + 30 : 160} />
        {screens.sm && <ViettelLogo height={22} />}
        {screens.lg && (
          <>
            <Divider type="vertical" style={{ height: 22, margin: '0 2px' }} />
            <Typography.Text type="secondary" style={{ fontSize: 13, whiteSpace: 'nowrap' }}>
              {vi.tagline}
            </Typography.Text>
          </>
        )}
        <div style={{ flex: 1 }} />
        {screens.md && <ApiStatus />}
        <UserMenu />
      </Layout.Header>
      <Layout>
        {/* Sidebar cố định dưới header khi cuộn trang; menu dài hơn màn hình thì tự cuộn bên trong
            (cuộn ở div con để không cắt nút mở sidebar của màn hẹp nằm ngoài mép Sider) */}
        <Layout.Sider
          width={SIDER_W}
          breakpoint="lg"
          collapsedWidth={0}
          style={{ position: 'sticky', top: HEADER_H, height: `calc(100vh - ${HEADER_H}px)`, zIndex: 9 }}
        >
          <div style={{ height: '100%', overflowY: 'auto' }}>
            <Menu
              theme="dark"
              mode="inline"
              selectedKeys={active ? [active.key] : []}
              items={items}
              style={{ textTransform: 'uppercase', fontWeight: 600, fontSize: 13, borderInlineEnd: 0, paddingTop: 4 }}
            />
          </div>
        </Layout.Sider>
        <Layout.Content style={{ padding: 20 }}>
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
