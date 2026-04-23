import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { createPortal } from 'react-dom'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import { House, Palette, User, SignOut, Gear, CaretRight, CaretLeft, Sun, Moon, Article, FolderOpen, ShieldCheck, SquaresFour, ArrowSquareOut } from '@phosphor-icons/react'
import { useAuth } from '../contexts/AuthContext'
import { useTheme } from '../contexts/useTheme'
import apiClient from '../services/apiClient'

/* ── Design System Tokens — Sidebar ────────────────────────────────────────
   5 cores fixas da sidebar — independentes do sistema de cores do tenant.
   São tokens de estrutura de navegação, não de tema de produto.
   Referência: Sidebar Design System Color Palette (5 Core Colors).        */
const SB = {
  surface:  { light: '#F8FAFC', dark: '#1E2233' },  // fundo da sidebar
  header:   { light: '#E2E8F0', dark: '#161929' },  // fundo do header — tom distinto do surface
  content:  { light: '#1E293B', dark: '#F1F5F9' },  // texto e ícones
  muted:    { light: '#475569', dark: '#94A3B8' },  // labels de seção, secundário
  overlay:  { light: '#E2E8F0', dark: '#252B42' },  // hover row — mais escuro que surface
  // Selected item: usa CSS vars do tenant → var(--color-1) / var(--on-color-1)
} as const

type Mode = 'light' | 'dark'
/** Resolve token light/dark pelo themeMode atual */
function tk<T extends { light: string; dark: string }>(token: T, mode: Mode): string {
  return token[mode]
}

/* ── Flyout (portal) — abre à direita do elemento âncora ────────────────── */
interface FlyoutProps {
  anchorRef: React.RefObject<HTMLElement | null>
  open: boolean
  onClose: () => void
  children: React.ReactNode
  isDark?: boolean
  /** alignBottom: ancora a borda inferior do flyout na borda inferior do âncora (útil para footer) */
  alignBottom?: boolean
}
function Flyout({ anchorRef, open, onClose, children, isDark, alignBottom }: FlyoutProps) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    function onMouse(e: MouseEvent) {
      if (
        ref.current && !ref.current.contains(e.target as Node) &&
        anchorRef.current && !anchorRef.current.contains(e.target as Node)
      ) onClose()
    }
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', onMouse)
    document.addEventListener('keydown',   onKey)
    return () => {
      document.removeEventListener('mousedown', onMouse)
      document.removeEventListener('keydown',   onKey)
    }
  }, [open, onClose, anchorRef])

  if (!open || !anchorRef.current) return null
  const rect = anchorRef.current.getBoundingClientRect()
  const pos = alignBottom
    ? { bottom: window.innerHeight - rect.bottom, left: rect.right + 8 }
    : { top: Math.min(rect.top, window.innerHeight - 200), left: rect.right + 8 }

  const flyBg     = isDark ? '#1C2035' : '#ffffff'
  const flyBorder = isDark ? '1px solid rgba(255,255,255,0.10)' : '1px solid #e2e8f0'
  const flyShadow = isDark ? '0 8px 32px rgba(0,0,0,.50)' : '0 8px 32px rgba(0,0,0,.18)'

  return createPortal(
    <div ref={ref} style={{
      position: 'fixed', ...pos, zIndex: 9999,
      background: flyBg, borderRadius: 12,
      boxShadow: flyShadow, border: flyBorder,
      minWidth: 200, padding: '8px 0', animation: 'flyout-in .15s ease',
    }}>
      <style>{`@keyframes flyout-in{from{opacity:0;transform:translateX(-6px)}to{opacity:1;transform:none}}`}</style>
      {children}
    </div>,
    document.body,
  )
}

