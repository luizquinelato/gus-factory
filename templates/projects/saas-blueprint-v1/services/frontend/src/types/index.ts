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
  // Preferências de acessibilidade
  accessibility_level: AccessibilityLevel
  high_contrast_mode: boolean
  reduce_motion: boolean
  colorblind_safe_palette: boolean
}

export interface ColorScheme {
  color_schema_mode: string    // 'default' | 'custom'
  theme_mode: string           // 'light' | 'dark'
  accessibility_level: string  // 'regular' | 'AA' | 'AAA'
  color1: string
  color2: string
  color3: string
  color4: string
  color5: string
  on_color1: string
  on_color2: string
  on_color3: string
  on_color4: string
  on_color5: string
  on_gradient_1_2: string
  on_gradient_2_3: string
  on_gradient_3_4: string
  on_gradient_4_5: string
  on_gradient_5_1: string
}

export interface TenantColors {
  color_schema_mode: string
  colors: ColorScheme[]
}

export interface LoginResponse {
  access_token: string
  refresh_token: string       // opaque token — rotacionado a cada POST /auth/refresh
  expires_in: number          // segundos até expirar o access token (ex: 300 = 5 min)
  token_type: string
  user: User
  tenant_colors: TenantColors
}

export type ThemeMode = 'light' | 'dark'
export type AccessibilityLevel = 'regular' | 'AA' | 'AAA'
export type ColorSchemaMode = 'default' | 'custom'

export interface BaseColors {
  color1: string
  color2: string
  color3: string
  color4: string
  color5: string
}

export interface ColorVariant extends BaseColors {
  accessibility_level: string
  on_color1: string
  on_color2: string
  on_color3: string
  on_color4: string
  on_color5: string
  on_gradient_1_2: string
  on_gradient_2_3: string
  on_gradient_3_4: string
  on_gradient_4_5: string
  on_gradient_5_1: string
}
