import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Form, Input, Typography } from 'antd'
import { Link, useNavigate } from 'react-router-dom'

import { loginUser, type LoginPayload } from '../api/auth'
import { currentUserQueryKey } from '../routes/authState'

export function LoginPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const loginMutation = useMutation({
    mutationFn: loginUser,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: currentUserQueryKey })
      navigate('/', { replace: true })
    },
  })

  return (
    <main className="auth-page">
      <section className="auth-panel">
        <Typography.Title level={1}>登录</Typography.Title>
        <Form<LoginPayload>
          layout="vertical"
          requiredMark={false}
          onFinish={(values) => loginMutation.mutate(values)}
        >
          <Form.Item
            label="账号或邮箱"
            name="login"
            rules={[{ required: true, message: '请输入账号或邮箱' }]}
          >
            <Input autoComplete="username" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password autoComplete="current-password" />
          </Form.Item>

          {loginMutation.isError ? (
            <Alert
              showIcon
              type="error"
              message="账号或密码不正确"
              className="auth-alert"
            />
          ) : null}

          <Button
            block
            type="primary"
            htmlType="submit"
            aria-label="登录"
            loading={loginMutation.isPending}
          >
            登录
          </Button>
        </Form>
        <div className="auth-switch">
          <span>没有账号</span>
          <Link to="/register">注册</Link>
        </div>
      </section>
    </main>
  )
}
