import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'
import { storage } from '../utils/storage'

const API_BASE = '/api/v1'

const apiClient = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
})

// ── Request interceptor — injeta o Bearer token ───────────────────────────
apiClient.interceptors.request.use((config) => {
  const token = storage.getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// ── Controle de refresh em progresso (evita múltiplas chamadas simultâneas) ──
let _refreshing: Promise<string | null> | null = null

async function tryRefresh(): Promise<string | null> {
  const refreshToken = storage.getRefreshToken()
  if (!refreshToken) return null

  try {
    const { data } = await axios.post(`${API_BASE}/auth/refresh`, { refresh_token: refreshToken })
    storage.setToken(data.access_token)
    storage.setRefreshToken(data.refresh_token)   // rotação — salva o novo refresh token
    return data.access_token
  } catch {
    return null
  }
}

function clearSession() {
  storage.removeToken()
  storage.removeRefreshToken()
  storage.removeUser()
  storage.removeTenantColors()
  window.location.href = '/login'
}

// ── Response interceptor — 401 → tenta refresh automático ────────────────
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean }

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true  // evita loop infinito

      // Serializa múltiplos 401 simultâneos em uma única chamada de refresh
      if (!_refreshing) _refreshing = tryRefresh().finally(() => { _refreshing = null })
      const newToken = await _refreshing

      if (newToken) {
        // Retry da requisição original com o novo access token
        if (originalRequest.headers) {
          originalRequest.headers['Authorization'] = `Bearer ${newToken}`
        }
        return apiClient(originalRequest)
      }

      clearSession()
    }

    return Promise.reject(error)
  },
)

export default apiClient
