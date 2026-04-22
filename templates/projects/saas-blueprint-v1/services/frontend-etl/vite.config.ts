import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Porta do backend varia por mode:
//   prod → 10000  |  dev → 10010
// Fonte da verdade: helms/ports.yml
const BACKEND_PORT: Record<string, number> = {
  prod: 10000,
  dev:  10010,
}

export default defineConfig(({ mode }) => {
  const backendDev  = BACKEND_PORT[mode] ?? BACKEND_PORT.dev
  const backendProd = BACKEND_PORT[mode] ?? BACKEND_PORT.prod

  return {
    plugins: [react()],
    // Dev server  (npm run dev  → port 3345 --mode dev  → backend 10010)
    server: {
      proxy: {
        '/api':    { target: `http://localhost:${backendDev}`,  changeOrigin: true },
        '/static': { target: `http://localhost:${backendDev}`,  changeOrigin: true },
      },
    },
    // Preview server (npm run preview → port 3344 --mode prod → backend 10000)
    preview: {
      proxy: {
        '/api':    { target: `http://localhost:${backendProd}`, changeOrigin: true },
        '/static': { target: `http://localhost:${backendProd}`, changeOrigin: true },
      },
    },
  }
})
