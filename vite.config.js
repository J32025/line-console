import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // dev: proxy /api ไป vercel dev (port 3000) ถ้ารันคู่กัน
      '/api': { target: 'http://localhost:3000', changeOrigin: true },
    },
  },
})
