<!-- blueprint: db_changes=true seed_data=true -->
# 09. Multi-Tenant Color Schema System

This document defines the complete architecture for dynamic per-tenant color system: 5 base colors, gradients, on-colors, 3 WCAG levels, 2 modes (default/custom) and 2 themes (light/dark).

## 🎨 1. Architecture — 3 Layers

| Layer | Responsibility |
|---|---|
| **Database** | `tenant_colors` — stores 5 colors per `(tenant, mode, theme, level)` = 12 rows per tenant |
| **Backend** | Calculates `on-colors`, gradients and WCAG variants at runtime |
| **Frontend** | Injects as CSS Custom Properties via `useColorApplication` |

### Database combinations (12 per tenant)
```
color_schema_mode × theme_mode × accessibility_level
    default       ×    light   ×   regular / AA / AAA  (3 rows)
    default       ×    dark    ×   regular / AA / AAA  (3 rows)
    custom        ×    light   ×   regular / AA / AAA  (3 rows)
    custom        ×    dark    ×   regular / AA / AAA  (3 rows)
```

## 🗃️ 2. Database Schema

```sql
CREATE TABLE tenant_colors (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    color_schema_mode    VARCHAR(10)  NOT NULL CHECK (color_schema_mode IN ('default','custom')),
    theme_mode           VARCHAR(10)  NOT NULL CHECK (theme_mode IN ('light','dark')),
    accessibility_level  VARCHAR(10)  NOT NULL CHECK (accessibility_level IN ('regular','AA','AAA')),
    color1  VARCHAR(7) NOT NULL,
    color2  VARCHAR(7) NOT NULL,
    color3  VARCHAR(7) NOT NULL,
    color4  VARCHAR(7) NOT NULL,
    color5  VARCHAR(7) NOT NULL,
    on_color1  VARCHAR(7) NOT NULL,
    on_color2  VARCHAR(7) NOT NULL,
    on_color3  VARCHAR(7) NOT NULL,
    on_color4  VARCHAR(7) NOT NULL,
    on_color5  VARCHAR(7) NOT NULL,
    on_gradient_1_2  VARCHAR(7) NOT NULL,
    on_gradient_2_3  VARCHAR(7) NOT NULL,
    on_gradient_3_4  VARCHAR(7) NOT NULL,
    on_gradient_4_5  VARCHAR(7) NOT NULL,
    on_gradient_5_1  VARCHAR(7) NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, color_schema_mode, theme_mode, accessibility_level)
);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS color_schema_mode VARCHAR(10) DEFAULT 'default';
```

## 🎨 4. Two Default Palettes

### Palette 1 — **Cosmos** (cool, tech-forward, premium)
| Color | Hex | Name | Usage |
|---|---|---|---|
| color1 | `#6366F1` | Indigo vivid | Primary, buttons |
| color2 | `#22D3EE` | Cyan | Info, secondary |
| color3 | `#34D399` | Emerald | Success, growth |
| color4 | `#A78BFA` | Violet | Accent, badges |
| color5 | `#0F172A` | Slate dark | Anchor, dark brand |

### Palette 2 — **Solano** (warm, dynamic energy)
| Color | Hex | Name | Usage |
|---|---|---|---|
| color1 | `#F97316` | Orange vivid | Energy, CTA |
| color2 | `#FACC15` | Yellow | Highlight, alert |
| color3 | `#22C55E` | Green | Growth |
| color4 | `#3B82F6` | Blue | Trust |
| color5 | `#1C1917` | Stone dark | Anchor, elegance |

## 🧮 5. Luminance Calculation and WCAG Variants

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
    """Returns #FFFFFF or #000000 based on WCAG level."""
    thresholds = {'regular': 4.5, 'AA': 4.5, 'AAA': 7.0}
    ratio = thresholds.get(level, 4.5)
    return '#FFFFFF' if contrast_ratio(hex_bg, '#FFFFFF') >= ratio else '#000000'
```

## 🌐 6. Color API (Backend)

```
GET  /api/tenant/colors/unified     → returns all 12 combinations + active color_schema_mode
POST /api/tenant/colors/mode        → body: { "mode": "default" | "custom" }
PUT  /api/tenant/colors/custom      → body: { light: {color1..5}, dark: {color1..5} }
```

## 🖌️ 7. Frontend — colorApplication.ts and useColorApplication

```typescript
// src/utils/colorApplication.ts
export function applyColorsToDOM(colorData: ColorData): void {
  const root = document.documentElement;
  const { color1, color2, color3, color4, color5 } = colorData;
  root.style.setProperty('--color-1', color1);
  root.style.setProperty('--color-2', color2);
  root.style.setProperty('--color-3', color3);
  root.style.setProperty('--color-4', color4);
  root.style.setProperty('--color-5', color5);
  ['1','2','3','4','5'].forEach(n =>
    root.style.setProperty(`--on-color-${n}`, (colorData as any)[`on_color${n}`])
  );
  root.style.setProperty('--gradient-1-2', `linear-gradient(135deg,${color1},${color2})`);
  root.style.setProperty('--gradient-2-3', `linear-gradient(135deg,${color2},${color3})`);
  root.style.setProperty('--gradient-3-4', `linear-gradient(135deg,${color3},${color4})`);
  root.style.setProperty('--gradient-4-5', `linear-gradient(135deg,${color4},${color5})`);
  root.style.setProperty('--gradient-5-1', `linear-gradient(135deg,${color5},${color1})`);
  root.style.setProperty('--on-gradient-1-2', colorData.on_gradient_1_2);
  root.style.setProperty('--on-gradient-2-3', colorData.on_gradient_2_3);
  root.style.setProperty('--on-gradient-3-4', colorData.on_gradient_3_4);
  root.style.setProperty('--on-gradient-4-5', colorData.on_gradient_4_5);
  root.style.setProperty('--on-gradient-5-1', colorData.on_gradient_5_1);
}
```

## 🗄️ 11. Persistence — DB and Cache

| What changes | Where persisted in DB | Local cache |
|---|---|---|
| User switches light ↔ dark | `users.theme_mode` (via `PATCH /api/user/me`) | `ThemeContext` in memory |
| Tenant switches default ↔ custom | `tenants.color_schema_mode` (via `POST /api/tenant/colors/mode`) | `localStorage('color_schema_mode')` |
| Tenant edits custom colors | `tenant_colors` (UPSERT via `PUT /api/tenant/colors/custom`) | `localStorage('color_data')` |

**Mandatory implementation rules:**
1. Never save `theme_mode` only in localStorage — the backend is the source of truth.
2. After any `PUT` or `POST` of color/mode, clear `localStorage('color_data')` before rewriting.
3. The `colorDataLoaded` event triggers CSS re-application without reload.

## 🖥️ 10. Visual Reference Files

| File | What it shows |
|---|---|
| `templates/reference/login.html` | Login screen — animated canvas + glassmorphism card |
| `templates/reference/color-settings.html` | Color page — complete interactive layout with all calculation functions |

The `color-settings.html` is the canonical reference for:
- Layout structure (sidebar + main + light/dark panels)
- Functions `luminance()`, `onColor()`, `gradientOnColor()`, `applyLevel()`, `calculateVariants()` — translate 1:1 to TypeScript (frontend) and Python (backend)
