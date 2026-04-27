"""
routers/outbox_router.py
========================
Endpoints administrativos para gerenciar eventos dead-letter no events_outbox.

Acesso restrito a administradores (require_admin).

Endpoints
---------
GET  /admin/outbox/stats
    Totais de eventos pendentes, processados e em dead-letter.

POST /admin/outbox/test
    Injeta um evento 'system.outbox_test' no outbox para validar o pipeline
    completo: INSERT → OutboxProcessor → EventBus.emit → processed_at.

GET  /admin/outbox/dead-letters
    Lista eventos com failed_at IS NOT NULL (esgotaram todas as tentativas).

POST /admin/outbox/{event_id}/retry
    Reseta attempts e failed_at de um evento para que o OutboxProcessor
    tente reentregá-lo no próximo ciclo.

DELETE /admin/outbox/{event_id}
    Descarta definitivamente um evento dead-letter (não pode ser desfeito).
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.dependencies.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/outbox", tags=["outbox-admin"])


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats", summary="Totais do events_outbox")
async def outbox_stats(
    db: AsyncSession = Depends(get_db_session),
    admin=Depends(require_admin),
):
    """Retorna contagens de eventos por status, filtradas pelo tenant do admin."""
    tenant_id = admin.get("tenant_id") if isinstance(admin, dict) else getattr(admin, "tenant_id", None)
    result = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE processed_at IS NOT NULL)                    AS processed,
                COUNT(*) FILTER (WHERE failed_at    IS NOT NULL)                    AS dead_letter,
                COUNT(*) FILTER (WHERE processed_at IS NULL AND failed_at IS NULL)  AS pending
            FROM events_outbox
            WHERE tenant_id = :tenant_id
        """),
        {"tenant_id": tenant_id},
    )
    row = result.fetchone()
    return {
        "pending":     row.pending,
        "processed":   row.processed,
        "dead_letter": row.dead_letter,
    }


# ── Pipeline test ─────────────────────────────────────────────────────────────

@router.post("/test", summary="Injeta evento de teste no outbox")
async def test_pipeline(
    db: AsyncSession = Depends(get_db_session),
    admin=Depends(require_admin),
):
    """
    Insere um evento 'system.outbox_test' no outbox para validar o pipeline completo:

      1. INSERT INTO events_outbox  (esta chamada)
      2. COMMIT
      3. OutboxProcessor lê no próximo ciclo (~2s)
      4. EventBus.emit('system.outbox_test', payload) — sem handlers = log + processed_at
      5. Stats: pending → processed

    Use a UI de outbox para acompanhar o ciclo em tempo real (botão Atualizar).
    """
    triggered_by = admin.get("email", "admin") if isinstance(admin, dict) else getattr(admin, "email", str(admin))
    tenant_id    = admin.get("tenant_id")      if isinstance(admin, dict) else getattr(admin, "tenant_id", None)
    payload = {"triggered_by": triggered_by, "note": "pipeline test via admin UI"}

    await db.execute(
        text("""
            INSERT INTO events_outbox (event_name, payload, tenant_id)
            VALUES ('system.outbox_test', CAST(:payload AS jsonb), :tenant_id)
        """),
        {"payload": json.dumps(payload), "tenant_id": tenant_id},
    )
    await db.commit()
    logger.info("Admin: evento de teste 'system.outbox_test' inserido por %s (tenant=%s).", triggered_by, tenant_id)
    return {
        "detail": "Evento 'system.outbox_test' inserido no outbox.",
        "note":   "Aguarde ~2s e clique em Atualizar para ver o evento processado.",
    }


# ── Recent events (qualquer status) ──────────────────────────────────────────

@router.get("/recent", summary="Últimos eventos do outbox (qualquer status)")
async def list_recent(
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    admin=Depends(require_admin),
):
    """
    Lista os eventos mais recentes independente do status, filtrados pelo tenant do admin.
    Útil para acompanhar o ciclo completo: pending → processed (ou dead-letter).
    """
    tenant_id = admin.get("tenant_id") if isinstance(admin, dict) else getattr(admin, "tenant_id", None)
    result = await db.execute(
        text("""
            SELECT id, event_name, attempts, max_attempts, last_error,
                   created_at, processed_at, failed_at
            FROM   events_outbox
            WHERE  tenant_id = :tenant_id
            ORDER  BY created_at DESC
            LIMIT  :limit
        """),
        {"tenant_id": tenant_id, "limit": limit},
    )
    rows = result.fetchall()

    def status(r):
        if r.processed_at: return "processed"
        if r.failed_at:    return "dead-letter"
        return "pending"

    return {
        "total": len(rows),
        "events": [
            {
                "id":           r.id,
                "event_name":   r.event_name,
                "status":       status(r),
                "attempts":     r.attempts,
                "max_attempts": r.max_attempts,
                "last_error":   r.last_error,
                "created_at":   r.created_at.isoformat() if r.created_at else None,
                "processed_at": r.processed_at.isoformat() if r.processed_at else None,
                "failed_at":    r.failed_at.isoformat()    if r.failed_at    else None,
            }
            for r in rows
        ],
    }


