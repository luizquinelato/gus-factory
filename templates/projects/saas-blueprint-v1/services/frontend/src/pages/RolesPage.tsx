import React, { useEffect, useState } from 'react'
import { Crown, User, Eye, Lock, FloppyDisk } from '@phosphor-icons/react'
import { toast } from 'sonner'
import apiClient from '../services/apiClient'

// ── Types ─────────────────────────────────────────────────────────────────────

type CapKey = 'can_read' | 'can_write' | 'can_delete'

interface Role {
  name: string
  description: string | null
  is_system: boolean
  can_read: boolean
  can_write: boolean
  can_delete: boolean
}

type Draft = Record<string, Pick<Role, CapKey>>

// ── Helpers ───────────────────────────────────────────────────────────────────

const ROLE_META: Record<string, { icon: React.ReactNode; color: string }> = {
  admin: { icon: <Crown size={16} weight="fill" />, color: 'var(--color-1)' },
  user:  { icon: <User  size={16} weight="fill" />, color: '#6366F1'        },
  view:  { icon: <Eye   size={16} weight="fill" />, color: '#64748B'        },
}

const CAPS: { key: CapKey; label: string }[] = [
  { key: 'can_read',   label: 'Leitura'  },
  { key: 'can_write',  label: 'Escrita'  },
  { key: 'can_delete', label: 'Deleção'  },
]

function isDirty(role: Role, draft: Draft) {
  const d = draft[role.name]
  if (!d) return false
  return CAPS.some(c => role[c.key] !== d[c.key])
}

function makeDraft(roles: Role[]): Draft {
  return Object.fromEntries(roles.map(r => [r.name, { can_read: r.can_read, can_write: r.can_write, can_delete: r.can_delete }]))
}

// ── Sub-components ────────────────────────────────────────────────────────────

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
          <path d="M1 3.5L3.8 6.5L9 1" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  )
}

function CheckCell({ checked, disabled, onChange }: { checked: boolean; disabled: boolean; onChange: () => void }) {
  return (
    <button
      onClick={onChange}
      disabled={disabled}
      className="w-5 h-5 rounded border-2 flex items-center justify-center transition-colors flex-shrink-0"
      style={{
        borderColor: checked ? 'var(--color-1)' : '#CBD5E1',
        background:  checked ? 'var(--color-1)' : 'transparent',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.55 : 1,
      }}
    >
      {checked && (
        <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
          <path d="M1 3.5L3.8 6.5L9 1" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function RolesPage() {
  const [roles,   setRoles]   = useState<Role[]>([])
  const [draft,   setDraft]   = useState<Draft>({})
  const [loading, setLoading] = useState(true)
  const [saving,  setSaving]  = useState(false)
  useEffect(() => {
    apiClient.get('/admin/roles')
      .then(({ data }) => { setRoles(data); setDraft(makeDraft(data)) })
      .catch(() => toast.error('Erro ao carregar roles.'))
      .finally(() => setLoading(false))
  }, [])

  const anyDirty     = roles.some(r => isDirty(r, draft))
  const editableRoles = roles.filter(r => r.name !== 'admin')

  function allCapChecked(key: CapKey) {
    return editableRoles.length > 0 && editableRoles.every(r => (draft[r.name] ?? r)[key])
  }

  function handleToggle(name: string, key: CapKey) {
    setDraft(prev => ({ ...prev, [name]: { ...prev[name], [key]: !prev[name][key] } }))
  }

  function handleMarkAllCap(key: CapKey) {
    const next = !allCapChecked(key)
    setDraft(prev => {
      const updated = { ...prev }
      editableRoles.forEach(r => { updated[r.name] = { ...updated[r.name], [key]: next } })
      return updated
    })
  }

  async function handleSaveAll() {
    const changed = roles.filter(r => isDirty(r, draft))
    if (changed.length === 0) return
    setSaving(true)
    try {
      await apiClient.patch('/admin/roles', changed.map(r => ({ name: r.name, ...draft[r.name] })))
      setRoles(prev => prev.map(r => ({ ...r, ...draft[r.name] })))
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
        <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">Papéis</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Define as capacidades de cada papel. O acesso por página é configurado em{' '}
          <a href="/admin/pages" className="underline" style={{ color: 'var(--color-1)' }}>Páginas</a>.
        </p>
      </div>

      <div>
      {/* ── Título + botão Salvar ── */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Capacidades por Role
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
              {/* Linha 1 — nomes das colunas */}
              <tr>
                <th className="py-2" />
                {CAPS.map(c => (
                  <th key={c.key} className="text-center py-2 px-4 text-xs font-bold uppercase tracking-wider text-gray-600 dark:text-gray-300 w-28">
                    {c.label}
                  </th>
                ))}
              </tr>
              {/* Linha 2 — "Role" + checkboxes de marcar todos */}
              <tr className="border-b border-gray-100 dark:border-gray-700">
                <th className="text-left pb-2 text-xs font-bold uppercase tracking-wider text-gray-600 dark:text-gray-300">Role</th>
                {CAPS.map(c => (
                  <th key={c.key} className="text-center pb-2 px-4 w-28">
                    <div className="flex justify-center">
                      <HeaderCheckbox checked={allCapChecked(c.key)} disabled={saving} onChange={() => handleMarkAllCap(c.key)} />
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {roles.map((role, i) => {
                const meta    = ROLE_META[role.name]
                const isAdmin = role.name === 'admin'
                const caps    = draft[role.name] ?? role
                return (
                  <tr key={role.name} className={`transition-colors hover:bg-gray-100 dark:hover:bg-gray-700/50 ${i % 2 === 0 ? 'bg-gray-50 dark:bg-gray-700/30' : ''}`}>
                    <td className="py-3 pl-3 rounded-l-lg">
                      <div className="flex items-center gap-2">
                        <span style={{ color: meta?.color }}>{meta?.icon}</span>
                        <span className="font-semibold text-gray-800 dark:text-gray-100 capitalize">{role.name}</span>
                        {isAdmin && (
                          <span className="flex items-center gap-1 text-[10px] font-semibold text-gray-400 dark:text-gray-500 border border-gray-200 dark:border-gray-600 rounded-full px-2 py-0.5">
                            <Lock size={9} />sistema
                          </span>
                        )}
                      </div>
                      {role.description && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 pl-6">{role.description}</p>}
                    </td>
                    {CAPS.map(c => (
                      <td key={c.key} className="text-center py-3 px-4">
                        <div className="flex justify-center">
                          <CheckCell
                            checked={caps[c.key]}
                            disabled={isAdmin || saving}
                            onChange={() => handleToggle(role.name, c.key)}
                          />
                        </div>
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}

        <p className="text-xs text-gray-400 dark:text-gray-500 mt-4 pt-4 border-t border-gray-100 dark:border-gray-700">
          O papel <strong>admin</strong> sempre tem acesso total e não pode ser alterado.
        </p>
      </section>
      </div>


    </div>
  )
}
