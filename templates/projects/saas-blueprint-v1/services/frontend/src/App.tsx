import React, { useEffect, useCallback } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'sonner'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { ThemeProvider } from './contexts/ThemeContext'
import { useTheme } from './contexts/useTheme'
import LoginPage from './pages/LoginPage'
import AppShell from './components/AppShell'
import HomePage from './pages/HomePage'
import ColorSettingsPage from './pages/ColorSettingsPage'
import ProfilePage from './pages/ProfilePage'
import Menu1Page from './pages/Menu1Page'
import Menu21Page from './pages/Menu21Page'
import Menu22Page from './pages/Menu22Page'
import RolesPage from './pages/RolesPage'
import PagesPage from './pages/PagesPage'
import apiClient from './services/apiClient'
import type { ThemeMode, ColorSchemaMode, ColorScheme, User } from './types'

/**
 * Detecta ?force_logout=1 na URL — enviado pelo ETL ao fazer logout.
 * Limpa a sessão do frontend principal imediatamente, sem esperar o token expirar.
 */
function ForceLogoutHandler() {
  const { logout } = useAuth()
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('force_logout') === '1') {
      window.history.replaceState({}, '', window.location.pathname)
      logout()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

/**
 * Tela de carregamento exibida enquanto o AuthProvider valida o token no servidor.
 * Evita que a UI da sessão anterior apareça antes do redirect ao /login.
 */
function Loading() {
  return (
    <div className="flex h-screen items-center justify-center bg-gray-100 dark:bg-gray-950">
      <p className="text-sm text-gray-400">Carregando…</p>
    </div>
  )
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isValidating } = useAuth()
  if (isValidating) return <Loading />
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isValidating, user } = useAuth()
  if (isValidating) return <Loading />
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (!user?.is_admin) return <Navigate to="/" replace />
  return <>{children}</>
}

/**
 * Roda dentro do ThemeProvider — busca cores frescas do banco a cada sessão.
 * O render inicial já usa as cores do localStorage (rápido), depois atualiza.
 */
/** Sets [DEV] prefix in the browser tab title when running in dev mode. */
function DevTitleEffect() {
  useEffect(() => {
    if (import.meta.env.MODE === 'dev' && !document.title.startsWith('[DEV]')) {
      document.title = `[DEV] ${document.title}`
    }
  }, [])
  return null
}

/**
 * Sincroniza theme_mode com o banco quando a aba recebe foco novamente —
 * captura mudanças feitas no outro frontend (ex.: ETL). Não roda no mount:
 * o valor inicial vem do localStorage/AuthContext (já validado) e uma
 * chamada no mount causaria race com toggles locais recentes.
 */
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
    const onVisible = () => { if (document.visibilityState === 'visible') syncTheme() }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [syncTheme])

  return null
}

function ColorRefresher() {
  const { setColors, setSchemaMode } = useTheme()
  const { updateTenantColors } = useAuth()

  useEffect(() => {
    apiClient
      .get<{ colors: ColorScheme[]; color_schema_mode: string }>('/tenant/colors/unified')
      .then(({ data }) => {
        setColors(data.colors)
        setSchemaMode(data.color_schema_mode as ColorSchemaMode)
        // Mantém localStorage em sincronia → próximo reload inicia com dados corretos
        updateTenantColors({ colors: data.colors, color_schema_mode: data.color_schema_mode })
      })
      .catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return null
}

function AuthenticatedApp() {
  const { tenantColors, user } = useAuth()

  const initialColors = tenantColors?.colors ?? []
  const initialSchema = (tenantColors?.color_schema_mode ?? 'default') as ColorSchemaMode
  const initialTheme  = (user?.theme_mode ?? 'light') as ThemeMode

  return (
    <ThemeProvider
      initialColors={initialColors}
      initialSchema={initialSchema}
      initialTheme={initialTheme}
    >
      {/* Atualiza cores do banco em background sem bloquear o render */}
      <UserRefresher />
      <ColorRefresher />
      {/* Prefixes browser tab title with [DEV] in dev mode */}
      <DevTitleEffect />
      <AppShell>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/color-settings" element={<AdminRoute><ColorSettingsPage /></AdminRoute>} />
          <Route path="/admin/roles"    element={<AdminRoute><RolesPage /></AdminRoute>} />
          <Route path="/admin/pages"   element={<AdminRoute><PagesPage /></AdminRoute>} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/menu-1" element={<Menu1Page />} />
          <Route path="/menu-2/sub-1" element={<Menu21Page />} />
          <Route path="/menu-2/sub-2" element={<Menu22Page />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </ThemeProvider>
  )
}

export default function App() {
  return (
    <AuthProvider>
      {/* Limpa sessão imediatamente se o ETL redirecionou com ?force_logout=1 */}
      <ForceLogoutHandler />
      {/* Toast global — posicionado fora do ThemeProvider para ser sempre visível */}
      <Toaster position="top-right" closeButton />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <AuthenticatedApp />
            </ProtectedRoute>
          }
        />
      </Routes>
    </AuthProvider>
  )
}
