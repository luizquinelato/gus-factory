/**
 * queueApiService.ts
 * ==================
 * Todos os calls de Queue Management para o backend ETL.
 * Usa o apiClient (axios com interceptor Bearer + refresh automático).
 */
import apiClient from './apiClient'
import type {
  QueueStats, QueueType, WorkerStatus, WorkerType,
  WorkerConfig, JobError, FakeJobResult, SystemSetting,
} from '../types'

// ── Queues ────────────────────────────────────────────────────────────────────

export const getQueues = (): Promise<{ queues: QueueStats[] }> =>
  apiClient.get('/queues').then(r => r.data)

export const getQueue = (type: QueueType): Promise<QueueStats> =>
  apiClient.get(`/queues/${type}`).then(r => r.data)

export const getQueueDepth = (type: QueueType): Promise<{ queue: string; depth: number }> =>
  apiClient.get(`/queues/${type}/depth`).then(r => r.data)

export const purgeQueue = (type: QueueType): Promise<{ messages_purged: number; message: string }> =>
  apiClient.post(`/queues/${type}/purge`).then(r => r.data)

// ── Workers — status ──────────────────────────────────────────────────────────

export const getWorkers = (): Promise<WorkerStatus> =>
  apiClient.get('/workers').then(r => r.data)

export const getWorkerPool = (type: WorkerType): Promise<WorkerStatus> =>
  apiClient.get(`/workers/${type}`).then(r => r.data)

// ── Workers — global lifecycle ────────────────────────────────────────────────

export const startAllWorkers = (): Promise<{ message: string }> =>
  apiClient.post('/workers/start').then(r => r.data)

export const stopAllWorkers = (): Promise<{ message: string }> =>
  apiClient.post('/workers/stop').then(r => r.data)

export const restartAllWorkers = (): Promise<{ message: string }> =>
  apiClient.post('/workers/restart').then(r => r.data)

// ── Workers — per-type lifecycle ──────────────────────────────────────────────

export const startWorkerPool = (type: WorkerType): Promise<{ message: string }> =>
  apiClient.post(`/workers/${type}/start`).then(r => r.data)

export const stopWorkerPool = (type: WorkerType): Promise<{ message: string }> =>
  apiClient.post(`/workers/${type}/stop`).then(r => r.data)

export const restartWorkerPool = (type: WorkerType): Promise<{ message: string }> =>
  apiClient.post(`/workers/${type}/restart`).then(r => r.data)

// ── Workers — scaling ─────────────────────────────────────────────────────────

export const scaleWorker = (
  type: WorkerType,
  payload: { delta: number } | { count: number },
): Promise<{ new_count?: number; count?: number; message?: string }> =>
  apiClient.post(`/workers/${type}/scale`, payload).then(r => r.data)

// ── Workers — error log ───────────────────────────────────────────────────────

export const getErrorLog = (limit = 100): Promise<{ errors: JobError[]; total: number }> =>
  apiClient.get('/workers/errors', { params: { limit } }).then(r => r.data)

export const clearErrorLog = (): Promise<{ message: string }> =>
  apiClient.delete('/workers/errors').then(r => r.data)

// ── Fake job ──────────────────────────────────────────────────────────────────

export const dispatchFakeJob = (tenantId = 1): Promise<FakeJobResult> =>
  apiClient.post('/workers/jobs/fake', null, { params: { tenant_id: tenantId } }).then(r => r.data)

// ── Settings ──────────────────────────────────────────────────────────────────

export const getSettings = (): Promise<{ settings: SystemSetting[] }> =>
  apiClient.get('/settings').then(r => r.data)

export const getSetting = (key: string): Promise<SystemSetting> =>
  apiClient.get(`/settings/${key}`).then(r => r.data)

export const updateSetting = (key: string, value: unknown): Promise<{ key: string; value: unknown }> =>
  apiClient.put(`/settings/${key}`, { value }).then(r => r.data)
