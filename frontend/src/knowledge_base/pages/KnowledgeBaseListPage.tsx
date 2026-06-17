import { useState } from 'react'
import {
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  Modal,
  Row,
  Space,
  Typography,
  message,
  Popconfirm,
} from 'antd'
import {
  BookOutlined,
  DeleteOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { knowledgeBaseApi, type KnowledgeBase } from '../../shared/api/knowledge-base'
import { useCurrentUser, isAdmin } from '../../shared/hooks/useAuth'

const { Title, Text, Paragraph } = Typography

export default function KnowledgeBaseListPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const currentUser = useCurrentUser()
  const [createOpen, setCreateOpen] = useState(false)
  const [form] = Form.useForm()

  const { data: bases = [], isLoading } = useQuery({
    queryKey: ['knowledge-bases'],
    queryFn: () => knowledgeBaseApi.listBases().then((r) => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (values: { name: string; description?: string }) =>
      knowledgeBaseApi.createBase(values).then((r) => r.data),
    onSuccess: (kb) => {
      message.success('知识库创建成功')
      setCreateOpen(false)
      form.resetFields()
      queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
      navigate(`/knowledge-base/${kb.id}`)
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || '创建失败')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (kbId: string) => knowledgeBaseApi.deleteBase(kbId),
    onSuccess: () => {
      message.success('已删除')
      queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || '删除失败')
    },
  })

  const renderCard = (kb: KnowledgeBase) => {
    const showDelete = kb.can_manage || (currentUser && isAdmin(currentUser))
    return (
    <Col xs={24} sm={12} lg={8} key={kb.id}>
      <Card
        hoverable
        onClick={() => navigate(`/knowledge-base/${kb.id}`)}
        actions={
          showDelete
            ? [
                <Popconfirm
                  key="delete"
                  title="确定删除该知识库？"
                  description="将删除所有文档与向量数据"
                  onConfirm={(e) => {
                    e?.stopPropagation()
                    deleteMutation.mutate(kb.id)
                  }}
                  onCancel={(e) => e?.stopPropagation()}
                >
                  <Button
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={(e) => e.stopPropagation()}
                  >
                    删除
                  </Button>
                </Popconfirm>,
              ]
            : undefined
        }
      >
        <Space align="start">
          <BookOutlined style={{ fontSize: 28, color: 'var(--color-primary)' }} />
          <div>
            <Title level={5} style={{ margin: 0 }}>
              {kb.name}
            </Title>
            <Text type="secondary" style={{ fontSize: 12 }}>
              创建者：{kb.username || '—'} · {kb.ready_document_count}/{kb.document_count} 文档可用
            </Text>
            {kb.description && (
              <Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ marginTop: 8, marginBottom: 0 }}>
                {kb.description}
              </Paragraph>
            )}
          </div>
        </Space>
      </Card>
    </Col>
    )
  }

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>
            <BookOutlined style={{ marginRight: 8 }} />
            知识库
          </Title>
          <Text type="secondary">全站共享知识库 · 人人可上传 · 本地 bge-m3 向量化 + RAG 问答</Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          新建知识库
        </Button>
      </div>

      {isLoading ? null : bases.length === 0 ? (
        <Empty description="暂无知识库">
          <Button type="primary" onClick={() => setCreateOpen(true)}>
            创建第一个知识库
          </Button>
        </Empty>
      ) : (
        <Row gutter={[16, 16]}>{bases.map(renderCard)}</Row>
      )}

      <Modal
        title="新建知识库"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        okText="创建"
        confirmLoading={createMutation.isPending}
        okButtonProps={{ htmlType: 'button' }}
        onOk={() => {
          form
            .validateFields()
            .then((values) => createMutation.mutate(values))
            .catch(() => {})
        }}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => createMutation.mutate(values)}
        >
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如：测试规范库" maxLength={120} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="可选" maxLength={500} />
          </Form.Item>
        </Form>
      </Modal>

      <Text type="secondary" style={{ display: 'block', textAlign: 'right', marginTop: 24, fontSize: 12 }}>
        designed by @yuzechao
      </Text>
    </div>
  )
}
