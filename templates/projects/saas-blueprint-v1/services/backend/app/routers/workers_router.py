"""
workers_router.py
=================
GET  /api/v1/workers                              → status de todos os pools
GET  /api/v1/workers/{worker_type}                → status de um pool
POST /api/v1/workers/start                        → start global
POST /api/v1/workers/stop                         → stop global
POST /api/v1/workers/restart                      → restart global
POST /api/v1/workers/{worker_type}/start          → start de um tipo
POST /api/v1/workers/{worker_type}/stop           → stop de um tipo
POST /api/v1/workers/{worker_type}/restart        → restart de um tipo
POST /api/v1/workers/{worker_type}/scale          → body: {delta: ±N} | {count: N}
GET  /api/v1/workers/errors                       → log de erros do processor
DELETE /api/v1/workers/errors                     → limpa o log de erros
POST /api/v1/workers/jobs/fake                    → dispara fake job para testes
"""
from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from app.dependencies.auth import require_admin
from app.etl.worker_manager import WorkerManager
from app.etl.fake_job import dispatch_fake_job

router = APIRouter(prefix="/workers", tags=["ETL — Workers"])

WorkerType = Literal["extraction", "transform", "processor"]


# ── status ────────────────────────────────────────────────────────────────────

@router.get("", summary="Get status of all worker pools")
async def get_all_workers(_user=Depends(require_admin)):
    return WorkerManager.get_instance().status()


@router.get("/errors", summary="Get processor error log")
async def get_error_log(limit: int = 100, _user=Depends(require_admin)):
    return {
        "errors": WorkerManager.get_instance().get_error_log(limit),
        "total":  len(WorkerManager.get_instance().error_log),
    }


@router.get("/{worker_type}", summary="Get status of a specific worker pool")
async def get_worker_pool(worker_type: WorkerType, _user=Depends(require_admin)):
    return WorkerManager.get_instance().status(worker_type)


# ── global lifecycle ──────────────────────────────────────────────────────────

@router.post("/start", summary="Start all worker pools")
async def start_all(_user=Depends(require_admin)):
    WorkerManager.get_instance().start()
    return {"message": "All workers started"}


@router.post("/stop", summary="Stop all worker pools (graceful)")
async def stop_all(_user=Depends(require_admin)):
    WorkerManager.get_instance().stop()
    return {"message": "All workers stopping (graceful)"}


@router.post("/restart", summary="Restart all worker pools")
async def restart_all(_user=Depends(require_admin)):
    WorkerManager.get_instance().restart()
    return {"message": "All workers restarting"}


# ── per-type lifecycle ────────────────────────────────────────────────────────

@router.post("/{worker_type}/start", summary="Start a specific worker type")
async def start_pool(worker_type: WorkerType, _user=Depends(require_admin)):
    WorkerManager.get_instance().start(worker_type)
    return {"worker_type": worker_type, "message": f"{worker_type} workers started"}


@router.post("/{worker_type}/stop", summary="Stop a specific worker type (graceful)")
async def stop_pool(worker_type: WorkerType, _user=Depends(require_admin)):
    WorkerManager.get_instance().stop(worker_type)
    return {"worker_type": worker_type, "message": f"{worker_type} workers stopping"}


@router.post("/{worker_type}/restart", summary="Restart a specific worker type")
async def restart_pool(worker_type: WorkerType, _user=Depends(require_admin)):
    WorkerManager.get_instance().restart(worker_type)
    return {"worker_type": worker_type, "message": f"{worker_type} workers restarting"}


# ── scaling ───────────────────────────────────────────────────────────────────

@router.post("/{worker_type}/scale", summary="Scale a worker pool (delta or absolute count)")
async def scale_pool(
    worker_type: WorkerType,
    body: dict = Body(..., examples=[{"delta": 1}, {"count": 5}]),
    _user=Depends(require_admin),
):
    wm = WorkerManager.get_instance()
    if "count" in body:
        count = int(body["count"])
        if count < 0:
            raise HTTPException(status_code=422, detail="count must be >= 0")
        wm.set_count(worker_type, count)
        return {"worker_type": worker_type, "count": count, "message": "Pool resized"}
    elif "delta" in body:
        delta = int(body["delta"])
        wm.scale(worker_type, delta)
        new_count = len(wm._pools[worker_type])
        return {"worker_type": worker_type, "delta": delta, "new_count": new_count}
    raise HTTPException(status_code=422, detail="Body must contain 'count' or 'delta'")


# ── error log management ──────────────────────────────────────────────────────

@router.delete("/errors", summary="Clear the processor error log")
async def clear_errors(_user=Depends(require_admin)):
    WorkerManager.get_instance().clear_error_log()
    return {"message": "Error log cleared"}


# ── fake job ──────────────────────────────────────────────────────────────────

@router.post("/jobs/fake", summary="Dispatch a fake ETL job for pipeline testing")
async def fake_job(tenant_id: int = 1, _user=Depends(require_admin)):
    """
    Dispara 1 mensagem na extraction_queue.
    O pipeline completo irá gerar 20 transform + 20 processor messages,
    simulando todos os cenários de sucesso e falha do ProcessorWorker.
    """
    return dispatch_fake_job(tenant_id)
