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
  Space,
} from 'antd'
import { UserAddOutlined, SettingOutlined, KeyOutlined, DeleteOutlined, TranslationOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { usersApi, authApi } from '../../shared/api/client'
import { listJobs, deleteJobRecord } from '../../shared/api/translate-jobs'
import type { User } from '../../shared/api/client'
import type { JobView } from '../../shared/api/translate-jobs'

const { Title, Text } = Typography

export default function AdminPage() {
  const queryClient = useQueryClient()
  const currentUser = JSON.parse(localStorage.getItem('user') || '{}')
  const [registerModalOpen, setRegisterModalOpen] = useState(false)
  const [resetModalOpen, setResetModalOpen] = useState(false)
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [deleteJobModalOpen, setDeleteJobModalOpen] = useState(false)
  const [selectedUser, setSelectedUser] = useState<User | null>(null)
  const [selectedJob, setSelectedJob] = useState<JobView | null>(null)
  const [registerForm] = Form.useForm()
  const [resetForm] = Form.useForm()

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then((r) => r.data),
  })

  const registerMutation = useMutation({
    mutationFn: (data: { username: string; password?: string; role?: string }) =>
      authApi.register(data),
    onSuccess: (_, values) => {
      message.success(`用户 ${values.username} 添加成功`)
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

  const deleteMutation = useMutation({
    mutationFn: (userId: number) => usersApi.delete(userId),
    onSuccess: () => {
      message.success(`用户 ${selectedUser?.username} 已删除`)
      setSelectedUser(null)
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || '删除失败')
    },
  })

  const { data: translateJobs = [] } = useQuery({
    queryKey: ['admin-translate-jobs'],
    queryFn: listJobs,
  })

  const deleteJobMutation = useMutation({
    mutationFn: (jobId: string) => deleteJobRecord(jobId),
    onSuccess: () => {
      message.success('翻译记录已删除')
      setDeleteJobModalOpen(false)
      setSelectedJob(null)
      queryClient.invalidateQueries({ queryKey: ['admin-translate-jobs'] })
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || '删除失败')
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
      width: 180,
      render: (_: any, record: User) => (
        <div style={{ display: 'flex', gap: 4 }}>
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
          {record.id !== currentUser?.id && (
            <Button
              type="link"
              danger
              icon={<DeleteOutlined />}
              onClick={() => {
                setSelectedUser(record)
                setDeleteModalOpen(true)
              }}
            >
              删除
            </Button>
          )}
        </div>
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
          添加用户
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

      <Card
        title={
          <Text strong style={{ color: 'var(--color-text)' }}>
            <TranslationOutlined style={{ marginRight: 8 }} />
            翻译记录（共 {translateJobs.length} 条）
          </Text>
        }
        style={{ border: '1px solid var(--color-border)', marginTop: 24 }}
      >
        <Table
          dataSource={translateJobs}
          columns={[
            { title: '任务名称', dataIndex: 'name', key: 'name', ellipsis: true },
            { title: '用户', dataIndex: 'username', key: 'username', width: 120 },
            {
              title: '状态',
              dataIndex: 'status',
              key: 'status',
              width: 100,
              render: (s: string) => {
                const map: Record<string, { color: string; label: string }> = {
                  queued: { color: 'default', label: '排队中' },
                  running: { color: 'processing', label: '运行中' },
                  completed: { color: 'success', label: '已完成' },
                  failed: { color: 'error', label: '失败' },
                  cancelled: { color: 'warning', label: '已取消' },
                }
                const item = map[s] || { color: 'default', label: s }
                return <Tag color={item.color}>{item.label}</Tag>
              },
            },
            {
              title: '创建时间',
              dataIndex: 'created_at',
              key: 'created_at',
              width: 160,
              render: (v: string) =>
                new Date(v).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }),
            },
            {
              title: '操作',
              key: 'actions',
              width: 80,
              render: (_: any, record: JobView) => (
                <Button
                  type="link"
                  danger
                  icon={<DeleteOutlined />}
                  disabled={record.status === 'queued' || record.status === 'running'}
                  onClick={() => {
                    setSelectedJob(record)
                    setDeleteJobModalOpen(true)
                  }}
                >
                  删除
                </Button>
              ),
            },
          ]}
          rowKey="job_id"
          pagination={{ defaultPageSize: 10, pageSizeOptions: [10, 20, 50], showSizeChanger: true }}
          locale={{ emptyText: '暂无翻译记录' }}
        />
      </Card>

      <Modal
        title="添加用户"
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
              添加
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

      <Modal
        title="确认删除用户"
        open={deleteModalOpen}
        onCancel={() => {
          setDeleteModalOpen(false)
          setSelectedUser(null)
        }}
        onOk={() => {
          const user = selectedUser
          setDeleteModalOpen(false)
          setSelectedUser(null)
          if (user) {
            deleteMutation.mutate(user.id)
          }
        }}
        okText="确认删除"
        okType="danger"
        cancelText="取消"
        confirmLoading={deleteMutation.isPending}
        destroyOnClose
      >
        <p>确定要删除用户「<strong>{selectedUser?.username}</strong>」吗？此操作不可撤销。</p>
      </Modal>

      <Modal
        title="确认删除翻译记录"
        open={deleteJobModalOpen}
        onCancel={() => {
          setDeleteJobModalOpen(false)
          setSelectedJob(null)
        }}
        onOk={() => {
          const job = selectedJob
          setDeleteJobModalOpen(false)
          setSelectedJob(null)
          if (job) {
            deleteJobMutation.mutate(job.job_id)
          }
        }}
        okText="确认删除"
        okType="danger"
        cancelText="取消"
        confirmLoading={deleteJobMutation.isPending}
        destroyOnClose
      >
        <p>确定要删除翻译记录「<strong>{selectedJob?.name}</strong>」吗？仅删除数据库记录，磁盘数据保留。此操作不可撤销。</p>
      </Modal>
    </div>
  )
}
