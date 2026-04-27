"""
modules/demo/events.py
======================
Handlers de eventos do módulo Demo.

Este arquivo é importado pelo __init__.py do módulo, que garante que os
handlers são registrados no EventBus antes do app subir.

Padrão para módulos reais
--------------------------
Crie um events.py em cada módulo com os handlers dos eventos que ele CONSOME.
Os eventos que ele EMITE estão documentados no Mapa de Eventos (modular-monolith.md).

Exemplo real (módulo estoque):
    # modules/estoque/events.py
    from app.core.event_bus import EventBus
    from app.modules.estoque.service import EstoqueService

    async def on_order_confirmed(payload: dict) -> None:
        await EstoqueService.reservar_estoque(
            order_id  = payload["order_id"],
            tenant_id = payload["tenant_id"],
            items     = payload["items"],
        )

    async def on_order_cancelled(payload: dict) -> None:
        await EstoqueService.liberar_reserva(payload["order_id"], payload["tenant_id"])

    EventBus.subscribe("order.confirmed",  on_order_confirmed)   # emit_reliable
    EventBus.subscribe("order.cancelled",  on_order_cancelled)   # emit_reliable
"""
import logging

from app.core.event_bus import EventBus

logger = logging.getLogger(__name__)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def on_demo_ping(payload: dict) -> None:
    """
    Handler de demonstração para o evento 'demo.ping'.

    Em módulos reais, aqui você chamaria o service do módulo:
        await MeuService.processar(payload["tenant_id"], payload["dados"])
    """
    sender    = payload.get("from", "desconhecido")
    message   = payload.get("msg", "")
    tenant_id = payload.get("tenant_id")

    logger.info(
        "🏓 [demo] demo.ping recebido | tenant=%s | from=%s | msg=%s",
        tenant_id, sender, message,
    )

    # Simulação de trabalho do handler
    # Em produção: await algum_service.processar(payload)


# ── Subscrições ───────────────────────────────────────────────────────────────
# Este bloco é executado no import do arquivo. O __init__.py do módulo
# importa este arquivo, garantindo o registro antes do app subir.

EventBus.subscribe("demo.ping", on_demo_ping)