interface FlyoutItemProps {
  icon: React.ElementType; label: string; onClick: () => void
  danger?: boolean; isDark?: boolean
}
function FlyoutItem({ icon: Icon, label, onClick, danger, isDark }: FlyoutItemProps) {
  const [hov, setHov] = useState(false)
  const hovBg  = hov ? (danger ? (isDark ? 'rgba(239,68,68,0.15)' : '#fef2f2') : (isDark ? '#252B42' : '#f8fafc')) : 'transparent'
  const color  = danger ? (isDark ? '#f87171' : '#ef4444') : (isDark ? '#E2E8F0' : '#334155')
  return (
    <button onClick={onClick}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        width: '100%', padding: '9px 16px',
        background: hovBg, border: 'none', cursor: 'pointer',
        textAlign: 'left', color, fontSize: 14, fontWeight: 500,
        transition: 'background .12s',
      }}>
      <Icon size={16} style={{ flexShrink: 0 }} />
      {label}
    </button>
  )
}

/* ── Tooltip — label à direita do ícone no rail colapsado ───────────────── */
function Tooltip({ label, visible }: { label: string; visible: boolean }) {
  if (!visible) return null
  return (
    <div style={{
      position: 'absolute', left: 'calc(100% + 10px)', top: '50%',
      transform: 'translateY(-50%)',
      background: '#1e293b', color: '#f8fafc',
      fontSize: 12, fontWeight: 600,
      padding: '5px 10px', borderRadius: 6,
      whiteSpace: 'nowrap', pointerEvents: 'none',
      boxShadow: '0 4px 12px rgba(0,0,0,.25)',
      zIndex: 9999,
    }}>
      {label}
      <span style={{
        position: 'absolute', right: '100%', top: '50%',
        transform: 'translateY(-50%)',
        border: '4px solid transparent',
        borderRight: '5px solid #1e293b',
      }} />
    </div>
  )
}

/* ── FooterBtn — botão do footer com tooltip no estado colapsado ─────────── */
interface FooterBtnProps {
  icon: React.ElementType; label: string; collapsed: boolean
  onClick: () => void; content: string; overlay: string
  iconColor?: string; weight?: 'regular' | 'fill'
  rightEl?: React.ReactNode
  baseBg?: string; hoverBg?: string
  isActive?: boolean; selBg?: string; selColor?: string
}
const FooterBtn = React.forwardRef<HTMLButtonElement, FooterBtnProps>(
  function FooterBtn(
    { icon: Icon, label, collapsed, onClick, content, overlay,
      iconColor, weight = 'regular', rightEl,
      baseBg = 'transparent', hoverBg,
      isActive, selBg, selColor },
    ref,
  ) {
    const [hov, setHov] = useState(false)
    const bg    = isActive ? (selBg ?? overlay) : hov ? (hoverBg ?? overlay) : baseBg
    const color = isActive ? (selColor ?? content) : content
    const icoC  = isActive ? (selColor ?? content) : (iconColor ?? color)
    return (
      <div style={{ position: 'relative' }}>
        <button ref={ref} onClick={onClick}
          onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
          style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: collapsed ? '8px 0' : '8px 10px',
            justifyContent: collapsed ? 'center' : 'flex-start',
            width: '100%', border: 'none', cursor: 'pointer',
            borderRadius: 8, background: bg, color,
            fontSize: 13, fontWeight: 500, transition: 'background .15s',
          }}>
          <Icon size={17} weight={weight} style={{ flexShrink: 0, color: icoC }} />
          {!collapsed && <span style={{ flex: 1, textAlign: 'left' }}>{label}</span>}
          {!collapsed && rightEl}
        </button>
        <Tooltip label={label} visible={collapsed && hov} />
      </div>
    )
  }
)

/* ── NavItem — encapsula hover state para item de nav ───────────────────── */
interface NavItemProps {
  to: string; icon: React.ElementType; label: string; collapsed: boolean
  selBg: string; selColor: string; content: string; overlay: string
}
function NavItem({ to, icon: Icon, label, collapsed, selBg, selColor, content, overlay }: NavItemProps) {
  const [hov, setHov] = useState(false)
  return (
    <div style={{ position: 'relative' }}>
      <NavLink to={to} end
        onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
        style={({ isActive }) => ({
          display: 'flex', alignItems: 'center', gap: 10,
          padding: collapsed ? '9px 0' : '9px 10px',
          justifyContent: collapsed ? 'center' : 'flex-start',
          borderRadius: 8, fontSize: 14, fontWeight: 500, textDecoration: 'none',
          transition: 'background .15s',
          background: isActive ? selBg : hov ? overlay : 'transparent',
          color: isActive ? selColor : content,
        })}>
        {({ isActive }) => (
          <>
            <Icon size={17} weight={isActive ? 'fill' : 'regular'} style={{ flexShrink: 0 }} />
            {!collapsed && <span>{label}</span>}
          </>
        )}
      </NavLink>
      <Tooltip label={label} visible={collapsed && hov} />
    </div>
  )
}

