<!-- blueprint: db_changes=true seed_data=true -->
# 09. Sistema de Color Schema Multi-Tenant

Este documento define a arquitetura completa do sistema de cores dinâmicas por tenant: 5 cores base, gradientes, on-colors, 3 níveis WCAG, 2 modos (default/custom) e 2 temas (light/dark).

## 🎨 1. Arquitetura — 3 Camadas

| Camada | Responsabilidade |
|---|---|
| **Banco** | `tenant_colors` — armazena as 5 cores por `(tenant, mode, theme, level)` = 12 linhas por tenant |
| **Backend** | Calcula `on-colors`, gradientes e variantes WCAG em tempo de execução |
| **Frontend** | Injeta como CSS Custom Properties via `useColorApplication` |

### Combinações no banco (12 por tenant)
```
color_schema_mode × theme_mode × accessibility_level
    default       ×    light   ×   regular / AA / AAA  (3 linhas)
    default       ×    dark    ×   regular / AA / AAA  (3 linhas)
    custom        ×    light   ×   regular / AA / AAA  (3 linhas)
    custom        ×    dark    ×   regular / AA / AAA  (3 linhas)
```

## 🗃️ 2. Schema do Banco de Dados

```sql
-- Tabela de cores por tenant
CREATE TABLE tenant_colors (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    color_schema_mode    VARCHAR(10)  NOT NULL CHECK (color_schema_mode IN ('default','custom')),
    theme_mode           VARCHAR(10)  NOT NULL CHECK (theme_mode IN ('light','dark')),
    accessibility_level  VARCHAR(10)  NOT NULL CHECK (accessibility_level IN ('regular','AA','AAA')),
    -- 5 cores base (hex, ex: #6366f1)
    color1  VARCHAR(7) NOT NULL,
    color2  VARCHAR(7) NOT NULL,
    color3  VARCHAR(7) NOT NULL,
    color4  VARCHAR(7) NOT NULL,
    color5  VARCHAR(7) NOT NULL,
    -- on-colors calculados pelo backend
    on_color1  VARCHAR(7) NOT NULL,
    on_color2  VARCHAR(7) NOT NULL,
    on_color3  VARCHAR(7) NOT NULL,
    on_color4  VARCHAR(7) NOT NULL,
    on_color5  VARCHAR(7) NOT NULL,
    -- on-gradients calculados
    on_gradient_1_2  VARCHAR(7) NOT NULL,
    on_gradient_2_3  VARCHAR(7) NOT NULL,
    on_gradient_3_4  VARCHAR(7) NOT NULL,
    on_gradient_4_5  VARCHAR(7) NOT NULL,
    on_gradient_5_1  VARCHAR(7) NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, color_schema_mode, theme_mode, accessibility_level)
);
-- O campo color_schema_mode do tenant indica qual modo está ativo
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS color_schema_mode VARCHAR(10) DEFAULT 'default';
```

## 🌓 3. Light/Dark Mode por Usuário

A preferência de tema (`light` | `dark` | `system`) é salva em `users.theme_preference` e gerenciada pelo `ThemeContext`:

```tsx
// src/contexts/ThemeContext.tsx
import { createContext, useContext, useEffect, useState } from 'react';
type Theme = 'light' | 'dark';
const ThemeContext = createContext<{ theme: Theme; toggleTheme: () => void } | null>(null);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setTheme] = useState<Theme>(() =>
    (localStorage.getItem('theme') as Theme) ?? 'light'
  );
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    localStorage.setItem('theme', theme);
  }, [theme]);
  const toggleTheme = () => setTheme(t => t === 'light' ? 'dark' : 'light');
  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>;
};
export const useTheme = () => { const ctx = useContext(ThemeContext); if (!ctx) throw new Error('useTheme'); return ctx; };
```

## 🎨 4. Duas Paletas Padrão

### Paleta 1 — **Cosmos** (fria, tech-forward, premium)
| Cor | Hex | Nome | Uso |
|---|---|---|---|
| color1 | `#6366F1` | Indigo vivid | Primário, botões |
| color2 | `#22D3EE` | Cyan | Info, secundário |
| color3 | `#34D399` | Emerald | Sucesso, crescimento |
| color4 | `#A78BFA` | Violet | Accent, badges |
| color5 | `#0F172A` | Slate dark | Âncora, dark brand |

