<!-- blueprint: db_changes=false seed_data=false -->
# 07. Padrões de Código do Frontend

Este documento define os padrões obrigatórios para o desenvolvimento do Frontend em React (Vite + TypeScript).

## 🔒 1. AuthContext e apiClient (Axios)

O frontend **nunca** se comunica diretamente com o Auth Service. Toda comunicação passa pelo Backend (API Gateway). O `apiClient` injeta o `access_token` em toda requisição e **renova automaticamente** a sessão ao receber um 401 — o usuário nunca percebe a expiração do token de 5 minutos.

### Estratégia de dois tokens

| Token | TTL | Armazenamento | Responsabilidade |
|---|---|---|---|
| `access_token` | 5 min | `localStorage` | Autenticação de cada request |
| `refresh_token` | 7 dias | `localStorage` | Renovar o `access_token` expirado |

A cada `POST /auth/refresh` bem-sucedido, **ambos** os tokens são rotacionados (o antigo refresh é invalidado no servidor).

```typescript
// src/services/apiClient.ts
import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'
import { storage } from '../utils/storage'

const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// ── 1. Injetar Bearer token em cada request ───────────────────────────────
apiClient.interceptors.request.use((config) => {
  const token = storage.getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// ── 2. Auto-refresh em 401 ────────────────────────────────────────────────
// Múltiplos 401 simultâneos são serializados — apenas 1 chamada de refresh ocorre.
let _refreshing: Promise<string | null> | null = null

async function tryRefresh(): Promise<string | null> {
  const refreshToken = storage.getRefreshToken()
  if (!refreshToken) return null
  try {
    const { data } = await axios.post('/api/v1/auth/refresh', { refresh_token: refreshToken })
    storage.setToken(data.access_token)
    storage.setRefreshToken(data.refresh_token)  // token rotacionado
    return data.access_token
  } catch {
    return null
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config as AxiosRequestConfig & { _retry?: boolean }
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      if (!_refreshing) _refreshing = tryRefresh().finally(() => { _refreshing = null })
      const newToken = await _refreshing
      if (newToken) {
        if (original.headers) original.headers['Authorization'] = `Bearer ${newToken}`
        return apiClient(original)           // retry com novo token
      }
      // Refresh falhou → limpa tudo e redireciona para login
      storage.removeToken(); storage.removeRefreshToken()
      storage.removeUser(); storage.removeTenantColors()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)

export default apiClient
```

> **Regra:** Nunca use `axios` diretamente nos componentes. Importe sempre `apiClient` para garantir o interceptor de refresh.

### AuthContext

O `AuthContext` gerencia o usuário autenticado **e** as cores do tenant (recebidas no login — ver `06-backend-patterns.md` seção 8). O estado é persistido no `localStorage` via `utils/storage.ts`.

```typescript
// src/types/index.ts — interfaces canônicas
export interface User {
  id: number;
  name: string;
  email: string;
  role: string;
  is_admin: boolean;
  tenant_id: number;
  theme_mode: 'light' | 'dark';
  accessibility_level: 'regular' | 'AA' | 'AAA';
  avatar_url?: string | null;
}

export interface ColorRow {
  color_schema_mode: 'default' | 'custom';
  theme_mode: 'light' | 'dark';
  accessibility_level: 'regular' | 'AA' | 'AAA';
  color1: string; color2: string; color3: string; color4: string; color5: string;
  on_color1: string; on_color2: string; on_color3: string; on_color4: string; on_color5: string;
  on_gradient_1_2: string; on_gradient_2_3: string; on_gradient_3_4: string;
  on_gradient_4_5: string; on_gradient_5_1: string;
}

export interface TenantColorsPayload {
  color_schema_mode: 'default' | 'custom';
  colors: ColorRow[];  // 12 linhas — todas as combinações
}
```

```typescript
// src/contexts/AuthContext.tsx
import React, { createContext, useContext, useState, useEffect } from 'react';
import apiClient from '../services/apiClient';
import { storage } from '../utils/storage';
import type { User, ColorRow, TenantColorsPayload } from '../types';

interface AuthState {
  user: User | null;
  tenantColors: TenantColorsPayload | null;
  isAuthenticated: boolean;
}

interface AuthContextType extends AuthState {
  login: (token: string, userData: User, tenantColors: TenantColorsPayload) => void;
  logout: () => Promise<void>;
  updateUser: (partial: Partial<User>) => void;
  updateTenantColors: (colors: TenantColorsPayload) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<AuthState>({
    user: storage.getUser(),
    tenantColors: storage.getTenantColors(),
    isAuthenticated: !!storage.getToken(),
  });

  const login = (token: string, userData: User, tenantColors: TenantColorsPayload) => {
    storage.setToken(token);
    storage.setUser(userData);
    storage.setTenantColors(tenantColors);
    setState({ user: userData, tenantColors, isAuthenticated: true });
  };

  const logout = async () => {
    try { await apiClient.post('/auth/logout'); } catch { /* silent */ }
    storage.clear();
    setState({ user: null, tenantColors: null, isAuthenticated: false });
    window.location.href = '/login';
  };

  const updateUser = (partial: Partial<User>) => {
    setState(prev => {
      const updated = { ...prev.user!, ...partial };
      storage.setUser(updated);
      return { ...prev, user: updated };
    });
  };

  const updateTenantColors = (colors: TenantColorsPayload) => {
    storage.setTenantColors(colors);
    setState(prev => ({ ...prev, tenantColors: colors }));
  };

  return (
    <AuthContext.Provider value={{ ...state, login, logout, updateUser, updateTenantColors }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
};
```

