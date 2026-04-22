// ThemeContext — ETL Frontend (idêntico ao frontend principal)
import {
  createContext, useState, useLayoutEffect, useCallback, type ReactNode
} from 'react'
import { applyColorsToDOM } from '../utils/colorApplication'
import type { ColorScheme, ThemeMode, AccessibilityLevel, ColorSchemaMode } from '../types'

interface ThemeContextValue {
  themeMode: ThemeMode
  schemaMode: ColorSchemaMode
  accessibilityLevel: AccessibilityLevel
  colors: ColorScheme[]
  setThemeMode: (m: ThemeMode) => void
  setSchemaMode: (m: ColorSchemaMode) => void
  setAccessibilityLevel: (l: AccessibilityLevel) => void
  setColors: (c: ColorScheme[]) => void
  applyTheme: () => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

interface ThemeProviderProps {
  children: ReactNode
  initialColors?: ColorScheme[]
  initialSchema?: ColorSchemaMode
  initialTheme?: ThemeMode
}

export function ThemeProvider({
  children,
  initialColors = [],
  initialSchema = 'default',
  initialTheme = 'light',
}: ThemeProviderProps) {
  const [themeMode,          setThemeModeState]          = useState<ThemeMode>(initialTheme)
  const [schemaMode,         setSchemaModeState]         = useState<ColorSchemaMode>(initialSchema)
  const [accessibilityLevel, setAccessibilityLevelState] = useState<AccessibilityLevel>('regular')
  const [colors,             setColors]                  = useState<ColorScheme[]>(initialColors)

  const applyTheme = useCallback(() => {
    applyColorsToDOM(colors, themeMode, schemaMode, accessibilityLevel)
  }, [colors, themeMode, schemaMode, accessibilityLevel])

  useLayoutEffect(() => { applyTheme() }, [applyTheme])

  const setThemeMode         = useCallback((m: ThemeMode)         => setThemeModeState(m), [])
  const setSchemaMode        = useCallback((m: ColorSchemaMode)   => setSchemaModeState(m), [])
  const setAccessibilityLevel = useCallback((l: AccessibilityLevel) => setAccessibilityLevelState(l), [])

  return (
    <ThemeContext.Provider value={{
      themeMode, schemaMode, accessibilityLevel, colors,
      setThemeMode, setSchemaMode, setAccessibilityLevel, setColors, applyTheme,
    }}>
      {children}
    </ThemeContext.Provider>
  )
}

export { ThemeContext }
