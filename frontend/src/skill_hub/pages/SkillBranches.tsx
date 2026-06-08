import { useMemo } from 'react'
import {
  Card,
  Row,
  Col,
  message,
  Typography,
  Tag,
  Avatar,
  Space,
  Button,
} from 'antd'
import {
  ApartmentOutlined,
  ArrowLeftOutlined,
  CrownOutlined,
  ProfileOutlined,
  UserOutlined,
  PlusOutlined,
  HomeOutlined,
  BranchesOutlined,
} from '@ant-design/icons'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { skillsApi } from '../../shared/api/client'
import type { Skill, Branch } from '../../shared/api/client'

const { Title, Text } = Typography

const TYPE_PIN: Record<string, number> = { master: 0, standard: 1, personal: 2 }

export default function SkillBranches() {
  const { skillId } = useParams<{ skillId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: skill } = useQuery({
    queryKey: ['skill', skillId],
    queryFn: () => skillsApi.get(skillId!).then((r) => r.data),
    enabled: !!skillId,
  })

  const { data: branches = [], isLoading } = useQuery<Branch[]>({
    queryKey: ['branches', skillId],
    queryFn: () => skillsApi.listBranches(skillId!).then((r) => r.data),
    enabled: !!skillId,
  })

  const createBranchMutation = useMutation({
    mutationFn: () => skillsApi.createBranch(skillId!),
    onSuccess: () => {
      message.success('个人分支创建成功')
      queryClient.invalidateQueries({ queryKey: ['branches', skillId] })
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || '创建失败')
    },
  })

  const currentUserId = useMemo(() => {
    try {
      return JSON.parse(localStorage.getItem('user') || '{}').id || null
    } catch {
      return null
    }
  }, [])

  const hasMyPersonalBranch = useMemo(
    () => currentUserId !== null && branches.some((b: Branch) => b.user_id === currentUserId && b.branch_type === 'personal'),
    [branches, currentUserId]
  )

  const sortedBranches = useMemo(() => {
    return [...branches]
      .map((b: Branch, idx: number) => ({ b, idx }))
      .sort((a, b) => {
        const ra = TYPE_PIN[a.b.branch_type] ?? 99
        const rb = TYPE_PIN[b.b.branch_type] ?? 99
        if (ra !== rb) return ra - rb
        if (currentUserId) {
          if (a.b.user_id === currentUserId) return -1
          if (b.b.user_id === currentUserId) return 1
        }
        return a.idx - b.idx
      })
      .map((x) => x.b)
  }, [branches, currentUserId])

  const myPersonalBranchId = useMemo(() => {
    if (currentUserId === null) return null
    const found = branches.find(
      (b: Branch) => b.user_id === currentUserId && b.branch_type === 'personal'
    )
    return found?.id || null
  }, [branches, currentUserId])

  const renderCard = (b: Branch) => {
    const isMaster = b.branch_type === 'master'
    const isStandard = b.branch_type === 'standard'
    const isMine = currentUserId !== null && b.user_id === currentUserId && b.branch_type === 'personal'

    let borderColor = 'var(--color-border)'
    let bg = 'var(--color-bg)'
    let avatarBg = '#e4e4e7'
    let AvatarIcon = <UserOutlined />
    let tagNode = (
      <Tag style={{ margin: 0 }}>Personal</Tag>
    )

    if (isMaster) {
      borderColor = 'var(--color-primary)'
      bg = 'rgba(0,112,243,0.04)'
      avatarBg = 'var(--color-primary)'
      AvatarIcon = <CrownOutlined />
      tagNode = (
        <Tag color="green" style={{ margin: 0 }}>
          <CrownOutlined /> Master（主干）
        </Tag>
      )
    } else if (isStandard) {
      borderColor = '#1890ff'
      bg = 'rgba(24,144,255,0.04)'
      avatarBg = '#1890ff'
      AvatarIcon = <ProfileOutlined />
      tagNode = (
        <Tag color="blue" style={{ margin: 0 }}>
          <ProfileOutlined /> Standard（标准模板）
        </Tag>
      )
    } else if (isMine) {
      borderColor = '#a855f7'
      bg = 'rgba(168,85,247,0.04)'
      avatarBg = '#a855f7'
      AvatarIcon = <HomeOutlined />
      tagNode = (
        <Tag color="purple" style={{ margin: 0 }}>
          <HomeOutlined /> 我的分支
        </Tag>
      )
    }

    return (
      <Col xs={24} sm={12} md={8} lg={6} key={b.id}>
        <Card
          hoverable
          onClick={() => navigate(`/skill/${skillId}/branch/${b.id}`)}
          style={{ border: `1px solid ${borderColor}`, background: bg }}
        >
          <Space size="middle" align="start">
            <Avatar size={48} icon={AvatarIcon} style={{ backgroundColor: avatarBg, color: '#fff' }} />
            <div>
              <Title level={5} style={{ color: 'var(--color-text)', margin: 0 }}>
                {b.username}
              </Title>
              <Space size={4} style={{ marginTop: 4 }}>
                {tagNode}
              </Space>
            </div>
          </Space>
        </Card>
      </Col>
    )
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
          <Space size="small" style={{ marginBottom: 4 }}>
            <Button
              type="text"
              size="small"
              icon={<ArrowLeftOutlined />}
              onClick={() => navigate('/')}
              style={{ color: 'var(--color-text-secondary)', padding: 0 }}
            >
              返回仓库列表
            </Button>
          </Space>
          <Title level={3} style={{ color: 'var(--color-text)', margin: 0 }}>
            <ApartmentOutlined style={{ color: 'var(--color-primary)', marginRight: 8 }} />
            {skill?.display_name || 'Skill'} · Branches
          </Title>
          <Text type="secondary">
            <BranchesOutlined /> {skill?.name}（id: {skillId?.slice(0, 8)}…）
            {skill?.definition && <span> · {skill.definition}</span>}
          </Text>
        </div>

        {!hasMyPersonalBranch && currentUserId && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => createBranchMutation.mutate()}
            loading={createBranchMutation.isPending}
          >
            创建个人分支
          </Button>
        )}
        {hasMyPersonalBranch && myPersonalBranchId && (
          <Button
            icon={<HomeOutlined />}
            onClick={() => navigate(`/skill/${skillId}/branch/${myPersonalBranchId}`)}
            style={{ borderColor: '#a855f7', color: '#a855f7' }}
          >
            进入我的分支
          </Button>
        )}
      </div>

      {isLoading ? null : sortedBranches.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--color-text-secondary)' }}>
          该 Skill 暂无 Branch
        </div>
      ) : (
        <Row gutter={[16, 16]}>{sortedBranches.map(renderCard)}</Row>
      )}
    </div>
  )
}
