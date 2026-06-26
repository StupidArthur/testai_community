import { useState, useMemo, type ReactNode } from 'react'
import {
  Row,
  Col,
  Button,
  Modal,
  Input,
  message,
  Typography,
  Tag,
  Space,
  Empty,
  Select,
  Divider,
} from 'antd'
import {
  PlusOutlined,
  ThunderboltOutlined,
  FilterOutlined,
  LockOutlined,
  UserOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { skillsApi } from '../../shared/api/client'
import { useCurrentUser } from '../../shared/hooks/useAuth'
import SkillCard, { type SkillCardVariant } from '../components/SkillCard'
import type { Skill, SkillCategory } from '../../shared/api/client'

const { Title, Text } = Typography

const EMPTY_FORM = {
  name: '',
  display_name: '',
  definition: '',
  category: '',
  tags: [] as string[],
}

type SkillGroup = {
  key: SkillCardVariant
  title: string
  icon: ReactNode
  hint: string
  items: Skill[]
}

export default function Dashboard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const currentUser = useCurrentUser()
  const currentUserId = currentUser?.id ?? null

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

  const skillGroups = useMemo((): SkillGroup[] => {
    const platform: Skill[] = []
    const mine: Skill[] = []
    const community: Skill[] = []

    for (const s of skills) {
      if (s.platform_locked) {
        platform.push(s)
      } else if (currentUserId !== null && s.standard_owner_id === currentUserId) {
        mine.push(s)
      } else {
        community.push(s)
      }
    }

    return [
      {
        key: 'mine',
        title: '我创建的',
        icon: <UserOutlined />,
        hint: '你拥有 standard 模板维护权；可在个人分支编辑，由 Admin 合并到 master。',
        items: mine,
      },
      {
        key: 'community',
        title: '其他人创建的',
        icon: <TeamOutlined />,
        hint: '可浏览、创建个人分支，并从 standard Fork 到自己的分支后编辑。',
        items: community,
      },
      {
        key: 'platform',
        title: '平台内置',
        icon: <LockOutlined />,
        hint: '系统托管能力；仅 Admin 可编辑 standard，不可 Fork 或创建个人分支。',
        items: platform,
      },
    ]
  }, [skills, currentUserId])

  const visibleGroups = skillGroups.filter((g) => g.items.length > 0)
  const totalCount = skills.length

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

  const renderSection = (group: SkillGroup) => (
    <section key={group.key} style={{ marginBottom: 32 }}>
      <div style={{ marginBottom: 16 }}>
        <Space align="center" size={10} wrap>
          <Title level={4} style={{ margin: 0, color: 'var(--color-text)' }}>
            {group.icon}
            <span style={{ marginLeft: 8 }}>{group.title}</span>
          </Title>
          <Tag style={{ margin: 0 }}>{group.items.length}</Tag>
        </Space>
        <Text type="secondary" style={{ display: 'block', marginTop: 6, fontSize: 13 }}>
          {group.hint}
        </Text>
      </div>
      <Row gutter={[16, 16]} align="stretch">
        {group.items.map((s) => (
          <Col xs={24} sm={12} lg={8} xl={6} key={s.id} style={{ display: 'flex' }}>
            <div style={{ width: '100%' }}>
              <SkillCard
                skill={s}
                variant={group.key}
                onClick={() => navigate(`/skill/${s.id}`)}
              />
            </div>
          </Col>
        ))}
      </Row>
    </section>
  )

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
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
          <Text type="secondary">
            TestAI Community 资产中心 · 共 {totalCount} 个 Skill
            {filterCategory ? `（已筛选分类）` : ''}
          </Text>
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

      {isLoading ? null : totalCount === 0 ? (
        <Empty description={filterCategory ? '该分类下暂无 Skill' : '暂无 Skill 仓库'} />
      ) : (
        <>
          {visibleGroups.map((group, idx) => (
            <div key={group.key}>
              {idx > 0 && <Divider style={{ margin: '8px 0 28px' }} />}
              {renderSection(group)}
            </div>
          ))}
        </>
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
