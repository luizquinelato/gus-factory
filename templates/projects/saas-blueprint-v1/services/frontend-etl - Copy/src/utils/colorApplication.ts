/**
 * colorApplication.ts — ETL Frontend
 * Idêntico ao do frontend principal — aplica CSS vars de cor ao :root.
 */
import type { ColorScheme, ThemeMode, AccessibilityLevel } from '../types'

export function applyColorsToDOM(
  colors: ColorScheme[],
  themeMode: ThemeMode,
  schemaMode: string,
  accessibilityLevel: AccessibilityLevel = 'regular',
): void {
  const scheme = colors.find(
    (c) =>
      c.color_schema_mode === schemaMode &&
      c.theme_mode === themeMode &&
      c.accessibility_level === accessibilityLevel,
  )
  if (!scheme) return

  const root = document.documentElement

  for (let n = 1; n <= 5; n++) {
    root.style.setProperty(`--color-${n}`, scheme[`color${n}` as keyof ColorScheme] as string)
    root.style.setProperty(`--on-color-${n}`, scheme[`on_color${n}` as keyof ColorScheme] as string)
  }

  const pairs: [number, number][] = [[1,2],[2,3],[3,4],[4,5],[5,1]]
  for (const [a, b] of pairs) {
    const onGrad = scheme[`on_gradient_${a}_${b}` as keyof ColorScheme] as string
    const ca = scheme[`color${a}` as keyof ColorScheme] as string
    const cb = scheme[`color${b}` as keyof ColorScheme] as string
    root.style.setProperty(`--on-gradient-${a}-${b}`, onGrad)
    root.style.setProperty(`--gradient-${a}-${b}`, `linear-gradient(135deg, ${ca}, ${cb})`)
  }

  const c = (n: number) => scheme[`color${n}` as keyof ColorScheme] as string
  root.style.setProperty('--gradient-full', `linear-gradient(135deg, ${c(1)}, ${c(2)}, ${c(3)}, ${c(4)}, ${c(5)})`)

  if (themeMode === 'dark') root.classList.add('dark')
  else root.classList.remove('dark')
}

export function getActiveScheme(
  colors: ColorScheme[],
  schemaMode: string,
  themeMode: ThemeMode,
  accessibilityLevel: AccessibilityLevel = 'regular',
): ColorScheme | undefined {
  return colors.find(
    (c) =>
      c.color_schema_mode === schemaMode &&
      c.theme_mode === themeMode &&
      c.accessibility_level === accessibilityLevel,
  )
}
