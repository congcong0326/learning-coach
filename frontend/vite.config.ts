/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000'
const devAllowedHosts = ['my-leetcode.com']

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 允许本地代理域名访问 dev server，同时保留 Vite 的 host 校验边界。
    allowedHosts: devAllowedHosts,
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
})
