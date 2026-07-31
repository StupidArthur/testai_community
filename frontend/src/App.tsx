import { App as AntdApp, ConfigProvider, theme } from 'antd'
import { RouterProvider } from 'react-router-dom'
import { router } from './router'
import { useThemeStore } from './shared/hooks/useTheme'
import { useAuthBootstrap } from './shared/hooks/useAuth'
import { antdTheme, antdThemeDark } from './shared/styles/tokens'

export default function App() {
  const mode = useThemeStore((s) => s.mode)
  useAuthBootstrap()
  return (
    <ConfigProvider
      theme={{
        algorithm: mode === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: mode === 'dark' ? antdThemeDark : antdTheme,
      }}
    >
      {/* message/notification 挂到 body，避免被 Drawer/Modal 遮住 */}
      <AntdApp
        message={{ getContainer: () => document.body }}
        notification={{ getContainer: () => document.body }}
      >
        <RouterProvider router={router} />
      </AntdApp>
    </ConfigProvider>
  )
}
