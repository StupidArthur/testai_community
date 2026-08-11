import { useState } from 'react'
import { Button, Form, Input, Modal, Space, Table, Tag, Typography, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { dataCleaningApi } from '../../shared/api/data-cleaning'
import { useCurrentUser, isAdmin } from '../../shared/hooks/useAuth'

const { Title, Text } = Typography

export default function AnchorDictPage() {
  const navigate = useNavigate()
  const user = useCurrentUser()
  const admin = isAdmin(user)
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()

  const { data: anchors = [], isLoading } = useQuery({
    queryKey: ['dc-anchors'],
    queryFn: () => dataCleaningApi.listAnchors().then((r) => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (values: { id: string; label: string; parent_id?: string; synonyms?: string[]; description?: string }) =>
      dataCleaningApi.createAnchor({
        ...values,
        synonyms: values.synonyms
          ? String(values.synonyms)
              .split(/[,，]/)
              .map((s) => s.trim())
              .filter(Boolean)
          : [],
      }),
    onSuccess: () => {
      message.success('锚点已创建')
      setOpen(false)
      form.resetFields()
      queryClient.invalidateQueries({ queryKey: ['dc-anchors'] })
    },
    onError: (err: any) => message.error(err.response?.data?.detail || '创建失败'),
  })

  if (!admin) {
    return <Text type="secondary">仅 Admin 可管理锚点词典</Text>
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>锚点词典</Title>
          <Text type="secondary">Admin 维护功能树；LLM 提炼时会自动匹配锚点</Text>
        </div>
        <Space>
          <Button onClick={() => navigate('/knowledge-base?tab=clean')}>返回清洗列表</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新建锚点</Button>
        </Space>
      </div>
      <Table
        rowKey="id"
        loading={isLoading}
        dataSource={anchors}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 140 },
          { title: '名称', dataIndex: 'label' },
          { title: '父节点', dataIndex: 'parent_id', width: 120 },
          {
            title: '同义词',
            dataIndex: 'synonyms',
            render: (syns: string[]) => syns.map((s) => <Tag key={s}>{s}</Tag>),
          },
          { title: '启用', dataIndex: 'enabled', width: 80, render: (v: boolean) => (v ? '是' : '否') },
        ]}
      />
      <Modal
        title="新建锚点"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        okText="确定"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="id" label="ID（英文）" rules={[{ required: true }]}>
            <Input placeholder="login_sms" />
          </Form.Item>
          <Form.Item name="label" label="显示名" rules={[{ required: true }]}>
            <Input placeholder="登录-短信验证码" />
          </Form.Item>
          <Form.Item name="parent_id" label="父节点 ID">
            <Input placeholder="login" />
          </Form.Item>
          <Form.Item name="synonyms" label="同义词（逗号分隔）">
            <Input placeholder="短信验证码,SMS OTP" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
