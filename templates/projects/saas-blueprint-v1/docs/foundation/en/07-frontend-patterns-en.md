<!-- blueprint: db_changes=false seed_data=false -->
# 07. Frontend Code Patterns

This document defines the mandatory patterns for Frontend development in React (Vite + TypeScript).

## 🔒 1. AuthContext and apiClient (Axios)

The frontend **never** communicates directly with the Auth Service. All communication goes through the Backend. The JWT token must be automatically injected in all requests.

```typescript
// src/services/apiClient.ts
import axios from 'axios';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:{{ BACKEND_PORT }}/api/v1',
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default apiClient;
```

### AuthContext

The `AuthContext` trusts `localStorage` for the first render (no flicker) and then **verifies the token against the server** via `GET /users/me`. While the verification is in flight, `isValidating` is `true` and `ProtectedRoute` must render `<Loading />` instead of the protected UI. This prevents the "session leak" where a stale cached user briefly flashes on screen before the interceptor redirects to `/login` (e.g. after a DB rollback+migrate invalidates the token's `user_id`).

```typescript
// src/contexts/AuthContext.tsx
import React, { createContext, useContext, useState, useEffect } from 'react';
import apiClient from '../services/apiClient';

interface User { id: number; name: string; email: string; role: string; tenant_id: number; }

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  /**
   * `true` while the token from localStorage has not yet been confirmed by the
   * server via `GET /users/me`. During this window, `ProtectedRoute` must show
   * `<Loading />` — otherwise the previous session's UI would flash before the
   * redirect to `/login` (e.g. after a DB rollback+migrate).
   */
  isValidating: boolean;
}

interface AuthContextType extends AuthState {
  login: (token: string, userData: User) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function loadFromStorage(): AuthState {
  const token      = localStorage.getItem('access_token');
  const storedUser = localStorage.getItem('user_data');
  const user       = storedUser ? (JSON.parse(storedUser) as User) : null;
  const hasSession = !!token && !!user;
  // isValidating starts `true` if there's a cached session — must be confirmed server-side
  return { user, isAuthenticated: hasSession, isValidating: hasSession };
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<AuthState>(loadFromStorage);

  // Validates the token against the server on mount. On 401, the Axios
  // interceptor already clears the session and redirects to /login. Here we
  // just refresh the `user` with fresh data and release the UI.
  useEffect(() => {
    if (!state.isValidating) return;
    let cancelled = false;
    apiClient.get<User>('/users/me')
      .then(({ data }) => {
        if (cancelled) return;
        localStorage.setItem('user_data', JSON.stringify(data));
        setState(prev => ({ ...prev, user: data, isValidating: false }));
      })
      .catch(() => {
        // 401 was already handled by the interceptor (redirect). For other
        // errors (network/backend offline), release the UI keeping the cache.
        if (cancelled) return;
        setState(prev => ({ ...prev, isValidating: false }));
      });
    return () => { cancelled = true; };
  }, [state.isValidating]);

  const login = (token: string, userData: User) => {
    localStorage.setItem('access_token', token);
    localStorage.setItem('user_data', JSON.stringify(userData));
    setState({ user: userData, isAuthenticated: true, isValidating: false });
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user_data');
    setState({ user: null, isAuthenticated: false, isValidating: false });
    window.location.href = '/login';
  };

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
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

## 🛡️ 2. ProtectedRoute

No business page should be accessible without authentication. While `isValidating` is `true`, `ProtectedRoute` **must** render `<Loading />` — never the protected route's UI.

```typescript
// src/components/Loading.tsx — neutral screen shown during validation
export function Loading() {
  return (
    <div className="flex h-screen items-center justify-center bg-gray-100 dark:bg-gray-950">
      <p className="text-sm text-gray-400">Loading…</p>
    </div>
  );
}
```

```typescript
// src/components/ProtectedRoute.tsx
import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Loading } from './Loading';

export const ProtectedRoute: React.FC<{ requiredRole?: string }> = ({ requiredRole }) => {
  const { isAuthenticated, isValidating, user } = useAuth();
  if (isValidating) return <Loading />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (requiredRole && user?.role !== requiredRole && user?.role !== 'admin')
    return <Navigate to="/unauthorized" replace />;
  return <Outlet />;
};
```

## 🖼️ 5. Icon Library

The standard and mandatory library for icons is **Phosphor Icons** (`@phosphor-icons/react`).

Phosphor offers **6 visual weights** for the same icon (`thin`, `light`, `regular`, `bold`, `fill`, `duotone`).

### Usage Pattern

- **Sidebar / Menus:** `weight="regular"` or `weight="light"`
- **Titles / Headers:** `weight="bold"`
- **Active / Selected States:** `weight="fill"`
- **Dashboards / Illustrations:** `weight="duotone"`

```tsx
import { Users, ChartLineUp, CheckCircle } from '@phosphor-icons/react';

