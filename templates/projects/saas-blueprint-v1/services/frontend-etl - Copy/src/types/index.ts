// Tipos espelhados do frontend principal — mantidos sincronizados manualmente.
export interface User {
  id: number
  tenant_id: number
  name: string
  username: string
  email: string
  role: string
  is_admin: boolean
  theme_mode: 'light' | 'dark'
  avatar_url?: string | null
  accessibility_level: AccessibilityLevel
  high_contrast_mode: boolean
  reduce_motion: boolean
  colorblind_safe_palette: boolean
}

export interface ColorScheme {
  color_schema_mode: string
  theme_mode: string
  accessibility_level: string
  color1: string; color2: string; color3: string; color4: string; color5: string
  on_color1: string; on_color2: string; on_color3: string; on_color4: string; on_color5: string
  on_gradient_1_2: string; on_gradient_2_3: string; on_gradient_3_4: string
  on_gradient_4_5: string; on_gradient_5_1: string
}

export interface TenantColors {
  color_schema_mode: string
  colors: ColorScheme[]
}

export interface OttExchangeResponse {
  access_token: string
  token_type: string
  user: User
  tenant_colors: TenantColors
}

export type ThemeMode         = 'light' | 'dark'
export type AccessibilityLevel = 'regular' | 'AA' | 'AAA'
export type ColorSchemaMode   = 'default' | 'custom'
