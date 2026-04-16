import { useState } from 'react'
import type { ColorVariantFull } from '../utils/colorCalculations'
import { calculateContrastRatio } from '../utils/colorCalculations'

type Level = 'regular' | 'AA' | 'AAA'

interface Props {
  lightVariants: Record<Level, ColorVariantFull>
  darkVariants:  Record<Level, ColorVariantFull>
}

const LEVELS: Level[] = ['regular', 'AA', 'AAA']

const LEVEL_META: Record<Level, { label: string; color: string; desc: string }> = {
  regular: { label: 'Regular',   color: '#64748b', desc: 'Sem ajuste de contraste' },
  AA:      { label: 'WCAG AA',   color: '#d97706', desc: 'Contraste mínimo 4.5:1'  },
  AAA:     { label: 'WCAG AAA',  color: '#059669', desc: 'Contraste mínimo 7:1'    },
}

const SZ = 48   // tamanho dos boxes Aa em px
const PAIRS: [number, number][] = [[1,2],[2,3],[3,4],[4,5],[5,1]]

function OnColorRow({ variant }: { variant: ColorVariantFull }) {
  return (
    <div style={{ display: 'flex', gap: 4 }}>
      {([1,2,3,4,5] as const).map(n => {
        const bg  = variant[`color${n}`]
        const fg  = variant[`on_color${n}`]
        const cr  = calculateContrastRatio(bg, fg)
        return (
          <div key={n} title={`${bg} | cr ${cr.toFixed(1)}:1`}
            style={{
              flex: 1, height: SZ, borderRadius: 8,
              background: bg, display: 'flex',
              alignItems: 'center', justifyContent: 'center',
              color: fg, fontWeight: 700, fontSize: 14, cursor: 'default',
            }}>
            Aa
          </div>
        )
      })}
    </div>
  )
}

function GradientRow({ variant }: { variant: ColorVariantFull }) {
  return (
    <div style={{ display: 'flex', gap: 4 }}>
      {PAIRS.map(([a, b]) => {
        const v   = variant as unknown as Record<string, string>
        const ca  = v[`color${a}`]
        const cb  = v[`color${b}`]
        const fg  = v[`on_gradient_${a}_${b}`]
        return (
          <div key={`${a}-${b}`} title={`gradient ${a}→${b}`}
            style={{
              flex: 1, height: SZ, borderRadius: 8,
              background: `linear-gradient(135deg, ${ca}, ${cb})`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: fg, fontWeight: 700, fontSize: 14, cursor: 'default',
            }}>
            Aa
          </div>
        )
      })}
    </div>
  )
}

function Panel({ variant, label, isDark }: { variant: ColorVariantFull; label: string; isDark: boolean }) {
  const [hov, setHov] = useState(false)
  const bg          = isDark ? '#1e293b' : '#f8fafc'
  const borderColor = hov ? 'var(--color-1)' : (isDark ? '#334155' : '#e2e8f0')
  const lColor      = isDark ? '#94a3b8' : '#64748b'

  return (
    <div onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{ borderRadius: 10, border: `1px solid ${borderColor}`, background: bg, padding: 12, transition: 'border-color .15s' }}>
      <p style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.05em', color: lColor, marginBottom: 8 }}>{label}</p>
      <div className="flex flex-col gap-1">
        <OnColorRow variant={variant} />
        <GradientRow variant={variant} />
      </div>
    </div>
  )
}

export default function ColorVariantsPreview({ lightVariants, darkVariants }: Props) {
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-5">
      {LEVELS.map((lvl, i) => {
        const meta = LEVEL_META[lvl]
        return (
          <div key={lvl}>
            {i > 0 && <hr className="border-gray-100 dark:border-gray-700 my-4" />}
            <div className="flex items-center gap-2 mb-3">
              <span className="inline-block px-2.5 py-0.5 rounded-full text-xs font-bold text-white"
                style={{ background: meta.color }}>{meta.label}</span>
              <span className="text-xs text-gray-400 dark:text-gray-500">{meta.desc}</span>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Panel variant={lightVariants[lvl]} label="☀️ Claro"  isDark={false} />
              <Panel variant={darkVariants[lvl]}  label="🌙 Escuro" isDark={true}  />
            </div>
          </div>
        )
      })}
    </div>
  )
}
