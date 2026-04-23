/**
 * QueueManagementPage.tsx
 * =======================
 * Tela de configuração de filas ETL:
 *  - Status das 3 filas (depth, rates, consumers)
 *  - Controle de workers por tipo (start/stop/restart/scale)
 *  - Configurações ETL (worker counts, ai_enabled)
 *  - Botão de fake job para testes
 *  - Log de erros do processor
 *  - Auto-refresh a cada 5s
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ArrowClockwise, ArrowFatLinesDown, ArrowSquareOut,
  CheckCircle, Cpu, Flask, Funnel, Gear, Info,
  Lightning, Play, PlugsConnected, Skull, Square, Warning, X,
} from '@phosphor-icons/react'

import { useToast } from '../hooks/useToast'
import type { Toast } from '../hooks/useToast'
import { useConfirmation } from '../hooks/useConfirmation'
import type { ConfirmState } from '../hooks/useConfirmation'
import type { JobError, QueueStats, QueueType, SystemSetting, WorkerPool, WorkerType } from '../types'
import * as api from '../services/queueApiService'

// ── constants ─────────────────────────────────────────────────────────────────

const WORKER_TYPES: WorkerType[] = ['extraction', 'transform', 'processor']
const REFRESH_INTERVAL_MS = 5_000

const WORKER_ICONS: Record<WorkerType, React.ReactNode> = {
  extraction: <ArrowFatLinesDown size={18} weight="duotone" />,
  transform:  <Funnel            size={18} weight="duotone" />,
  processor:  <Cpu               size={18} weight="duotone" />,
}

const WORKER_LABELS: Record<WorkerType, string> = {
  extraction: 'Extraction',
  transform:  'Transform',
  processor:  'Processor',
}

// ── inline Toast renderer ─────────────────────────────────────────────────────

function ToastList({ toasts, onRemove }: { toasts: Toast[]; onRemove: (id: string) => void }) {
  const icons: Record<string, React.ReactNode> = {
    success: <CheckCircle size={16} weight="fill" style={{ color: 'var(--color-success)' }} />,
    error:   <X           size={16} weight="fill" style={{ color: 'var(--color-danger)' }} />,
    warning: <Warning     size={16} weight="fill" style={{ color: 'var(--color-warning)' }} />,
    info:    <Info        size={16} weight="fill" style={{ color: 'var(--color-info)' }} />,
  }
  if (!toasts.length) return null
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-80">
      {toasts.map(t => (
        <div key={t.id}
          className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-lg flex items-start gap-3 p-3 text-sm">
          {icons[t.type]}
          <span className="flex-1 text-gray-800 dark:text-gray-100">{t.message}</span>
          <button onClick={() => onRemove(t.id)} className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors">
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}

// ── inline Confirm modal ──────────────────────────────────────────────────────

function ConfirmModal({
  state, onConfirm, onCancel,
}: { state: ConfirmState; onConfirm: () => void; onCancel: () => void }) {
  const confirmStyle: React.CSSProperties = state.variant === 'danger'
    ? { background: 'var(--color-danger)',  color: 'var(--on-color-danger)'  }
    : state.variant === 'warning'
    ? { background: 'var(--color-warning)', color: 'var(--on-color-warning)' }
    : { background: 'var(--color-1)',       color: 'var(--on-color-1)'       }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-2xl p-6 w-full max-w-sm flex flex-col gap-4">
        <h3 className="font-semibold text-gray-800 dark:text-gray-100">{state.title}</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">{state.message}</p>
        <div className="flex gap-2 justify-end">
          <button
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            onClick={onCancel}
          >
            {state.cancelLabel ?? 'Cancelar'}
          </button>
          <button
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-colors"
            style={confirmStyle}
            onClick={onConfirm}
          >
            {state.confirmLabel ?? 'Confirmar'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function QueueManagementPage() {
  const { showToast, toasts, removeToast }             = useToast()
  const { confirm, confirmState, handleConfirm, handleCancel } = useConfirmation()

  const [queues,   setQueues]   = useState<QueueStats[]>([])
  const [workers,  setWorkers]  = useState<Record<WorkerType, WorkerPool> | null>(null)
  const [settings, setSettings] = useState<SystemSetting[]>([])
  const [errors,   setErrors]   = useState<JobError[]>([])
  const [loading,  setLoading]  = useState<Record<string, boolean>>({})
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const setLoad = (key: string, v: boolean) =>
    setLoading(prev => ({ ...prev, [key]: v }))

  // ── data fetch ───────────────────────────────────────────────────────────────

  const refresh = useCallback(async () => {
    try {
      const [qRes, wRes, eRes] = await Promise.all([
        api.getQueues(), api.getWorkers(), api.getErrorLog(50),
      ])
      setQueues(qRes.queues)
      setWorkers(wRes as any)
      setErrors(eRes.errors)
      setLastRefresh(new Date())
    } catch {
      // silently fail on auto-refresh
    }
  }, [])

  const loadSettings = useCallback(async () => {
    try {
      const res = await api.getSettings()
      setSettings(res.settings)
    } catch {/* ignore */}
  }, [])

  useEffect(() => {
    refresh(); loadSettings()
    timerRef.current = setInterval(refresh, REFRESH_INTERVAL_MS)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [refresh, loadSettings])

  // ── worker actions ───────────────────────────────────────────────────────────

  const workerAction = async (
    key:          string,
    fn:           () => Promise<any>,
    msg:          string,
    refreshDelay: number = 0,
  ) => {
    setLoad(key, true)
    try {
      await fn()
      showToast(msg, 'success')
      if (refreshDelay > 0) await new Promise(r => setTimeout(r, refreshDelay))
      await refresh()
    } catch { showToast('Operação falhou', 'error') }
    finally { setLoad(key, false) }
  }



  // ── purge ─────────────────────────────────────────────────────────────────

  const handlePurge = async (queueType: QueueType) => {
    const depth = queues.find(q => q.name.startsWith(queueType))?.messages_ready ?? 0
    const ok = await confirm({
      title:   `Purge ${queueType} queue`,
      message: depth > 0
        ? `This will permanently delete ${depth} pending message${depth !== 1 ? 's' : ''}. This cannot be undone.`
        : `Queue is empty. Purge anyway?`,
      confirmLabel:  'Yes, purge',
      variant: 'danger',
    })
    if (!ok) return
    setLoad(`purge-${queueType}`, true)
    try {
      const res = await api.purgeQueue(queueType)
      showToast(`Purged ${res.messages_purged} messages from ${queueType}`, 'success')
      await refresh()
    } catch { showToast('Purge failed', 'error') }
    finally { setLoad(`purge-${queueType}`, false) }
  }

  // ── fake job ──────────────────────────────────────────────────────────────

  const handleFakeJob = async () => {
    setLoad('fakejob', true)
    try {
      const res = await api.dispatchFakeJob()
      showToast(`Fake job #${res.job_id} dispatched — ${res.expected.transform_messages} transform + ${res.expected.processor_messages} processor msgs incoming`, 'success')
      setTimeout(refresh, 1000)
    } catch { showToast('Failed to dispatch fake job', 'error') }
    finally { setLoad('fakejob', false) }
  }

  // ── settings save ─────────────────────────────────────────────────────────

  const handleSettingsSave = async (changes: { key: string; value: unknown }[]) => {
    await Promise.all(changes.map(({ key, value }) => api.updateSetting(key, value)))
    showToast(
      `${changes.length} setting${changes.length !== 1 ? 's' : ''} atualizado${changes.length !== 1 ? 's' : ''}`,
      'success',
    )
    await loadSettings()
  }

  // ── derived state ─────────────────────────────────────────────────────────
  // Workers iniciam automaticamente no startup do backend (main.py lifespan).
  // "Start" só faz sentido quando não há nenhum worker vivo no pool.
  const allWorkersAlive = workers != null &&
    WORKER_TYPES.every(t => (workers[t]?.alive ?? 0) > 0)

  // ── rabbitmq management url ───────────────────────────────────────────────
  const rabbitMgmtUrl = window.location.port === '3345'
    ? 'http://localhost:15674'
    : 'http://localhost:15675'

  // ── render ────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-full p-8 space-y-6">

      {/* Toast notifications */}
      <ToastList toasts={toasts} onRemove={removeToast} />

      {/* Confirm modal */}
      {confirmState?.open && (
        <ConfirmModal state={confirmState} onConfirm={handleConfirm} onCancel={handleCancel} />
      )}

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100 flex items-center gap-2">
            <Lightning size={24} weight="duotone" style={{ color: 'var(--color-1)' }} />
            Filas
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {lastRefresh ? `Última atualização: ${lastRefresh.toLocaleTimeString()}` : 'Carregando…'}
            {' '}· Auto-refresh a cada {REFRESH_INTERVAL_MS / 1000}s
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            onClick={refresh}
          >
            <ArrowClockwise size={14} /> Refresh
          </button>
          <a
            href={rabbitMgmtUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            title={`Abrir RabbitMQ Management (${rabbitMgmtUrl})`}
          >
            <ArrowSquareOut size={14} /> RabbitMQ
          </a>
          <button
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ background: 'var(--color-create)', color: 'var(--on-color-create)' }}
            onClick={() => workerAction('start-all', api.startAllWorkers, 'All workers started')}
            disabled={loading['start-all'] || allWorkersAlive}
            title={allWorkersAlive ? 'Todos os workers já estão rodando' : 'Iniciar todos os workers'}
          >
            <Play size={14} /> Start All
          </button>
          <button
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-colors disabled:opacity-50"
            style={{ background: 'var(--color-cancel)', color: 'var(--on-color-cancel)' }}
            onClick={() => workerAction('stop-all', api.stopAllWorkers, 'All workers stopping')}
            disabled={loading['stop-all']}
          >
            <Square size={14} /> Stop All
          </button>
          <button
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-colors disabled:opacity-50"
            style={{ background: 'var(--color-warning)', color: 'var(--on-color-warning)' }}
            onClick={() => workerAction('restart-all', api.restartAllWorkers, 'All workers restarting', 800)}
            disabled={loading['restart-all']}
          >
            <ArrowClockwise size={14} /> Restart All
          </button>
          <button
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-colors disabled:opacity-50"
            style={{ background: 'var(--color-1)', color: 'var(--on-color-1)' }}
            onClick={handleFakeJob}
            disabled={loading['fakejob']}
            title="Dispara um job fake para testar o pipeline completo"
          >
            <Flask size={14} />
            {loading['fakejob'] ? 'Enviando…' : 'Fake Job'}
          </button>
        </div>
      </div>

      {/* Queue stats */}
      <div>
        <div className="text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-3">
          Filas
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {queues.length > 0
            ? queues.map(q => {
                const qType = q.name.replace('_queue', '') as QueueType
                return (
                  <QueueCard
                    key={q.name}
                    queue={q}
                    onPurge={() => handlePurge(qType)}
                    purging={!!loading[`purge-${qType}`]}
                  />
                )
              })
            : WORKER_TYPES.map(t => (
                <div key={t} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-4 animate-pulse">
                  <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/2 mb-2" />
                  <div className="h-3 bg-gray-100 dark:bg-gray-600 rounded w-3/4" />
                </div>
              ))
          }
        </div>
      </div>

      {/* Worker pools */}
      <div>
        <div className="text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-3">
          Worker Pools
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {WORKER_TYPES.map(type => {
            const pool = workers?.[type] ?? { count: 0, alive: 0, workers: [] }
            return (
              <WorkerPoolCard
                key={type}
                type={type}
                pool={pool}
                loading={!!loading[`action-${type}`]}
                onStart={()   => workerAction(`action-${type}`, () => api.startWorkerPool(type),   `${type} started`)}
                onStop={()    => workerAction(`action-${type}`, () => api.stopWorkerPool(type),    `${type} stopping`)}
                onRestart={() => workerAction(`action-${type}`, () => api.restartWorkerPool(type), `${type} restarting`, 800)}
                onKill={()    => workerAction(`action-${type}`, () => api.stopWorkerPool(type),    `${type} killed`)}
              />
            )
          })}
        </div>
      </div>

      {/* Settings */}
      {settings.length > 0 && (
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-3">
            Configuração
          </div>
          <SettingsPanel settings={settings} onSave={handleSettingsSave} />
        </div>
      )}

      {/* Error log */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 flex items-center gap-1.5">
            <Warning size={13} style={{ color: 'var(--color-warning)' }} />
            Erros do Processor
            {errors.length > 0 && (
              <span className="ml-1 px-1.5 py-0.5 text-xs bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 rounded font-bold">
                {errors.length}
              </span>
            )}
          </div>
          {errors.length > 0 && (
            <button
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              onClick={async () => { await api.clearErrorLog(); setErrors([]) }}
            >
              Limpar
            </button>
          )}
        </div>
        {errors.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400 italic">Nenhum erro registrado.</p>
        ) : (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
            <div className="flex flex-col divide-y divide-gray-100 dark:divide-gray-700 max-h-72 overflow-y-auto">
              {[...errors].reverse().map((e, i) => (
                <div key={i} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-xs hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                  <span className={`shrink-0 rounded px-2 py-0.5 font-semibold ${ERROR_CODE_CLASS[e.error_code] ?? 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'}`}>
                    {e.error_code}
                  </span>
                  <span className="text-gray-500 dark:text-gray-400 font-mono">job #{e.job_id} · item {e.item_index}</span>
                  <span className="font-mono" style={e.ai_enabled ? { color: 'var(--color-1)' } : { color: '#9ca3af' }}>
                    ai={String(e.ai_enabled)}
                  </span>
                  <span className="text-gray-500 dark:text-gray-400 flex-1 truncate" title={e.error_detail}>
                    {e.error_detail}
                  </span>
                  <span className="text-gray-400 dark:text-gray-500 ml-auto whitespace-nowrap">
                    {new Date(e.created_at * 1000).toLocaleTimeString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── error badge classes ───────────────────────────────────────────────────────

const ERROR_CODE_CLASS: Record<string, string> = {
  ai_integration_not_configured: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  embedding_api_timeout:         'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  embedding_api_rate_limit:      'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  embedding_api_invalid_response:'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  load_db_connection_failed:     'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  load_schema_mismatch:          'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
}

// ── sub-components ────────────────────────────────────────────────────────────

function QueueCard({ queue, onPurge, purging }: {
  queue:   QueueStats
  onPurge: () => void
  purging: boolean
}) {
  const depth  = queue.messages_ready
  const busy   = queue.messages_unacknowledged
  const isOk   = depth < 100
  const isWarn = depth >= 100 && depth < 500

  const badgeStyle: React.CSSProperties = isOk
    ? { background: 'var(--color-1)',       color: 'var(--on-color-1)'       }
    : isWarn
    ? { background: 'var(--color-warning)', color: 'var(--on-color-warning)' }
    : { background: 'var(--color-danger)',  color: 'var(--on-color-danger)'  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-4 flex flex-col gap-3 hover:border-[color:var(--color-1)] transition-colors">
      <div className="flex items-center gap-2 text-sm font-semibold text-gray-800 dark:text-gray-100">
        <PlugsConnected size={16} weight="duotone" style={{ color: 'var(--color-1)' }} />
        {queue.name.replace('_queue', '').replace('_', ' ')}
        <span className="ml-auto inline-flex items-center justify-center h-5 text-xs px-2 rounded font-semibold" style={badgeStyle}>
          {queue.state}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
        <span>Prontas</span>     <span className="font-mono font-bold text-gray-800 dark:text-gray-100">{depth}</span>
        <span>Processando</span> <span className="font-mono">{busy}</span>
        <span>Consumers</span>   <span className="font-mono">{queue.consumers}</span>
        <span>Publish/s</span>   <span className="font-mono">{queue.publish_rate.toFixed(2)}</span>
        <span>Deliver/s</span>   <span className="font-mono">{queue.deliver_rate.toFixed(2)}</span>
        <span>Ack/s</span>       <span className="font-mono">{queue.ack_rate.toFixed(2)}</span>
      </div>

      <button
        className="inline-flex items-center justify-center gap-1 w-full py-1.5 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 border border-red-200 dark:border-red-800"
        style={{ color: 'var(--color-danger)' }}
        onClick={onPurge}
        disabled={purging}
        title={`Purge ${queue.name.replace('_queue', '')} queue`}
      >
        <X size={11} /> {purging ? 'Purgando…' : `Purge ${queue.name.replace('_queue', '')}`}
      </button>
    </div>
  )
}

// ── Settings panel ────────────────────────────────────────────────────────────

// Ordem explícita e labels curtos para exibição em linha
const ETL_KEY_ORDER  = ['ai_enabled', 'extraction_workers', 'transform_workers', 'processor_workers'] as const
const ETL_KEY_LABELS: Record<string, string> = {
  ai_enabled:          'AI',
  extraction_workers:  'Extraction',
  transform_workers:   'Transform',
  processor_workers:   'Processor',
}

function SettingsPanel({
  settings, onSave,
}: { settings: SystemSetting[]; onSave: (changes: { key: string; value: unknown }[]) => Promise<void> }) {
  // Manter ordem AI → E → T → L
  const relevant = ETL_KEY_ORDER
    .map(k => settings.find(s => s.key === k))
    .filter((s): s is SystemSetting => s !== undefined)

  const [vals, setVals] = useState<Record<string, string>>(() =>
    Object.fromEntries(relevant.map(s => [s.key, String(s.value)]))
  )
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setVals(Object.fromEntries(relevant.map(s => [s.key, String(s.value)])))
  }, [settings]) // eslint-disable-line react-hooks/exhaustive-deps

  const dirtyKeys = relevant.filter(s => vals[s.key] !== String(s.value)).map(s => s.key)
  const hasDirty  = dirtyKeys.length > 0

  const handleSave = async () => {
    setSaving(true)
    try {
      const changes = relevant
        .filter(s => vals[s.key] !== String(s.value))
        .map(s => ({
          key:   s.key,
          value: s.type === 'boolean' ? vals[s.key] === 'true'
               : s.type === 'integer' ? parseInt(vals[s.key])
               : vals[s.key],
        }))
      await onSave(changes)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-800 dark:text-gray-100">
          <Gear size={16} weight="duotone" style={{ color: 'var(--color-1)' }} />
          Configuração de Workers
        </div>
        <button
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          style={{ background: 'var(--color-save)', color: 'var(--on-color-save)' }}
          onClick={handleSave}
          disabled={!hasDirty || saving}
          title={hasDirty ? `Salvar ${dirtyKeys.length} alteração${dirtyKeys.length !== 1 ? 'ões' : ''}` : 'Nenhuma alteração'}
        >
          {saving ? '…' : 'Salvar'}
        </button>
      </div>

      {/* Todos os campos em uma única linha */}
      <div className="grid grid-cols-4 gap-3">
        {relevant.map(s => (
          <SettingRow
            key={s.key}
            setting={s}
            shortLabel={ETL_KEY_LABELS[s.key] ?? s.key}
            value={vals[s.key] ?? String(s.value)}
            onChange={v => setVals(prev => ({ ...prev, [s.key]: v }))}
          />
        ))}
      </div>
    </div>
  )
}

function SettingRow({ setting, shortLabel, value, onChange }: {
  setting:    SystemSetting
  shortLabel: string
  value:      string
  onChange:   (v: string) => void
}) {
  const isBoolean = setting.type === 'boolean'

  return (
    <div className="flex flex-col gap-1.5">
      <label
        className="text-xs font-semibold text-gray-500 dark:text-gray-400"
        title={setting.description || setting.key}
      >
        {shortLabel}
      </label>
      {isBoolean ? (
        <select
          className="w-full px-2 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 outline-none focus:border-[color:var(--color-1)] transition-colors"
          value={value}
          onChange={e => onChange(e.target.value)}
        >
          <option value="true">On</option>
          <option value="false">Off</option>
        </select>
      ) : (
        <input
          type="number"
          min={0}
          className="w-full px-2 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 font-mono outline-none focus:border-[color:var(--color-1)] transition-colors"
          value={value}
          onChange={e => onChange(e.target.value)}
        />
      )}
    </div>
  )
}

function WorkerPoolCard({
  type, pool, onStart, onStop, onRestart, onKill, loading,
}: {
  type:      WorkerType
  pool:      WorkerPool
  onStart:   () => void
  onStop:    () => void
  onRestart: () => void
  onKill:    () => void
  loading:   boolean
}) {
  const aliveRatio  = pool.count > 0 ? pool.alive / pool.count : 0
  const badgeStyle: React.CSSProperties = aliveRatio === 1
    ? { background: 'var(--color-create)',  color: 'var(--on-color-create)'  }
    : aliveRatio > 0
    ? { background: 'var(--color-warning)', color: 'var(--on-color-warning)' }
    : { background: 'var(--color-danger)',  color: 'var(--on-color-danger)'  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-4 flex flex-col gap-3 hover:border-[color:var(--color-1)] transition-colors">
      <div className="flex items-center gap-2">
        <span style={{ color: 'var(--color-1)' }}>{WORKER_ICONS[type]}</span>
        <span className="font-semibold text-sm text-gray-800 dark:text-gray-100">{WORKER_LABELS[type]}</span>
        <span className="ml-auto inline-flex items-center justify-center h-5 text-xs px-2 rounded font-semibold" style={badgeStyle}>
          {pool.alive}/{pool.count} alive
        </span>
      </div>

      {/* Lifecycle buttons */}
      <div className="flex gap-1.5 flex-wrap">
        <button
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          style={{ background: 'var(--color-create)', color: 'var(--on-color-create)' }}
          onClick={onStart}
          disabled={loading || pool.alive > 0}
          title={pool.alive > 0 ? 'Workers já estão rodando' : 'Iniciar workers'}
        >
          <Play size={12} /> Start
        </button>
        <button
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors disabled:opacity-40"
          style={{ background: 'var(--color-cancel)', color: 'var(--on-color-cancel)' }}
          onClick={onStop} disabled={loading}
        >
          <Square size={12} /> Stop
        </button>
        <button
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors disabled:opacity-40"
          style={{ background: 'var(--color-warning)', color: 'var(--on-color-warning)' }}
          onClick={onRestart} disabled={loading}
        >
          <ArrowClockwise size={12} /> Restart
        </button>
        <button
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors disabled:opacity-40"
          style={{ background: 'var(--color-danger)', color: 'var(--on-color-danger)' }}
          onClick={onKill} disabled={loading}
        >
          <Skull size={12} /> Kill
        </button>
      </div>

      {/* Workers list */}
      <div className="flex flex-col gap-1">
        {pool.workers.map(w => (
          <div key={w.worker_id}
            className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-700/50 rounded-lg px-2 py-1.5">
            <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: w.is_alive ? '#22c55e' : '#ef4444' }} />
            <span className="font-mono text-gray-700 dark:text-gray-200">#{w.worker_id}</span>
            <span className="ml-auto font-mono">{w.processed_count} ok / {w.error_count} err</span>
          </div>
        ))}
        {pool.workers.length === 0 && (
          <p className="text-xs text-gray-400 dark:text-gray-500 italic">Nenhum worker no pool</p>
        )}
      </div>
    </div>
  )
}