```typescript
// src/utils/storage.ts — helper centralizado de localStorage
import type { User, TenantColorsPayload } from '../types';

export const storage = {
  getToken:        () => localStorage.getItem('access_token'),
  setToken:        (t: string) => localStorage.setItem('access_token', t),
  getUser:         (): User | null => { const s = localStorage.getItem('user_data'); return s ? JSON.parse(s) : null; },
  setUser:         (u: User) => localStorage.setItem('user_data', JSON.stringify(u)),
  getTenantColors: (): TenantColorsPayload | null => { const s = localStorage.getItem('tenant_colors'); return s ? JSON.parse(s) : null; },
  setTenantColors: (c: TenantColorsPayload) => localStorage.setItem('tenant_colors', JSON.stringify(c)),
  clear:           () => ['access_token', 'user_data', 'tenant_colors'].forEach(k => localStorage.removeItem(k)),
};
```

## 🛡️ 2. ProtectedRoute

Nenhuma página de negócio deve ser acessível sem autenticação. Use o componente `ProtectedRoute` para blindar as rotas.

```typescript
// src/components/ProtectedRoute.tsx
import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

interface ProtectedRouteProps {
  requiredRole?: string;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ requiredRole }) => {
  const { isAuthenticated, user } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (requiredRole && user?.role !== requiredRole && user?.role !== 'admin') {
    return <Navigate to="/unauthorized" replace />;
  }

  return <Outlet />;
};
```

### Uso no App.tsx

```typescript
// src/App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { Settings } from './pages/Settings';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />

        {/* Rotas Protegidas */}
        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/dashboard" element={<Dashboard />} />
        </Route>

        {/* Rotas Protegidas com Role */}
        <Route element={<ProtectedRoute requiredRole="admin" />}>
          <Route path="/settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

## 🎨 3. ThemeContext (Light/Dark + Acessibilidade + Cores do Tenant)

O `ThemeContext` é responsável por:
1. Alternar `light` / `dark` (classe no `<html>`) e persistir no backend.
2. Gerenciar `schemaMode` (`default` / `custom`) para as cores do tenant.
3. Gerenciar `accessibilityLevel` (`regular` / `AA` / `AAA`) conforme preferência do usuário.
4. Aplicar as CSS Custom Properties no DOM via `useColorApplication`.

> **Hook de uso:** `useTheme` está em `src/contexts/useTheme.ts` — arquivo separado do `ThemeContext.tsx`.

```typescript
// src/contexts/ThemeContext.tsx
import React, { createContext, useState, useEffect, useCallback } from 'react';
import apiClient from '../services/apiClient';
import { useAuth } from './AuthContext';
import { applyColorsToDOM } from '../hooks/useColorApplication';
import type { ColorRow } from '../types';

export type ThemeMode = 'light' | 'dark';
export type SchemaMode = 'default' | 'custom';
export type AccessibilityLevel = 'regular' | 'AA' | 'AAA';

export interface ThemeContextValue {
  themeMode: ThemeMode;
  schemaMode: SchemaMode;
  accessibilityLevel: AccessibilityLevel;
  colors: ColorRow[];                           // todas as 12 linhas em memória
  setThemeMode: (m: ThemeMode) => Promise<void>;
  setSchemaMode: (m: SchemaMode) => void;
  setAccessibilityLevel: (l: AccessibilityLevel) => Promise<void>;
  toggleTheme: () => Promise<void>;
}

