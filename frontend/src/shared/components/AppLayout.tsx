import { useState, useEffect } from 'react'
import { Layout, Button as AntButton, Typography, Dropdown, Modal, Input, message } from 'antd'
import type { MenuProps } from 'antd'
import {
  ThunderboltOutlined,
  AppstoreOutlined,
  SettingOutlined,
  LogoutOutlined,
  MoonOutlined,
  SunOutlined,
  SwapOutlined,
  LockOutlined,
  UserOutlined,
  HistoryOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useThemeStore } from '../hooks/useTheme'
import { authApi, setOnUnauthorized } from '../api/client'
import { useCurrentUser } from '../hooks/useAuth'
import type { ReactNode } from 'react'

const { Header, Content } = Layout
const { Text } = Typography

const navBtnStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  padding: '4px 14px',
  fontSize: 14,
  border: 'none',
  borderRadius: 16,
  cursor: 'pointer',
  background: 'transparent',
  boxShadow: 'none',
  transition: 'color 0.2s, background 0.2s',
  fontFamily: 'inherit',
  lineHeight: '22px',
  color: 'var(--color-text-secondary)',
}

const navBtnActiveStyle: React.CSSProperties = {
  ...navBtnStyle,
  color: 'var(--color-primary)',
  background: 'color-mix(in srgb, var(--color-primary) 10%, transparent)',
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

  useEffect(() => {
    setOnUnauthorized(() => {
      navigate('/login', { replace: true })
    })
  }, [navigate])

  const [passwordModalOpen, setPasswordModalOpen] = useState(false)
  const [passwordForm, setPasswordForm] = useState({ old_password: '', new_password: '', confirm_password: '' })
  const [changePwdLoading, setChangePwdLoading] = useState(false)

  const user = useCurrentUser()
  const isAdmin = user?.role === 'Admin'

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    navigate('/login')
  }

  const handleChangePassword = async () => {
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      message.error('两次输入的密码不一致')
      return
    }
    if (passwordForm.new_password.length < 6) {
      message.error('新密码长度不能少于 6 位')
      return
    }
    setChangePwdLoading(true)
    try {
      await authApi.changePassword({
        old_password: passwordForm.old_password,
        new_password: passwordForm.new_password,
      })
      message.success('密码修改成功')
      setPasswordModalOpen(false)
      setPasswordForm({ old_password: '', new_password: '', confirm_password: '' })
    } catch (err: any) {
      message.error(err.response?.data?.detail || '修改失败')
    } finally {
      setChangePwdLoading(false)
    }
  }

  const isActive = (path: string) => location.pathname.startsWith(path)

  return (
    <Layout style={{ height: '100%', overflow: 'hidden' }}>
      <Header
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          zIndex: 1000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--color-bg)',
          borderBottom: '1px solid var(--color-border)',
          padding: '0 24px',
          height: 64,
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
            label="Skill 管理"
            active={isActive('/skills')}
            onClick={() => navigate('/skills')}
          />
          <NavButton
            icon={<HistoryOutlined />}
            label="更新日志"
            active={isActive('/changelog')}
            onClick={() => navigate('/changelog')}
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
          <Dropdown
            menu={{
              items: [
                {
                  key: 'change-password',
                  icon: <LockOutlined />,
                  label: '修改密码',
                  onClick: () => setPasswordModalOpen(true),
                },
                {
                  type: 'divider',
                },
                {
                  key: 'logout',
                  icon: <LogoutOutlined />,
                  label: '注销',
                  onClick: handleLogout,
                },
              ],
            }}
          >
            <AntButton type="text" style={{ color: 'var(--color-text-secondary)' }}>
              <UserOutlined style={{ marginRight: 6 }} />
              {user?.username ?? ''}
            </AntButton>
          </Dropdown>
        </div>
      </Header>
      <Content style={{ background: 'var(--color-bg-secondary)', padding: '24px', marginTop: 64, height: 'calc(100% - 64px)', overflow: 'hidden' }}>
        <Outlet />
      </Content>

      <Modal
        title="修改密码"
        open={passwordModalOpen}
        onOk={handleChangePassword}
        onCancel={() => {
          setPasswordModalOpen(false)
          setPasswordForm({ old_password: '', new_password: '', confirm_password: '' })
        }}
        confirmLoading={changePwdLoading}
        okText="确认修改"
        cancelText="取消"
      >
        <div style={{ marginBottom: 12 }}>
          <Typography.Text strong style={{ display: 'block', marginBottom: 4 }}>当前密码</Typography.Text>
          <Input.Password
            placeholder="请输入当前密码"
            value={passwordForm.old_password}
            onChange={(e) => setPasswordForm((f) => ({ ...f, old_password: e.target.value }))}
          />
        </div>
        <div style={{ marginBottom: 12 }}>
          <Typography.Text strong style={{ display: 'block', marginBottom: 4 }}>新密码</Typography.Text>
          <Input.Password
            placeholder="请输入新密码（至少 6 位）"
            value={passwordForm.new_password}
            onChange={(e) => setPasswordForm((f) => ({ ...f, new_password: e.target.value }))}
          />
        </div>
        <div>
          <Typography.Text strong style={{ display: 'block', marginBottom: 4 }}>确认新密码</Typography.Text>
          <Input.Password
            placeholder="请再次输入新密码"
            value={passwordForm.confirm_password}
            onChange={(e) => setPasswordForm((f) => ({ ...f, confirm_password: e.target.value }))}
          />
        </div>
      </Modal>
    </Layout>
  )
}
