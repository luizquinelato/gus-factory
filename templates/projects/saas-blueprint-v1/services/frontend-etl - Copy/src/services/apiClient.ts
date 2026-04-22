/**
 * apiClient.ts — ETL Frontend
 *
 * Diferenças em relação ao frontend principal:
 * - Sem refresh token (ETL não tem mecanismo próprio de renovação).
 * - 401 → salva path atual em sessionStorage e redireciona ao /login com ?etl=1.
 *   URL limpa — sem porta ou token expostos na barra de endereços.
 */
import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'
import { storage } from '../utils/storage'

// URL do frontend principal — deve bater com a porta real em cada ambiente.
// Em dev: :5178 | Em prod (preview): :5177
const MAIN_FRONTEND =
  window.location.port === '3345'
    ? 'http://localhost:5178'
    : 'http://localhost:5177'

const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// ── Request: injeta Bearer token ──────────────────────────────────────────────
apiClient.interceptors.request.use((config) => {
  const token = storage.getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// ── Response: 401 → limpa sessão e volta ao login com ?etl=1 ────────────────
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const req = error.config as AxiosRequestConfig & { _retry?: boolean }

    if (error.response?.status === 401 && !req._retry) {
      req._retry = true
      storage.clear()
      // Salva o path atual para restaurar após re-autenticação (sem expor URL/porta)
      sessionStorage.setItem('etl_return_path', window.location.pathname + window.location.search)
      window.location.href = `${MAIN_FRONTEND}/login?etl=1`
    }

    return Promise.reject(error)
  },
)

export default apiClient