/* ── NavGroup — item de nav com flyout (igual ao Configurações) ─────────── */
interface NavGroupProps {
  icon: React.ElementType; label: string; collapsed: boolean; isDark: boolean
  routes: string[]
  items: { to: string; label: string; icon: React.ElementType }[]
  selBg: string; selColor: string; content: string; muted: string; overlay: string
}
function NavGroup({ icon: Icon, label, collapsed, isDark, routes, items, selBg, selColor, content, muted, overlay }: NavGroupProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const isActive = routes.some(r => location.pathname.startsWith(r))
  const [open, setOpen] = useState(false)
  const [hov,  setHov]  = useState(false)
  const btnRef = useRef<HTMLButtonElement>(null)

  return (
    <div style={{ position: 'relative' }}>
      <button ref={btnRef}
        onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
        onClick={() => setOpen(v => !v)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 10,
          padding: collapsed ? '9px 0' : '9px 10px',
          justifyContent: collapsed ? 'center' : 'flex-start',
          borderRadius: 8, border: 'none', cursor: 'pointer',
          fontSize: 14, fontWeight: 500, transition: 'background .15s',
          background: isActive ? selBg : open || hov ? overlay : 'transparent',
          color: isActive ? selColor : content,
        }}>
        <Icon size={17} weight={isActive || open ? 'fill' : 'regular'} style={{ flexShrink: 0 }} />
        {!collapsed && <span style={{ flex: 1, textAlign: 'left' }}>{label}</span>}
        {!collapsed && <CaretRight size={12} style={{ color: isActive ? selColor : muted, flexShrink: 0 }} />}
      </button>
      <Tooltip label={label} visible={collapsed && hov && !open} />
      <Flyout anchorRef={btnRef} open={open} onClose={() => setOpen(false)} isDark={isDark}>
        <div style={{
          padding: '10px 16px 8px',
          borderBottom: isDark ? '1px solid rgba(255,255,255,0.08)' : '1px solid #e2e8f0',
          boxShadow: isDark ? '0 2px 8px rgba(0,0,0,0.35)' : '0 2px 8px rgba(0,0,0,0.08)',
        }}>
          <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: 'var(--color-1)' }}>{label}</p>
        </div>
        <div style={{ padding: '4px 0' }}>
          {items.map(item => (
            <FlyoutItem key={item.to} icon={item.icon} label={item.label} isDark={isDark}
              onClick={() => { setOpen(false); navigate(item.to) }} />
          ))}
        </div>
      </Flyout>
    </div>
  )
}

const W_OPEN = 240
const W_COLL = 64

