#!/usr/bin/env python3
"""
Migration 0004: Event Bus — Outbox Pattern
==========================================
Project : SaaS Blueprint V1
Creates : events_outbox

Tabela de outbox para o padrão Transactional Outbox:
- Módulos de negócio gravam eventos confiáveis aqui, dentro da mesma
  transação que altera o dado de negócio (via EventBus.emit_reliable).
- OutboxProcessor (background task) lê, entrega e marca como processado.
- Eventos financeiros/estoque DEVEM usar emit_reliable.
- Eventos informativos/cache podem usar emit (best-effort in-process).

Runner registra esta migration em migration_history após apply() suceder.
NÃO registre dentro de apply() — o runner cuida disso.
"""
import logging

logger = logging.getLogger(__name__)


def apply(conn) -> None:
    logger.info("Applying 0004_event_bus_schema...")
    with conn.cursor() as cur:

        # events_outbox
        # Ordem: [id] → [campos próprios] → [tenant_id] → [created_at]
        # Sem active/last_updated_at — outbox é append-only com timestamps explícitos.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS events_outbox (
                -- 1. ID
                id           BIGSERIAL    PRIMARY KEY,
                -- 2. Campos próprios
                event_name   VARCHAR(100) NOT NULL,
                payload      JSONB        NOT NULL DEFAULT '{}',
                attempts     SMALLINT     NOT NULL DEFAULT 0,
                max_attempts SMALLINT     NOT NULL DEFAULT 3,
                last_error   TEXT,
                processed_at TIMESTAMPTZ,
                failed_at    TIMESTAMPTZ,
                -- 3. Campos herdados
                tenant_id    INTEGER      NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
            );
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_outbox_tenant ON events_outbox (tenant_id);")

        # Índice parcial — cobre apenas eventos pendentes (processed_at IS NULL AND failed_at IS NULL)
        # Mantém o scan eficiente mesmo com milhões de eventos históricos processados.
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_outbox_pending
                ON events_outbox (tenant_id, created_at)
                WHERE processed_at IS NULL AND failed_at IS NULL;
        """)

    logger.info("0004_event_bus_schema applied.")


def rollback(conn) -> None:
    logger.info("Rolling back 0004_event_bus_schema...")
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS events_outbox CASCADE;")
    logger.info("0004_event_bus_schema rolled back.")
