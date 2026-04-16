import { useState, useMemo, useRef } from 'react'
import ReactDOM from 'react-dom'
import { CheckCircle, Palette, PaintBrush, ArrowCounterClockwise, FloppyDisk } from '@phosphor-icons/react'
import type { BaseColors } from '../utils/colorCalculations'
import { buildColorVariant } from '../utils/colorCalculations'
import ColorVariantsPreview from './ColorVariantsPreview'

const SWATCH_SIZE = 64
const COLOR_KEYS: (keyof BaseColors)[] = ['color1','color2','color3','color4','color5']

const _FULL_HEX = /^#[0-9A-Fa-f]{6}$/
/** Retorna true apenas para hex completo #rrggbb — evita warnings do <input type="color"> */
function isCompleteHex(v: string) { return _FULL_HEX.test(v) }

interface Props {
  schemaMode: 'default' | 'custom'
  defaultLightColors: BaseColors
  defaultDarkColors:  BaseColors
  customLightColors:  BaseColors
  customDarkColors:   BaseColors
  onSave: (light: BaseColors, dark: BaseColors) => Promise<void>
  onModeChange: (mode: 'default' | 'custom') => Promise<void>
}

/** Swatch 64×64 com color picker embutido + hex input abaixo */
function Swatch({ value, label, editable, onChange }: {
  value: string; label: string; editable: boolean; onChange: (v: string) => void
}) {
  // Hex completo (#rrggbb) para o color picker e background — fallback enquanto o usuário digita
  const safeHex = isCompleteHex(value) ? value : '#000000'
  return (
    <div className="flex flex-col items-center gap-1">
      <div style={{
        position: 'relative', width: SWATCH_SIZE, height: SWATCH_SIZE,
        borderRadius: 10, background: safeHex,
        cursor: editable ? 'pointer' : 'default',
        boxShadow: '0 2px 8px rgba(0,0,0,.22)', overflow: 'hidden',
        border: '2px solid rgba(0,0,0,.1)',
      }}>
        {editable && (
          <input type="color" value={safeHex} onChange={e => onChange(e.target.value)}
            style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer', width: '100%', height: '100%' }} />
        )}
      </div>
      <span className="text-[10px] font-semibold text-gray-400 dark:text-gray-500">{label}</span>
      <input
        type="text" value={value} disabled={!editable}
        onChange={e => /^#[0-9A-Fa-f]{0,6}$/.test(e.target.value) && onChange(e.target.value)}
        className="w-16 text-center text-[10px] font-mono rounded outline-none border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 px-1 py-0.5 disabled:bg-gray-50 dark:disabled:bg-gray-800"
      />
    </div>
  )
}

function ColorPanel({ label, colors, editable, onChange, isDark }: {
  label: string; colors: BaseColors; editable: boolean; isDark: boolean
  onChange: (key: keyof BaseColors, v: string) => void
}) {
  const [hovered, setHovered] = useState(false)
  const panelBg    = isDark ? '#1e293b' : '#f8fafc'
  const labelColor = isDark ? '#94a3b8' : '#64748b'

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        borderRadius: 12, padding: 16, background: panelBg,
        border: `1px solid ${hovered ? 'var(--color-1)' : (isDark ? '#334155' : '#e2e8f0')}`,
        transition: 'border-color 0.2s ease',
      }}>
      <p style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.05em', color: labelColor, marginBottom: 12 }}>{label}</p>
      <div className="flex gap-2 justify-between">
        {COLOR_KEYS.map((k, i) => (
          <Swatch key={k} value={colors[k]} label={`C${i+1}`} editable={editable} onChange={v => onChange(k, v)} />
        ))}
      </div>
    </div>
  )
}

