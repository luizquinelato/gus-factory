import React, { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowClockwise, ArrowCounterClockwise, CheckCircle, Clock, Play, Tray, Trash, Warning } from '@phosphor-icons/react'
import { toast } from 'sonner'
import apiClient from '../services/apiClient'

// ── Types ─────────────────────────────────────────────────────────────────────

interface OutboxStats { pending: number; processed: number; dead_letter: number }

interface OutboxEvent {
  id: number; event_name: string; status: 'pending' | 'processed' | 'dead-letter'
  attempts: number; max_attempts: number; last_error: string | null
  created_at: string | null; processed_at: string | null; failed_at: string | null
  payload?: Record<string, unknown>
}

// ── StatCard ──────────────────────────────────────────────────────────────────

function StatCard({ icon: Icon, label, value, color }: { icon: React.ElementType; label: string; value: number; color: string }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-5 flex items-center gap-4">
      <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: `${color}22` }}>
        <Icon size={20} style={{ color }} />
      </div>
      <div>
        <p className="text-2xl font-bold text-gray-800 dark:text-gray-100">{value}</p>
        <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

// ── Status badge ──────────────────────────────────────────────────────────────

const STATUS_STYLE: Record<string, { label: string; bg: string; color: string }> = {
  'pending':     { label: 'Pendente',    bg: 'var(--color-warning)', color: 'var(--on-color-warning)' },
  'processed':   { label: 'Processado',  bg: 'var(--color-success)', color: 'var(--on-color-success)' },
  'dead-letter': { label: 'Dead-letter', bg: 'var(--color-danger)',  color: 'var(--on-color-danger)'  },
}

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLE[status] ?? STATUS_STYLE['pending']
  return (
    <span
      className="inline-flex items-center justify-center text-[11px] font-semibold px-2 py-0.5 rounded"
      style={{ background: s.bg, color: s.color }}
    >
      {s.label}
    </span>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function OutboxPage() {
  const [stats,       setStats]       = useState<OutboxStats>({ pending: 0, processed: 0, dead_letter: 0 })
  const [recent,      setRecent]      = useState<OutboxEvent[]>([])
  const [deadLetters, setDeadLetters] = useState<OutboxEvent[]>([])
  const [loading,     setLoading]     = useState(true)
  const [expanded,    setExpanded]    = useState<number | null>(null)
  const [acting,      setActing]      = useState<number | null>(null)
  const [testing,     setTesting]     = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const autoRefreshRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // silent=true → não mostra loading skeleton (usado no auto-refresh)
  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [s, r, d] = await Promise.all([
        apiClient.get('/admin/outbox/stats'),
        apiClient.get('/admin/outbox/recent?limit=20'),
        apiClient.get('/admin/outbox/dead-letters?limit=50'),
      ])
      setStats(s.data)
      setRecent(r.data.events)
      setDeadLetters(d.data.events)
    } catch { if (!silent) toast.error('Erro ao carregar outbox.') }
    finally  { if (!silent) setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  // Auto-refresh silencioso a cada 2s — sem piscar
  useEffect(() => {
    if (autoRefresh) {
      autoRefreshRef.current = setInterval(() => load(true), 2000)
    } else {
      if (autoRefreshRef.current) clearInterval(autoRefreshRef.current)
    }
    return () => { if (autoRefreshRef.current) clearInterval(autoRefreshRef.current) }
  }, [autoRefresh, load])

  async function handleRetry(id: number) {
    setActing(id)
    try {
      await apiClient.post(`/admin/outbox/${id}/retry`)
      toast.success('Evento recolocado na fila.')
      load()
    } catch { toast.error('Erro ao retentar.') }
    finally  { setActing(null) }
  }

  async function handleDiscard(id: number) {
    if (!window.confirm('Descartar permanentemente este evento?')) return
    setActing(id)
    try {
      await apiClient.delete(`/admin/outbox/${id}`)
      toast.success('Evento descartado.')
      load()
    } catch { toast.error('Erro ao descartar.') }
    finally  { setActing(null) }
  }

  async function handleTest() {
    setTesting(true)
    try {
      await apiClient.post('/admin/outbox/test')
      toast.success('Evento de teste enviado! Aguarde ~2s e atualize.')
      setAutoRefresh(true)
      // Para o auto-refresh após 10s (tempo suficiente para ver o ciclo completo)
      setTimeout(() => setAutoRefresh(false), 10_000)
      load()
    } catch { toast.error('Erro ao enviar evento de teste.') }
    finally  { setTesting(false) }
  }

  const fmtDate = (d: string | null) => d ? new Date(d).toLocaleString('pt-BR') : '—'

  return (
    <div className="min-h-full p-8 space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">Event Outbox</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Monitoramento do Outbox Pattern. Apenas eventos em <strong>dead-letter</strong> requerem ação manual.
        </p>
      </div>

      {/* Pipeline test */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-5 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: 'var(--color-1)22' }}>
            <Play size={18} style={{ color: 'var(--color-1)' }} />
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">Testar Pipeline</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Injeta um evento <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded text-xs">system.outbox_test</code> no outbox.
              O OutboxProcessor entrega em ~2s — acompanhe os stats ao vivo.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          {/* Auto-refresh toggle */}
          <button
            onClick={() => setAutoRefresh(v => !v)}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold border transition-colors ${
              autoRefresh
                ? 'border-[color:var(--color-1)] text-[color:var(--color-1)] bg-[color:var(--color-1)]/10'
                : 'border-gray-200 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:border-gray-300 dark:hover:border-gray-500 bg-white dark:bg-gray-800'
            }`}
          >
            <ArrowClockwise size={13} className={autoRefresh ? 'animate-spin' : ''} />
            {autoRefresh ? 'Ao vivo' : 'Auto-refresh'}
          </button>
          {/* Disparar teste */}
          <button
            onClick={handleTest}
            disabled={testing}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all disabled:opacity-60"
            style={{ background: 'var(--color-1)', color: 'var(--on-color-1)' }}
          >
            <Play size={15} weight="fill" className={testing ? 'animate-pulse' : ''} />
            {testing ? 'Enviando…' : 'Disparar evento'}
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <StatCard icon={Clock}       label="Pendentes"   value={stats.pending}     color="#f59e0b" />
        <StatCard icon={CheckCircle} label="Processados" value={stats.processed}   color="#22c55e" />
        <StatCard icon={Warning}     label="Dead-letter" value={stats.dead_letter} color="#ef4444" />
      </div>

      {/* Recent events */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <ArrowClockwise size={16} className="text-gray-400" />
            <span className="text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Eventos Recentes
            </span>
          </div>
          <button onClick={() => load()} disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-semibold border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50">
            <ArrowClockwise size={14} className={loading ? 'animate-spin' : ''} />
            Atualizar
          </button>
        </div>
        <section className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm mb-6">
          {loading ? (
            <p className="text-sm text-gray-400 p-6">Carregando...</p>
          ) : recent.length === 0 ? (
            <p className="text-sm text-gray-400 p-6">Nenhum evento ainda. Clique em "Disparar evento" para testar.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 dark:border-gray-700">
                    <th className="text-left py-3 px-4 text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">Evento</th>
                    <th className="text-left py-3 px-4 text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">Status</th>
                    <th className="text-left py-3 px-4 text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 hidden md:table-cell">Criado em</th>
                    <th className="text-left py-3 px-4 text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 hidden lg:table-cell">Processado em</th>
                    <th className="text-center py-3 px-4 text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">Tent.</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((ev, i) => (
                    <tr key={ev.id} className={`transition-colors hover:bg-gray-50 dark:hover:bg-gray-700/50 ${i % 2 === 0 ? 'bg-gray-50/50 dark:bg-gray-700/20' : ''}`}>
                      <td className="py-2.5 px-4 font-mono text-xs text-gray-700 dark:text-gray-300">{ev.event_name}</td>
                      <td className="py-2.5 px-4"><StatusBadge status={ev.status} /></td>
                      <td className="py-2.5 px-4 text-gray-500 dark:text-gray-400 text-xs hidden md:table-cell">{fmtDate(ev.created_at)}</td>
                      <td className="py-2.5 px-4 text-gray-500 dark:text-gray-400 text-xs hidden lg:table-cell">{fmtDate(ev.processed_at)}</td>
                      <td className="py-2.5 px-4 text-center text-xs text-gray-500 dark:text-gray-400">{ev.attempts}/{ev.max_attempts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {/* Dead-letter list */}
      <div>
        <div className="flex items-center mb-2">
          <div className="flex items-center gap-2">
            <Tray size={16} className="text-gray-400" />
            <span className="text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Eventos Dead-Letter
            </span>
          </div>
        </div>

        <section className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
          {loading ? (
            <p className="text-sm text-gray-400 p-6">Carregando...</p>
          ) : deadLetters.length === 0 ? (
            <div className="p-10 text-center">
              <CheckCircle size={32} className="mx-auto mb-3 text-green-400" />
              <p className="text-sm font-semibold text-gray-600 dark:text-gray-300">Nenhum evento em dead-letter</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">O outbox está saudável.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 dark:border-gray-700">
                    <th className="text-left py-3 px-4 text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">Evento</th>
                    <th className="text-left py-3 px-4 text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 hidden md:table-cell">Criado em</th>
                    <th className="text-left py-3 px-4 text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 hidden lg:table-cell">Falhou em</th>
                    <th className="text-center py-3 px-4 text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">Tent.</th>
                    <th className="py-3 px-4" />
                  </tr>
                </thead>
                <tbody>
                  {deadLetters.map((ev, i) => (
                    <React.Fragment key={ev.id}>
                      <tr
                        className={`cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-gray-700/50 ${i % 2 === 0 ? 'bg-gray-50/50 dark:bg-gray-700/20' : ''}`}
                        onClick={() => setExpanded(expanded === ev.id ? null : ev.id)}
                      >
                        <td className="py-3 px-4">
                          <span className="font-mono text-xs bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 px-2 py-1 rounded">
                            {ev.event_name}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-gray-500 dark:text-gray-400 text-xs hidden md:table-cell">{fmtDate(ev.created_at)}</td>
                        <td className="py-3 px-4 text-gray-500 dark:text-gray-400 text-xs hidden lg:table-cell">{fmtDate(ev.failed_at)}</td>
                        <td className="py-3 px-4 text-center">
                          <span className="text-xs font-semibold text-red-500">{ev.attempts}/{ev.max_attempts}</span>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2 justify-end" onClick={e => e.stopPropagation()}>
                            <button onClick={() => handleRetry(ev.id)} disabled={acting === ev.id} title="Retentar"
                              className="p-1.5 rounded-lg text-gray-400 hover:text-green-500 hover:bg-green-50 dark:hover:bg-green-900/20 transition-colors disabled:opacity-50">
                              <ArrowCounterClockwise size={16} className={acting === ev.id ? 'animate-spin' : ''} />
                            </button>
                            <button onClick={() => handleDiscard(ev.id)} disabled={acting === ev.id} title="Descartar"
                              className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50">
                              <Trash size={16} />
                            </button>
                          </div>
                        </td>
                      </tr>
                      {expanded === ev.id && (
                        <tr className="bg-gray-50 dark:bg-gray-900/40">
                          <td colSpan={5} className="px-6 pb-4 pt-2">
                            {ev.last_error && (
                              <p className="text-xs text-red-500 dark:text-red-400 mb-2 font-mono">
                                <strong>Erro:</strong> {ev.last_error}
                              </p>
                            )}
                            <pre className="text-xs bg-gray-100 dark:bg-gray-800 rounded-lg p-3 overflow-x-auto text-gray-700 dark:text-gray-300">
                              {JSON.stringify(ev.payload, null, 2)}
                            </pre>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs text-gray-400 dark:text-gray-500 p-4 border-t border-gray-100 dark:border-gray-700">
            Clique em uma linha para ver o payload. Retry recoloca na fila; Descartar remove permanentemente.
          </p>
        </section>
      </div>

    </div>
  )
}
