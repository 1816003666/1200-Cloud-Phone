import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 本地开发：前端 5174（5173 被其他项目占用），API 代理到后端 8001，WebSocket 也代理
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8001',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