export const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, tenantColors, updateUser } = useAuth();

  const [themeMode, setThemeModeState] = useState<ThemeMode>(user?.theme_mode ?? 'light');
  const [schemaMode, setSchemaModeState] = useState<SchemaMode>(
    tenantColors?.color_schema_mode ?? 'default'
  );
  const [accessibilityLevel, setAccessibilityLevelState] = useState<AccessibilityLevel>(
    user?.accessibility_level ?? 'regular'
  );
  const colors = tenantColors?.colors ?? [];

  // Aplica classe dark/light no <html> e injeta CSS vars do tenant
  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove('light', 'dark');
    root.classList.add(themeMode);

    const activeRow = colors.find(c =>
      c.color_schema_mode === schemaMode &&
      c.theme_mode         === themeMode &&
      c.accessibility_level === accessibilityLevel
    );
    if (activeRow) applyColorsToDOM(activeRow);
  }, [themeMode, schemaMode, accessibilityLevel, colors]);

  const setThemeMode = useCallback(async (m: ThemeMode) => {
    setThemeModeState(m);
    updateUser({ theme_mode: m });
    try { await apiClient.patch('/users/me/preferences', { theme_mode: m }); } catch { /* silent */ }
  }, [updateUser]);

  const setAccessibilityLevel = useCallback(async (l: AccessibilityLevel) => {
    setAccessibilityLevelState(l);
    updateUser({ accessibility_level: l });
    try { await apiClient.patch('/users/me/preferences', { accessibility_level: l }); } catch { /* silent */ }
  }, [updateUser]);

  const toggleTheme = useCallback(
    () => setThemeMode(themeMode === 'light' ? 'dark' : 'light'),
    [themeMode, setThemeMode]
  );

  const setSchemaMode = (m: SchemaMode) => setSchemaModeState(m);

  return (
    <ThemeContext.Provider value={{
      themeMode, schemaMode, accessibilityLevel, colors,
      setThemeMode, setSchemaMode, setAccessibilityLevel, toggleTheme,
    }}>
      {children}
    </ThemeContext.Provider>
  );
};
```

```typescript
// src/contexts/useTheme.ts — hook separado (evita importar ThemeContext em todo lugar)
import { useContext } from 'react';
import { ThemeContext } from './ThemeContext';

export const useTheme = () => {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
};
```

## 🧭 4. Padrão de Roteamento e Abas (Tabs)

Para garantir a melhor experiência do usuário (UX), o frontend **não deve usar estado local (`useState`) para controlar abas principais**. O uso de estado quebra funcionalidades nativas do navegador como "Abrir em nova aba", "Voltar", compartilhamento de URL e bookmarks.

A abordagem obrigatória é **Rotas Dedicadas por Aba** usando o React Router.

### Convenção de URLs

```text
/[modulo]                    → Página principal (lista/dashboard)
/[modulo]/[id]               → Detalhe do item (aba padrão)
/[modulo]/[id]/[aba]         → Aba específica do detalhe
```

### Exemplo de Implementação

```tsx
// src/pages/clientes/ClienteLayout.tsx
import { Outlet, NavLink, useParams } from 'react-router-dom';

export const ClienteLayout = () => {
  const { id } = useParams();

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex space-x-8 px-6" aria-label="Tabs">
          <NavLink
            to={`/clientes/${id}`}
            end
            className={({ isActive }) =>
              `py-4 px-1 border-b-2 font-medium text-sm ${
                isActive
                  ? 'border-primary text-primary'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`
            }
          >
            Resumo
          </NavLink>
          <NavLink
            to={`/clientes/${id}/pedidos`}
            className={({ isActive }) =>
              `py-4 px-1 border-b-2 font-medium text-sm ${
                isActive
                  ? 'border-primary text-primary'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`
            }
          >
            Pedidos
          </NavLink>
          <NavLink
            to={`/clientes/${id}/historico`}
            className={({ isActive }) =>
              `py-4 px-1 border-b-2 font-medium text-sm ${
                isActive
                  ? 'border-primary text-primary'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`
            }
          >
            Histórico
          </NavLink>
        </nav>
      </div>

      {/* O conteúdo da aba específica será renderizado aqui */}
      <div className="p-6 flex-1 overflow-auto">
        <Outlet />
      </div>
    </div>
  );
};
```

### Configuração no Router

```tsx
// src/App.tsx
<Route path="/clientes/:id" element={<ClienteLayout />}>
  <Route index element={<ClienteResumoTab />} />
  <Route path="pedidos" element={<ClientePedidosTab />} />
  <Route path="historico" element={<ClienteHistoricoTab />} />
</Route>
```

## 🖼️ 5. Biblioteca de Ícones

A biblioteca padrão e obrigatória para ícones no projeto é o **Phosphor Icons** (`@phosphor-icons/react`).

### Por que Phosphor Icons?
Diferente de outras bibliotecas, o Phosphor oferece **6 pesos visuais** para o mesmo ícone (`thin`, `light`, `regular`, `bold`, `fill`, `duotone`). Isso permite uma flexibilidade de design excepcional sem precisar misturar bibliotecas diferentes.

### Padrão de Uso

- **Sidebar / Menus:** `weight="regular"` ou `weight="light"`
- **Títulos / Headers:** `weight="bold"`
- **Estados Ativos / Selecionados:** `weight="fill"`
- **Dashboards / Ilustrações:** `weight="duotone"`

```tsx
import { Users, ChartLineUp, CheckCircle } from '@phosphor-icons/react';

// Exemplo em um menu lateral (inativo vs ativo)
<div className="flex items-center gap-2">
  <Users size={24} weight={isActive ? "fill" : "regular"} className={isActive ? "text-primary" : "text-gray-500"} />
  <span>Clientes</span>
</div>

// Exemplo em um card de dashboard
<div className="bg-surface p-4 rounded-lg">
  <ChartLineUp size={32} weight="duotone" className="text-accent mb-2" />
  <h3 className="text-lg font-bold">Vendas do Mês</h3>
