import {
  CloudUploadOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  AuditOutlined,
  DiffOutlined,
  FilePptOutlined,
  FileSearchOutlined,
  HddOutlined,
  SettingOutlined,
  TeamOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'
import { vi } from './lib/vi'
import Alerts from './pages/Alerts'
import Compare from './pages/Compare'
import Dashboard from './pages/Dashboard'
import Gaps from './pages/Gaps'
import Report from './pages/Report'
import Imports from './pages/Imports'
import Inventory from './pages/Inventory'
import ServerDetail from './pages/ServerDetail'
import SettingsPage from './pages/Settings'
import AuditPage from './pages/Audit'
import Users from './pages/Users'

export interface NavRoute {
  key: string
  path: string
  label: string
  icon: ReactNode
  element: ReactNode
  /** Trang phân tích → hiện bộ lọc toàn cục */
  filters: boolean
}

// Menu: Tổng quan · Cảnh báo · Server · Danh mục server · Nhập dữ liệu · Tài khoản (PLAN §8.0, §8.6).
// Nhập dữ liệu / Tài khoản chỉ hiện cho admin (auth/access.ts; backend cũng chặn).
export const navRoutes: NavRoute[] = [
  { key: 'dashboard', path: '/', label: vi.nav.dashboard, icon: <DashboardOutlined />, element: <Dashboard />, filters: true },
  { key: 'alerts', path: '/alerts', label: vi.nav.alerts, icon: <WarningOutlined />, element: <Alerts />, filters: true },
  { key: 'servers', path: '/servers', label: vi.nav.servers, icon: <HddOutlined />, element: <ServerDetail />, filters: true },
  { key: 'inventory', path: '/inventory', label: vi.nav.inventory, icon: <DatabaseOutlined />, element: <Inventory />,
    filters: true },
  { key: 'compare', path: '/compare', label: vi.nav.compare, icon: <DiffOutlined />, element: <Compare />, filters: true },
  { key: 'report', path: '/report', label: vi.nav.report, icon: <FilePptOutlined />, element: <Report />, filters: false },
  { key: 'gaps', path: '/gaps', label: vi.nav.gaps, icon: <FileSearchOutlined />, element: <Gaps />, filters: true },
  { key: 'imports', path: '/imports', label: vi.nav.imports, icon: <CloudUploadOutlined />, element: <Imports />,
    filters: false },
  { key: 'users', path: '/users', label: vi.nav.users, icon: <TeamOutlined />, element: <Users />, filters: false },
  { key: 'settings', path: '/settings', label: vi.nav.settings, icon: <SettingOutlined />, element: <SettingsPage />,
    filters: false },
  { key: 'audit', path: '/audit', label: vi.nav.audit, icon: <AuditOutlined />, element: <AuditPage />, filters: false },
]

export function activeRoute(pathname: string): NavRoute | undefined {
  return navRoutes.find((r) => (r.path === '/' ? pathname === '/' : pathname.startsWith(r.path)))
}
