"""
core/outbox_processor.py
========================
Background asyncio task que processa a tabela `events_outbox`.

Ciclo de vida:
  main.py (lifespan) → OutboxProcessor.start() → loop assíncrono
                     → OutboxProcessor.stop()   → encerra graciosamente

Algoritmo por ciclo:
  1. SELECT ... FOR UPDATE SKIP LOCKED
       Seguro para múltiplas instâncias do processo (ex: dois workers uvicorn).
       Cada instância pega um lote diferente — sem processamento duplicado.
  2. Para cada evento: injeta __event_id__ e __tenant_id__ no payload,
       depois chama EventBus.emit(event_name, payload).
  3. Sucesso → processed_at = NOW()
  4. Falha   → attempts += 1, last_error = msg
               Se attempts >= max_attempts → failed_at = NOW() (dead-letter)
  5. COMMIT do lote inteiro.

Metadados injetados automaticamente no payload de cada handler:
  __event_id__  : int  — ID único da linha em events_outbox.
                          Use como chave de idempotência:
                          INSERT ... ON CONFLICT (event_id) DO NOTHING
  __tenant_id__ : int  — tenant_id da coluna da tabela (fonte de verdade).
                          Handlers DEVEM usar este valor para filtrar queries,
                          nunca payload["tenant_id"] diretamente.

Eventos com failed_at IS NOT NULL ficam na tabela para auditoria e podem
ser reprocessados manualmente via admin UI (Configurações → Outbox).
"""
from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.event_bus import EventBus

logger = logging.getLogger(__name__)

POLL_INTERVAL: float = 2.0   # segundos entre cada ciclo de polling
BATCH_SIZE:    int   = 50    # máximo de eventos por ciclo


class OutboxProcessor:
    """Gerencia o loop de background para processamento do outbox."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        """Inicia o loop em background. Chamado no lifespan do FastAPI."""
        if self._task and not self._task.done():
            logger.warning("OutboxProcessor já está em execução.")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="outbox_processor")
        logger.info("✅ OutboxProcessor iniciado (poll=%ss, batch=%s).", POLL_INTERVAL, BATCH_SIZE)

    def stop(self) -> None:
        """Para o loop graciosamente. Chamado no shutdown do lifespan."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("⏹ OutboxProcessor parado.")

    # ── Loop interno ─────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._process_batch()
            except Exception as exc:
                logger.error("OutboxProcessor erro inesperado no ciclo: %s", exc, exc_info=True)
            await asyncio.sleep(POLL_INTERVAL)

    async def _process_batch(self) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("""
                    SELECT id, event_name, payload, attempts, max_attempts, tenant_id
                    FROM   events_outbox
                    WHERE  processed_at IS NULL
                      AND  failed_at    IS NULL
                    ORDER  BY created_at
                    LIMIT  :limit
                    FOR UPDATE SKIP LOCKED
                """),
                {"limit": BATCH_SIZE},
            )
            rows = result.fetchall()

            if not rows:
                return

            for row in rows:
                await self._deliver(db, row)

            await db.commit()

    async def _deliver(self, db, row) -> None:
        """Tenta entregar um evento. Atualiza status dentro da sessão aberta."""
        try:
            payload = json.loads(row.payload) if isinstance(row.payload, str) else row.payload

            # Injeta metadados do outbox — presentes em TODOS os handlers de emit_reliable.
            # __event_id__  → chave de idempotência (use em INSERT ... ON CONFLICT DO NOTHING)
            # __tenant_id__ → fonte de verdade para isolamento multi-tenant no handler
            payload = {
                **payload,
                "__event_id__":  row.id,
                "__tenant_id__": row.tenant_id,
            }

            await EventBus.emit(row.event_name, payload)

            await db.execute(
                text("UPDATE events_outbox SET processed_at = NOW() WHERE id = :id"),
                {"id": row.id},
            )
            logger.debug("OutboxProcessor: '%s' (id=%s) entregue.", row.event_name, row.id)

        except Exception as exc:
            new_attempts = row.attempts + 1
            is_dead = new_attempts >= row.max_attempts

            await db.execute(
                text("""
                    UPDATE events_outbox
                    SET    attempts   = :attempts,
                           last_error = :err,
                           failed_at  = CASE WHEN :dead THEN NOW() ELSE NULL END
                    WHERE  id = :id
                """),
                {
                    "attempts": new_attempts,
                    "err":      str(exc)[:1000],
                    "dead":     is_dead,
                    "id":       row.id,
                },
            )

            if is_dead:
                logger.error(
                    "OutboxProcessor: '%s' (id=%s) esgotou %s tentativas — dead-letter. Erro: %s",
                    row.event_name, row.id, row.max_attempts, exc,
                )
            else:
                logger.warning(
                    "OutboxProcessor: '%s' (id=%s) falhou (tentativa %s/%s): %s",
                    row.event_name, row.id, new_attempts, row.max_attempts, exc,
                )


# Singleton — uma instância por processo
outbox_processor = OutboxProcessor()
