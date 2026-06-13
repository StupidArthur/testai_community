import { useState } from 'react'
import { Card, Row, Col, Button, Modal, Input, message, Typography, Tag, Space, Empty } from 'antd'
import { PlusOutlined, ThunderboltOutlined, CodeOutlined, BookOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { skillsApi } from '../../shared/api/client'
import { useCurrentUser, isAdmin as checkAdmin } from '../../shared/hooks/useAuth'
import type { Skill } from '../../shared/api/client'

const { Title, Text } = Typography

export default function Dashboard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [modalOpen, setModalOpen] = useState(false)
  const [form, setForm] = useState({ name: '', display_name: '', definition: '' })

  const { data: skills = [], isLoading } = useQuery({
    queryKey: ['skills'],
    queryFn: () => skillsApi.list().then((r) => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (data: { name: string; display_name: string; definition?: string }) =>
      skillsApi.create(data),
    onSuccess: () => {
      message.success('Skill 创建成功')
      setModalOpen(false)
      setForm({ name: '', display_name: '', definition: '' })
      queryClient.invalidateQueries({ queryKey: ['skills'] })
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || '创建失败')
    },
  })

  const currentUser = useCurrentUser()
  const isAdmin = checkAdmin(currentUser)

  const handleCreate = async () => {
    if (!form.name.trim() || !form.display_name.trim()) {
      message.warning('请填写 name 和 display_name')
      return
    }
    createMutation.mutate(form)
  }

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
            <ThunderboltOutlined style={{ color: 'var(--color-primary)', marginRight: 8 }} />
            Skill 仓库
          </Title>
          <Text type="secondary">TestAI Community 资产中心 · 每个 Skill 是一个独立的 9 维 Agent 仓库</Text>
        </div>
        {isAdmin && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            新建 Skill 仓库
          </Button>
        )}
      </div>

      {isLoading ? null : skills.length === 0 ? (
        <Empty description="暂无 Skill 仓库" />
      ) : (
        <Row gutter={[16, 16]}>
          {skills.map((s: Skill) => (
            <Col xs={24} sm={12} md={8} key={s.id}>
              <Card
                hoverable
                style={{ border: '1px solid var(--color-border)' }}
                onClick={() => navigate(`/skill/${s.id}`)}
              >
                <Space size="middle" align="start">
                  <BookOutlined style={{ fontSize: 32, color: 'var(--color-primary)' }} />
                  <div>
                    <Title level={5} style={{ color: 'var(--color-text)', margin: 0 }}>
                      <CodeOutlined style={{ marginRight: 6 }} />
                      {s.display_name}
                    </Title>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {s.name}
                    </Text>
                    <br />
                    {s.definition && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {s.definition.length > 60 ? s.definition.slice(0, 60) + '…' : s.definition}
                      </Text>
                    )}
                  </div>
                </Space>
                <div style={{ marginTop: 12 }}>
                  <Tag color="cyan">{s.id.slice(0, 8)}</Tag>
                </div>
              </Card>
            </Col>
          ))}
        </Row>
      )}

      <Modal
        title="新建 Skill 仓库"
        open={modalOpen}
        onOk={handleCreate}
        onCancel={() => setModalOpen(false)}
        confirmLoading={createMutation.isPending}
        okText="创建"
        cancelText="取消"
      >
        <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          系统会自动为你建好 master（主干）和 template（标准模板）两个 Branch，
          template 会预置一个 v0 初始版本。
        </Text>
        <div style={{ marginBottom: 12 }}>
          <Text strong style={{ display: 'block', marginBottom: 4 }}>
            name <span style={{ color: '#ff4d4f' }}>*</span>
            <Tag color="default" style={{ marginLeft: 8 }}>
              英文唯一标识
            </Tag>
          </Text>
          <Input
            placeholder="如 API_Test_Generator"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          />
        </div>
        <div style={{ marginBottom: 12 }}>
          <Text strong style={{ display: 'block', marginBottom: 4 }}>
            display_name <span style={{ color: '#ff4d4f' }}>*</span>
            <Tag color="default" style={{ marginLeft: 8 }}>
              人类可读名
            </Tag>
          </Text>
          <Input
            placeholder="如 API 测试用例生成专家"
            value={form.display_name}
            onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
          />
        </div>
        <div>
          <Text strong style={{ display: 'block', marginBottom: 4 }}>
            definition（详细定义）
          </Text>
          <Input.TextArea
            rows={3}
            placeholder="例：为 QA 团队生成高覆盖率的 API 测试用例…"
            value={form.definition}
            onChange={(e) => setForm((f) => ({ ...f, definition: e.target.value }))}
          />
        </div>
      </Modal>
    </div>
  )
}