export default function ColorCustomizerUnified({
  schemaMode,
  defaultLightColors, defaultDarkColors,
  customLightColors, customDarkColors,
  onSave, onModeChange,
}: Props) {
  // localMode: seleção pendente — NÃO salva no banco até clicar Salvar
  const [localMode, setLocalMode] = useState<'default' | 'custom'>(schemaMode)
  const isCustom = localMode === 'custom'

  const [light,     setLight]     = useState<BaseColors>(isCustom ? customLightColors : defaultLightColors)
  const [dark,      setDark]      = useState<BaseColors>(isCustom ? customDarkColors  : defaultDarkColors)
  const [saving,    setSaving]    = useState(false)
  const [showToast, setShowToast] = useState(false)

  // Referência dos valores custom vindos do banco (para dirty check de edição de cores)
  const dbLight = useRef<BaseColors>(customLightColors)
  const dbDark  = useRef<BaseColors>(customDarkColors)

  // Dirty: modo diferente do banco OU cores custom editadas
  const isDirty = useMemo(() => {
    if (localMode !== schemaMode) return true
    if (localMode === 'custom') {
      return JSON.stringify(light) !== JSON.stringify(dbLight.current)
          || JSON.stringify(dark)  !== JSON.stringify(dbDark.current)
    }
    return false
  }, [localMode, schemaMode, light, dark])

  function setColor(theme: 'light'|'dark', key: keyof BaseColors, val: string) {
    if (theme === 'light') setLight(p => ({ ...p, [key]: val }))
    else                   setDark(p  => ({ ...p, [key]: val }))
  }

  // Troca de modo é local — não chama API
  function handleModeSwitch(mode: 'default' | 'custom') {
    setLocalMode(mode)
    if (mode === 'default') { setLight(defaultLightColors); setDark(defaultDarkColors) }
    else                    { setLight(customLightColors);  setDark(customDarkColors)  }
  }

  const lv = useMemo(() => ({
    regular: buildColorVariant(light, 'regular'),
    AA:      buildColorVariant(light, 'AA'),
    AAA:     buildColorVariant(light, 'AAA'),
  }), [light])
  const dv = useMemo(() => ({
    regular: buildColorVariant(dark, 'regular'),
    AA:      buildColorVariant(dark, 'AA'),
    AAA:     buildColorVariant(dark, 'AAA'),
  }), [dark])

  async function handleSave() {
    setSaving(true)
    try {
      // 1. Salva mudança de modo se necessário
      if (localMode !== schemaMode) await onModeChange(localMode)

      // 2. Salva cores apenas se estiver em custom E tiverem sido editadas
      const colorsEdited = localMode === 'custom' && (
        JSON.stringify(light) !== JSON.stringify(dbLight.current) ||
        JSON.stringify(dark)  !== JSON.stringify(dbDark.current)
      )
      if (colorsEdited) {
        await onSave(light, dark)
        dbLight.current = light
        dbDark.current  = dark
      }

      setShowToast(true)
      setTimeout(() => setShowToast(false), 3000)
    } finally { setSaving(false) }
  }

  // Restaura modo e cores ao estado do banco
  function handleReset() {
    setLocalMode(schemaMode)
    if (schemaMode === 'default') { setLight(defaultLightColors); setDark(defaultDarkColors) }
    else                          { setLight(dbLight.current);    setDark(dbDark.current)    }
  }

  const sectionHead = 'text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-3'

  return (
    <div>
      {/* ── Action bar ── */}
      <div className="flex items-center justify-between mb-6 gap-4
                      bg-gray-50 dark:bg-gray-800/60 border border-gray-200 dark:border-gray-700
                      rounded-xl px-4 py-3 shadow-sm transition-colors hover:border-[var(--color-1)]">

        {/* Seletor de esquema — mais destacado */}
        <div className="flex items-center gap-3">
          <span className="text-[11px] font-bold uppercase tracking-wider text-gray-700 dark:text-gray-200 whitespace-nowrap">
            Esquema
          </span>
          <div className="flex items-center gap-1 bg-white dark:bg-gray-700 rounded-lg p-1 border border-gray-200 dark:border-gray-600 shadow-sm">
            {([['default', <><Palette size={13} />Padrão</>], ['custom', <><PaintBrush size={13} />Customizado</>]] as const).map(([id, lbl]) => {
              const active = localMode === id
              return (
                <button key={id} onClick={() => handleModeSwitch(id)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all"
                  style={active
                    ? { background: 'var(--color-1)', color: 'var(--on-color-1)', cursor: 'default' }
                    : { background: 'transparent', color: '#64748b', cursor: 'pointer' }
                  }>
                  {lbl}
                </button>
              )
            })}
          </div>
        </div>

        {/* Botões de ação */}
        <div className="flex gap-2">
          <button
            onClick={handleReset}
            disabled={!isDirty}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold border whitespace-nowrap transition-all"
            style={{
              borderColor: !isDirty ? '#e2e8f0' : '#cbd5e1',
              background:  !isDirty ? '#f8fafc'  : '#f1f5f9',
              color:       !isDirty ? '#94a3b8'  : '#475569',
              cursor:      !isDirty ? 'not-allowed' : 'pointer',
            }}>
            <ArrowCounterClockwise size={15} />Restaurar
          </button>
          <button
            onClick={handleSave}
            disabled={!isDirty || saving}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold border-none transition-all"
            style={{
              background: !isDirty ? '#e2e8f0' : 'var(--color-save)',
              color:      !isDirty ? '#94a3b8' : 'var(--on-color-save)',
              cursor: (!isDirty || saving) ? 'not-allowed' : 'pointer',
              opacity: saving ? .6 : 1,
            }}>
            <FloppyDisk size={15} className={saving ? 'animate-spin' : undefined} />
            Salvar
          </button>
        </div>
      </div>

      {/* ── Toast de sucesso ── */}
      {showToast && ReactDOM.createPortal(
        <div style={{
          position: 'fixed', top: 24, right: 24, zIndex: 9999,
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '12px 20px', borderRadius: 12,
          background: 'var(--color-success)',
          color: 'var(--on-color-success)',
          boxShadow: '0 4px 24px rgba(0,0,0,.18)',
          fontSize: 14, fontWeight: 600,
          animation: 'sbv1-toast-in 0.25s ease',
        }}>
          <style>{`@keyframes sbv1-toast-in { from { opacity:0; transform:translateY(-10px) } to { opacity:1; transform:translateY(0) } }`}</style>
          <CheckCircle size={18} weight="bold" />
          Cores salvas com sucesso!
        </div>,
        document.body,
      )}

      {/* ── Color edit panels ── */}
      <section className="mb-6">
        <h3 className={sectionHead}>{isCustom ? 'Personalizar Cores' : 'Cores (somente leitura)'}</h3>
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-5">
          <div className="grid grid-cols-2 gap-4">
            <ColorPanel label="☀️ Claro"  colors={light} editable={isCustom} isDark={false} onChange={(k,v) => setColor('light',k,v)} />
            <ColorPanel label="🌙 Escuro" colors={dark}  editable={isCustom} isDark={true}  onChange={(k,v) => setColor('dark', k,v)} />
          </div>
        </div>
      </section>

      {/* ── Variant preview ── */}
      <section>
        <h3 className={sectionHead}>Preview WCAG em Tempo Real</h3>
        <ColorVariantsPreview lightVariants={lv} darkVariants={dv} />
      </section>
    </div>
  )
}
