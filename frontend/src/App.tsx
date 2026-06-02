import {
  CalendarOutlined,
  CheckCircleOutlined,
  CodeOutlined,
  DatabaseOutlined,
  DownloadOutlined,
  FileSearchOutlined,
  FundProjectionScreenOutlined,
  KeyOutlined,
  ProfileOutlined,
} from '@ant-design/icons'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { Layout, Space, Tag, Typography } from 'antd'
import { type ReactNode, useMemo } from 'react'
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'

import { getBackendHealth } from './api/health'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { AppRoutes } from './routes/AppRoutes'
import { ProtectedRoute } from './routes/ProtectedRoute'
import './styles/app.css'

const { Header, Sider, Content } = Layout

const navItems = [
  { to: '/problems', label: '题库', icon: <DatabaseOutlined aria-hidden="true" /> },
  { to: '/study-plan', label: '学习计划', icon: <CalendarOutlined aria-hidden="true" /> },
  { to: '/dashboard', label: '仪表盘', icon: <FundProjectionScreenOutlined aria-hidden="true" /> },
  { to: '/workspace', label: '工作台', icon: <CodeOutlined aria-hidden="true" /> },
  { to: '/settings/api-keys', label: 'API 设置', icon: <KeyOutlined aria-hidden="true" /> },
  { to: '/settings/backup-restore', label: '备份恢复', icon: <DownloadOutlined aria-hidden="true" /> },
  { to: '/review', label: '复盘', icon: <ProfileOutlined aria-hidden="true" /> },
  { to: '/trace', label: 'Trace', icon: <FileSearchOutlined aria-hidden="true" /> },
]

function BackendHealthBadge() {
  const { data, isError, isLoading } = useQuery({
    queryKey: ['backend-health'],
    queryFn: getBackendHealth,
    retry: false,
  })

  if (isLoading) {
    return <Tag color="processing">API 检查中</Tag>
  }

  if (isError || data?.status !== 'ok') {
    return <Tag color="error">API 异常</Tag>
  }

  return (
    <Tag color="success" icon={<CheckCircleOutlined />}>
      API 正常
    </Tag>
  )
}

function AppShell({ children }: { children: ReactNode }) {
  return (
    <Layout className="app-shell">
      <Sider className="app-sider" width={232}>
        <div className="brand-block">
          <Typography.Title level={1}>Agentic Coding Learning Coach</Typography.Title>
          <span className="environment-label">local</span>
        </div>

        <nav className="side-nav" aria-label="主导航">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                isActive ? 'side-nav-link side-nav-link-active' : 'side-nav-link'
              }
            >
              <span className="side-nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </Sider>

      <Layout>
        <Header className="app-header">
          <Space className="header-content">
            <span className="header-title">训练控制台</span>
            <BackendHealthBadge />
          </Space>
        </Header>
        <Content className="app-content">
          <ProtectedRoute>{children}</ProtectedRoute>
        </Content>
      </Layout>
    </Layout>
  )
}

function AppFrame() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        path="/*"
        element={
          <AppShell>
            <AppRoutes />
          </AppShell>
        }
      />
    </Routes>
  )
}

function App() {
  const queryClient = useMemo(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
          },
        },
      }),
    [],
  )

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppFrame />
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
