import React from 'react'
import Sidebar from './Sidebar'

interface AppShellProps {
  children: React.ReactNode
}

export default function AppShell({ children }: AppShellProps) {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      {/*
        Fundo neutro: claro → #f1f5f9 / escuro → #0f172a
        O dark: é ativado pelo `html.dark` que applyColorsToDOM aplica no toggle
      */}
      <main className="flex-1 overflow-y-auto bg-gray-100 dark:bg-gray-950 flex flex-col">
        <div className="flex-1">{children}</div>
        <footer className="flex flex-col items-center gap-2 py-4 select-none">
          <div style={{
            width: 260,
            height: 1,
            background: 'linear-gradient(90deg, transparent, #94a3b8 30%, #94a3b8 70%, transparent)',
            boxShadow: '0 1px 6px rgba(148,163,184,0.5)',
          }} />
          <span className="text-[11px] text-gray-400 dark:text-gray-600">
            © 2026 Luiz Gustavo Quinelato · SaaS Blueprint V1
          </span>
        </footer>
      </main>
    </div>
  )
}
