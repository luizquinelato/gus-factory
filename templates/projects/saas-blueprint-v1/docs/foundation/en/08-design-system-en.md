<!-- blueprint: db_changes=false seed_data=false -->
# 08. Design System and CSS Variables

This document defines the Design System architecture, ensuring all CSS is based on variables (CSS Custom Properties) and components use those variables consistently.

## 🎨 1. Base Library Choice

To avoid reinventing the wheel and ensure accessibility (a11y), the project must use a headless or utility component library as the base. **Tailwind CSS** is the standard choice for styling, combined with **Radix UI** or **Headless UI** for accessible behavior.

- **Tailwind CSS**: Provides the utility system and native integration with CSS variables.
- **Radix UI / Headless UI**: Provides accessible components (modals, dropdowns, tabs) without predefined style.

## 🏗️ 2. CSS Variables Structure (index.css)

```css
/* services/frontend/src/index.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    /* ── Color System (5 tenant colors — overridden by useColorApplication) ── */
    --color-1: #6366f1;
    --color-2: #22d3ee;
    --color-3: #34d399;
    --color-4: #a78bfa;
    --color-5: #0f172a;

    /* On-colors: text color on solid background (WCAG-calculated by backend) */
    --on-color-1: #ffffff;
    --on-color-2: #000000;
    --on-color-3: #000000;
    --on-color-4: #ffffff;
    --on-color-5: #ffffff;

    /* Gradients: injected by useColorApplication */
    --gradient-1-2: linear-gradient(135deg, #6366f1, #22d3ee);
    --gradient-2-3: linear-gradient(135deg, #22d3ee, #34d399);
    --gradient-3-4: linear-gradient(135deg, #34d399, #a78bfa);
    --gradient-4-5: linear-gradient(135deg, #a78bfa, #0f172a);
    --gradient-5-1: linear-gradient(135deg, #0f172a, #6366f1);
    --gradient-full: linear-gradient(135deg, #6366f1, #22d3ee, #34d399, #a78bfa, #0f172a);

    /* On-gradients: text color on gradient (backend-calculated) */
    --on-gradient-1-2: #ffffff;
    --on-gradient-2-3: #000000;
    --on-gradient-3-4: #000000;
    --on-gradient-4-5: #ffffff;
    --on-gradient-5-1: #ffffff;

    /* ── Universal Colors (immutable by tenant) ── */
    --color-success: #22c55e;  --on-color-success: #ffffff;
    --color-warning: #eab308;  --on-color-warning: #000000;
    --color-error:   #ef4444;  --on-color-error:   #ffffff;
    --color-info:    #3b82f6;  --on-color-info:    #ffffff;

    /* ── CRUD Actions ── */
    --crud-create: var(--color-success);  --on-crud-create: var(--on-color-success);
    --crud-edit:   var(--color-info);     --on-crud-edit:   var(--on-color-info);
    --crud-delete: var(--color-error);    --on-crud-delete: var(--on-color-error);
    --crud-cancel: #9ca3af;               --on-crud-cancel: #ffffff;
  }

  .dark { color-scheme: dark; }
}
```

> **Rule:** never use hardcoded hex or rgb in components. Always use `var(--color-1)`, `var(--gradient-1-2)`, etc. The only exception is the **Sidebar**, which has its own fixed Design System tokens (see section 5 below).

## 🗂️ 5. Sidebar Design System — Fixed Tokens

The Sidebar uses **5 fixed color tokens**, separate and independent from the tenant's dynamic color system (`color1–5`). These are **navigation structure tokens**, not product theme tokens.

| Token | Light | Dark | Usage |
|---|---|---|---|
| **Header** | `#E2E8F0` | `#161929` | Header background (logo + name) — distinct tone from Surface |
| **Surface** | `#F8FAFC` | `#1E2233` | Sidebar body background |
| **Content** | `#1E293B` | `#F1F5F9` | Text and icons of nav items |
| **Muted** | `#475569` | `#94A3B8` | Section labels, footer icons, secondary text |
| **Overlay** | `#E2E8F0` | `#252B42` | Hover row, Light/Dark segmented control background |

**User avatar:** uses the tenant's `color1→color2` gradient (light scheme) — the only element in the navigation shell that references dynamic tenant colors.

**Selected state — uses tenant CSS vars (not fixed values):**
- Background: `var(--color-1)` — adapts to the active tenant palette
- Text/icon: `var(--on-color-1)` — calculated by the backend via WCAG

**Sidebar shadow:** `2px 0 8px rgba(0,0,0,.06)` in light / `2px 0 16px rgba(0,0,0,.35)` in dark.

> These tokens are not injected via `useColorApplication` — they are defined in the `SB` object inline in the `Sidebar.tsx` component.

## 🧩 3. Tailwind CSS Integration

```javascript
// services/frontend/tailwind.config.js
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        'color-1': 'var(--color-1)',    'on-color-1': 'var(--on-color-1)',
        'color-2': 'var(--color-2)',    'on-color-2': 'var(--on-color-2)',
        'color-3': 'var(--color-3)',    'on-color-3': 'var(--on-color-3)',
        'color-4': 'var(--color-4)',    'on-color-4': 'var(--on-color-4)',
        'color-5': 'var(--color-5)',    'on-color-5': 'var(--on-color-5)',
        primary:   'var(--color-1)',    'on-primary':   'var(--on-color-1)',
        secondary: 'var(--color-2)',    'on-secondary': 'var(--on-color-2)',
        accent:    'var(--color-3)',    'on-accent':    'var(--on-color-3)',
        success:   'var(--color-success)',  'on-success': 'var(--on-color-success)',
        warning:   'var(--color-warning)',  'on-warning': 'var(--on-color-warning)',
        error:     'var(--color-error)',    'on-error':   'var(--on-color-error)',
        info:      'var(--color-info)',     'on-info':    'var(--on-color-info)',
      },
      backgroundImage: {
        'gradient-12':   'var(--gradient-1-2)',
        'gradient-23':   'var(--gradient-2-3)',
        'gradient-34':   'var(--gradient-3-4)',
        'gradient-45':   'var(--gradient-4-5)',
        'gradient-51':   'var(--gradient-5-1)',
        'gradient-full': 'var(--gradient-full)',
      },
    },
  },
  plugins: [],
}
```

## 📦 4. Component Pattern

All components must exclusively use Tailwind classes configured with CSS variables. Never use hardcoded colors (e.g.: `bg-blue-500`) in business components.

```tsx
// Primary Button example
export const PrimaryButton = ({ children, onClick }) => (
  <button
    onClick={onClick}
    className="bg-primary text-on-primary px-4 py-2 rounded-md hover:opacity-90 transition-opacity"
  >
    {children}
  </button>
);

// Card example (Surface)
export const Card = ({ title, children }) => (
  <div className="bg-surface text-on-surface p-6 rounded-lg shadow-md border border-gray-200 dark:border-gray-700">
    <h2 className="text-xl font-bold mb-4">{title}</h2>
    {children}
  </div>
);

// Universal Action Button (Delete)
export const DeleteButton = ({ onClick }) => (
  <button
    onClick={onClick}
    className="bg-action-delete text-on-error px-3 py-1 rounded hover:opacity-90"
  >
    Delete
  </button>
);
```
