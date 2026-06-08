import { useNavigate } from 'react-router-dom'
import { Card, Typography } from 'antd'
import { ThunderboltOutlined, SwapOutlined } from '@ant-design/icons'

const { Title, Text } = Typography

export default function Portal() {
  const navigate = useNavigate()

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--color-bg-secondary)',
        padding: 40,
      }}
    >
      <div style={{ textAlign: 'center', marginBottom: 48 }}>
        <Title level={2} style={{ color: 'var(--color-text)', marginBottom: 8 }}>
          TestAI Community
        </Title>
        <Text type="secondary">
          统一测试资产与 AI 翻译平台
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

        {/* AI 翻译卡片 */}
        <Card
          hoverable
          style={{
            width: 300,
            border: '1px solid var(--color-border)',
            background: 'var(--color-bg)',
            cursor: 'pointer',
          }}
          onClick={() => navigate('/translate')}
        >
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, padding: '8px 0' }}>
            <SwapOutlined style={{ fontSize: 48, color: 'var(--color-primary)' }} />
            <Title level={4} style={{ color: 'var(--color-text)', margin: 0, textAlign: 'center' }}>
              AI 翻译
            </Title>
            <Text type="secondary" style={{ textAlign: 'center' }}>
              UI 录制文件上传<br />
              自动翻译为中文测试用例<br />
              阶段一 / 二 / 四完整 pipeline
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
    </div>
  )
}
