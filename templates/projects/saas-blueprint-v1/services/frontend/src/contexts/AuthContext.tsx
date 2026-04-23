import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react'
import apiClient from '../services/apiClient'
import type { User, TenantColors, LoginResponse } from '../types'
import { storage } from '../utils/storage'

interface AuthState {
  user: User | null
  tenantColors: TenantColors | null
  token: string | null
  isAuthenticated: boolean
  /**
   * `true` enquanto o token lido do localStorage ainda não foi confirmado pelo
   * servidor via `GET /users/me`. Durante esse intervalo, ProtectedRoute deve
   * exibir <Loading /> — impede que a UI da sessão anterior apareça antes do
   * redirect ao /login (ex.: após rollback+migrate do banco).
   */
  isValidating: boolean
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<LoginResponse>
  logout: () => void
  updateUser: (u: Partial<User>) => void
  updateTenantColors: (partial: Partial<TenantColors>) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function loadFromStorage(): AuthState {
  try {
    const token        = storage.getToken()
    const user         = JSON.parse(storage.getUser()         || 'null') as User | null
    const tenantColors = JSON.parse(storage.getTenantColors() || 'null') as TenantColors | null
    const hasSession   = !!token && !!user
    // isValidating começa true se há sessão em cache — precisa confirmar com o servidor
    return { token, user, tenantColors, isAuthenticated: hasSession, isValidating: hasSession }
  } catch {
    return { token: null, user: null, tenantColors: null, isAuthenticated: false, isValidating: false }
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(loadFromStorage)

  // Valida o token contra o servidor no mount. Em 401, o interceptor do Axios
  // já faz clearSession() + window.location.href = '/login' (full navigation).
  // Aqui só precisamos atualizar o user com dados frescos e liberar a UI.
  useEffect(() => {
    if (!state.isValidating) return
    let cancelled = false
    apiClient.get<User>('/users/me')
      .then(({ data }) => {
        if (cancelled) return
        storage.setUser(JSON.stringify(data))
        setState(prev => ({ ...prev, user: data, isValidating: false }))
      })
      .catch(() => {
        // 401 já foi tratado pelo interceptor (redirect). Para outros erros
        // (rede/backend offline), libera a UI mantendo a sessão em cache.
        if (cancelled) return
        setState(prev => ({ ...prev, isValidating: false }))
      })
    return () => { cancelled = true }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const login = useCallback(async (email: string, password: string): Promise<LoginResponse> => {
    const { data } = await apiClient.post<LoginResponse>('/auth/login', { email, password })

    storage.setToken(data.access_token)
    storage.setRefreshToken(data.refresh_token)   // persiste refresh token para auto-refresh
    storage.setUser(JSON.stringify(data.user))
    storage.setTenantColors(JSON.stringify(data.tenant_colors))

    setState({
      token: data.access_token,
      user: data.user,
      tenantColors: data.tenant_colors,
      isAuthenticated: true,
      isValidating: false,
    })
    return data
  }, [])

  const logout = useCallback(() => {
    // Captura o token ANTES de limpar o storage.
    // O interceptor do Axios roda assincronamente (microtask) — se limpássemos
    // primeiro, storage.getToken() retornaria null e o header Authorization
    // não seria enviado, impedindo a invalidação da sessão no servidor.
    const token = storage.getToken()

    storage.removeToken()
    storage.removeRefreshToken()
    storage.removeUser()
    storage.removeTenantColors()
    setState({ token: null, user: null, tenantColors: null, isAuthenticated: false, isValidating: false })

    if (token) {
      // Fire-and-forget com Authorization explícito — bypass do interceptor.
      apiClient.post('/auth/logout', {}, {
        headers: { Authorization: `Bearer ${token}` },
      }).catch(() => {})
    }
  }, [])

  const updateUser = useCallback((partial: Partial<User>) => {
    setState((prev) => {
      if (!prev.user) return prev
      const updated = { ...prev.user, ...partial }
      storage.setUser(JSON.stringify(updated))
      return { ...prev, user: updated }
    })
  }, [])

  const updateTenantColors = useCallback((partial: Partial<TenantColors>) => {
    setState((prev) => {
      const updated = { ...prev.tenantColors, ...partial } as TenantColors
      storage.setTenantColors(JSON.stringify(updated))
      return { ...prev, tenantColors: updated }
    })
  }, [])

  return (
    <AuthContext.Provider value={{ ...state, login, logout, updateUser, updateTenantColors }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
