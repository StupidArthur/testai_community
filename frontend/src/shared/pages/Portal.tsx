import { useNavigate } from 'react-router-dom'
import { Card, Typography } from 'antd'
import { ThunderboltOutlined, ToolOutlined, BookOutlined } from '@ant-design/icons'

const { Title, Text } = Typography

export default function Portal() {
  const navigate = useNavigate()

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--color-bg-secondary)',
        padding: 40,
        minHeight: 'calc(100vh - 64px - 48px)',
      }}
    >
      <div style={{ textAlign: 'center', marginBottom: 48 }}>
        <Title level={2} style={{ color: 'var(--color-text)', marginBottom: 8 }}>
          TestAI Community
        </Title>
        <Text type="secondary">
          统一测试资产与工具平台
        </Text>
      </div>

      <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap', justifyContent: 'center', maxWidth: 720 }}>
        {/* Skill 管理卡片 */}
        <Card
          hoverable
          style={{
            width: 300,
            border: '1px solid var(--color-border)',
            background: 'var(--color-bg)',
            cursor: 'pointer',
          }}
          onClick={() => navigate('/skills')}
        >
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, padding: '8px 0' }}>
            <ThunderboltOutlined style={{ fontSize: 48, color: 'var(--color-primary)' }} />
            <Title level={4} style={{ color: 'var(--color-text)', margin: 0, textAlign: 'center' }}>
              Skill 管理
            </Title>
            <Text type="secondary" style={{ textAlign: 'center' }}>
              Prompt 资产中心<br />
              9 维 Agent 编辑器<br />
              版本管理与分支协作
            </Text>
            <Text
              style={{
                color: 'var(--color-primary)',
                fontWeight: 500,
                marginTop: 8,
              }}
            >
              进入 →
            </Text>
          </div>
        </Card>

        {/* 工具集卡片 */}
        <Card
          hoverable
          style={{
            width: 300,
            border: '1px solid var(--color-border)',
            background: 'var(--color-bg)',
            cursor: 'pointer',
          }}
          onClick={() => navigate('/tool-hub')}
        >
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, padding: '8px 0' }}>
            <ToolOutlined style={{ fontSize: 48, color: 'var(--color-primary)' }} />
            <Title level={4} style={{ color: 'var(--color-text)', margin: 0, textAlign: 'center' }}>
              工具集
            </Title>
            <Text type="secondary" style={{ textAlign: 'center' }}>
              功能录制（客户端下载）<br />
              AI 翻译等平台集成工具<br />
              说明书与版本 changelog
            </Text>
            <Text
              style={{
                color: 'var(--color-primary)',
                fontWeight: 500,
                marginTop: 8,
              }}
            >
              进入 →
            </Text>
          </div>
        </Card>

        {/* 知识库：清洗入库 + RAG 问答 */}
        <Card
          hoverable
          style={{
            width: 300,
            border: '1px solid var(--color-border)',
            background: 'var(--color-bg)',
            cursor: 'pointer',
          }}
          onClick={() => navigate('/knowledge-base')}
        >
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, padding: '8px 0' }}>
            <BookOutlined style={{ fontSize: 48, color: 'var(--color-primary)' }} />
            <Title level={4} style={{ color: 'var(--color-text)', margin: 0, textAlign: 'center' }}>
              知识库
            </Title>
            <Text type="secondary" style={{ textAlign: 'center' }}>
              文档清洗审核入库<br />
              锚点对齐与冲突检测<br />
              RAG 智能问答
            </Text>
            <Text
              style={{
                color: 'var(--color-primary)',
                fontWeight: 500,
                marginTop: 8,
              }}
            >
              进入 →
            </Text>
          </div>
        </Card>
      </div>

      <Text type="secondary" style={{ marginTop: 48, fontSize: 12 }}>
        designed by @yuzechao
      </Text>
    </div>
  )
}
