/**
 * useToast.ts
 * ===========
 * Hook simples de notificações toast.
 * API: showToast(message, type) — tipo compatível com QueueManagementPage.
 *
 * Uso:
 *   const { showToast, toasts, removeToast } = useToast()
 *   showToast('Workers started', 'success')
 *   showToast('Operation failed', 'error')
 *
 * Renderização: use <ToastList toasts={toasts} onRemove={removeToast} />
 * ou importe o helper inline da página.
 */
import { useCallback, useState } from 'react'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface Toast {
  id:      string
  message: string
  type:    ToastType
}

const TOAST_DURATION_MS = 4000

export const useToast = () => {
  const [toasts, setToasts] = useState<Toast[]>([])

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const showToast = useCallback((message: string, type: ToastType = 'info') => {
    const id = Math.random().toString(36).slice(2, 10)
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => removeToast(id), TOAST_DURATION_MS)
  }, [removeToast])

  return { showToast, toasts, removeToast }
}
