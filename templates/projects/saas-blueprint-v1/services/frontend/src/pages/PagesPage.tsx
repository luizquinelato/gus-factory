import { useEffect, useState } from 'react'
import { Crown, FloppyDisk, MagnifyingGlass } from '@phosphor-icons/react'
import { toast } from 'sonner'
import apiClient from '../services/apiClient'

// ── Types ─────────────────────────────────────────────────────────────────────

type MinRole = 'view' | 'user' | 'admin'

interface Page {
  page_key: string
  label: string
  route: string
  group_label: string | null
  min_role: MinRole
}

type Draft = Record<string, MinRole>

// ── Helpers ───────────────────────────────────────────────────────────────────

function toFlags(min_role: MinRole) {
  return {
    admin: true,
    user:  min_role === 'user' || min_role === 'view',
    view:  min_role === 'view',
  }
}

function toMinRole(user: boolean, view: boolean): MinRole {
  if (view)  return 'view'
  if (user)  return 'user'
  return 'admin'
}

function makeDraft(pages: Page[]): Draft {
  return Object.fromEntries(pages.map(p => [p.page_key, p.min_role]))
}

// ── Checkbox components ───────────────────────────────────────────────────────

function HeaderCheckbox({ checked, disabled, onChange }: { checked: boolean; disabled: boolean; onChange: () => void }) {
  return (
    <button
      onClick={onChange}
      disabled={disabled}
      title={checked ? 'Desmarcar todos' : 'Marcar todos'}
      className="w-5 h-5 rounded border-2 flex items-center justify-center mx-auto transition-colors"
      style={{
        borderColor: checked ? 'var(--color-1)' : '#CBD5E1',
        background:  checked ? 'var(--color-1)' : 'transparent',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.55 : 1,
        flexShrink: 0,
      }}
    >
      {checked && (
        <svg width="8" height="6" viewBox="0 0 10 8" fill="none">
          <path d="M1 3.5L3.8 6.5L9 1" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      )}
    </button>
  )
}

