import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The FastAPI backend runs on :8000. The dev server forwards /api/* to it, so the browser never makes a cross-origin call.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, ''), timeout: 300000 },
    },
  },
})