<Users size={24} weight={isActive ? "fill" : "regular"} className={isActive ? "text-primary" : "text-gray-500"} />
```

## 🏗️ 6. AppShell — Main Layout

All protected routes are wrapped by `AppShell`, which composes `<Sidebar>` + `<main>`. **Never render the Sidebar directly inside a page.**

```tsx
// src/components/AppShell.tsx
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';

export const AppShell: React.FC = () => (
  <div className="flex h-screen overflow-hidden bg-gray-100 dark:bg-gray-950">
    <Sidebar />
    <main className="flex-1 overflow-y-auto"><Outlet /></main>
  </div>
);
```

## 🗂️ 7. Sidebar Component

The Sidebar has **6 fixed regions**, in this vertical order:

1. **Header (Logo + Name)** — square logo with `var(--gradient-1-2)` + app name + collapse button on right edge
2. **Principal section** — `PRINCIPAL` label + `Home` always first; other modules in **alphabetical order**; Phosphor icons required
3. **Settings section** (admin only) — Gear button → Flyout with admin sub-pages
4. **Spacer** — `flex: 1` pushes footer to the bottom
5. **Footer** — Light/Dark segmented control + Settings (admin) + separator + Profile
6. **Profile (bottom)** — `color1→color2` avatar + name + email; clickable → Flyout with "My Profile" and "Sign Out"

> **Important:** the Sidebar uses its own **Design System of 6 fixed tokens** (Header, Surface, Content, Muted, Overlay — see `08-design-system.md`), fixed and independent of the tenant's colors. The avatar is the only exception — uses `color1→color2` from the tenant.

### Selected state — uses tenant CSS vars:

| Element | Value |
|---|---|
| Background | `var(--color-1)` |
| Text/icon | `var(--on-color-1)` |

### Collapsed state:
- Header: centered logo + expand button on right edge
- Nav: centered icons + **label tooltip** appears to the right on hover
- Footer: current mode icon (sun/moon) + centered avatar

### Flyouts — dark mode:
Every `<Flyout>` receives `isDark={isDark}` to apply correct background, border and shadow. `<FlyoutItem>` also receives `isDark`. Flyouts close with **Escape key** in addition to clicking outside.

### Adding modules:

```tsx
// ── Inside <nav> in the Principal section — add in alphabetical order:
<NavItem to="/clients"  icon={Users}   label="Clients"  collapsed={collapsed} ... />
<NavItem to="/products" icon={Package} label="Products" collapsed={collapsed} ... />
// Home always first, rest A→Z
```

### Phosphor icon weights:

- Normal item: `weight="regular"`
- Active item: `weight="fill"`
- Gear (Settings): `weight="fill"` when flyout open or route active, `weight="regular"` when closed

```tsx
// src/components/Sidebar.tsx — tokens and reference structure (simplified)
import { House, Palette, User, SignOut, Gear, CaretRight, CaretLeft, Sun, Moon } from '@phosphor-icons/react'

// ── Sidebar fixed tokens (independent of tenant) ──
const SB = {
  header:   { light: '#E2E8F0', dark: '#161929' },  // header (logo + name)
  surface:  { light: '#F8FAFC', dark: '#1E2233' },  // sidebar body
  content:  { light: '#1E293B', dark: '#F1F5F9' },  // text and icons
  muted:    { light: '#475569', dark: '#94A3B8' },  // labels, footer icons
  overlay:  { light: '#E2E8F0', dark: '#252B42' },  // hover row, segmented control bg
} as const

