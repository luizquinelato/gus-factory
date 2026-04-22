import type { BaseColors } from '../utils/colorCalculations'

// Paleta Blue/Navy/Pink — 5 tokens definidos pelo usuário (migration 0002 "default").
// Usados como fallback quando a API ainda não carregou (skeleton render).
// Todos validados WCAG threshold=0.5 → on_color = #FFFFFF.
export const DEFAULT_LIGHT_COLORS: BaseColors = {
  color1: '#1D4ED8',  // Primary   — blue-700   lum=0.107
  color2: '#1A1D2E',  // Surface   — navy dark   lum=0.013
  color3: '#BE185D',  // Accent    — pink-700    lum=0.124
  color4: '#475569',  // Muted     — slate-600   lum=0.089
  color5: '#A78BFA',  // Violet    — violet-400  lum=0.336
}

export const DEFAULT_DARK_COLORS: BaseColors = {
  color1: '#60A5FA',  // Primary   — blue-400    lum=0.363
  color2: '#252B42',  // Surface   — navy darker lum=0.025
  color3: '#F472B6',  // Accent    — pink-400    lum=0.347
  color4: '#94A3B8',  // Muted     — slate-400   lum=0.360
  color5: '#A78BFA',  // Violet    — violet-400  lum=0.336 (same)
}

export const COLOR_NAMES: (keyof BaseColors)[] = [
  'color1', 'color2', 'color3', 'color4', 'color5',
]

export const COLOR_LABELS: Record<string, string> = {
  color1: 'Cor Principal',
  color2: 'Cor Secundária',
  color3: 'Cor Terciária',
  color4: 'Cor Quaternária',
  color5: 'Cor Quinária',
}