</div>
```


## 🏗️ 6. AppShell — Layout Principal

Todas as rotas protegidas são envolvidas pelo `AppShell`, que compõe `<Sidebar>` + `<main>`. **Nunca renderize a Sidebar diretamente dentro de uma página.**

```tsx
// src/components/AppShell.tsx
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';

export const AppShell: React.FC = () => (
  <div className="flex h-screen overflow-hidden bg-gray-100 dark:bg-gray-950">
    <Sidebar />
    <main className="flex-1 overflow-y-auto">
      <Outlet />
    </main>
  </div>
);
```

```tsx
// src/App.tsx — roteamento com AppShell
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AppShell } from './components/AppShell';
import { LoginPage } from './pages/LoginPage';
import { HomePage } from './pages/HomePage';
import { ProfilePage } from './pages/ProfilePage';
import { ColorSettingsPage } from './pages/ColorSettingsPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<AppShell />}>
            <Route path="/" element={<Navigate to="/home" replace />} />
            <Route path="/home" element={<HomePage />} />
            <Route path="/perfil" element={<ProfilePage />} />
            <Route path="/configuracoes/cores" element={<ColorSettingsPage />} />
            {/* Módulos do projeto — adicionar aqui em ordem alfabética */}
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

## 🗂️ 7. Sidebar Component

A Sidebar possui **6 regiões fixas**, nesta ordem vertical:

1. **Header (Logo + Nome)** — logo quadrado com `var(--gradient-1-2)` + nome da aplicação + botão collapse na borda direita
2. **Seção Principal** — label `PRINCIPAL` + `Home` sempre primeiro; demais módulos em **ordem alfabética**; ícones Phosphor obrigatórios
3. **Seção Configurações** (admin only) — botão Gear → Flyout com sub-páginas de admin
4. **Spacer** — `flex: 1` empurra o footer para baixo
5. **Footer** — segmented control Light/Dark + Configurações (admin) + separador + Profile
6. **Profile (bottom)** — avatar `color1→color2` + nome + email; clicável → Flyout com "Meu Perfil" e "Sair da conta"

> **Importante:** a Sidebar usa um **Design System próprio de 6 tokens** (Header, Surface, Content, Muted, Overlay — ver `08-design-system.md`), fixos e independentes das cores do tenant. O avatar é a única exceção — usa `color1→color2` do tenant.

### Selected state — usa CSS vars do tenant:

| Elemento | Valor |
|---|---|
| Background | `var(--color-1)` |
| Texto/ícone | `var(--on-color-1)` |

### Collapsed state:
- Header: logo centralizado + botão expand na borda direita
- Nav: ícones centrados + **tooltip com label** aparece à direita no hover
- Footer: ícone do modo atual (sol/lua) + avatar centralizado

### Flyouts — dark mode:
Todo `<Flyout>` recebe `isDark={isDark}` para aplicar fundo, borda e sombra corretos. `<FlyoutItem>` também recebe `isDark`. Flyouts fecham com **Escape key** além do clique fora.

### Regra de adição de módulos:

```tsx
// ── Dentro de <nav> na seção Principal — adicionar em ordem alfabética:
<NavItem to="/clientes" icon={Users}   label="Clientes"  collapsed={collapsed} ... />
<NavItem to="/produtos" icon={Package} label="Produtos"  collapsed={collapsed} ... />
// Home sempre primeiro, resto A→Z
```

### Ícones Phosphor:

- Item normal: `weight="regular"`
- Item ativo: `weight="fill"`
- Gear (Settings): `weight="fill"` quando flyout aberto ou rota ativa, `weight="regular"` quando fechado