export default function Sidebar() {
  const { themeMode, toggleTheme, colors, schemaMode } = useTheme()
  const isDark = themeMode === 'dark'

  // Avatar: only element using tenant colors (gradient color1→color2, light scheme)
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
    }}>
      {/* 1. HEADER: Logo + App Name (background: SB.header) + collapse button */}
      {/* 2. NAV PRINCIPAL (label + NavItems with Tooltip when collapsed) */}
      {/* 3. Spacer */}
      {/* 4. FOOTER: Light/Dark segmented control | Settings → Flyout isDark | separator | Profile → Flyout isDark */}
    </aside>
  )
}
```

## 🔐 8. Login Page — Animated Canvas + Glassmorphism

> **Mandatory reference**: `gus-pulse/services/frontend-app/src/` — use exactly this architecture.
>
> Design: canvas with moving particles (dark background), centered glassmorphism card, entry animation with `framer-motion`.
>
> Additional package: `npm install framer-motion`

```tsx
// src/pages/LoginPage.tsx
import { motion } from 'framer-motion'
import { useState } from 'react'
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

  // ?etl=1 → user came from ETL; desired path is in the ETL's sessionStorage
  const isEtlRedirect = new URLSearchParams(location.search).get('etl') === '1'

  if (isAuthenticated) return <Navigate to="/home" replace />

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setError(''); setIsLoading(true)
    try {
      await login(email, password)

      if (isEtlRedirect) {
        // Generate OTT and open the ETL root — ETL reads sessionStorage for deep link
        const { data } = await apiClient.post<{ ott: string; etl_url: string }>('/auth/ott')
        window.location.href = `${data.etl_url}?ott=${data.ott}`
        return
      }

      // Normal login → main frontend home
    } catch { setError('Login failed. Please try again.')
    } finally { setIsLoading(false) }
  }

  return (
    <div className="min-h-screen relative overflow-hidden">
      <QuantumBackground />
      <div className="relative z-10 flex min-h-screen items-center justify-center p-8">
        <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className="w-full max-w-[480px] rounded-[32px] p-12 backdrop-blur-[20px]"
          style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)' }}>
          <div className="text-center mb-10">
            <div className="w-20 h-20 mx-auto mb-6 rounded-[20px] flex items-center justify-center"
              style={{ background: 'var(--gradient-1-2)' }}>
              <span className="text-3xl font-black" style={{ color: 'var(--on-gradient-1-2)' }}>
                {{ PROJECT_PREFIX }}
              </span>
            </div>
            <h1 className="text-white text-[2rem] font-bold mb-2">{{ PROJECT_NAME }}</h1>
          </div>
          <form onSubmit={handleSubmit}>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              className="w-full px-5 py-4 rounded-2xl text-white mb-6 focus:outline-none" placeholder="you@company.com" />
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              className="w-full px-5 py-4 rounded-2xl text-white mb-8 focus:outline-none" placeholder="••••••••" />
            {error && <p className="text-sm text-red-300 mb-4">{error}</p>}
            <button type="submit" disabled={isLoading}
              className="w-full py-4 rounded-2xl font-semibold"
              style={{ background: 'var(--gradient-1-2)', color: 'var(--on-gradient-1-2)' }}>
              {isLoading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>
        </motion.div>
      </div>
    </div>
  )
}
```

## 🔑 9. ETL Frontend — OttBootstrap Pattern

The ETL frontend has no login of its own. Authentication is done via **One-Time Token (OTT)** generated by the backend after login on the main frontend. The `OttBootstrap` component encapsulates this entire logic.

### Direct access flow (deep link)

When the user directly accesses an ETL URL (e.g. `/pipelines`) without an active session:

1. ETL saves the current path in `sessionStorage` (ETL's own origin) and redirects to `/login?etl=1`
2. User logs in → `LoginPage` sees `?etl=1` → calls `POST /auth/ott` → redirects to ETL root with `?ott=<uuid>`
3. `OttBootstrap` detects `?ott`, removes it from URL immediately, exchanges for token, reads `sessionStorage`
4. `useLayoutEffect` navigates to original path before first paint — no screen flash

### OttBootstrap — canonical structure

```tsx
// src/App.tsx (frontend-etl)
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

const MAIN_FRONTEND = window.location.port === '3345'
  ? 'http://localhost:5178'
  : 'http://localhost:5177'

const ETL_RETURN_PATH_KEY = 'etl_return_path'

function OttBootstrap({ children }: { children: React.ReactNode }) {
  const { setSession } = useAuth()
  const navigate = useNavigate()           // available because BrowserRouter is in main.tsx
  const [ready, setReady] = useState(false)
  const ran = useRef(false)                // guard: OTT is single-use
  const returnPathRef = useRef<string | null>(null)

  useEffect(() => {
    if (ran.current) return
    ran.current = true

    const ott = new URLSearchParams(window.location.search).get('ott')

    if (ott) {
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
      sessionStorage.setItem(ETL_RETURN_PATH_KEY, window.location.pathname + window.location.search)
      window.location.href = `${MAIN_FRONTEND}/login?etl=1`
    }
  }, [setSession])

  // useLayoutEffect: navigate before first paint → no home page flash
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

### Why `useLayoutEffect` and not `useEffect`?

`useEffect` runs **after** the browser paints — the user would see a flash of the home page (`/`) before the navigation. `useLayoutEffect` runs **before** the paint, in React's commit phase, completely eliminating the flash.

> **Rule:** never use `?redirect=http://localhost:3344/path` in the login URL. Always use `?etl=1` + `sessionStorage` to keep URLs clean and free of exposed ports or tokens.

---

## 🧭 4. Routing and Tab Pattern

Use **dedicated routes per tab** via React Router. Never use `useState` to control main tabs.

### URL Convention

```text
/[module]                    → Main page (list/dashboard)
/[module]/[id]               → Item detail (default tab)
/[module]/[id]/[tab]         → Specific detail tab
```
