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

// ── ETL Types ──────────────────────────────────────────────────────────────────

export type WorkerType = 'extraction' | 'transform' | 'processor'
export type QueueType  = WorkerType

export interface QueueStats {
  name:                    string
  messages_ready:          number
  messages_unacknowledged: number
  messages:                number
  consumers:               number
  state:                   string
  memory:                  number
  publish_rate:            number
  deliver_rate:            number
  ack_rate:                number
}

export interface WorkerInstance {
  worker_id:       number
  worker_type:     string
  queue:           string
  is_alive:        boolean
  is_running:      boolean
  processed_count: number
  error_count:     number
  last_message_at: number | null
}

export interface WorkerPool {
  count:   number
  alive:   number
  workers: WorkerInstance[]
}

export type WorkerStatus = Record<WorkerType, WorkerPool>

export interface WorkerConfig {
  extraction_workers: number
  transform_workers:  number
  processor_workers:  number
  ai_enabled:         boolean
}

export interface JobError {
  tenant_id:    number
  job_id:       number
  worker_type:  string
  error_code:   string
  error_detail: string
  entity_id:    string
  item_index:   number
  ai_enabled:   boolean
  created_at:   number
}

export interface FakeJobResult {
  job_id:    number
  run_id:    string
  tenant_id: number
  message:   string
  expected: {
    extraction_messages: number
    transform_messages:  number
    processor_messages:  number
    processor_ai_true:   number
    processor_ai_false:  number
  }
}

export interface SystemSetting {
  key:         string
  value:       string
  type:        string
  description: string
}

// ── Theme ──────────────────────────────────────────────────────────────────────

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