### Paleta 2 — **Solano** (quente, energia brasileira, dinâmica)
| Cor | Hex | Nome | Uso |
|---|---|---|---|
| color1 | `#F97316` | Orange vivid | Energia, CTA |
| color2 | `#FACC15` | Yellow | Destaque, alerta |
| color3 | `#22C55E` | Green | Crescimento |
| color4 | `#3B82F6` | Blue | Confiança |
| color5 | `#1C1917` | Stone dark | Âncora, elegância |

> A paleta padrão usada ao criar um novo projeto é **Cosmos**. O seed insere as 12 combinações com `color_schema_mode='default'`.

## 🧮 5. Cálculo de Luminância e Variantes WCAG

```python
# services/backend/app/services/color_service.py
import math

def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def luminance(hex_color: str) -> float:
    r, g, b = [v / 255.0 for v in hex_to_rgb(hex_color)]
    lin = lambda c: c / 12.92 if c <= 0.03928 else math.pow((c + 0.055) / 1.055, 2.4)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

def contrast_ratio(c1: str, c2: str) -> float:
    l1, l2 = luminance(c1), luminance(c2)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)

def get_on_color(hex_bg: str, level: str = 'regular') -> str:
    """Retorna #FFFFFF ou #000000 conforme o nível WCAG."""
    thresholds = {'regular': 4.5, 'AA': 4.5, 'AAA': 7.0}
    ratio = thresholds.get(level, 4.5)
    return '#FFFFFF' if contrast_ratio(hex_bg, '#FFFFFF') >= ratio else '#000000'

def get_gradient_on_color(c1: str, c2: str) -> str:
    """On-color para gradiente: usa luminância média dos dois extremos."""
    avg_lum = (luminance(c1) + luminance(c2)) / 2
    return '#FFFFFF' if avg_lum < 0.5 else '#000000'

def build_color_payload(colors: dict, level: str = 'regular') -> dict:
    """Monta o payload completo a partir das 5 cores base."""
    c = colors  # c['color1'] .. c['color5']
    return {
        **c,
        'on_color1': get_on_color(c['color1'], level),
        'on_color2': get_on_color(c['color2'], level),
        'on_color3': get_on_color(c['color3'], level),
        'on_color4': get_on_color(c['color4'], level),
        'on_color5': get_on_color(c['color5'], level),
        'on_gradient_1_2': get_gradient_on_color(c['color1'], c['color2']),
        'on_gradient_2_3': get_gradient_on_color(c['color2'], c['color3']),
        'on_gradient_3_4': get_gradient_on_color(c['color3'], c['color4']),
        'on_gradient_4_5': get_gradient_on_color(c['color4'], c['color5']),
        'on_gradient_5_1': get_gradient_on_color(c['color5'], c['color1']),
    }
```

## 🌐 6. API de Cores (Backend)

```
GET  /api/tenant/colors/unified     → retorna as 12 combinações + color_schema_mode ativo
POST /api/tenant/colors/mode        → body: { "mode": "default" | "custom" }
PUT  /api/tenant/colors/custom      → body: { light: {color1..5}, dark: {color1..5} }
                                      salva as 6 linhas custom (2 temas × 3 níveis calculados)
```

O endpoint `unified` retorna:
```json
{
  "success": true,
  "color_schema_mode": "default",
  "colors": [
    { "color_schema_mode": "default", "theme_mode": "light", "accessibility_level": "regular",
      "color1": "#6366f1", "on_color1": "#ffffff", "on_gradient_1_2": "#ffffff", ... },
    ...
  ]
}
```

## 🖌️ 7. Frontend — colorApplication.ts e useColorApplication

