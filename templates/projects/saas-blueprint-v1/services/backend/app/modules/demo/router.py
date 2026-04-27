"""
modules/demo/router.py
======================
Endpoints do módulo Demo — serve como exemplo testável do Event Bus + Outbox Pattern.

Endpoints
---------
POST /api/v1/modules/demo/ping
    Emite 'demo.ping' via emit_reliable() → grava no events_outbox.
    O OutboxProcessor entrega o evento ao handler em até POLL_INTERVAL segundos.
    Use para verificar que o pipeline Event Bus → Outbox → Handler está funcionando.

GET  /api/v1/modules/demo/ping/status
    Retorna os últimos eventos 'demo.ping' no outbox (pendentes, processados, falhos).
    Útil para confirmar que o OutboxProcessor está rodando.

Remova este módulo em produção ou substitua por módulos de negócio reais.
"""
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.event_bus import EventBus
from app.dependencies.auth import require_authentication

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/ping", summary="Emite demo.ping via Outbox (teste do Event Bus)")
async def ping(
    message: str = Query(default="hello", description="Mensagem de teste"),
    db: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_authentication),
):
    """
    Grava um evento 'demo.ping' no events_outbox dentro de uma transação.
    O OutboxProcessor (background) entrega ao handler em até ~2 segundos.

    Fluxo completo:
      1. INSERT INTO events_outbox (dentro da transação desta request)
      2. COMMIT
      3. OutboxProcessor lê o evento no próximo ciclo (poll=2s)
      4. EventBus.emit("demo.ping", payload) → on_demo_ping() é chamado
      5. events_outbox.processed_at = NOW()

    Verifique os logs do backend para confirmar a entrega.
    """
    tenant_id = user.get("tenant_id")
    payload = {
        "from": user.get("email", "unknown"),
        "msg":  message,
    }

    await EventBus.emit_reliable("demo.ping", payload, db, tenant_id=tenant_id)
    await db.commit()

    logger.info("demo/ping: evento gravado no outbox por %s", user.get("email"))
    return {
        "detail":  "Evento 'demo.ping' gravado no outbox.",
        "payload": payload,
        "note":    "Verifique os logs do backend — o handler será chamado em até 2s.",
    }


@router.get("/ping/status", summary="Status dos últimos eventos demo.ping no outbox")
async def ping_status(
    limit: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_authentication),
):
    """
    Lista os últimos eventos 'demo.ping' no outbox com seu status de processamento,
    filtrados pelo tenant do usuário autenticado.
    Útil para verificar que o OutboxProcessor está rodando corretamente.
    """
    result = await db.execute(
        text("""
            SELECT id, payload, attempts, last_error,
                   created_at, processed_at, failed_at
            FROM   events_outbox
            WHERE  event_name = 'demo.ping'
              AND  tenant_id  = :tenant_id
            ORDER  BY created_at DESC
            LIMIT  :limit
        """),
        {"tenant_id": user.get("tenant_id"), "limit": limit},
    )
    rows = result.fetchall()

    events = []
    for r in rows:
        if r.processed_at:
            status = "processed"
        elif r.failed_at:
            status = "dead-letter"
        else:
            status = "pending"

        events.append({
            "id":           r.id,
            "status":       status,
            "attempts":     r.attempts,
            "last_error":   r.last_error,
            "created_at":   r.created_at.isoformat() if r.created_at else None,
            "processed_at": r.processed_at.isoformat() if r.processed_at else None,
            "failed_at":    r.failed_at.isoformat() if r.failed_at else None,
        })

    return {"total": len(events), "events": events}
