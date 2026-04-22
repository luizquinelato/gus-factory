"""
queues_router.py
================
GET  /api/v1/queues                      → lista todas as filas com stats
GET  /api/v1/queues/{queue_type}         → stats de uma fila
GET  /api/v1/queues/{queue_type}/depth   → só a profundidade (mensagens prontas)
POST /api/v1/queues/{queue_type}/purge   → apaga todas as mensagens

Requer: usuário autenticado com permissão ETL (admin ou page_key=etl_settings).
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.auth import require_admin
from app.etl.queue_manager import QueueManager

router = APIRouter(prefix="/queues", tags=["ETL — Queues"])

QueueType = Literal["extraction", "transform", "processor"]

QUEUE_MAP = {
    "extraction": "extraction_queue",
    "transform":  "transform_queue",
    "processor":  "processor_queue",
}


def _queue_name(queue_type: QueueType) -> str:
    if queue_type not in QUEUE_MAP:
        raise HTTPException(status_code=422, detail=f"Invalid queue_type: {queue_type}")
    return QUEUE_MAP[queue_type]


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("", summary="List all queues with stats")
async def list_queues(_user=Depends(require_admin)):
    qm = QueueManager.get_instance()
    return {"queues": qm.get_all_queue_stats()}


@router.get("/{queue_type}", summary="Get stats for a single queue")
async def get_queue(queue_type: QueueType, _user=Depends(require_admin)):
    qm   = QueueManager.get_instance()
    name = _queue_name(queue_type)
    return qm.get_queue_stats(name)


@router.get("/{queue_type}/depth", summary="Get queue depth (ready messages only)")
async def get_queue_depth(queue_type: QueueType, _user=Depends(require_admin)):
    qm   = QueueManager.get_instance()
    name = _queue_name(queue_type)
    return {"queue": queue_type, "depth": qm.get_depth(name)}


@router.post("/{queue_type}/purge", summary="Purge all messages from a queue")
async def purge_queue(queue_type: QueueType, _user=Depends(require_admin)):
    """
    ⚠️ Irreversível — remove todas as mensagens da fila.
    O frontend deve exibir confirmação antes de chamar este endpoint.
    """
    qm      = QueueManager.get_instance()
    name    = _queue_name(queue_type)
    depth   = qm.get_depth(name)
    purged  = qm.purge_queue(name)
    return {
        "queue":          queue_type,
        "messages_found": depth,
        "messages_purged": purged,
        "message": f"Queue '{queue_type}' purged successfully",
    }