export default function Sidebar() {
  const [collapsed,    setCollapsed]    = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [profileOpen,  setProfileOpen]  = useState(false)
  const [profileHov,   setProfileHov]   = useState(false)

  const settingsBtnRef = useRef<HTMLButtonElement>(null)
  const profileBtnRef  = useRef<HTMLButtonElement>(null)

  const { logout, user, updateUser } = useAuth()
  const { themeMode, setThemeMode, colors, schemaMode } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()

  // Pai ativo: qualquer rota filha do grupo Settings acende o botão pai
  const SETTINGS_ROUTES = ['/color-settings', '/admin/roles', '/admin/pages']
  const isSettingsActive = SETTINGS_ROUTES.some(r => location.pathname.startsWith(r))

  const mode: Mode = themeMode === 'dark' ? 'dark' : 'light'
  const isDark = mode === 'dark'

  // ── Design System token shortcuts por mode ──────────────────────────────
  const surface  = tk(SB.surface, mode)
  const header   = tk(SB.header,  mode)
  const content  = tk(SB.content, mode)
  const muted    = tk(SB.muted,   mode)
  const overlay  = tk(SB.overlay, mode)
  // Selected item: usa cor do tenant (color1 / on-color-1) — segue a paleta ativa
  const selBg    = 'var(--color-1)'
  const selColor = 'var(--on-color-1)'
  const border   = isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.06)'
  const circleBg = isDark ? '#2A2D3E' : '#FFFFFF'
  const circleB  = isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.12)'

  // ── Avatar: usa gradiente do esquema de cores do tenant ─────────────────
  // Usa themeMode atual para buscar o esquema correto (dark/light).
  // on_gradient_1_2 é calculado via WCAG — garante contraste correto sobre o gradiente.
  const scheme = useMemo(() =>
    colors.find(c => c.color_schema_mode === schemaMode && c.theme_mode === themeMode && c.accessibility_level === 'regular'),
    [colors, schemaMode, themeMode],
  )
  const avatarBg = scheme ? `linear-gradient(135deg, ${scheme.color1}, ${scheme.color2})` : 'var(--gradient-1-2)'
  const avatarFg = scheme?.on_gradient_1_2 ?? 'var(--on-gradient-1-2)'
  const initials = user?.name
    ? user.name.trim().split(/\s+/).filter(Boolean).slice(0, 2).map(n => n[0].toUpperCase()).join('')
    : '?'

  const isAdmin = user?.is_admin ?? false

  // @IF etl
  // ── ETL link ─────────────────────────────────────────────────────────────────
  // OTT é pré-gerado silenciosamente quando o admin loga (useEffect abaixo).
  // Clique normal → instantâneo. Expirou (>25s) ou falhou → loading no botão.
  // OTT de uso único: após consumir, pré-aquece o próximo em background.
  // Clique-direito → "Abrir em nova aba" funciona via href no <a>.
  const ETL_OTT_SAFE_TTL = 25_000  // margem de 5s antes dos 30s do backend
  const etlBase = window.location.port === '5178' ? 'http://localhost:3345' : 'http://localhost:3344'
  const [etlHref,    setEtlHref]    = useState('#')
  const [etlHov,     setEtlHov]     = useState(false)
  const [etlLoading, setEtlLoading] = useState(false)
  // Refs espelham states — evita closure stale no onClick antes do re-render
  const etlHrefRef    = useRef('#')
  const etlGenAt      = useRef(0)               // timestamp da última geração bem-sucedida
  // Promise ref: hover e click concorrentes compartilham o mesmo fetch em andamento
  const etlGenPromise = useRef<Promise<void> | null>(null)

  const generateEtlHref = useCallback((): Promise<void> => {
    if (etlGenPromise.current) return etlGenPromise.current  // reutiliza fetch em andamento
    etlGenPromise.current = apiClient.post('/auth/ott')
      .then(({ data }) => {
        const url = `${etlBase}?ott=${data.ott}`
        etlHrefRef.current = url
        etlGenAt.current   = Date.now()
        setEtlHref(url)
      })
      .catch(() => {
        etlHrefRef.current = '#'
        etlGenAt.current   = 0
        setEtlHref('#')
      })
      .finally(() => { etlGenPromise.current = null })
    return etlGenPromise.current
  }, [etlBase])

  // Pré-gera OTT assim que o admin estiver autenticado — clique será instantâneo
  useEffect(() => { if (isAdmin) generateEtlHref() }, [isAdmin, generateEtlHref])
  // @ENDIF etl

  const toggleTheme = useCallback(() => {
    const next: typeof themeMode = isDark ? 'light' : 'dark'
    setThemeMode(next)
    updateUser({ theme_mode: next })
    apiClient.patch('/users/me/preferences', { theme_mode: next }).catch(() => {})
  }, [isDark, setThemeMode, updateUser])

  function handleLogout() { logout(); navigate('/login', { replace: true }) }

  const W = collapsed ? W_COLL : W_OPEN

  return (
    <aside style={{
      position: 'relative', display: 'flex', flexDirection: 'column',
      width: W, height: '100%', background: surface,
      transition: 'width .25s ease', flexShrink: 0,
      borderRight: `1px solid ${border}`,
      boxShadow: isDark ? '2px 0 16px rgba(0,0,0,.35)' : '2px 0 8px rgba(0,0,0,.06)',
    }}>

      {/* ── HEADER: Logo + nome da aplicação ───────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', flexShrink: 0, position: 'relative',
        padding: collapsed ? '14px 0' : '14px 16px',
        justifyContent: collapsed ? 'center' : 'flex-start',
        background: header,
        borderBottom: `1px solid ${border}`, minHeight: 80, gap: 10,
      }}>
        {/* Logo */}
        <img
          src="/favicon.svg"
          alt="logo"
          style={{ width: 32, height: 32, borderRadius: 8, flexShrink: 0 }}
        />

        {/* Nome — só quando expandido */}
        {!collapsed && (
          <span style={{ fontSize: 15, fontWeight: 700, color: content, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            SaaS Blueprint V1
          </span>
        )}

      </div>

      {/* Botão collapse/expand — centro vertical da sidebar */}
      <div style={{ position: 'absolute', top: '50%', right: -13, transform: 'translateY(-50%)', zIndex: 1 }}>
        <button onClick={() => setCollapsed(v => !v)} title={collapsed ? 'Expandir' : 'Recolher'}
          style={{ width: 26, height: 26, borderRadius: '50%', background: circleBg, border: `1px solid ${circleB}`, color: muted, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {collapsed ? <CaretRight size={13} /> : <CaretLeft size={13} />}
        </button>
      </div>

      {/* ── NAV: PRINCIPAL ─────────────────────────────────────────────── */}
      <nav style={{ padding: '8px 8px 4px', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {!collapsed && (
          <p style={{ fontSize: 10, fontWeight: 700, color: muted, textTransform: 'uppercase', letterSpacing: '.08em', padding: '6px 10px 4px', margin: 0 }}>Principal</p>
        )}
        <NavItem to="/" icon={House} label="Home" collapsed={collapsed} selBg={selBg} selColor={selColor} content={content} overlay={overlay} />
        <NavItem to="/menu-1" icon={Article} label="Menu 1" collapsed={collapsed} selBg={selBg} selColor={selColor} content={content} overlay={overlay} />
        <NavGroup
          icon={FolderOpen} label="Menu 2" collapsed={collapsed} isDark={isDark}
          routes={['/menu-2']}
          items={[
            { to: '/menu-2/sub-1', label: 'Menu 2.1', icon: Article },
            { to: '/menu-2/sub-2', label: 'Menu 2.2', icon: Article },
          ]}
          selBg={selBg} selColor={selColor} content={content} muted={muted} overlay={overlay}
        />
        {/* Adicionar módulos aqui em ordem alfabética: */}
      </nav>

      {/* ── Spacer ─────────────────────────────────────────────────────── */}
      <div style={{ flex: 1 }} />

      {/* ── FOOTER: Configurações (admin) + Theme toggle + Logout ──────── */}
      <div style={{
        padding: collapsed ? '10px 0' : '10px 10px 14px',
        borderTop: `1px solid ${border}`,
        display: 'flex', flexDirection: 'column', gap: 4,
      }}>
        {/* Theme toggle — segmented control (expandido) / ícone (colapsado) */}
        {collapsed ? (
          <FooterBtn
            icon={isDark ? Moon : Sun}
            label={isDark ? 'Dark Mode' : 'Light Mode'}
            collapsed={collapsed} onClick={toggleTheme}
            content={content} overlay={overlay} iconColor={muted}
          />
        ) : (
          <div style={{
            display: 'flex', borderRadius: 10, padding: 3,
            background: isDark ? 'rgba(0,0,0,0.30)' : 'rgba(0,0,0,0.07)',
            margin: '2px 0',
          }}>
            {([
              { label: 'Light', Icon: Sun,  active: !isDark, onClick: () => isDark  && toggleTheme() },
              { label: 'Dark',  Icon: Moon, active:  isDark, onClick: () => !isDark && toggleTheme() },
            ] as const).map(({ label, Icon, active, onClick }) => (
              <button key={label} onClick={onClick} style={{
                flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                padding: '7px 0', borderRadius: 7, border: 'none', cursor: 'pointer',
                background: active ? (isDark ? '#2A2D3E' : '#ffffff') : 'transparent',
                color: active ? content : muted,
                fontWeight: active ? 600 : 500, fontSize: 12,
                boxShadow: active ? '0 1px 4px rgba(0,0,0,.14)' : 'none',
                transition: 'all .2s',
              }}>
                <Icon size={13} weight={active ? 'fill' : 'regular'} />
                {label}
              </button>
            ))}
          </div>
        )}

        {/* Ações de admin (ETL quando habilitado + Configurações) */}
        {isAdmin && (
          <>
            {/* @IF etl */}
            {/* ETL: <a> com href pré-gerado — permite clique normal (mesma aba)
                e clique-direito → "Abrir em nova aba" do browser.
                Loading exibido apenas se OTT expirou ou falhou na geração inicial. */}
            <div style={{ position: 'relative' }}>
              <a
                href={etlHref}
                onMouseEnter={() => setEtlHov(true)}
                onMouseLeave={() => setEtlHov(false)}
                onFocus={generateEtlHref}
                onClick={async (e) => {
                  e.preventDefault()
                  if (etlLoading) return

                  // OTT ausente ou expirado (> margem segura do TTL) → gera com loading
                  const isStale = Date.now() - etlGenAt.current > ETL_OTT_SAFE_TTL
                  if (etlHrefRef.current === '#' || isStale) {
                    if (isStale) { etlHrefRef.current = '#'; etlGenAt.current = 0; setEtlHref('#') }
                    setEtlLoading(true)
                    await generateEtlHref()
                    setEtlLoading(false)
                  }

                  const target = etlHrefRef.current
                  // Consome OTT e pré-aquece o próximo silenciosamente (OTT é de uso único)
                  etlHrefRef.current = '#'
                  etlGenAt.current   = 0
                  setEtlHref('#')
                  if (target !== '#') {
                    generateEtlHref()          // fire-and-forget para próximo clique/right-click
                    window.location.href = target
                  }
                }}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: collapsed ? '8px 0' : '8px 10px',
                  justifyContent: collapsed ? 'center' : 'flex-start',
                  width: '100%', borderRadius: 8,
                  cursor: etlLoading ? 'wait' : 'pointer',
                  pointerEvents: etlLoading ? 'none' : 'auto',
                  opacity: etlLoading ? 0.65 : 1,
                  background: etlHov && !etlLoading ? overlay : 'transparent',
                  color: content, textDecoration: 'none',
                  fontSize: 13, fontWeight: 500, transition: 'background .15s, opacity .15s',
                }}
              >
                <ArrowSquareOut size={17} weight="regular" style={{ flexShrink: 0, color: etlLoading ? 'var(--color-1)' : muted }} />
                {!collapsed && (
                  <span style={{ flex: 1, textAlign: 'left' }}>
                    {etlLoading ? 'Abrindo ETL…' : 'Módulo ETL'}
                  </span>
                )}
              </a>
              <Tooltip label={etlLoading ? 'Abrindo ETL…' : 'Módulo ETL'} visible={collapsed && etlHov} />
            </div>
            {/* @ENDIF etl */}
            <FooterBtn
              ref={settingsBtnRef}
              icon={Gear} label="Configurações" collapsed={collapsed}
              onClick={() => { setSettingsOpen(v => !v); setProfileOpen(false) }}
              content={content} overlay={overlay}
              iconColor={isSettingsActive ? selColor : settingsOpen ? 'var(--color-1)' : muted}
              weight={isSettingsActive || settingsOpen ? 'fill' : 'regular'}
              baseBg={settingsOpen ? overlay : 'transparent'}
              isActive={isSettingsActive} selBg={selBg} selColor={selColor}
              rightEl={<CaretRight size={13} style={{ color: isSettingsActive ? selColor : muted }} />}
            />
            <Flyout anchorRef={settingsBtnRef} open={settingsOpen} onClose={() => setSettingsOpen(false)} isDark={isDark} alignBottom>
              <div style={{
                padding: '10px 16px 8px',
                borderBottom: isDark ? '1px solid rgba(255,255,255,0.08)' : '1px solid #e2e8f0',
                boxShadow: isDark ? '0 2px 8px rgba(0,0,0,0.35)' : '0 2px 8px rgba(0,0,0,0.08)',
              }}>
                <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: 'var(--color-1)' }}>Configurações</p>
              </div>
              <div style={{ padding: '4px 0' }}>
                <FlyoutItem icon={Palette}       label="Cores"    isDark={isDark} onClick={() => { setSettingsOpen(false); navigate('/color-settings') }} />
                <FlyoutItem icon={SquaresFour}   label="Páginas"  isDark={isDark} onClick={() => { setSettingsOpen(false); navigate('/admin/pages') }} />
                <FlyoutItem icon={ShieldCheck}   label="Papéis"   isDark={isDark} onClick={() => { setSettingsOpen(false); navigate('/admin/roles') }} />
              </div>
            </Flyout>
          </>
        )}

        {/* Separador */}
        <div style={{ height: 1, background: border, margin: '4px 0' }} />

        {/* Profile — bottom */}
        <div style={{ position: 'relative' }}>
          <button ref={profileBtnRef}
            onClick={() => { setProfileOpen(v => !v); setSettingsOpen(false) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: collapsed ? '6px 0' : '6px 4px',
              justifyContent: collapsed ? 'center' : 'flex-start',
              width: '100%', background: 'none', border: 'none', cursor: 'pointer',
              borderRadius: 8, minWidth: 0, transition: 'background .15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = overlay; setProfileHov(true) }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; setProfileHov(false) }}>
            <div style={{
              width: 36, height: 36, borderRadius: '50%', background: avatarBg,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: avatarFg, fontWeight: 700, fontSize: 14, flexShrink: 0,
              overflow: 'hidden',
            }}>
              {user?.avatar_url
                ? <img src={user.avatar_url} alt="avatar" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                : initials}
            </div>
            {!collapsed && (
              <div style={{ flex: 1, minWidth: 0, textAlign: 'left' }}>
                <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: content, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', lineHeight: 1.4, display: 'flex', alignItems: 'center', gap: 6 }}>
                  {user?.name ?? '—'}
                  {import.meta.env.MODE === 'dev' && (
                    <span style={{ fontSize: 9, fontWeight: 700, padding: '1px 5px', borderRadius: 3, background: '#facc15', color: '#713f12', flexShrink: 0 }}>DEV</span>
                  )}
                </p>
                <p style={{ margin: 0, fontSize: 11, color: muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {user?.email ?? ''}
                </p>
              </div>
            )}
          </button>
          <Tooltip label={user?.name ?? 'Perfil'} visible={collapsed && profileHov} />
        </div>

        {/* Flyout: Perfil */}
        <Flyout anchorRef={profileBtnRef} open={profileOpen} onClose={() => setProfileOpen(false)} isDark={isDark} alignBottom>
          <div style={{ padding: '12px 16px 8px', borderBottom: isDark ? '1px solid rgba(255,255,255,0.08)' : '1px solid #f1f5f9' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 36, height: 36, borderRadius: '50%', background: avatarBg, display: 'flex', alignItems: 'center', justifyContent: 'center', color: avatarFg, fontWeight: 700, fontSize: 14, overflow: 'hidden' }}>
                {user?.avatar_url
                  ? <img src={user.avatar_url} alt="avatar" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  : initials}
              </div>
              <div>
                <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: isDark ? '#F1F5F9' : '#1e293b' }}>{user?.name}</p>
                <p style={{ margin: 0, fontSize: 11, color: isDark ? '#94A3B8' : '#64748b' }}>{user?.email}</p>
              </div>
            </div>
          </div>
          <div style={{ padding: '4px 0' }}>
            <FlyoutItem icon={User}    label="Meu Perfil"    isDark={isDark} onClick={() => { setProfileOpen(false); navigate('/profile') }} />
            <FlyoutItem icon={SignOut} label="Sair da conta" isDark={isDark} onClick={() => { setProfileOpen(false); handleLogout() }} danger />
          </div>
        </Flyout>
      </div>
    </aside>
  )
}
