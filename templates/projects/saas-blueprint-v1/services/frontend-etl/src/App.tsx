/**
 * App.tsx — ETL Frontend
 *
 * Sem login próprio. Fluxo de autenticação via OTT:
 *   1. Admin clica "Módulo ETL" no frontend principal.
 *   2. Backend gera OTT (UUID, TTL 30s) e retorna etl_url.
 *   3. Abre nova aba: http://localhost:3344?ott=<uuid>
 *   4. OttBootstrap detecta ?ott, chama exchange-ott, salva sessão.
 *   5. Sem OTT nem sessão → salva o path atual em sessionStorage e redireciona
 *      ao /login do frontend principal com apenas ?etl=1 (sem URL/porta exposta).
 *   6. Após login, o frontend principal gera OTT e abre a raiz do ETL.
 *   7. OttBootstrap troca o OTT, lê sessionStorage e navega para o path original
 *      via useLayoutEffect (antes do primeiro paint — sem flash).
 *   8. Qualquer 401 futuro → apiClient repete o mesmo fluxo de sessionStorage.
 */
import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { Toaster } from 'sonner'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { ThemeProvider } from './contexts/ThemeContext'
import { useTheme } from './contexts/useTheme'
import AppShell from './components/AppShell'
import HomePage from './pages/HomePage'
import ProfilePage from './pages/ProfilePage'
import QueueManagementPage from './pages/QueueManagementPage'
import apiClient from './services/apiClient'
import { storage } from './utils/storage'
import type { ThemeMode, ColorSchemaMode, ColorScheme, User } from './types'

// URL do frontend principal — derivada da porta atual do ETL
const MAIN_FRONTEND =
  window.location.port === '3345' ? 'http://localhost:5178' : 'http://localhost:5177'

// ── Tela de carregamento ──────────────────────────────────────────────────────
function Loading() {
  return (
    <div className="flex h-screen items-center justify-center bg-gray-100 dark:bg-gray-950">
      <p className="text-sm text-gray-400">Autenticando…</p>
    </div>
  )
}

// ── Sincroniza theme_mode com o banco ao montar e ao voltar para a aba ────────
function UserRefresher() {
  const { updateUser } = useAuth()
  const { setThemeMode } = useTheme()

  const syncTheme = useCallback(async () => {
    try {
      const { data } = await apiClient.get<User>('/users/me')
      // Suprime transições durante a sincronização → sem "piscar"
      const style = document.createElement('style')
      style.innerHTML = '*,*::before,*::after{transition:none!important;animation-duration:0s!important}'
      document.head.appendChild(style)
      setThemeMode(data.theme_mode as ThemeMode)
      updateUser({ theme_mode: data.theme_mode })
      // Remove após dois frames — browser já repintou com o novo tema
      requestAnimationFrame(() => requestAnimationFrame(() => style.remove()))
    } catch {}
  }, [setThemeMode, updateUser]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    syncTheme()
    // Re-sincroniza ao voltar para esta aba — captura mudanças feitas no outro frontend
    const onVisible = () => { if (document.visibilityState === 'visible') syncTheme() }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [syncTheme])

  return null
}

// ── Atualiza cores do banco em background ─────────────────────────────────────
function ColorRefresher() {
  const { setColors, setSchemaMode } = useTheme()
  const { updateTenantColors } = useAuth()
  useEffect(() => {
    apiClient
      .get<{ colors: ColorScheme[]; color_schema_mode: string }>('/tenant/colors/unified')
      .then(({ data }) => {
        setColors(data.colors)
        setSchemaMode(data.color_schema_mode as ColorSchemaMode)
        updateTenantColors({ colors: data.colors, color_schema_mode: data.color_schema_mode })
      })
      .catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

// ── Prefixo [DEV] no título da aba ───────────────────────────────────────────
function DevTitleEffect() {
  useEffect(() => {
    if (import.meta.env.MODE === 'dev' && !document.title.startsWith('[DEV]')) {
      document.title = `[DEV] ${document.title}`
    }
  }, [])
  return null
}

// ── Shell autenticado (ThemeProvider + rotas) ─────────────────────────────────
function AuthenticatedApp() {
  const { tenantColors, user } = useAuth()
  const initialColors = tenantColors?.colors ?? []
  const initialSchema = (tenantColors?.color_schema_mode ?? 'default') as ColorSchemaMode
  const initialTheme  = (user?.theme_mode ?? 'light') as ThemeMode

  return (
    <ThemeProvider initialColors={initialColors} initialSchema={initialSchema} initialTheme={initialTheme}>
      <UserRefresher />
      <ColorRefresher />
      <DevTitleEffect />
      <AppShell>
        <Routes>
          <Route path="/"                   element={<HomePage />} />
          <Route path="/profile"            element={<ProfilePage />} />
          <Route path="/queue-management"   element={<QueueManagementPage />} />
          <Route path="*"                   element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </ThemeProvider>
  )
}

// Chave usada em sessionStorage para preservar o deep link entre origens
const ETL_RETURN_PATH_KEY = 'etl_return_path'

// ── Bootstrap OTT — troca token ou valida sessão existente ───────────────────
function OttBootstrap({ children }: { children: React.ReactNode }) {
  const { setSession } = useAuth()
  const navigate = useNavigate()
  const [ready, setReady] = useState(false)
  // Guard StrictMode: OTT é de uso único — impede segunda chamada em dev
  const ran = useRef(false)
  // Path a restaurar após o primeiro render autenticado (sem flash de tela)
  const returnPathRef = useRef<string | null>(null)

  useEffect(() => {
    if (ran.current) return
    ran.current = true

    const params = new URLSearchParams(window.location.search)
    const ott = params.get('ott')

    if (ott) {
      // Remove OTT da URL imediatamente (segurança: evita reuso via histórico)
      window.history.replaceState({}, '', window.location.pathname)
      apiClient
        .post('/auth/exchange-ott', { ott })
        .then(({ data }) => {
          setSession(data.access_token, data.user, data.tenant_colors)
          // Recupera o deep link salvo antes do redirecionamento ao login
          const saved = sessionStorage.getItem(ETL_RETURN_PATH_KEY)
          sessionStorage.removeItem(ETL_RETURN_PATH_KEY)
          if (saved && saved !== '/') returnPathRef.current = saved
          setReady(true)
        })
        .catch(() => {
          sessionStorage.removeItem(ETL_RETURN_PATH_KEY)
          window.location.href = `${MAIN_FRONTEND}/login`
        })
      return
    }

    // Sem OTT — valida sessão existente no localStorage
    if (storage.getToken() && storage.getUser()) {
      setReady(true)
    } else {
      // Salva o path atual no sessionStorage do próprio ETL (sem expor URL/porta)
      sessionStorage.setItem(ETL_RETURN_PATH_KEY, window.location.pathname + window.location.search)
      // Redireciona ao login com apenas um flag — URL de login fica limpa
      window.location.href = `${MAIN_FRONTEND}/login?etl=1`
    }
  }, [setSession])

  // Restaura o deep link antes do primeiro paint — evita flash da home page
  useLayoutEffect(() => {
    if (ready && returnPathRef.current) {
      const path = returnPathRef.current
      returnPathRef.current = null
      navigate(path, { replace: true })
    }
  }, [ready, navigate])

  if (!ready) return <Loading />
  return <>{children}</>
}

// ── Root ──────────────────────────────────────────────────────────────────────
export default function App() {
  return (
    <AuthProvider>
      <Toaster position="top-right" closeButton />
      <OttBootstrap>
        <AuthenticatedApp />
      </OttBootstrap>
    </AuthProvider>
  )
}
