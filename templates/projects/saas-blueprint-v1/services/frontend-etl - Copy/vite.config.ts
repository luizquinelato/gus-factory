import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Porta do backend varia por mode (igual ao frontend principal):
//   dev  → 10010  |  prod → 10000
// Fonte da verdade: helms/ports.yml
// Porta do ETL: 3345 (dev) | 3344 (prod) — passada via --port no package.json
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
    },
  },
  preview: {
    proxy: {
      '/api': {
        target: `http://localhost:${BACKEND_PORT[mode] ?? BACKEND_PORT.prod}`,
        changeOrigin: true,
      },
    },
  },
}))
