import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Form, Input, Typography } from 'antd'
import { Link, useNavigate } from 'react-router-dom'

import { registerUser, type RegisterPayload } from '../api/auth'
import { currentUserQueryKey } from '../routes/authState'

export function RegisterPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const registerMutation = useMutation({
    mutationFn: registerUser,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: currentUserQueryKey })
      navigate('/settings/api-keys', { replace: true })
    },
  })

  return (
    <main className="auth-page">
      <section className="auth-panel">
        <Typography.Title level={1}>注册</Typography.Title>
        <Form<RegisterPayload>
          layout="vertical"
          requiredMark={false}
          onFinish={(values) => registerMutation.mutate(values)}
        >
          <Form.Item
            label="用户名"
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input autoComplete="username" />
          </Form.Item>
          <Form.Item
            label="邮箱"
            name="email"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '请输入有效邮箱' },
            ]}
          >
            <Input autoComplete="email" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, min: 8, message: '请输入至少 8 位密码' }]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>

          {registerMutation.isError ? (
            <Alert
              showIcon
              type="error"
              message="注册失败，请更换用户名或邮箱"
              className="auth-alert"
            />
          ) : null}

          <Button
            block
            type="primary"
            htmlType="submit"
            aria-label="注册"
            loading={registerMutation.isPending}
          >
            注册
          </Button>
        </Form>
        <div className="auth-switch">
          <span>已有账号</span>
          <Link to="/login">登录</Link>
        </div>
      </section>
    </main>
  )
}