```tsx
// src/components/Sidebar.tsx — tokens e estrutura de referência (simplificada)
import { House, Palette, User, SignOut, Gear, CaretRight, CaretLeft, Sun, Moon } from '@phosphor-icons/react'
import { useAuth } from '../contexts/AuthContext'
import { useTheme } from '../contexts/useTheme'

// ── Tokens fixos da Sidebar (independentes do tenant) ──
const SB = {
  header:   { light: '#E2E8F0', dark: '#161929' },  // header (logo+nome)
  surface:  { light: '#F8FAFC', dark: '#1E2233' },  // body da sidebar
  content:  { light: '#1E293B', dark: '#F1F5F9' },  // texto e ícones
  muted:    { light: '#475569', dark: '#94A3B8' },  // labels, ícones de footer
  overlay:  { light: '#E2E8F0', dark: '#252B42' },  // hover row, segmented control bg
} as const

export default function Sidebar() {
  const { themeMode, toggleTheme, colors, schemaMode } = useTheme()
  const { user, logout } = useAuth()
  const isDark = themeMode === 'dark'

  // Avatar: único elemento com cores do tenant (gradiente color1→color2, scheme light)
  const scheme = colors.find(c =>
    c.color_schema_mode === schemaMode && c.theme_mode === 'light' && c.accessibility_level === 'regular'
  )
  const avatarBg = scheme
    ? `linear-gradient(135deg, ${scheme.color1}, ${scheme.color2})`
    : 'var(--gradient-1-2)'

  return (
    <aside style={{
      background: isDark ? SB.surface.dark : SB.surface.light,
      boxShadow: isDark ? '2px 0 16px rgba(0,0,0,.35)' : '2px 0 8px rgba(0,0,0,.06)',
      /* ... */
    }}>

      {/* ── 1. HEADER: Logo + Nome ── */}
      {/* background: SB.header; logo div com var(--gradient-1-2); app name text */}
      {/* botão collapse position:absolute right:-13 */}

      {/* ── 2. NAV PRINCIPAL ── */}
      {/* Label "PRINCIPAL" (uppercase, muted) + NavItems com Tooltip no collapsed */}

      {/* ── 3. Spacer ── */}
      {/* <div style={{ flex: 1 }} /> */}

      {/* ── 4. FOOTER ── */}
      {/* Segmented control Light/Dark (expandido) | ícone modo atual (colapsado) */}
      {/* FooterBtn Configurações → Flyout isDark={isDark} (admin only) */}
      {/* Separador 1px */}
      {/* Profile button → Flyout isDark={isDark}: "Meu Perfil" + "Sair da conta" */}

    </aside>
  )
}
```


## 🔐 8. Login Page — Canvas Animado + Glassmorphism

> **Referência obrigatória**: `gus-pulse/services/frontend-app/src/` — usar exatamente esta arquitetura.
>
> Design: canvas com partículas em movimento (fundo escuro), card glassmorphism centralizado, animação de entrada com `framer-motion`. **Não usar** o padrão antigo de dois painéis com gradiente.
>
> Pacote adicional: `npm install framer-motion`

```tsx
// src/components/QuantumBackground.tsx
// Canvas animado com partículas — referência: gus-pulse QuantumBackground.tsx
// As cores das partículas são lidas das CSS Custom Properties do tenant no init.
import { useEffect, useRef } from 'react'

interface Particle { x: number; y: number; vx: number; vy: number; radius: number; color: string }

export default function QuantumBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Usa as cores da marca via CSS Custom Properties (carregadas pelo useColorApplication)
    const style = getComputedStyle(document.documentElement)
    const brandColors = [
      style.getPropertyValue('--color-1').trim() || '#297BFF',
      style.getPropertyValue('--color-2').trim() || '#0CC02A',
      style.getPropertyValue('--color-3').trim() || '#005F61',
      style.getPropertyValue('--color-4').trim() || '#6F74B8',
    ]

    const resizeCanvas = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight }
    resizeCanvas()

    const particles: Particle[] = Array.from({ length: 80 }, () => ({
      x: Math.random() * canvas.width, y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 0.5, vy: (Math.random() - 0.5) * 0.5,
      radius: Math.random() * 2 + 1,
      color: brandColors[Math.floor(Math.random() * brandColors.length)],
    }))

    let animId: number
    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      particles.forEach(p => {
        p.x += p.vx; p.y += p.vy
        if (p.x < 0 || p.x > canvas.width) p.vx *= -1
        if (p.y < 0 || p.y > canvas.height) p.vy *= -1
        ctx.beginPath(); ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
        ctx.fillStyle = p.color; ctx.fill()
      })
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x, dy = particles[i].y - particles[j].y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < 150) {
            ctx.beginPath()
            ctx.strokeStyle = `rgba(255,255,255,${0.1 * (1 - dist / 150)})`
            ctx.lineWidth = 1; ctx.moveTo(particles[i].x, particles[i].y)
            ctx.lineTo(particles[j].x, particles[j].y); ctx.stroke()
          }
        }
      }
      animId = requestAnimationFrame(animate)
    }
    animate()
    window.addEventListener('resize', resizeCanvas)
    return () => { cancelAnimationFrame(animId); window.removeEventListener('resize', resizeCanvas) }
  }, [])

  return (
    <canvas ref={canvasRef} className="fixed top-0 left-0 w-full h-full"
      style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)' }} />
  )
}
```

