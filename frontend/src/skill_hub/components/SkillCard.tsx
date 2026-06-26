import type { ReactNode } from 'react'
import { Card, Typography, Tag, Space } from 'antd'
import {
  BookOutlined,
  CodeOutlined,
  LockOutlined,
  UserOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import type { Skill } from '../../shared/api/client'

const { Title, Text, Paragraph } = Typography

export type SkillCardVariant = 'platform' | 'mine' | 'community'

const VARIANT_STYLE: Record<
  SkillCardVariant,
  { border: string; accent: string; badge: ReactNode }
> = {
  platform: {
    border: '1px solid #faad14',
    accent: '#faad14',
    badge: (
      <Tag color="gold" icon={<LockOutlined />} style={{ margin: 0 }}>
        平台内置 · 仅 Admin 可编辑
      </Tag>
    ),
  },
  mine: {
    border: '1px solid #a855f7',
    accent: '#a855f7',
    badge: (
      <Tag color="purple" icon={<UserOutlined />} style={{ margin: 0 }}>
        我创建的
      </Tag>
    ),
  },
  community: {
    border: '1px solid var(--color-border)',
    accent: 'var(--color-primary)',
    badge: (
      <Tag icon={<TeamOutlined />} style={{ margin: 0 }}>
        他人创建
      </Tag>
    ),
  },
}

type SkillCardProps = {
  skill: Skill
  variant: SkillCardVariant
  onClick: () => void
}

/** Skill 仓库列表卡片：等高布局，标题/摘要/标签对齐。 */
export default function SkillCard({ skill, variant, onClick }: SkillCardProps) {
  const style = VARIANT_STYLE[variant]

  return (
    <Card
      hoverable
      onClick={onClick}
      style={{
        height: '100%',
        border: style.border,
        background: 'var(--color-bg)',
      }}
      styles={{
        body: {
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          padding: 16,
        },
      }}
    >
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', marginBottom: 10 }}>
        <div
          style={{
            width: 44,
            height: 44,
            borderRadius: 10,
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: `${style.accent}18`,
            color: style.accent,
            fontSize: 22,
          }}
        >
          {variant === 'platform' ? <LockOutlined /> : <BookOutlined />}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Title
            level={5}
            style={{
              color: 'var(--color-text)',
              margin: 0,
              lineHeight: 1.35,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {skill.display_name}
          </Title>
          <Text
            type="secondary"
            style={{
              fontSize: 12,
              fontFamily: 'var(--font-mono)',
              display: 'block',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            <CodeOutlined style={{ marginRight: 4 }} />
            {skill.name}
          </Text>
        </div>
      </div>

      <div style={{ marginBottom: 10 }}>{style.badge}</div>

      <Paragraph
        type="secondary"
        style={{
          fontSize: 13,
          lineHeight: 1.55,
          marginBottom: 12,
          flex: 1,
          minHeight: 40,
        }}
        ellipsis={{ rows: 2 }}
      >
        {skill.definition?.trim() || '暂无详细定义'}
      </Paragraph>

      <Space size={[4, 4]} wrap style={{ marginTop: 'auto' }}>
        <Tag color="blue">{skill.category_label || skill.category}</Tag>
        {variant === 'community' && skill.standard_owner_username && (
          <Tag color="default">@{skill.standard_owner_username}</Tag>
        )}
        {(skill.tags || []).slice(0, 3).map((t) => (
          <Tag key={t}>{t}</Tag>
        ))}
        {(skill.tags || []).length > 3 && (
          <Tag>+{(skill.tags || []).length - 3}</Tag>
        )}
      </Space>
    </Card>
  )
}
