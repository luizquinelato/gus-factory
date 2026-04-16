import { useCallback, useEffect, useState } from 'react'
import { Lock } from '@phosphor-icons/react'
import { useTheme } from '../contexts/useTheme'
import { useAuth } from '../contexts/AuthContext'
import apiClient from '../services/apiClient'
import type { BaseColors } from '../utils/colorCalculations'
import type { ColorScheme, ColorSchemaMode } from '../types'
import ColorCustomizerUnified from '../components/ColorCustomizerUnified'
import { DEFAULT_LIGHT_COLORS, DEFAULT_DARK_COLORS } from '../config/defaultColors'

const SEMANTIC_COLORS = [
  { key: 'success', label: 'Success', note: 'criar, confirmar'   },
  { key: 'danger',  label: 'Danger',  note: 'deletar, erro'      },
  { key: 'warning', label: 'Warning', note: 'editar, atenção'    },
  { key: 'info',    label: 'Info',    note: 'informar, detalhe'  },
  { key: 'neutral', label: 'Neutral', note: 'cancelar, secundário' },
]

const ACTION_COLORS = [
  { key: 'create', label: 'create', maps: '→ success'  },
  { key: 'save',   label: 'save',   maps: '→ color-1 ★' },
  { key: 'update', label: 'update', maps: '→ color-1 ★' },
  { key: 'edit',   label: 'edit',   maps: '→ warning'  },
  { key: 'delete', label: 'delete', maps: '→ danger'   },
  { key: 'cancel', label: 'cancel', maps: '→ neutral'  },
]

function Swatch({ varKey, label, sub }: { varKey: string; label: string; sub: string }) {
  return (
    <div className="flex flex-col items-center gap-1.5 flex-1">
      <div style={{
        width: '100%', height: 48, borderRadius: 8,
        background: `var(--color-${varKey})`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: `var(--on-color-${varKey})`,
        fontWeight: 700, fontSize: 14,
      }}>Aa</div>
      <span className="text-[11px] font-semibold text-gray-600 dark:text-gray-300">{label}</span>
      <span className="text-[10px] text-gray-400 dark:text-gray-500 text-center leading-tight">{sub}</span>
    </div>
  )
}

function extractBase(
  colors: ColorScheme[], schemaMode: string, theme: 'light' | 'dark', fallback: BaseColors,
): BaseColors {
  const s = colors.find(
    c => c.color_schema_mode === schemaMode && c.theme_mode === theme && c.accessibility_level === 'regular',
  )
  if (!s) return fallback
  return { color1: s.color1, color2: s.color2, color3: s.color3, color4: s.color4, color5: s.color5 }
}

export default function ColorSettingsPage() {
  const { schemaMode, setColors, setSchemaMode } = useTheme()
  const { updateTenantColors } = useAuth()

  const [allColors, setAllColors] = useState<ColorScheme[]>([])
  const [loading,   setLoading]   = useState(true)

  // Busca TODAS as cores do banco ao montar (default + custom, light + dark, 3 WCAG levels)
  useEffect(() => {
    apiClient.get<{ colors: ColorScheme[]; color_schema_mode: string }>('/tenant/colors/unified')
      .then(({ data }) => {
        setAllColors(data.colors)
        setColors(data.colors)           // atualiza ThemeContext com dados frescos
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [setColors])

  // Cores para cada modo — passadas ao componente filho para troca local
  const defaultLight = extractBase(allColors, 'default', 'light', DEFAULT_LIGHT_COLORS)
  const defaultDark  = extractBase(allColors, 'default', 'dark',  DEFAULT_DARK_COLORS)
  const customLight  = extractBase(allColors, 'custom',  'light', DEFAULT_LIGHT_COLORS)
  const customDark   = extractBase(allColors, 'custom',  'dark',  DEFAULT_DARK_COLORS)

  // Salva apenas as cores (modo já tratado pelo filho via handleModeChange)
  const handleSaveColors = useCallback(async (light: BaseColors, dark: BaseColors) => {
    const { data } = await apiClient.put('/tenant/colors/unified', { light_colors: light, dark_colors: dark })
    setAllColors(data.colors)
    setColors(data.colors)
    // Salva colors + color_schema_mode juntos → evita localStorage parcialmente atualizado
    updateTenantColors({ colors: data.colors, color_schema_mode: data.color_schema_mode })
  }, [setColors, updateTenantColors])

  // Chamado pelo filho quando o modo precisa ser persistido no banco
  const handleModeChange = useCallback(async (mode: 'default' | 'custom') => {
    await apiClient.post('/tenant/colors/mode', { mode })
    setSchemaMode(mode as ColorSchemaMode)
    setColors(allColors)
    updateTenantColors({ color_schema_mode: mode })
  }, [setSchemaMode, allColors, setColors, updateTenantColors])

  const sectionHead = 'text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-3'

  return (
    <div className="min-h-full p-8 space-y-6">
      <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">Cores</h1>

      {/* ── Brand colors (editável) ── */}
      <div>
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div style={{
              width: 40, height: 40, borderRadius: '50%',
              border: '3px solid #e2e8f0', borderTopColor: 'var(--color-1)',
              animation: 'spin 0.8s linear infinite',
            }} />
            <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
          </div>
        ) : (
          <ColorCustomizerUnified
            key={allColors.length > 0 ? 'loaded' : 'loading'}
            schemaMode={schemaMode}
            defaultLightColors={defaultLight}
            defaultDarkColors={defaultDark}
            customLightColors={customLight}
            customDarkColors={customDark}
            onSave={handleSaveColors}
            onModeChange={handleModeChange}
          />
        )}
      </div>

      {/* ── Universal colors (somente leitura) ── */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className={sectionHead}>Cores Universais</h3>
            <p className="text-xs text-gray-400 dark:text-gray-500 -mt-2">
              Fixas — não mudam com o esquema de cores do tenant.
            </p>
          </div>
          <span className="flex items-center gap-1 text-[10px] font-semibold text-gray-400 dark:text-gray-500
                           bg-gray-100 dark:bg-gray-700 px-2.5 py-1 rounded-full">
            <Lock size={10} /> somente leitura
          </span>
        </div>

        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-5">
          {/* Semânticas */}
          <p className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">Semânticas</p>
          <div className="flex gap-3 mb-5">
            {SEMANTIC_COLORS.map(c => <Swatch key={c.key} varKey={c.key} label={c.label} sub={c.note} />)}
          </div>

          {/* Ações */}
          <p className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">
            Aliases de Ação &nbsp;<span className="normal-case font-normal">(★ segue a cor primária da marca)</span>
          </p>
          <div className="flex gap-3">
            {ACTION_COLORS.map(c => <Swatch key={c.key} varKey={c.key} label={c.label} sub={c.maps} />)}
          </div>
        </div>
      </section>
    </div>
  )
}
