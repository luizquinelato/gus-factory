/**
 * App.tsx — ETL Frontend
 *
 * Fluxo de autenticação SSO via OTT:
 *   1. Admin clica "Módulo ETL" no Sidebar principal.
 *   2. Backend gera OTT (UUID, TTL 30s) e retorna etl_url.
 *   3. Frontend principal abre: http://localhost:3344?ott=<uuid>
 *   4. Este App detecta ?ott, chama POST /api/v1/auth/exchange-ott,
 *      armazena token + user + tenant_colors no localStorage e renderiza o shell.
 *   5. Sem OTT nem token → salva path em sessionStorage e redireciona ao
 *      /login do frontend principal com apenas ?etl=1 (sem URL/porta exposta).
 *   6. Após login, frontend principal gera OTT e abre a raiz do ETL.
 *   7. Bootstrap troca OTT, lê sessionStorage, aplica replaceState antes de
 *      montar o BrowserRouter — URL correta desde o primeiro render, sem flash.
 *   8. Qualquer 401 futuro → apiClient repete o mesmo fluxo.
 */
import { useEffect, useRef, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { ThemeProvider } from './contexts/ThemeContext'
import Sidebar from './components/Sidebar'
import apiClient from './services/apiClient'
import { storage } from './utils/storage'
import type { OttExchangeResponse, TenantColors, ColorScheme, ThemeMode, ColorSchemaMode } from './types'

// ── URL do frontend principal (para redirecionamento) ─────────────────────────
const MAIN_FRONTEND =
  window.location.port === '3345' ? 'http://localhost:5178' : 'http://localhost:5177'

// ── Loading / Redirect screens ────────────────────────────────────────────────
function Loading() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', fontFamily: 'system-ui, sans-serif' }}>
      <p style={{ color: '#64748b' }}>Autenticando…</p>
    </div>
  )
}

// ── AppShell — sidebar + conteúdo principal ───────────────────────────────────
function AppShell() {
  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar />
      <main style={{ flex: 1, overflowY: 'auto', background: 'var(--bg, #f1f5f9)', padding: 32 }}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

// ── Home page (placeholder ETL dashboard) ─────────────────────────────────────
function HomePage() {
  const { user } = useAuth()
  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8, color: 'var(--color-1, #334155)' }}>
        Módulo ETL
      </h1>
      <p style={{ color: '#64748b', marginTop: 0 }}>
        Bem-vindo, {user?.name}. O dashboard ETL está em construção.
      </p>
    </div>
  )
}

// ── Bootstrap: troca OTT ou valida sessão existente ──────────────────────────
type BootState = 'loading' | 'ok'

function Bootstrap() {
  const { setSession, isAuthenticated, tenantColors, user } = useAuth()
  const [state, setState] = useState<BootState>('loading')
  // Guard contra React StrictMode (dev): o useEffect roda 2x, mas o OTT é
  // de uso único — a segunda chamada receberia 401 e redirecionaria para o
  // frontend principal. O ref garante que a lógica execute apenas uma vez.
  const ran = useRef(false)

  useEffect(() => {
    if (ran.current) return
    ran.current = true

    async function run() {
      const params = new URLSearchParams(window.location.search)
      const ott = params.get('ott')

      if (ott) {
        // Remove OTT da URL imediatamente (segurança: evita reuso via histórico)
        window.history.replaceState({}, '', window.location.pathname)
        try {
          const { data } = await apiClient.post<OttExchangeResponse>('/auth/exchange-ott', { ott })
          setSession(data.access_token, data.user, data.tenant_colors)
          // Restaura o deep link antes do BrowserRouter ser montado — sem flash
          const saved = sessionStorage.getItem('etl_return_path')
          sessionStorage.removeItem('etl_return_path')
          if (saved && saved !== '/') window.history.replaceState({}, '', saved)
          setState('ok')
        } catch {
          // OTT inválido/expirado → volta ao frontend principal
          window.location.href = MAIN_FRONTEND
        }
        return
      }

      // Sem OTT — verifica sessão existente no localStorage
      if (storage.getToken() && storage.getUser()) {
        setState('ok')
      } else {
        // Salva o path atual no sessionStorage do ETL (sem expor URL/porta na URL)
        sessionStorage.setItem('etl_return_path', window.location.pathname + window.location.search)
        window.location.href = `${MAIN_FRONTEND}/login?etl=1`
      }
    }
    run()
  }, [setSession])

  if (state === 'loading') return <Loading />

  // Resolve initialColors e initialTheme para ThemeProvider a partir do usuário autenticado
  const colors      = (tenantColors?.colors ?? []) as ColorScheme[]
  const schemaMode  = (tenantColors?.color_schema_mode ?? 'default') as ColorSchemaMode
  const themeMode   = (user?.theme_mode ?? 'light') as ThemeMode

  return (
    <ThemeProvider initialColors={colors} initialSchema={schemaMode} initialTheme={themeMode}>
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    </ThemeProvider>
  )
}

// ── Root ──────────────────────────────────────────────────────────────────────
export default function App() {
  return (
    <AuthProvider>
      <Bootstrap />
    </AuthProvider>
  )
}
