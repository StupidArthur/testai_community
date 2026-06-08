import { ConfigProvider, theme } from 'antd'
import { RouterProvider } from 'react-router-dom'
import { router } from './router'
import { useThemeStore } from './shared/hooks/useTheme'
import { antdTheme, antdThemeDark } from './shared/styles/tokens'

export default function App() {
  const mode = useThemeStore((s) => s.mode)
  return (
    <ConfigProvider
      theme={{
        algorithm: mode === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: mode === 'dark' ? antdThemeDark : antdTheme,
      }}
    >
      <RouterProvider router={router} />
    </ConfigProvider>
  )
}
