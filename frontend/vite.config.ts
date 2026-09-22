import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const apiProxy = {
  '/api': {
    target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: apiProxy,
  },
  preview: { port: 4173, proxy: apiProxy },
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.spec.ts'],
  },
})
