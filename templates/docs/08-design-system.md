<!-- blueprint: db_changes=false seed_data=false -->
# 08. Design System e CSS Variables

Este documento define a arquitetura do Design System, garantindo que todo o CSS seja baseado em variáveis (CSS Custom Properties) e que os componentes utilizem essas variáveis de forma consistente.

## 🎨 1. Escolha da Biblioteca Base

Para evitar reinventar a roda e garantir acessibilidade (a11y), o projeto deve utilizar uma biblioteca de componentes headless ou utilitária como base, sendo o **Tailwind CSS** a escolha padrão para estilização, combinado com **Radix UI** ou **Headless UI** para comportamento acessível.

- **Tailwind CSS**: Fornece o sistema de utilitários e a integração nativa com CSS variables.
- **Radix UI / Headless UI**: Fornece componentes acessíveis (modais, dropdowns, tabs) sem estilo predefinido, permitindo aplicar as variáveis do tenant.

## 🏗️ 2. Estrutura de Variáveis CSS (index.css)

O arquivo global de estilos (`index.css`) deve definir as variáveis CSS no `:root`. Estas variáveis serão sobrescritas dinamicamente pelo hook `useColorApplication` (definido no `06-color-schema.md`) quando o tenant carregar.

```css
/* services/frontend/src/index.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    /* ── Color System (5 cores do tenant — sobrescritas por useColorApplication) ── */
    --color-1: #6366f1;   /* indigo */
    --color-2: #22d3ee;   /* cyan   */
    --color-3: #34d399;   /* emerald */
    --color-4: #a78bfa;   /* violet */
    --color-5: #0f172a;   /* slate dark */

    /* On-colors: cor do texto sobre fundo sólido (calculadas pelo backend/WCAG) */
    --on-color-1: #ffffff;
    --on-color-2: #000000;
    --on-color-3: #000000;
    --on-color-4: #ffffff;
    --on-color-5: #ffffff;

    /* Gradientes: injetados por useColorApplication */
    --gradient-1-2: linear-gradient(135deg, #6366f1, #22d3ee);
    --gradient-2-3: linear-gradient(135deg, #22d3ee, #34d399);
    --gradient-3-4: linear-gradient(135deg, #34d399, #a78bfa);
    --gradient-4-5: linear-gradient(135deg, #a78bfa, #0f172a);
    --gradient-5-1: linear-gradient(135deg, #0f172a, #6366f1);
    --gradient-full: linear-gradient(135deg, #6366f1, #22d3ee, #34d399, #a78bfa, #0f172a);

    /* On-gradients: cor do texto sobre gradiente (calculada pelo backend) */
    --on-gradient-1-2: #ffffff;
    --on-gradient-2-3: #000000;
    --on-gradient-3-4: #000000;
    --on-gradient-4-5: #ffffff;
    --on-gradient-5-1: #ffffff;

    /* ── Cores Universais (imutáveis por tenant) ── */
    --color-success: #22c55e;  --on-color-success: #ffffff;
    --color-warning: #eab308;  --on-color-warning: #000000;
    --color-error:   #ef4444;  --on-color-error:   #ffffff;
    --color-info:    #3b82f6;  --on-color-info:    #ffffff;
    --color-save:    #10b981;  --on-color-save:    #ffffff;  /* ação de salvar (pendente/dirty) */

    /* ── Ações CRUD ── */
    --crud-create: var(--color-success);  --on-crud-create: var(--on-color-success);
    --crud-edit:   var(--color-info);     --on-crud-edit:   var(--on-color-info);
    --crud-delete: var(--color-error);    --on-crud-delete: var(--on-color-error);
    --crud-cancel: #9ca3af;               --on-crud-cancel: #ffffff;
    --crud-save:   var(--color-save);     --on-crud-save:   var(--on-color-save);
  }

  /* Dark mode: as color1-5 são as mesmas (injetadas por useColorApplication) */
  /* Os neutros de superfície mudam para dark */
  .dark {
    color-scheme: dark;
  }
}
```