```typescript
// src/utils/colorApplication.ts
export function applyColorsToDOM(colorData: ColorData): void {
  const root = document.documentElement;
  const { color1, color2, color3, color4, color5 } = colorData;
  // Cores base
  root.style.setProperty('--color-1', color1);
  root.style.setProperty('--color-2', color2);
  root.style.setProperty('--color-3', color3);
  root.style.setProperty('--color-4', color4);
  root.style.setProperty('--color-5', color5);
  // On-colors
  ['1','2','3','4','5'].forEach(n =>
    root.style.setProperty(`--on-color-${n}`, (colorData as any)[`on_color${n}`])
  );
  // Gradientes
  root.style.setProperty('--gradient-1-2', `linear-gradient(135deg,${color1},${color2})`);
  root.style.setProperty('--gradient-2-3', `linear-gradient(135deg,${color2},${color3})`);
  root.style.setProperty('--gradient-3-4', `linear-gradient(135deg,${color3},${color4})`);
  root.style.setProperty('--gradient-4-5', `linear-gradient(135deg,${color4},${color5})`);
  root.style.setProperty('--gradient-5-1', `linear-gradient(135deg,${color5},${color1})`);
  root.style.setProperty('--gradient-full', `linear-gradient(135deg,${color1},${color2},${color3},${color4},${color5})`);
  // On-gradients
  root.style.setProperty('--on-gradient-1-2', colorData.on_gradient_1_2);
  root.style.setProperty('--on-gradient-2-3', colorData.on_gradient_2_3);
  root.style.setProperty('--on-gradient-3-4', colorData.on_gradient_3_4);
  root.style.setProperty('--on-gradient-4-5', colorData.on_gradient_4_5);
  root.style.setProperty('--on-gradient-5-1', colorData.on_gradient_5_1);
}
```

```typescript
// src/hooks/useColorApplication.ts
import { useEffect } from 'react';
import { useTheme } from '../contexts/ThemeContext';
import { applyColorsToDOM } from '../utils/colorApplication';
import apiClient from '../services/apiClient';

export function useColorApplication() {
  const { theme } = useTheme();
  useEffect(() => {
    const apply = async () => {
      try {
        const colorMode = localStorage.getItem('color_schema_mode') ?? 'default';
        const cached = localStorage.getItem('color_data');
        const colors: ColorData[] = cached ? JSON.parse(cached) : [];
        const data = colors.find(c =>
          c.color_schema_mode === colorMode &&
          c.theme_mode === theme &&
          c.accessibility_level === 'regular'
        );
        if (data) { applyColorsToDOM(data); return; }
        // Sem cache — busca no backend
        const res = await apiClient.get('/tenant/colors/unified');
        if (res.data.success) {
          localStorage.setItem('color_data', JSON.stringify(res.data.colors));
          localStorage.setItem('color_schema_mode', res.data.color_schema_mode);
          const fresh = res.data.colors.find((c: ColorData) =>
            c.color_schema_mode === res.data.color_schema_mode &&
            c.theme_mode === theme && c.accessibility_level === 'regular'
          );
          if (fresh) applyColorsToDOM(fresh);
        }
      } catch (e) { console.error('useColorApplication:', e); }
    };
    apply();
    window.addEventListener('colorDataLoaded', apply);
    return () => window.removeEventListener('colorDataLoaded', apply);
  }, [theme]);
}
```

## 🗂️ 8. defaultColors.ts — Paletas Padrão

```typescript
// src/config/defaultColors.ts
export const PALETTE_COSMOS = {
  color1: '#6366F1', color2: '#22D3EE', color3: '#34D399', color4: '#A78BFA', color5: '#0F172A',
};
export const PALETTE_SOLANO = {
  color1: '#F97316', color2: '#FACC15', color3: '#22C55E', color4: '#3B82F6', color5: '#1C1917',
};
// Padrão do projeto — altere para PALETTE_SOLANO se preferir
export const DEFAULT_PALETTE = PALETTE_COSMOS;

export const colorNames = {
  color1: 'Cor 1', color2: 'Cor 2', color3: 'Cor 3', color4: 'Cor 4', color5: 'Cor 5',
};
export const colorDescriptions = {
  color1: 'Cor principal da marca — botões primários e destaques',
  color2: 'Cor secundária — info e feedback positivo',
  color3: 'Cor de profundidade — navegação e elementos de confiança',
  color4: 'Cor de accent — badges e elementos decorativos',
  color5: 'Âncora escura — brand area da sidebar e gradientes de profundidade',
};
```

## 🖌️ 9. ColorSettingsPage e ColorCustomizerUnified

> **Referência obrigatória**: `gus-plumo/services/frontend/src/` — **copiar exatamente** estes arquivos, adaptando apenas textos e import paths.

