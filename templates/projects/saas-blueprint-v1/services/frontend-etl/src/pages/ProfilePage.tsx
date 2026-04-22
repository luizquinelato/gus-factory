import React, { useRef, useState } from 'react'
import { User, Lock, FloppyDisk, Camera, Trash, SlidersHorizontal } from '@phosphor-icons/react'
import { toast } from 'sonner'
import { useAuth } from '../contexts/AuthContext'
import apiClient from '../services/apiClient'
import type { AccessibilityLevel } from '../types'

const inputCls = [
  'w-full px-4 py-2.5 rounded-lg text-sm outline-none transition-all',
  'border border-gray-200 dark:border-gray-600',
  'bg-white dark:bg-gray-700',
  'text-gray-800 dark:text-gray-100',
  'placeholder-gray-400 dark:placeholder-gray-500',
  'focus:border-[var(--color-1)]',
].join(' ')

const sectionTitle = 'flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-4'

export default function ProfilePage() {
  const { user, updateUser } = useAuth()

  const fileInputRef = useRef<HTMLInputElement>(null)

  const [name,          setName]          = useState(user?.name ?? '')
  const [currentPass,   setCurrentPass]   = useState('')
  const [newPass,       setNewPass]       = useState('')
  const [loadingName,   setLoadingName]   = useState(false)
  const [loadingPass,   setLoadingPass]   = useState(false)
  const [loadingAvatar, setLoadingAvatar] = useState(false)
  const [avatarHov,     setAvatarHov]     = useState(false)

  // Acessibilidade
  const [accessLevel,       setAccessLevel]       = useState<AccessibilityLevel>(user?.accessibility_level ?? 'regular')
  const [highContrast,      setHighContrast]      = useState(user?.high_contrast_mode ?? false)
  const [reduceMotion,      setReduceMotion]      = useState(user?.reduce_motion ?? false)
  const [colorblindPalette, setColorblindPalette] = useState(user?.colorblind_safe_palette ?? false)
  const [loadingAccess,     setLoadingAccess]     = useState(false)

  // initials fallback
  const initials = user?.name
    ? user.name.trim().split(/\s+/).filter(Boolean).slice(0, 2).map(n => n[0].toUpperCase()).join('')
    : '?'

  async function handleSaveName(e: React.FormEvent) {
    e.preventDefault(); setLoadingName(true)
    try {
      const { data } = await apiClient.patch('/users/me', { name })
      updateUser({ name: data.name }); toast.success('Nome atualizado com sucesso!')
    } catch { toast.error('Erro ao salvar o nome.') } finally { setLoadingName(false) }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault(); setLoadingPass(true)
    try {
      await apiClient.patch('/users/me/password', { current_password: currentPass, new_password: newPass })
      setCurrentPass(''); setNewPass(''); toast.success('Senha alterada com sucesso!')
    } catch { toast.error('Senha atual incorreta.') } finally { setLoadingPass(false) }
  }

  async function handleAvatarChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setLoadingAvatar(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const { data } = await apiClient.post('/users/me/avatar', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      updateUser({ avatar_url: data.avatar_url })
      toast.success('Foto atualizada com sucesso!')
    } catch { toast.error('Erro ao enviar a foto.') } finally {
      setLoadingAvatar(false)
      // reset so the same file can be selected again
      e.target.value = ''
    }
  }

  async function handleSaveAccessibility(e: React.FormEvent) {
    e.preventDefault(); setLoadingAccess(true)
    try {
      await apiClient.patch('/users/me/preferences', {
        accessibility_level: accessLevel,
        high_contrast_mode: highContrast,
        reduce_motion: reduceMotion,
        colorblind_safe_palette: colorblindPalette,
      })
      updateUser({ accessibility_level: accessLevel, high_contrast_mode: highContrast, reduce_motion: reduceMotion, colorblind_safe_palette: colorblindPalette })
      toast.success('Preferências de acessibilidade salvas!')
    } catch { toast.error('Erro ao salvar preferências.') } finally { setLoadingAccess(false) }
  }

  async function handleRemoveAvatar() {
    setLoadingAvatar(true)
    try {
      await apiClient.delete('/users/me/avatar')
      updateUser({ avatar_url: null })
      toast.success('Foto removida.')
    } catch { toast.error('Erro ao remover a foto.') } finally { setLoadingAvatar(false) }
  }

  const AVATAR_SIZE = 120

  return (
    <div className="min-h-full p-8 space-y-6">

      <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">Perfil</h1>

      {/* ── Dados ── */}
      <section className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6 transition-colors hover:border-[var(--color-1)]">
        <p className={sectionTitle}><User size={13} />Dados</p>

        {/* Avatar dentro do card */}
        <div className="flex items-center gap-5 mb-6">
          <div
            style={{ position: 'relative', width: AVATAR_SIZE, height: AVATAR_SIZE, flexShrink: 0, cursor: loadingAvatar ? 'wait' : 'pointer' }}
            onClick={() => !loadingAvatar && fileInputRef.current?.click()}
            onMouseEnter={() => setAvatarHov(true)}
            onMouseLeave={() => setAvatarHov(false)}
          >
            <div style={{
              width: AVATAR_SIZE, height: AVATAR_SIZE, borderRadius: '50%', overflow: 'hidden',
              background: 'var(--gradient-1-2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              border: '3px solid var(--color-1)',
              boxShadow: '0 4px 16px color-mix(in srgb, var(--color-1) 25%, transparent)',
            }}>
              {user?.avatar_url ? (
                <img src={user.avatar_url} alt="avatar" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : (
                <span style={{ color: 'var(--on-gradient-1-2)', fontWeight: 700, fontSize: 40, userSelect: 'none' }}>{initials}</span>
              )}
            </div>

            {/* Hover overlay */}
            {(avatarHov || loadingAvatar) && (
              <div style={{
                position: 'absolute', inset: 0, borderRadius: '50%',
                background: 'rgba(0,0,0,0.45)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Camera size={32} weight="bold" color="white" />
              </div>
            )}
          </div>

          {/* Label + remove */}
          <div className="flex flex-col gap-1.5">
            <p className="text-xs text-gray-400 dark:text-gray-500 select-none">
              {user?.avatar_url ? 'Clique na foto para trocar' : 'Clique na foto para adicionar'}
            </p>
            {user?.avatar_url && (
              <button
                onClick={handleRemoveAvatar}
                disabled={loadingAvatar}
                className="flex items-center gap-1 text-xs font-semibold border-none bg-transparent cursor-pointer w-fit"
                style={{ color: 'var(--color-delete)', opacity: loadingAvatar ? .5 : 1 }}
              >
                <Trash size={12} weight="bold" />
                Remover foto
              </button>
            )}
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            style={{ display: 'none' }}
            onChange={handleAvatarChange}
          />
        </div>

        <form onSubmit={handleSaveName} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1.5">Nome</label>
            <input className={inputCls} value={name} onChange={e => setName(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1.5">Email</label>
            <input className={`${inputCls} opacity-60 cursor-not-allowed`} value={user?.email ?? ''} disabled />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1.5">Função</label>
            <input className={`${inputCls} opacity-60 cursor-not-allowed capitalize`} value={user?.role ?? ''} disabled />
          </div>
          <div className="flex justify-end">
            <button type="submit" disabled={loadingName}
              className="px-6 py-2.5 rounded-lg text-sm font-semibold flex items-center gap-2 border-none"
              style={{ background: 'var(--color-1)', color: 'var(--on-color-1)', opacity: loadingName ? .7 : 1, cursor: loadingName ? 'not-allowed' : 'pointer' }}>
              <FloppyDisk size={14} />{loadingName ? 'Salvando...' : 'Salvar Dados'}
            </button>
          </div>
        </form>
      </section>

      {/* ── Acessibilidade ── */}
      <section className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6 transition-colors hover:border-[var(--color-1)]">
        <p className={sectionTitle}><SlidersHorizontal size={13} />Acessibilidade</p>
        <form onSubmit={handleSaveAccessibility} className="space-y-5">

          {/* Nível WCAG */}
          <div>
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">Nível de contraste (WCAG)</p>
            <div className="flex gap-2">
              {(['regular', 'AA', 'AAA'] as const).map(level => (
                <button
                  key={level}
                  type="button"
                  onClick={() => setAccessLevel(level)}
                  className="flex-1 py-2 rounded-lg text-sm font-semibold border transition-all"
                  style={accessLevel === level
                    ? { background: 'var(--color-1)', color: 'var(--on-color-1)', borderColor: 'var(--color-1)' }
                    : { background: 'transparent', borderColor: 'var(--color-1)', color: 'var(--color-1)' }
                  }
                >
                  {level === 'regular' ? 'Regular' : level}
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5">
              AA e AAA aumentam o contraste mínimo das cores para cumprir WCAG 2.1.
            </p>
          </div>

          {/* Toggles */}
          {([
            { key: 'highContrast',      value: highContrast,      set: setHighContrast,      label: 'Alto contraste',           desc: 'Aumenta o contraste das bordas e textos secundários.' },
            { key: 'reduceMotion',      value: reduceMotion,      set: setReduceMotion,      label: 'Reduzir animações',        desc: 'Desativa transições e animações da interface.' },
            { key: 'colorblindPalette', value: colorblindPalette, set: setColorblindPalette, label: 'Paleta para daltonismo',   desc: 'Substitui cores que podem ser confundidas por usuários daltônicos.' },
          ] as const).map(({ key, value, set, label, desc }) => (
            <div key={key} className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{label}</p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{desc}</p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={value}
                onClick={() => set(!value)}
                className="relative mt-0.5 w-10 h-6 rounded-full transition-colors flex-shrink-0 border-none cursor-pointer"
                style={{ background: value ? 'var(--color-1)' : '#d1d5db' }}
              >
                <span className="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform"
                  style={{ transform: value ? 'translateX(16px)' : 'translateX(0)' }} />
              </button>
            </div>
          ))}

          <div className="flex justify-end">
            <button type="submit" disabled={loadingAccess}
              className="px-6 py-2.5 rounded-lg text-sm font-semibold flex items-center gap-2 border-none"
              style={{ background: 'var(--color-1)', color: 'var(--on-color-1)', opacity: loadingAccess ? .7 : 1, cursor: loadingAccess ? 'not-allowed' : 'pointer' }}>
              <FloppyDisk size={14} />{loadingAccess ? 'Salvando...' : 'Salvar Acessibilidade'}
            </button>
          </div>
        </form>
      </section>

      {/* ── Segurança ── */}
      <section className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6 transition-colors hover:border-[var(--color-1)]">
        <p className={sectionTitle}><Lock size={13} />Segurança</p>
        <form onSubmit={handleChangePassword} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1.5">Senha Atual</label>
            <input type="password" required className={inputCls} value={currentPass} onChange={e => setCurrentPass(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1.5">Nova Senha</label>
            <input type="password" required className={inputCls} value={newPass} onChange={e => setNewPass(e.target.value)} />
          </div>
          <div className="flex justify-end">
            <button type="submit" disabled={loadingPass}
              className="px-6 py-2.5 rounded-lg text-sm font-semibold flex items-center gap-2 border-none"
              style={{ background: 'var(--color-1)', color: 'var(--on-color-1)', opacity: loadingPass ? .7 : 1, cursor: loadingPass ? 'not-allowed' : 'pointer' }}>
              <Lock size={14} />{loadingPass ? 'Alterando...' : 'Alterar Senha'}
            </button>
          </div>
        </form>
      </section>

    </div>
  )
}
