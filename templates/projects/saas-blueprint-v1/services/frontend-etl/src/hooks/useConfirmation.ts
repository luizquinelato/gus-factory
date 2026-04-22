/**
 * useConfirmation.ts
 * ==================
 * Hook de confirmação modal baseado em Promise.
 * API compatível com QueueManagementPage.
 *
 * Uso:
 *   const { confirm, confirmState, handleConfirm, handleCancel } = useConfirmation()
 *
 *   const ok = await confirm({
 *     title:        'Purge queue',
 *     message:      'This will delete 1500 messages.',
 *     confirmLabel: 'Yes, purge',
 *     variant:      'danger',
 *   })
 *   if (!ok) return
 *
 * Renderização: renderize <ConfirmModal> na página usando confirmState/handleConfirm/handleCancel.
 */
import { useCallback, useRef, useState } from 'react'

export type ConfirmVariant = 'danger' | 'warning' | 'info'

export interface ConfirmOptions {
  title:         string
  message:       string
  confirmLabel?: string
  cancelLabel?:  string
  variant?:      ConfirmVariant
}

export interface ConfirmState extends ConfirmOptions {
  open: boolean
}

export const useConfirmation = () => {
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null)
  const resolveRef = useRef<((value: boolean) => void) | null>(null)

  const confirm = useCallback((options: ConfirmOptions): Promise<boolean> => {
    return new Promise(resolve => {
      resolveRef.current = resolve
      setConfirmState({ ...options, open: true })
    })
  }, [])

  const handleConfirm = useCallback(() => {
    setConfirmState(null)
    resolveRef.current?.(true)
    resolveRef.current = null
  }, [])

  const handleCancel = useCallback(() => {
    setConfirmState(null)
    resolveRef.current?.(false)
    resolveRef.current = null
  }, [])

  return { confirm, confirmState, handleConfirm, handleCancel }
}