```tsx
// src/pages/LoginPage.tsx
// Glassmorphism card sobre canvas animado — referência: gus-pulse LoginPage.tsx
import { motion } from 'framer-motion'
import React, { useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import apiClient from '../services/apiClient'
import QuantumBackground from '../components/QuantumBackground'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const { login, isAuthenticated } = useAuth()
  const location = useLocation()

  // ?etl=1 → usuário veio do ETL; o path desejado está no sessionStorage do ETL
  const isEtlRedirect = new URLSearchParams(location.search).get('etl') === '1'

  if (isAuthenticated) return <Navigate to="/home" replace />

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setError(''); setIsLoading(true)
    try {
      await login(email, password)

      if (isEtlRedirect) {
        // Gera OTT e abre a raiz do ETL — o ETL lê sessionStorage para o deep link
        const { data } = await apiClient.post<{ ott: string; etl_url: string }>('/auth/ott')
        window.location.href = `${data.etl_url}?ott=${data.ott}`
        return
      }

      // Login normal → home do frontend principal
    } catch { setError('Falha ao entrar. Tente novamente.')
    } finally { setIsLoading(false) }
  }

  const inputStyle = { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }
  const focusIn  = (e: React.FocusEvent<HTMLInputElement>) => {
    e.target.style.borderColor = 'var(--color-1)'
    e.target.style.boxShadow = '0 0 0 4px color-mix(in srgb, var(--color-1) 20%, transparent)'
  }
  const focusOut = (e: React.FocusEvent<HTMLInputElement>) => {
    e.target.style.borderColor = 'rgba(255,255,255,0.1)'; e.target.style.boxShadow = 'none'
  }

  return (
    <div className="min-h-screen relative overflow-hidden">
      <QuantumBackground />
      <div className="relative z-10 flex min-h-screen items-center justify-center p-8">
        <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className="w-full max-w-[480px] rounded-[32px] p-12 backdrop-blur-[20px]"
          style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)',
            boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)' }}>

          {/* Logo + cabeçalho */}
          <div className="text-center mb-10">
            <div className="w-20 h-20 mx-auto mb-6 rounded-[20px] flex items-center justify-center"
              style={{ background: 'var(--gradient-1-2)', boxShadow: '0 10px 30px rgba(0,0,0,0.3)' }}>
              {/* Substituir pelo logo SVG real do projeto */}
              <span className="text-3xl font-black" style={{ color: 'var(--on-gradient-1-2)' }}>
                {{ PROJECT_PREFIX }}
              </span>
            </div>
            <h1 className="text-white text-[2rem] font-bold mb-2">{{ PROJECT_NAME }}</h1>
            <p className="text-slate-400 text-base mb-8">{{ PROJECT_DESCRIPTION_SHORT }}</p>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="mb-6">
              <label className="block text-slate-200 text-sm font-medium mb-2">Email</label>
              <input type="email" autoComplete="email" required value={email} disabled={isLoading}
                onChange={e => setEmail(e.target.value)} onFocus={focusIn} onBlur={focusOut}
                className="w-full px-5 py-4 rounded-2xl text-white text-base focus:outline-none transition-all duration-300"
                style={inputStyle} placeholder="voce@empresa.com" />
            </div>
            <div className="mb-8">
              <label className="block text-slate-200 text-sm font-medium mb-2">Senha</label>
              <input type="password" autoComplete="current-password" required value={password} disabled={isLoading}
                onChange={e => setPassword(e.target.value)} onFocus={focusIn} onBlur={focusOut}
                className="w-full px-5 py-4 rounded-2xl text-white text-base focus:outline-none transition-all duration-300"
                style={inputStyle} placeholder="••••••••" />
            </div>

            {error && (
              <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
                className="mb-6 p-3 rounded-lg bg-red-500/20 border border-red-500/30">
                <p className="text-sm text-red-300">{error}</p>
              </motion.div>
            )}

            <button type="submit" disabled={isLoading}
              className="w-full px-4 py-4 rounded-2xl text-base font-semibold transition-all duration-300 disabled:opacity-50 hover:-translate-y-0.5"
              style={{ background: 'var(--gradient-1-2)', color: 'var(--on-gradient-1-2)',
                boxShadow: '0 10px 25px rgba(0,0,0,0.3)' }}>
              {isLoading ? 'Entrando...' : 'Entrar'}
            </button>
          </form>
        </motion.div>
      </div>
    </div>
  )
}
```

## 👤 9. Profile Update Page

Página simples de edição de perfil (nome + senha). Acessível via `/perfil` e pelo ícone de usuário no bottom da Sidebar.

```tsx
// src/pages/ProfilePage.tsx
import { useState } from 'react';
import { User, Lock } from '@phosphor-icons/react';
import { useAuth } from '../contexts/AuthContext';
import apiClient from '../services/apiClient';

export const ProfilePage: React.FC = () => {
  const { user } = useAuth();
  const [name, setName] = useState(user?.name ?? '');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [success, setSuccess] = useState('');
  const [error, setError] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setSuccess(''); setError('');
    try {
      await apiClient.put('/users/me', {
        name,
        ...(currentPassword && newPassword ? { current_password: currentPassword, new_password: newPassword } : {}),
      });
      setSuccess('Perfil atualizado com sucesso.');
      setCurrentPassword(''); setNewPassword('');
    } catch {
      setError('Erro ao salvar. Verifique os dados e tente novamente.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="p-6 lg:p-10 max-w-xl">
      <div className="flex items-center gap-3 mb-8">
        <User size={28} weight="duotone" style={{ color: 'var(--color-1)' }} />
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Meu Perfil</h1>
      </div>

      <form onSubmit={handleSave} className="space-y-5 bg-white dark:bg-gray-900 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-800">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Nome</label>
          <input value={name} onChange={e => setName(e.target.value)}
            className="w-full px-3 py-2.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2" />
        </div>

        <hr className="border-gray-100 dark:border-gray-800" />
        <p className="text-xs font-medium text-gray-400 uppercase tracking-wider flex items-center gap-2">
          <Lock size={14} /> Alterar senha (opcional)
        </p>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Senha atual</label>
          <input type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)}
            className="w-full px-3 py-2.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Nova senha</label>
          <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)}
            className="w-full px-3 py-2.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2" />
        </div>

        {success && <p className="text-sm text-green-600 dark:text-green-400">{success}</p>}
        {error   && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        <button type="submit" disabled={isSaving}
          className="px-5 py-2.5 rounded-lg text-sm font-semibold disabled:opacity-60 transition-opacity"
          style={{ background: 'var(--gradient-1-2)', color: 'var(--on-gradient-1-2)' }}>
          {isSaving ? 'Salvando…' : 'Salvar alterações'}
        </button>
      </form>
    </div>
  );
};
```


