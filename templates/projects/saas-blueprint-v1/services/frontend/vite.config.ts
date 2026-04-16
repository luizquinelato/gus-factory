import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Porta do backend varia por mode:
//   prod → 10000  |  dev → 10010
// Fonte da verdade: helms/ports.yml
const BACKEND_PORT: Record<string, number> = {
  prod: 10000,
  dev:  10010,
}

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: `http://localhost:${BACKEND_PORT[mode] ?? BACKEND_PORT.dev}`,
        changeOrigin: true,
      },
      '/static': {
        target: `http://localhost:${BACKEND_PORT[mode] ?? BACKEND_PORT.dev}`,
        changeOrigin: true,
      },
    },
  },
}))
