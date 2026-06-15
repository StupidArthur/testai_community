import { useState, useMemo } from 'react'
import { Card, Row, Col, Button, Modal, Input, message, Typography, Tag, Space, Empty, Select } from 'antd'
import { PlusOutlined, ThunderboltOutlined, CodeOutlined, BookOutlined, FilterOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { skillsApi } from '../../shared/api/client'
import type { Skill, SkillCategory } from '../../shared/api/client'

const { Title, Text } = Typography

const EMPTY_FORM = {
  name: '',
  display_name: '',
  definition: '',
  category: '',
  tags: [] as string[],
}

export default function Dashboard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [modalOpen, setModalOpen] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [filterCategory, setFilterCategory] = useState<string | undefined>(undefined)
  const [tagSearch, setTagSearch] = useState('')

  const { data: categories = [] } = useQuery({
    queryKey: ['skill-categories'],
    queryFn: () => skillsApi.listCategories().then((r) => r.data),
  })

  const { data: skills = [], isLoading } = useQuery({
    queryKey: ['skills', filterCategory ?? 'all'],
    queryFn: () => skillsApi.list(filterCategory || undefined).then((r) => r.data),
  })

  const { data: tagOptions = [] } = useQuery({
    queryKey: ['tag-suggestions', tagSearch],
    queryFn: () => skillsApi.tagSuggestions(tagSearch || undefined).then((r) => r.data.tags),
    enabled: modalOpen,
  })

  const createMutation = useMutation({
    mutationFn: (data: typeof EMPTY_FORM) =>
      skillsApi.create({
        name: data.name,
        display_name: data.display_name,
        definition: data.definition,
        category: data.category,
        tags: data.tags,
      }),
    onSuccess: () => {
      message.success('Skill 创建成功')
      setModalOpen(false)
      setForm(EMPTY_FORM)
      queryClient.invalidateQueries({ queryKey: ['skills'] })
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || '创建失败')
    },
  })

  const categoryOptions = useMemo(
    () => categories.map((c: SkillCategory) => ({ value: c.id, label: c.label })),
    [categories],
  )

  const handleCreate = async () => {
    if (!form.name.trim() || !form.display_name.trim()) {
      message.warning('请填写 name 和 display_name')
      return
    }
    if (!form.category) {
      message.warning('请选择分类 category')
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
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <div>
          <Title level={3} style={{ color: 'var(--color-text)', margin: 0 }}>
            <ThunderboltOutlined style={{ color: 'var(--color-primary)', marginRight: 8 }} />
            Skill 仓库
          </Title>
          <Text type="secondary">TestAI Community 资产中心 · 按分类浏览与创建</Text>
        </div>
        <Space wrap>
          <Select
            allowClear
            placeholder="按分类筛选"
            style={{ minWidth: 180 }}
            value={filterCategory}
            onChange={(v) => setFilterCategory(v)}
            options={categoryOptions}
            suffixIcon={<FilterOutlined />}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            新建 Skill 仓库
          </Button>
        </Space>
      </div>

      {isLoading ? null : skills.length === 0 ? (
        <Empty description={filterCategory ? '该分类下暂无 Skill' : '暂无 Skill 仓库'} />
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
                  <Space size={[4, 4]} wrap>
                    <Tag color="blue">{s.category_label || s.category}</Tag>
                    {(s.tags || []).map((t) => (
                      <Tag key={t}>{t}</Tag>
                    ))}
                  </Space>
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
          创建后你将拥有 standard 分支维护模板；master 仅 Admin 可写。请选择分类便于团队浏览。
        </Text>
        <div style={{ marginBottom: 12 }}>
          <Text strong style={{ display: 'block', marginBottom: 4 }}>
            分类 category <span style={{ color: '#ff4d4f' }}>*</span>
          </Text>
          <Select
            style={{ width: '100%' }}
            placeholder="选择 Skill 所属分类"
            value={form.category || undefined}
            onChange={(v) => setForm((f) => ({ ...f, category: v }))}
            options={categoryOptions}
          />
        </div>
        <div style={{ marginBottom: 12 }}>
          <Text strong style={{ display: 'block', marginBottom: 4 }}>
            标签 tags（可选）
          </Text>
          <Select
            mode="tags"
            style={{ width: '100%' }}
            placeholder="输入后回车；可从历史标签中选择"
            value={form.tags}
            onChange={(tags) => setForm((f) => ({ ...f, tags }))}
            onSearch={setTagSearch}
            filterOption={false}
            options={tagOptions.map((t) => ({ value: t, label: t }))}
            tokenSeparators={[',', '，']}
          />
        </div>
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