> **Regra:** nunca use hex ou rgb hardcoded em componentes. Use sempre `var(--color-1)`, `var(--gradient-1-2)`, etc. A única exceção é a **Sidebar**, que possui seu próprio Design System de tokens fixos (ver seção 5 abaixo).

## 🗂️ 5. Sidebar Design System — Tokens Fixos

A Sidebar usa **6 tokens de cor fixos**, separados e independentes do sistema de cores dinâmicas do tenant (`color1–5`). São tokens de **estrutura de navegação**, não de tema de produto.

| Token | Light | Dark | Uso |
|---|---|---|---|
| **Header** | `#E2E8F0` | `#161929` | Background do header (logo + nome) — tom distinto do Surface |
| **Surface** | `#F8FAFC` | `#1E2233` | Background do body da sidebar |
| **Content** | `#1E293B` | `#F1F5F9` | Texto e ícones dos nav items |
| **Muted** | `#475569` | `#94A3B8` | Labels de seção, ícones de footer, texto secundário |
| **Overlay** | `#E2E8F0` | `#252B42` | Hover row, container do segmented control Light/Dark |

**Avatar do usuário:** usa o gradiente `color1→color2` do tenant (scheme light) — único elemento do shell que referencia cores dinâmicas.

**Selected state — usa CSS vars do tenant (não valores fixos):**
- Background: `var(--color-1)` — se adapta à paleta ativa do tenant
- Texto/ícone: `var(--on-color-1)` — calculado pelo backend via WCAG

**Sombra da sidebar:** `2px 0 8px rgba(0,0,0,.06)` em light / `2px 0 16px rgba(0,0,0,.35)` em dark.

> Estes tokens não são injetados via `useColorApplication` — são definidos no objeto `SB` inline no componente `Sidebar.tsx`.

## 🧩 3. Integração com Tailwind CSS

```javascript
// services/frontend/tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // ── Sistema color1-5 (tenant) ──
        'color-1':    'var(--color-1)',    'on-color-1': 'var(--on-color-1)',
        'color-2':    'var(--color-2)',    'on-color-2': 'var(--on-color-2)',
        'color-3':    'var(--color-3)',    'on-color-3': 'var(--on-color-3)',
        'color-4':    'var(--color-4)',    'on-color-4': 'var(--on-color-4)',
        'color-5':    'var(--color-5)',    'on-color-5': 'var(--on-color-5)',
        // ── Aliases semânticos → color1-5 ──
        primary:      'var(--color-1)',    'on-primary':   'var(--on-color-1)',
        secondary:    'var(--color-2)',    'on-secondary': 'var(--on-color-2)',
        accent:       'var(--color-3)',    'on-accent':    'var(--on-color-3)',
        // ── Universais ──
        success:      'var(--color-success)',  'on-success': 'var(--on-color-success)',
        warning:      'var(--color-warning)',  'on-warning': 'var(--on-color-warning)',
        error:        'var(--color-error)',    'on-error':   'var(--on-color-error)',
        info:         'var(--color-info)',     'on-info':    'var(--on-color-info)',
        save:         'var(--color-save)',     'on-save':    'var(--on-color-save)',
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

## 📦 4. Padrão de Componentes

Todos os componentes devem utilizar exclusivamente as classes do Tailwind configuradas com as variáveis CSS. Nunca utilize cores hardcoded (ex: `bg-blue-500`) em componentes de negócio.

```tsx
// Exemplo de Botão Primário
export const PrimaryButton = ({ children, onClick }) => (
  <button
    onClick={onClick}
    className="bg-primary text-on-primary px-4 py-2 rounded-md hover:opacity-90 transition-opacity"
  >
    {children}
  </button>
);

// Exemplo de Card (Surface)
export const Card = ({ title, children }) => (
  <div className="bg-surface text-on-surface p-6 rounded-lg shadow-md border border-gray-200 dark:border-gray-700">
    <h2 className="text-xl font-bold mb-4">{title}</h2>
    {children}
  </div>
);

// Exemplo de Botão de Ação Universal (Delete)
export const DeleteButton = ({ onClick }) => (
  <button
    onClick={onClick}
    className="bg-action-delete text-on-error px-3 py-1 rounded hover:opacity-90"
  >
    Excluir
  </button>
);
```
