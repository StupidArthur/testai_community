import { Layout, Button as AntButton, Typography } from 'antd'
import {
  ThunderboltOutlined,
  AppstoreOutlined,
  SettingOutlined,
  LogoutOutlined,
  MoonOutlined,
  SunOutlined,
  SwapOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useThemeStore } from '../hooks/useTheme'
import type { ReactNode } from 'react'

const { Header, Content } = Layout
const { Text } = Typography

const navBtnStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  padding: '4px 12px',
  fontSize: 14,
  border: 'none',
  borderRadius: 6,
  cursor: 'pointer',
  background: 'transparent',
  transition: 'color 0.2s, border-color 0.2s',
  fontFamily: 'inherit',
  lineHeight: '22px',
  borderBottom: '2px solid transparent',
  color: 'var(--color-text-secondary)',
}

const navBtnActiveStyle: React.CSSProperties = {
  ...navBtnStyle,
  color: 'var(--color-primary)',
  borderBottomColor: 'var(--color-primary)',
}

function NavButton({ icon, label, active, onClick }: { icon: ReactNode; label: string; active: boolean; onClick: () => void }) {
  return (
    <button className="nav-btn" style={active ? navBtnActiveStyle : navBtnStyle} onClick={onClick} type="button">
      {icon}
      {label}
    </button>
  )
}

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { mode, toggle } = useThemeStore()

  const user = JSON.parse(localStorage.getItem('user') || '{}')
  const isAdmin = user.role === 'Admin'

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    navigate('/login')
  }

  const isActive = (path: string) => location.pathname.startsWith(path)

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--color-bg)',
          borderBottom: '1px solid var(--color-border)',
          padding: '0 24px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <ThunderboltOutlined style={{ fontSize: 24, color: 'var(--color-primary)', cursor: 'pointer' }} onClick={() => navigate('/')} />
          <Text
            strong
            style={{ fontSize: 18, color: 'var(--color-text)', marginRight: 16, cursor: 'pointer' }}
            onClick={() => navigate('/')}
          >
            TestAI Community
          </Text>
          <NavButton
            icon={<SwapOutlined />}
            label="AI 翻译"
            active={isActive('/translate')}
            onClick={() => navigate('/translate')}
          />
          <NavButton
            icon={<AppstoreOutlined />}
            label="工作台"
            active={isActive('/skills')}
            onClick={() => navigate('/skills')}
          />
          {isAdmin && (
            <NavButton
              icon={<SettingOutlined />}
              label="用户管理"
              active={isActive('/admin')}
              onClick={() => navigate('/admin')}
            />
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <AntButton
            type="text"
            icon={mode === 'dark' ? <SunOutlined /> : <MoonOutlined />}
            onClick={toggle}
            title="Toggle theme"
            style={{ color: 'var(--color-text-secondary)' }}
          />
          <Text style={{ color: 'var(--color-text-secondary)' }}>{user.username}</Text>
          <AntButton
            type="text"
            icon={<LogoutOutlined />}
            onClick={handleLogout}
            style={{ color: 'var(--color-text-secondary)' }}
          >
            退出
          </AntButton>
        </div>
      </Header>
      <Content style={{ background: 'var(--color-bg-secondary)', padding: '24px' }}>
        <Outlet />
      </Content>
    </Layout>
  )
}
