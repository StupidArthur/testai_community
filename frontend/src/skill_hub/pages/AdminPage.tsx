import { useState } from 'react'
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  message,
  Typography,
  Tag,
} from 'antd'
import { UserAddOutlined, SettingOutlined, KeyOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { usersApi, authApi } from '../../shared/api/client'
import type { User } from '../../shared/api/client'

const { Title, Text } = Typography

export default function AdminPage() {
  const queryClient = useQueryClient()
  const [registerModalOpen, setRegisterModalOpen] = useState(false)
  const [resetModalOpen, setResetModalOpen] = useState(false)
  const [selectedUser, setSelectedUser] = useState<User | null>(null)
  const [registerForm] = Form.useForm()
  const [resetForm] = Form.useForm()

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then((r) => r.data),
  })

  const registerMutation = useMutation({
    mutationFn: (data: { username: string; password: string; role?: string }) =>
      authApi.register(data),
    onSuccess: (_, values) => {
      message.success(`用户 ${values.username} 创建成功`)
      registerForm.resetFields()
      setRegisterModalOpen(false)
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || '注册失败')
    },
  })

  const resetMutation = useMutation({
    mutationFn: ({ userId, newPassword }: { userId: number; newPassword: string }) =>
      usersApi.resetPassword(userId, { new_password: newPassword }),
    onSuccess: () => {
      message.success(`用户 ${selectedUser?.username} 密码已重置`)
      setResetModalOpen(false)
      resetForm.resetFields()
      setSelectedUser(null)
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || '重置失败')
    },
  })

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (role: string) => <Tag color={role === 'Admin' ? 'gold' : 'green'}>{role}</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: any, record: User) => (
        <Button
          type="link"
          icon={<KeyOutlined />}
          onClick={() => {
            setSelectedUser(record)
            setResetModalOpen(true)
          }}
          style={{ color: 'var(--color-primary)' }}
        >
          重置密码
        </Button>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 24,
        }}
      >
        <div>
          <Title level={3} style={{ color: 'var(--color-text)', margin: 0 }}>
            <SettingOutlined style={{ color: 'var(--color-primary)', marginRight: 8 }} />
            管理员面板
          </Title>
          <Text type="secondary">用户管理与账户注册</Text>
        </div>
        <Button
          type="primary"
          icon={<UserAddOutlined />}
          onClick={() => setRegisterModalOpen(true)}
        >
          注册新用户
        </Button>
      </div>

      <Card
        title={<Text strong style={{ color: 'var(--color-text)' }}>用户列表（共 {users.length} 人）</Text>}
        style={{ border: '1px solid var(--color-border)' }}
      >
        <Table
          dataSource={users}
          columns={columns}
          rowKey="id"
          pagination={false}
          locale={{ emptyText: '暂无用户' }}
        />
      </Card>

      <Modal
        title="注册新用户"
        open={registerModalOpen}
        onCancel={() => setRegisterModalOpen(false)}
        footer={null}
        destroyOnClose
      >
        <Form
          form={registerForm}
          layout="vertical"
          onFinish={(values) => registerMutation.mutate(values)}
        >
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input placeholder="请输入用户名" size="large" />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password placeholder="请输入密码" size="large" />
          </Form.Item>
          <Form.Item name="role" label="角色" initialValue="Engineer">
            <Select size="large">
              <Select.Option value="Engineer">Engineer</Select.Option>
              <Select.Option value="Admin">Admin</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              block
              size="large"
              loading={registerMutation.isPending}
            >
              注册
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`重置密码 - ${selectedUser?.username || ''}`}
        open={resetModalOpen}
        onCancel={() => {
          setResetModalOpen(false)
          resetForm.resetFields()
        }}
        footer={null}
        destroyOnClose
      >
        <Form
          form={resetForm}
          layout="vertical"
          onFinish={(values) => {
            if (selectedUser) {
              resetMutation.mutate({ userId: selectedUser.id, newPassword: values.new_password })
            }
          }}
        >
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[{ required: true, message: '请输入新密码' }]}
          >
            <Input.Password placeholder="请输入新密码" size="large" />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              block
              size="large"
              loading={resetMutation.isPending}
            >
              确认重置
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