# ── Dead-letter list ──────────────────────────────────────────────────────────

@router.get("/dead-letters", summary="Lista eventos dead-letter")
async def list_dead_letters(
    limit:  int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0,  ge=0),
    db: AsyncSession = Depends(get_db_session),
    admin=Depends(require_admin),
):
    """Lista eventos que esgotaram todas as tentativas de entrega, filtrados pelo tenant do admin."""
    tenant_id = admin.get("tenant_id") if isinstance(admin, dict) else getattr(admin, "tenant_id", None)
    result = await db.execute(
        text("""
            SELECT id, event_name, payload, attempts, max_attempts,
                   last_error, created_at, failed_at
            FROM   events_outbox
            WHERE  failed_at IS NOT NULL
              AND  tenant_id = :tenant_id
            ORDER  BY failed_at DESC
            LIMIT  :limit OFFSET :offset
        """),
        {"tenant_id": tenant_id, "limit": limit, "offset": offset},
    )
    rows = result.fetchall()

    return {
        "total": len(rows),
        "events": [
            {
                "id":           r.id,
                "event_name":   r.event_name,
                "payload":      r.payload,
                "attempts":     r.attempts,
                "max_attempts": r.max_attempts,
                "last_error":   r.last_error,
                "created_at":   r.created_at.isoformat() if r.created_at else None,
                "failed_at":    r.failed_at.isoformat()  if r.failed_at  else None,
            }
            for r in rows
        ],
    }


# ── Retry ─────────────────────────────────────────────────────────────────────

@router.post("/{event_id}/retry", summary="Retentar evento dead-letter")
async def retry_event(
    event_id: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db_session),
    admin=Depends(require_admin),
):
    """
    Reseta o evento para que o OutboxProcessor tente reentregá-lo.
    Zera attempts e failed_at — o evento volta para a fila de pendentes.
    """
    tenant_id = admin.get("tenant_id") if isinstance(admin, dict) else getattr(admin, "tenant_id", None)
    result = await db.execute(
        text("SELECT id FROM events_outbox WHERE id = :id AND tenant_id = :tenant_id AND failed_at IS NOT NULL"),
        {"id": event_id, "tenant_id": tenant_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Evento {event_id} não encontrado ou não é dead-letter.")

    await db.execute(
        text("""
            UPDATE events_outbox
            SET    attempts   = 0,
                   last_error = NULL,
                   failed_at  = NULL
            WHERE  id = :id AND tenant_id = :tenant_id
        """),
        {"id": event_id, "tenant_id": tenant_id},
    )
    await db.commit()
    logger.info("Admin: evento %s marcado para retry (tenant=%s).", event_id, tenant_id)
    return {"detail": f"Evento {event_id} recolocado na fila de pendentes."}


# ── Discard ───────────────────────────────────────────────────────────────────

@router.delete("/{event_id}", summary="Descartar evento dead-letter")
async def discard_event(
    event_id: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db_session),
    admin=Depends(require_admin),
):
    """
    Remove permanentemente um evento dead-letter do outbox.
    Use apenas quando o evento for realmente irrelevante para reprocessamento.
    """
    tenant_id = admin.get("tenant_id") if isinstance(admin, dict) else getattr(admin, "tenant_id", None)
    result = await db.execute(
        text("DELETE FROM events_outbox WHERE id = :id AND tenant_id = :tenant_id AND failed_at IS NOT NULL RETURNING id"),
        {"id": event_id, "tenant_id": tenant_id},
    )
    deleted = result.fetchone()
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Evento {event_id} não encontrado ou não é dead-letter.")

    await db.commit()
    logger.warning("Admin: evento %s descartado permanentemente do outbox (tenant=%s).", event_id, tenant_id)
    return {"detail": f"Evento {event_id} descartado."}
