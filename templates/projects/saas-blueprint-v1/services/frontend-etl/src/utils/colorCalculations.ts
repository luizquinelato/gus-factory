/**
 * colorCalculations.ts
 * ====================
 * Cálculos WCAG de luminância e on-color — mirror do backend Python.
 * Usado pelo ColorCustomizerUnified para preview em tempo real.
 */

export function calculateLuminance(hex: string): number {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16) / 255
  const g = parseInt(h.slice(2, 4), 16) / 255
  const b = parseInt(h.slice(4, 6), 16) / 255
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4))
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

export function calculateContrastRatio(c1: string, c2: string): number {
  const l1 = calculateLuminance(c1)
  const l2 = calculateLuminance(c2)
  const bright = Math.max(l1, l2)
  const dark   = Math.min(l1, l2)
  return (bright + 0.05) / (dark + 0.05)
}

export function pickOnColor(bg: string, threshold = 0.5): string {
  return calculateLuminance(bg) < threshold ? '#FFFFFF' : '#000000'
}

export function pickGradientOnColor(ca: string, cb: string, threshold = 0.5): string {
  const oa = pickOnColor(ca, threshold)
  const ob = pickOnColor(cb, threshold)
  if (oa === ob) return oa
  const avg = (calculateLuminance(ca) + calculateLuminance(cb)) / 2
  return avg < threshold ? '#FFFFFF' : '#000000'
}

export function applyDarken(hex: string, factor: number): string {
  const h = hex.replace('#', '')
  const r = Math.max(0, Math.round(parseInt(h.slice(0, 2), 16) * (1 - factor)))
  const g = Math.max(0, Math.round(parseInt(h.slice(2, 4), 16) * (1 - factor)))
  const b = Math.max(0, Math.round(parseInt(h.slice(4, 6), 16) * (1 - factor)))
  return '#' + [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('').toUpperCase()
}

export function applyAccessibilityLevel(hex: string, level: 'regular' | 'AA' | 'AAA'): string {
  if (level === 'regular') return hex.toUpperCase()
  const factor = level === 'AA' ? 0.05 : 0.10
  return applyDarken(hex, factor)
}

export interface BaseColors {
  color1: string; color2: string; color3: string; color4: string; color5: string
}

export interface ColorVariantFull extends BaseColors {
  accessibility_level: string
  on_color1: string; on_color2: string; on_color3: string; on_color4: string; on_color5: string
  on_gradient_1_2: string; on_gradient_2_3: string
  on_gradient_3_4: string; on_gradient_4_5: string; on_gradient_5_1: string
}

export function buildColorVariant(
  baseColors: BaseColors,
  level: 'regular' | 'AA' | 'AAA',
  threshold = 0.5,
): ColorVariantFull {
  const enhanced: BaseColors = {
    color1: applyAccessibilityLevel(baseColors.color1, level),
    color2: applyAccessibilityLevel(baseColors.color2, level),
    color3: applyAccessibilityLevel(baseColors.color3, level),
    color4: applyAccessibilityLevel(baseColors.color4, level),
    color5: applyAccessibilityLevel(baseColors.color5, level),
  }
  return {
    ...enhanced,
    accessibility_level: level,
    on_color1: pickOnColor(enhanced.color1, threshold),
    on_color2: pickOnColor(enhanced.color2, threshold),
    on_color3: pickOnColor(enhanced.color3, threshold),
    on_color4: pickOnColor(enhanced.color4, threshold),
    on_color5: pickOnColor(enhanced.color5, threshold),
    on_gradient_1_2: pickGradientOnColor(enhanced.color1, enhanced.color2, threshold),
    on_gradient_2_3: pickGradientOnColor(enhanced.color2, enhanced.color3, threshold),
    on_gradient_3_4: pickGradientOnColor(enhanced.color3, enhanced.color4, threshold),
    on_gradient_4_5: pickGradientOnColor(enhanced.color4, enhanced.color5, threshold),
    on_gradient_5_1: pickGradientOnColor(enhanced.color5, enhanced.color1, threshold),
  }
}

export function buildAllVariants(baseColors: BaseColors, threshold = 0.5): ColorVariantFull[] {
  return (['regular', 'AA', 'AAA'] as const).map((level) =>
    buildColorVariant(baseColors, level, threshold),
  )
}