## 🍞 10. Sistema de Notificações — sonner

`sonner` é a biblioteca padrão de toast para este projeto. Zero-config, React-first, acessível.

**Instalação:**
```
npm install sonner
```

**Configuração (App.tsx):**
```tsx
import { Toaster } from 'sonner'

// Dentro do JSX root (fora do AuthProvider para ser global):
<Toaster position="top-right" richColors closeButton />
```

**Uso em qualquer componente:**
```tsx
import { toast } from 'sonner'

// Tipos disponíveis:
toast.success('Usuário salvo com sucesso!')
toast.error('Erro ao salvar. Tente novamente.')
toast.warning('Sessão expirando em breve.')
toast.info('Configurações atualizadas.')
toast.loading('Salvando...')   // use toast.dismiss(id) para fechar

// Com promise (loading → success/error automático):
toast.promise(apiClient.post('/users', data), {
  loading: 'Criando usuário...',
  success: 'Usuário criado!',
  error: 'Erro ao criar usuário.',
})
```

> **Regra:** Substitua todos os `useState` de `success/error` por `toast.*` nos componentes novos.
> Componentes legados (ex: `ProfilePage`) podem ser migrados incrementalmente.

---

## 📝 11. Validação de Formulários — react-hook-form + zod

`react-hook-form` gerencia o estado dos inputs sem re-renders desnecessários.
`zod` define e valida o schema de forma tipada — o mesmo schema serve como tipo TypeScript.

**Como funciona:**
1. Define o schema com `zod` → automaticamente vira o tipo TypeScript via `z.infer`
2. Conecta ao `useForm` via `zodResolver` — validação acontece no submit
3. Cada `<input>` recebe `{...register("campo")}` — sem `onChange` manual
4. `formState.errors` contém os erros por campo, prontos para exibir

**Instalação:**
```
npm install react-hook-form zod @hookform/resolvers
```

**Exemplo canônico:**
```tsx
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { toast } from 'sonner'

// 1. Schema = validação + tipo TypeScript
const schema = z.object({
  name:  z.string().min(2, 'Nome deve ter ao menos 2 caracteres'),
  email: z.string().email('Email inválido'),
  role:  z.enum(['view', 'user', 'admin']),
})
type FormData = z.infer<typeof schema>  // { name: string; email: string; role: 'view'|'user'|'admin' }

// 2. Componente
export function CreateUserForm() {
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
  })

  const onSubmit = async (data: FormData) => {
    await toast.promise(apiClient.post('/users', data), {
      loading: 'Criando usuário...',
      success: 'Usuário criado!',
      error:   'Erro ao criar usuário.',
    })
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div>
        <input {...register('name')} placeholder="Nome" className={inputCls} />
        {errors.name && <p className="text-xs text-red-500">{errors.name.message}</p>}
      </div>
      <div>
        <input {...register('email')} type="email" placeholder="Email" className={inputCls} />
        {errors.email && <p className="text-xs text-red-500">{errors.email.message}</p>}
      </div>
      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Salvando...' : 'Criar'}
      </button>
    </form>
  )
}
```

---

## 🔃 12. Data Fetching — TanStack Query (React Query)

`@tanstack/react-query` gerencia o **estado do servidor**: cache, loading, refetch, invalidação.
Substitui o padrão `useState + useEffect + apiClient` para qualquer dado que vem da API.

**Como funciona:**
- `useQuery` busca dados e mantém cache automático. Se outro componente fizer a mesma query, usa o cache.
- `useMutation` executa operações (POST/PUT/DELETE) e permite invalidar o cache na conclusão.
- `QueryClient` é o gerenciador global — configurado uma vez no root.
- Dados ficam "frescos" por um tempo configurável (`staleTime`). Após isso, refetch em background.

**Instalação:**
```
npm install @tanstack/react-query
```

**Configuração (main.tsx):**
```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 1000 * 60 * 5 } }  // 5 min de cache
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={queryClient}>
    <App />
  </QueryClientProvider>
)
```

