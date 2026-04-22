import { HandWaving } from '@phosphor-icons/react'
import { useAuth } from '../contexts/AuthContext'

export default function HomePage() {
  const { user } = useAuth()
  const firstName = user?.name?.split(' ')[0] ?? 'Usuário'

  return (
    /* Preenche todo o main — centraliza vertical e horizontal */
    <div className="flex flex-col items-center justify-center min-h-full gap-7 p-10">

      {/* Ícone central */}
      <div style={{
        width: 120, height: 120, borderRadius: 32,
        background: 'var(--color-1)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        boxShadow: '0 8px 40px color-mix(in srgb, var(--color-1) 35%, transparent)',
      }}>
        <HandWaving size={56} weight="fill" color="var(--on-color-1)" />
      </div>

      {/* Texto — reage ao dark mode via dark: classes */}
      <div className="text-center">
        <h1 className="text-4xl font-extrabold mb-3 text-gray-800 dark:text-gray-100">
          Olá, {firstName}!
        </h1>
        <p className="text-lg text-gray-500 dark:text-gray-400 max-w-sm leading-relaxed">
          Bem-vindo ao{' '}
          <strong className="text-gray-800 dark:text-gray-200">SaaS Blueprint V1</strong>.{' '}
          Use o menu lateral para navegar.
        </p>
      </div>

      {/* Paleta ativa */}
      <div className="flex gap-2 mt-1">
        {[1,2,3,4,5].map(n => (
          <div key={n} style={{
            width: 36, height: 36, borderRadius: 10,
            background: `var(--color-${n})`,
            boxShadow: '0 2px 8px rgba(0,0,0,.12)',
          }} />
        ))}
      </div>
    </div>
  )
}
