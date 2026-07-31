import { useNavigate } from 'react-router-dom'
import { Typography } from 'antd'
import {
  ProjectOutlined,
  ThunderboltOutlined,
  ToolOutlined,
  BookOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons'
import './Portal.css'

const { Title, Text } = Typography

const SECONDARY = [
  {
    key: 'skills',
    path: '/skills',
    icon: <ThunderboltOutlined />,
    title: 'Skill 管理',
    desc: 'Prompt 资产 · 版本与分支',
  },
  {
    key: 'tools',
    path: '/tool-hub',
    icon: <ToolOutlined />,
    title: '工具集',
    desc: '功能录制 · AI 翻译',
  },
  {
    key: 'kb',
    path: '/knowledge-base',
    icon: <BookOutlined />,
    title: '知识库',
    desc: '清洗入库 · RAG 问答',
  },
] as const

/**
 * 登录后首页：大篇幅进入「项目管理」，其余模块为次要入口。
 */
export default function Portal() {
  const navigate = useNavigate()

  return (
    <div className="portal">
      <div className="portal__inner">
        <header className="portal__brand">
          <Title level={2} className="portal__brand-title">
            TestAI Community
          </Title>
          <Text type="secondary">统一测试资产与工具平台</Text>
        </header>

        <button
          type="button"
          className="portal__hero"
          onClick={() => navigate('/projects')}
        >
          <div className="portal__hero-icon" aria-hidden>
            <ProjectOutlined />
          </div>
          <div className="portal__hero-copy">
            <span className="portal__hero-label">项目管理</span>
            <span className="portal__hero-desc">
              项目 · 领域 · 周 Action · 进度与风险日更
            </span>
          </div>
          <span className="portal__hero-cta">
            进入
            <ArrowRightOutlined />
          </span>
        </button>

        <div className="portal__secondary-label">
          <Text type="secondary">其它能力</Text>
        </div>

        <div className="portal__secondary">
          {SECONDARY.map((item) => (
            <button
              key={item.key}
              type="button"
              className="portal__chip"
              onClick={() => navigate(item.path)}
            >
              <span className="portal__chip-icon">{item.icon}</span>
              <span className="portal__chip-text">
                <span className="portal__chip-title">{item.title}</span>
                <span className="portal__chip-desc">{item.desc}</span>
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
