"""
core/event_bus.py
=================
Event Bus in-process para comunicação desacoplada entre módulos.

Dois modos de emissão:

  emit()          → best-effort, in-process, síncrono.
                    Erros num handler são logados e isolados: os demais handlers
                    continuam executando. Usar para eventos informativos/cache.

  emit_reliable() → transacional via Outbox Pattern.
                    Grava o evento na tabela `events_outbox` dentro da mesma
                    transação do chamador. O OutboxProcessor (background task)
                    entrega com retry. Usar para eventos financeiros e de estoque.

Regra de escolha
----------------
  ├── Evento cruza fronteira financeira?        → emit_reliable
  │     ex: order.confirmed, payment.confirmed, purchase.received
  ├── Evento modifica estoque efetivamente?     → emit_reliable
  │     ex: order.paid, order.cancelled, order.delivered
  └── Evento é informativo / invalida cache?   → emit
        ex: product.updated, client.created, stock.low

Evolução futura
---------------
  Quando o volume justificar durabilidade externa, OutboxProcessor troca a
  entrega local por publish no RabbitMQ. Nenhum módulo muda — só o transporte.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class EventBus:
    """
    Registro global de handlers por nome de evento.

    Uso (no __init__.py do módulo):
        EventBus.subscribe("order.confirmed", estoque_service.on_order_confirmed)
        EventBus.subscribe("order.confirmed", financeiro_service.on_order_confirmed)
    """

    _handlers: dict[str, list[Callable]] = {}

    # ── Registro ──────────────────────────────────────────────────────────────

    @classmethod
    def subscribe(cls, event_name: str, handler: Callable) -> None:
        """Registra um handler para um evento. Vários handlers por evento são suportados."""
        cls._handlers.setdefault(event_name, []).append(handler)
        logger.debug("EventBus: '%s' registrado para '%s'", handler.__name__, event_name)

    @classmethod
    def clear(cls) -> None:
        """Remove todos os handlers. Útil em testes."""
        cls._handlers.clear()

    # ── Emissão best-effort ───────────────────────────────────────────────────

    @classmethod
    async def emit(cls, event_name: str, payload: dict) -> None:
        """
        Entrega in-process, best-effort.
        Falha num handler é logada e isolada — os demais handlers continuam.
        NÃO use para eventos que afetam saldo, estoque ou contabilidade.

        Quando chamado pelo OutboxProcessor (via emit_reliable), o payload
        contém duas chaves injetadas automaticamente pelo sistema:

          payload["__event_id__"]  : int — ID da linha em events_outbox.
              Use como chave de idempotência nos handlers:
              INSERT INTO stock_movements (...) VALUES (...)
              ON CONFLICT (outbox_event_id) DO NOTHING

          payload["__tenant_id__"] : int — tenant_id da coluna da tabela (fonte de verdade).
              Use SEMPRE este valor para filtrar queries no handler,
              nunca leia tenant_id diretamente do payload de negócio.
              Garante isolamento mesmo se o chamador omitir tenant_id no payload.

        Handlers de emit() direto (sem Outbox) NÃO recebem __event_id__ nem __tenant_id__
        automaticamente — o chamador é responsável por incluir tenant_id no payload.
        """
        handlers = cls._handlers.get(event_name, [])
        if not handlers:
            logger.debug("EventBus.emit: nenhum handler para '%s'", event_name)
            return

        for handler in handlers:
            try:
                await handler(payload)
            except Exception as exc:
                logger.error(
                    "EventBus handler '%s' falhou para '%s': %s",
                    handler.__name__, event_name, exc, exc_info=True,
                )

    # ── Emissão confiável (Outbox) ────────────────────────────────────────────

    @classmethod
    async def emit_reliable(
        cls,
        event_name: str,
        payload: dict,
        db: AsyncSession,
        tenant_id: int,
    ) -> None:
        """
        Grava o evento na tabela `events_outbox` dentro da transação do chamador.

        - O commit é responsabilidade do chamador.
        - Se a transação fizer rollback, o evento some junto — consistência garantida.
        - O OutboxProcessor entrega o evento após o commit, com retry automático.
        - tenant_id isola eventos por tenant (obrigatório — nunca omitir).

        Use para qualquer evento que afete saldo, estoque, contas ou contabilidade.
        """
        await db.execute(
            text("""
                INSERT INTO events_outbox (event_name, payload, tenant_id)
                VALUES (:name, CAST(:payload AS jsonb), :tenant_id)
            """),
            {"name": event_name, "payload": json.dumps(payload, default=str), "tenant_id": tenant_id},
        )
        logger.debug("EventBus.emit_reliable: '%s' (tenant=%s) gravado no outbox", event_name, tenant_id)
