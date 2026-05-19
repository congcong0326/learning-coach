import {
  CheckCircleOutlined,
  CodeOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  ProfileOutlined,
} from '@ant-design/icons'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { Layout, Space, Tag, Typography } from 'antd'
import { useMemo } from 'react'
import { BrowserRouter, NavLink } from 'react-router-dom'

import { getBackendHealth } from './api/health'
import { AppRoutes } from './routes/AppRoutes'
import './styles/app.css'

const { Header, Sider, Content } = Layout

const navItems = [
  { to: '/problems', label: '题库', icon: <DatabaseOutlined aria-hidden="true" /> },
  { to: '/workspace', label: '工作台', icon: <CodeOutlined aria-hidden="true" /> },
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

function AppShell() {
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
          <AppRoutes />
        </Content>
      </Layout>
    </Layout>
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
        <AppShell />
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
