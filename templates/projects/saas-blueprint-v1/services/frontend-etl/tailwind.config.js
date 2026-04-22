/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Cores do tenant — nomenclatura --color-N (padrão gus-plumo)
        brand: {
          1: 'var(--color-1)',
          2: 'var(--color-2)',
          3: 'var(--color-3)',
          4: 'var(--color-4)',
          5: 'var(--color-5)',
        },
      },
      backgroundImage: {
        'gradient-brand': 'var(--gradient-1-2)',
        'gradient-full':  'var(--gradient-full)',
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [],
}
