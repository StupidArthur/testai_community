import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

/** 从项目根目录 .env 读取 BACKEND_PORT / FRONTEND_PORT（与 backend 共用同一份） */
export default defineConfig(({ mode }) => {
  const rootEnv = loadEnv(mode, resolve(__dirname, '..'), '')
  const backendPort = rootEnv.BACKEND_PORT || '48010'
  const frontendPort = Number(rootEnv.FRONTEND_PORT || '3003')

  return {
    plugins: [react()],
    base: '/',
    resolve: {
      alias: {
        '@': resolve(__dirname, './src'),
      },
    },
    server: {
      host: true,
      port: frontendPort,
      proxy: {
        '/api': {
          target: `http://127.0.0.1:${backendPort}`,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
    },
  }
})
