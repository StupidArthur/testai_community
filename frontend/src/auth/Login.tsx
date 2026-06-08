import { useState } from 'react'
import { Form, Input, Button, Card, message, Typography } from 'antd'
import { UserOutlined, LockOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../shared/api/client'

const { Title, Text } = Typography

export default function Login() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      const res = await authApi.login(values)
      localStorage.setItem('token', res.data.access_token)
      localStorage.setItem('user', JSON.stringify(res.data.user))
      message.success('登录成功')
      navigate('/')
    } catch (err: any) {
      message.error(err.response?.data?.detail || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        background: 'linear-gradient(135deg, var(--color-bg-secondary) 0%, #e4e4f7 100%)',
      }}
    >
      <Card
        style={{
          width: 420,
          background: 'rgba(255,255,255,0.95)',
          border: '1px solid var(--color-border)',
          boxShadow: '0 0 40px rgba(0,112,243,0.08)',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <ThunderboltOutlined style={{ fontSize: 48, color: 'var(--color-primary)' }} />
          <Title level={2} style={{ color: 'var(--color-text)', marginTop: 12, marginBottom: 4 }}>
            TestAI Community
          </Title>
          <Text type="secondary">TestAI Community 智能平台</Text>
        </div>

        <Form onFinish={onFinish} layout="vertical">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" size="large" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" size="large" />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              block
              size="large"
              loading={loading}
            >
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
