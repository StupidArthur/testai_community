import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
    },
  },
  server: {
    host: true,
    port: 3003,
    proxy: {
      // 统一入口：combined 后端（:48010）
      // combined 后端内部代理到各自独立进程
      '/api': {
        target: 'http://127.0.0.1:48010',
        changeOrigin: true,
      },
      '/skills': {
        target: 'http://127.0.0.1:48010',
        changeOrigin: true,
      },
      '/translate': {
        target: 'http://127.0.0.1:48010',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