### Arquivos a copiar do plumo (sem modificar a lógica):

| Arquivo plumo | Destino no projeto |
|---|---|
| `pages/ColorSettingsPage.tsx` | `src/pages/ColorSettingsPage.tsx` |
| `components/ColorCustomizerUnified.tsx` | `src/components/ColorCustomizerUnified.tsx` |
| `components/ColorVariantsPreview.tsx` | `src/components/ColorVariantsPreview.tsx` |
| `hooks/useColorData.ts` | `src/hooks/useColorData.ts` |
| `hooks/useColorApplication.ts` | `src/hooks/useColorApplication.ts` |
| `services/colorApplicationService.ts` | `src/services/colorApplicationService.ts` |
| `services/colorDataService.ts` | `src/services/colorDataService.ts` |
| `utils/colorApplication.ts` | `src/utils/colorApplication.ts` |
| `utils/colorCalculations.ts` | `src/utils/colorCalculations.ts` |
| `utils/colorUtils.ts` | `src/utils/colorUtils.ts` |
| `config/defaultColors.ts` | `src/config/defaultColors.ts` |

### Estrutura e regras (não alterar):

```tsx
// src/pages/ColorSettingsPage.tsx — estrutura exata do plumo
import ColorCustomizerUnified from '../components/ColorCustomizerUnified'

const ColorSettingsPage: React.FC = () => (
  <div className="flex h-screen bg-gray-100 dark:bg-gray-900">
    <Sidebar />
    <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
      <ColorCustomizerUnified />
      {/* Color Usage Guide (5 colunas — uma por cor) */}
    </main>
  </div>
)
```

**Regras do `ColorCustomizerUnified` (não alterar):**
1. **Modo default**: campos bloqueados com ícone `Lock`. Botão ativo usa `var(--gradient-1-2)`.
2. **Modo custom**: editores hex + color picker. On-colors calculados em tempo real via `calculateVariantsForAllLevels`.
3. **Um clique salva tudo**: chama `PUT /api/tenant/colors/unified` + `POST /api/tenant/colors/mode` + dispara `window.dispatchEvent(new CustomEvent('colorDataLoaded'))` para aplicação imediata sem reload.
4. Ao trocar de modo, recarrega as cores do localStorage (`color_data`) antes de ir ao backend.
5. `ColorVariantsPreview` exibe as 3 variantes WCAG (regular, AA, AAA) em tempo real para light e dark.

## 🖥️ 10. Arquivos de Referência Visual

> Os arquivos abaixo estão em `docs/reference/` e devem ser **abertos no browser** para ver o design exato a implementar.

| Arquivo | O que mostra |
|---|---|
| `docs/reference/login.html` | Tela de login — canvas animado + card glassmorphism + form (abre e veja) |
| `docs/reference/color-settings.html` | Página de cores — layout completo, interativo, com **todas as funções de cálculo em JS** |

O `color-settings.html` é a referência canônica para:
- Estrutura de layout (sidebar + main + painéis light/dark)
- Funções `luminance()`, `onColor()`, `gradientOnColor()`, `darken()`, `applyLevel()`, `calculateVariants()`, `buildAllLevels()` — traduzir 1:1 para TypeScript no frontend e Python no backend
- Comentários sobre a estrutura do `localStorage` (`color_data`, `color_schema_mode`)

## 🗄️ 11. Persistência — DB e Cache

Toda mudança de cor ou de modo é **sempre persistida no banco** e depois refletida no cache local.

| O que muda | Onde persiste no DB | Cache local |
|---|---|---|
| Usuário troca light ↔ dark | `users.theme_mode` (UPDATE via `PATCH /api/user/me`) | `ThemeContext` em memória; não usa localStorage |
| Tenant troca default ↔ custom | `tenants.color_schema_mode` (UPDATE via `POST /api/tenant/colors/mode`) | `localStorage('color_schema_mode')` invalidado e reescrito |
| Tenant edita cores custom | `tenant_colors` (UPSERT via `PUT /api/tenant/colors/custom`) | `localStorage('color_data')` invalidado e reescrito |