**Exemplo — useQuery (buscar dados):**
```tsx
import { useQuery } from '@tanstack/react-query'
import apiClient from '../services/apiClient'
import type { User } from '../types'

function useUsers() {
  return useQuery({
    queryKey: ['users'],          // chave de cache — mesma key = mesmo cache
    queryFn: () => apiClient.get<{ items: User[]; total: number }>('/users').then(r => r.data),
  })
}

export function UsersList() {
  const { data, isLoading, error } = useUsers()

  if (isLoading) return <p>Carregando...</p>
  if (error)     return <p>Erro ao carregar usuários.</p>

  return <ul>{data?.items.map(u => <li key={u.id}>{u.name}</li>)}</ul>
}
```

**Exemplo — useMutation (criar/editar/deletar):**
```tsx
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

function useCreateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateUserPayload) => apiClient.post('/users', data).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })  // revalida a lista
      toast.success('Usuário criado!')
    },
    onError: () => toast.error('Erro ao criar usuário.'),
  })
}

// Uso no componente:
const createUser = useCreateUser()
<button onClick={() => createUser.mutate(formData)} disabled={createUser.isPending}>
  {createUser.isPending ? 'Criando...' : 'Criar'}
</button>
```

> **Regra:** Use `useQuery` para qualquer dado que vem da API e é exibido em UI.
> Use `useState + useEffect` apenas para estado local puro (sem servidor).

---

## 🔑 13. ETL Frontend — Padrão OttBootstrap

O frontend ETL não possui login próprio. A autenticação é feita via **One-Time Token (OTT)** gerado pelo backend após login no frontend principal. O componente `OttBootstrap` encapsula toda essa lógica.

### Fluxo de acesso direto (deep link)

Quando o usuário acessa diretamente uma URL do ETL (ex: `/pipelines`) sem sessão ativa:

1. ETL salva o path atual em `sessionStorage` (origin do ETL) e redireciona para `/login?etl=1`
2. Usuário loga → `LoginPage` vê `?etl=1` → chama `POST /auth/ott` → redireciona para raiz do ETL com `?ott=<uuid>`
3. `OttBootstrap` detecta `?ott`, remove da URL imediatamente, troca pelo token, lê `sessionStorage`
4. `useLayoutEffect` navega para o path original antes do primeiro paint — sem flash de tela

### OttBootstrap — estrutura canônica

```tsx
// src/App.tsx (frontend-etl)
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from './contexts/AuthContext'
import apiClient from './services/apiClient'
import { storage } from './utils/storage'

const MAIN_FRONTEND = window.location.port === '3345'
  ? 'http://localhost:5178'
  : 'http://localhost:5177'

const ETL_RETURN_PATH_KEY = 'etl_return_path'

function OttBootstrap({ children }: { children: React.ReactNode }) {
  const { setSession } = useAuth()
  const navigate = useNavigate()           // disponível pois BrowserRouter está no main.tsx
  const [ready, setReady] = useState(false)
  const ran = useRef(false)                // guard: OTT é de uso único
  const returnPathRef = useRef<string | null>(null)

  useEffect(() => {
    if (ran.current) return
    ran.current = true

    const ott = new URLSearchParams(window.location.search).get('ott')

    if (ott) {
      // Remove OTT da URL antes mesmo de fazer a troca (segurança)
      window.history.replaceState({}, '', window.location.pathname)
      apiClient.post('/auth/exchange-ott', { ott })
        .then(({ data }) => {
          setSession(data.access_token, data.user, data.tenant_colors)
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

    if (storage.getToken() && storage.getUser()) {
      setReady(true)
    } else {
      // Salva o path atual — sem expor URL/porta na barra de endereços
      sessionStorage.setItem(ETL_RETURN_PATH_KEY, window.location.pathname + window.location.search)
      window.location.href = `${MAIN_FRONTEND}/login?etl=1`
    }
  }, [setSession])

  // useLayoutEffect: navega antes do primeiro paint → sem flash da home page
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
```

### apiClient do ETL — 401 com deep link

```typescript
// src/services/apiClient.ts (frontend-etl)
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const req = error.config as AxiosRequestConfig & { _retry?: boolean }
    if (error.response?.status === 401 && !req._retry) {
      req._retry = true
      storage.removeToken(); storage.removeUser(); storage.removeTenantColors()
      // Preserva o path atual para restaurar após re-autenticação
      sessionStorage.setItem('etl_return_path', window.location.pathname + window.location.search)
      window.location.href = `${MAIN_FRONTEND}/login?etl=1`
    }
    return Promise.reject(error)
  },
)
```

### Por que `useLayoutEffect` e não `useEffect`?

`useEffect` roda **após** o browser pintar a tela — o usuário veria um flash da home page (`/`) antes de ser redirecionado. `useLayoutEffect` roda **antes** do paint, na fase de commit do React, eliminando o flash completamente.

> **Regra:** nunca use `?redirect=http://localhost:3344/path` na URL de login. Sempre use `?etl=1` + `sessionStorage` para manter as URLs limpas e sem exposição de porta ou token.
