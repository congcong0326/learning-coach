import {
  CheckCircleOutlined,
  DatabaseOutlined,
  LogoutOutlined,
} from '@ant-design/icons'
import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { Button, Layout, Space, Tag, Typography } from 'antd'
import { type ReactNode, useMemo } from 'react'
import { BrowserRouter, NavLink, Route, Routes, useNavigate } from 'react-router-dom'

import { logoutUser } from './api/auth'
import { getBackendHealth } from './api/health'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { AppRoutes } from './routes/AppRoutes'
import { ProtectedRoute } from './routes/ProtectedRoute'
import { currentUserQueryKey, useCurrentUserQuery } from './routes/authState'
import './styles/app.css'

const { Header, Sider, Content } = Layout

const navItems = [
  { to: '/problems', label: '题库', icon: <DatabaseOutlined aria-hidden="true" /> },
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
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: user } = useCurrentUserQuery()
  const logoutMutation = useMutation({
    mutationFn: logoutUser,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: currentUserQueryKey })
      navigate('/login', { replace: true })
    },
  })

  return (
    <Layout className="app-shell">
      <Sider className="app-sider" width={232}>
        <div className="brand-block">
          <Typography.Title level={1}>Coding Problem Library</Typography.Title>
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
            <span className="header-title">题库控制台</span>
            <Space>
              <BackendHealthBadge />
              {user ? <Tag>{user.display_name}</Tag> : null}
              <Button
                icon={<LogoutOutlined />}
                loading={logoutMutation.isPending}
                onClick={() => logoutMutation.mutate()}
              >
                退出
              </Button>
            </Space>
          </Space>
        </Header>
        <Content className="app-content">{children}</Content>
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
          <ProtectedRoute>
            <AppShell>
              <AppRoutes />
            </AppShell>
          </ProtectedRoute>
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