**Regras obrigatórias de implementação:**
1. Nunca salvar `theme_mode` só no localStorage — o backend é o source of truth.
2. Após qualquer `PUT` ou `POST` de cor/modo, limpar `localStorage('color_data')` e `localStorage('color_schema_mode')` antes de regravar com os novos valores retornados pela API.
3. O evento `colorDataLoaded` dispara a reaplicação do CSS sem reload (`window.dispatchEvent(new CustomEvent('colorDataLoaded'))`).

**Valores iniciais (seed data):**
- `tenants.color_schema_mode = 'default'` (modo de cor ativo do tenant)
- `users.theme_mode = 'light'` (tema do admin no primeiro login)

## 🚦 11. Cores Universais (Imutáveis)

Status e ações CRUD **nunca** são alterados pelo tenant. Definidos no `index.css` (ver doc 08).

- **Status**: `success` #22c55e · `warning` #eab308 · `error` #ef4444 · `info` #3b82f6
- **CRUD**: `--crud-create` · `--crud-edit` · `--crud-delete` · `--crud-cancel`

## ⚙️ 12. Backend — API de Cores (referência: plumo)

> **Referência obrigatória**: `gus-plumo/services/backend/app/`
>
> Copiar e adaptar:
> - `routers/tenant_colors_router.py` → `app/routers/tenant_colors_router.py`
> - `services/color_calculation_service.py` → `app/services/color_calculation_service.py`

### Endpoints obrigatórios

```
GET  /api/tenant/colors/unified        → todas as 12 combinações + color_schema_mode ativo do tenant
                                          requer: get_current_user (qualquer role)
PUT  /api/tenant/colors/unified        → salva light_colors + dark_colors (5 cores cada)
                                          backend calcula on-colors, gradientes e variantes AA/AAA
                                          requer: require_admin
POST /api/tenant/colors/mode           → body { "mode": "default" | "custom" }
                                          atualiza tenants.color_schema_mode no banco
                                          requer: get_current_user
```

### Schema dos modelos Pydantic (não alterar)

```python
class UnifiedColorUpdate(BaseModel):
    light_colors: Dict[str, str]   # color1..color5 apenas (on-colors calculados no backend)
    dark_colors:  Dict[str, str]

class ColorModeUpdate(BaseModel):
    mode: str   # 'default' | 'custom'

class ColorSchemeResponse(BaseModel):
    id: int; tenant_id: int; color_schema_mode: str
    accessibility_level: str; theme_mode: str; active: bool
    color1: str; color2: str; color3: str; color4: str; color5: str
    on_color1: str; on_color2: str; on_color3: str; on_color4: str; on_color5: str
    on_gradient_1_2: str; on_gradient_2_3: str; on_gradient_3_4: str
    on_gradient_4_5: str; on_gradient_5_1: str
    class Config: from_attributes = True
```

### ColorCalculationService — lógica obrigatória (não alterar)

```python
# app/services/color_calculation_service.py — referência: gus-plumo
# Copiar integralmente. Métodos principais:

class ColorCalculationService:
    def calculate_luminance(self, hex_color: str) -> float: ...          # WCAG luminance
    def calculate_contrast_ratio(self, c1: str, c2: str) -> float: ...   # WCAG contrast
    def pick_on_color(self, bg: str, threshold: float = 0.5) -> str: ... # '#FFF' ou '#000'
    def pick_gradient_on_color(self, ca: str, cb: str) -> str: ...       # média das luminâncias
    def apply_accessibility_enhancement(self, hex: str, level: str) -> str:
        # level='AA'  → darken 5%
        # level='AAA' → darken 10%
        # level='regular' → original
    def calculate_all_variants(self, base_colors: dict) -> ColorVariants:
        # Calcula on_color1..5 e on_gradient_1_2..5_1 de uma vez
```

### Fluxo do PUT /unified (lógica obrigatória)

```
Para cada theme_mode in ['light', 'dark']:
  Para cada level in ['regular', 'AA', 'AAA']:
    1. Aplica apply_accessibility_enhancement em cada color1..5
    2. Calcula calculate_all_variants (on-colors + gradientes)
    3. UPSERT na tabela tenant_colors onde
       tenant_id=X AND color_schema_mode='custom'
       AND theme_mode=theme AND accessibility_level=level
Total: 6 UPSERTs (2 temas × 3 níveis) por chamada.
```
