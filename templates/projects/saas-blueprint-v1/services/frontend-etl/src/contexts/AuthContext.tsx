/**
 * AuthContext — ETL Frontend
 *
 * Sem login próprio: autenticação via OTT (ver App.tsx > OttBootstrap).
 * Sem refresh token: 401 no apiClient redireciona ao frontend principal.
 */
import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import apiClient from '../services/apiClient'
import type { User, TenantColors } from '../types'
import { storage } from '../utils/storage'

interface AuthState {
  user: User | null
  tenantColors: TenantColors | null
  token: string | null
  isAuthenticated: boolean
}

interface AuthContextValue extends AuthState {
  setSession: (token: string, user: User, tenantColors: TenantColors) => void
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
    return { token, user, tenantColors, isAuthenticated: !!token && !!user }
  } catch {
    return { token: null, user: null, tenantColors: null, isAuthenticated: false }
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(loadFromStorage)

  /** Chamado após OTT exchange bem-sucedido — persiste sessão no localStorage. */
  const setSession = useCallback((token: string, user: User, tenantColors: TenantColors) => {
    storage.setToken(token)
    storage.setUser(JSON.stringify(user))
    storage.setTenantColors(JSON.stringify(tenantColors))
    setState({ token, user, tenantColors, isAuthenticated: true })
  }, [])

  const logout = useCallback(() => {
    // Captura o token ANTES de limpar — o interceptor Axios roda em microtask.
    const token = storage.getToken()
    storage.removeToken()
    storage.removeUser()
    storage.removeTenantColors()
    setState({ token: null, user: null, tenantColors: null, isAuthenticated: false })
    // Invalida a sessão no backend para encerrar o acesso em ambos os frontends.
    // O frontend principal será notificado via ?force_logout=1 no redirect.
    if (token) {
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
    <AuthContext.Provider value={{ ...state, setSession, logout, updateUser, updateTenantColors }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