function CheckCell({ checked, disabled, onChange }: { checked: boolean; disabled: boolean; onChange: () => void }) {
  return (
    <td className="text-center py-3 px-2">
      <button
        onClick={onChange}
        disabled={disabled}
        className="w-5 h-5 rounded border-2 flex items-center justify-center mx-auto transition-colors"
        style={{
          borderColor: checked ? 'var(--color-1)' : '#CBD5E1',
          background:  checked ? 'var(--color-1)' : 'transparent',
          cursor:  disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.65 : 1,
          flexShrink: 0,
        }}
      >
        {checked && (
          <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
            <path d="M1 3.5L3.8 6.5L9 1" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )}
      </button>
    </td>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function PagesPage() {
  const [pages,   setPages]   = useState<Page[]>([])
  const [draft,   setDraft]   = useState<Draft>({})
  const [loading, setLoading] = useState(true)
  const [filter,  setFilter]  = useState('')
  const [saving,  setSaving]  = useState(false)
  useEffect(() => {
    apiClient.get('/admin/pages')
      .then(({ data }) => { setPages(data); setDraft(makeDraft(data)) })
      .catch(() => toast.error('Erro ao carregar páginas.'))
      .finally(() => setLoading(false))
  }, [])

  const filtered = pages.filter(p => p.label.toLowerCase().includes(filter.toLowerCase()))
  const anyDirty = pages.some(p => draft[p.page_key] !== p.min_role)
  const allUser  = filtered.length > 0 && filtered.every(p => toFlags(draft[p.page_key] ?? p.min_role).user)
  const allView  = filtered.length > 0 && filtered.every(p => toFlags(draft[p.page_key] ?? p.min_role).view)

  function handleToggle(page_key: string, user: boolean, view: boolean) {
    setDraft(prev => ({ ...prev, [page_key]: toMinRole(user, view) }))
  }

  function handleMarkAllUser() {
    if (allUser) {
      // todos têm acesso de user → regredir todos para admin-only
      setDraft(_ => Object.fromEntries(pages.map(p => [p.page_key, 'admin' as MinRole])))
    } else {
      // elevar apenas os que estão em 'admin'; preservar os que já estão em 'view'
      setDraft(prev => Object.fromEntries(pages.map(p => {
        const cur = prev[p.page_key] ?? p.min_role
        return [p.page_key, cur === 'admin' ? 'user' : cur]
      })))
    }
  }

  function handleMarkAllView() {
    setDraft(prev => Object.fromEntries(pages.map(p => {
      const cur = prev[p.page_key] ?? p.min_role
      if (allView) {
        // Desmarcar view: só demote 'view' → 'user', não toca 'admin'
        return [p.page_key, cur === 'view' ? 'user' : cur]
      } else {
        // Marcar view: só promove 'user' → 'view', não toca 'admin' (evita bagunçar coluna Usuário)
        return [p.page_key, cur === 'user' ? 'view' : cur]
      }
    })))
  }

  async function handleSaveAll() {
    const changed = pages.filter(p => draft[p.page_key] !== p.min_role)
    if (changed.length === 0) return
    setSaving(true)
    try {
      await apiClient.patch('/admin/pages', changed.map(p => ({ page_key: p.page_key, min_role: draft[p.page_key] })))
      setPages(prev => prev.map(p => ({ ...p, min_role: draft[p.page_key] ?? p.min_role })))
      toast.success('Alterações salvas.')
    } catch {
      toast.error('Erro ao salvar alterações.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-full p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">Páginas</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Define o acesso mínimo por página. Admin sempre tem acesso a tudo.
        </p>
      </div>

      {/* ── Filtro ── */}
      <div className="relative">
        <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 pointer-events-none" />
        <input
          type="text"
          placeholder="Filtrar por nome…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="w-full pl-8 pr-4 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 outline-none focus:border-[var(--color-1)]"
        />
      </div>

      <div>
      {/* ── Título + botão Salvar ── */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Controle de Acesso por Página
        </div>
        <button
          onClick={handleSaveAll}
          disabled={!anyDirty || saving}
          className="inline-flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold border-none transition-all"
          style={{
            background: anyDirty ? 'var(--color-save)' : '#e2e8f0',
            color:      anyDirty ? 'var(--on-color-save)' : '#94a3b8',
            opacity:    saving ? 0.6 : 1,
            cursor:     !anyDirty || saving ? 'not-allowed' : 'pointer',
          }}
        >
          <FloppyDisk size={15} className={saving ? 'animate-spin' : undefined} />
          Salvar
        </button>
      </div>

      <section className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6">
        {loading ? (
          <p className="text-sm text-gray-400 dark:text-gray-500">Carregando...</p>
        ) : (
          <table className="w-full text-sm border-collapse">
            <thead>
              {/* Linha 1 — títulos das colunas */}
              <tr>
                <th className="py-2" />
                <th className="text-center py-2 px-2 text-xs font-bold uppercase tracking-wider text-gray-600 dark:text-gray-300 w-24">Admin</th>
                <th className="text-center py-2 px-2 text-xs font-bold uppercase tracking-wider text-gray-600 dark:text-gray-300 w-24">Usuário</th>
                <th className="text-center py-2 px-2 text-xs font-bold uppercase tracking-wider text-gray-600 dark:text-gray-300 w-28">Visualização</th>
              </tr>
              {/* Linha 2 — "Página" + checkboxes de marcar todos */}
              <tr className="border-b border-gray-100 dark:border-gray-700">
                <th className="text-left pb-2 text-xs font-bold uppercase tracking-wider text-gray-600 dark:text-gray-300">Página</th>
                <th className="text-center pb-2 px-2 w-24">
                  <div className="flex justify-center opacity-30">
                    <HeaderCheckbox checked disabled onChange={() => {}} />
                  </div>
                </th>
                <th className="text-center pb-2 px-2 w-24">
                  <div className="flex justify-center">
                    <HeaderCheckbox checked={allUser} disabled={saving} onChange={handleMarkAllUser} />
                  </div>
                </th>
                <th className="text-center pb-2 px-2 w-28">
                  <div className="flex justify-center">
                    <HeaderCheckbox checked={allView} disabled={saving} onChange={handleMarkAllView} />
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((page, i) => {
                const draftRole = draft[page.page_key] ?? page.min_role
                const flags     = toFlags(draftRole)

                return (
                  <tr key={page.page_key} className={`transition-colors hover:bg-gray-100 dark:hover:bg-gray-700/50 ${i % 2 === 0 ? 'bg-gray-50 dark:bg-gray-700/30' : ''}`}>
                    <td className="py-3 pl-3 rounded-l-lg">
                      <p className="font-semibold text-gray-800 dark:text-gray-100">{page.label}</p>
                      <p className="text-xs text-gray-400 dark:text-gray-500">
                        {page.group_label ? (
                          <><span className="opacity-60">{page.group_label}</span><span className="opacity-40 mx-1">›</span>{page.label}</>
                        ) : page.label}
                      </p>
                    </td>

                    <CheckCell checked disabled onChange={() => {}} />

                    <CheckCell
                      checked={flags.user}
                      disabled={saving}
                      onChange={() => handleToggle(page.page_key, !flags.user, !flags.user ? flags.view : false)}
                    />

                    <CheckCell
                      checked={flags.view}
                      disabled={saving || !flags.user}
                      onChange={() => flags.user && handleToggle(page.page_key, flags.user, !flags.view)}
                    />
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}

        <p className="flex items-center gap-1.5 text-xs text-gray-400 dark:text-gray-500 mt-4 pt-4 border-t border-gray-100 dark:border-gray-700">
          <Crown size={12} style={{ color: 'var(--color-1)' }} weight="fill" />
          Admin sempre tem acesso a todas as páginas, independente da configuração.
        </p>
      </section>
      </div>

    </div>
  )
}
