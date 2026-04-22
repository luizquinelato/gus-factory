"""
fake_job.py
===========
Publica 1 mensagem de extração fake na 'extraction_queue' para testar
o pipeline completo sem precisar de uma integração real.

Fluxo esperado:
  1 msg extraction → ExtractionWorker → 20 msgs transform
  20 msgs transform → TransformWorker → 20 msgs processor
    (10 com ai_enabled=True, 10 com ai_enabled=False)
  20 msgs processor → ProcessorWorker →
    10 ai=True:  3 success, 2 not_configured, 2 timeout, 2 rate_limit, 1 invalid_response
    10 ai=False: 7 success, 2 db_conn_failed, 1 schema_mismatch
"""
import time
import uuid
import logging

from app.etl.queue_manager import QueueManager

logger = logging.getLogger(__name__)


def dispatch_fake_job(tenant_id: int = 1) -> dict:
    """
    Publica 1 mensagem de extração fake.
    Retorna os metadados do job criado.
    """
    job_id  = int(time.time() * 1000) % 1_000_000   # pseudo-id legível
    run_id  = str(uuid.uuid4())[:8]

    message = {
        "tenant_id":  tenant_id,
        "job_id":     job_id,
        "run_id":     run_id,
        "type":       "fake_full_sync",
        "ai_enabled": True,    # stamped at job start — TransformWorker overrides per item
        "step":       "extraction",
        "source":     "fake_integration",
        "created_at": time.time(),
    }

    QueueManager.get_instance().publish("extraction_queue", message)

    logger.info(
        "FakeJob dispatched: job_id=%d run_id=%s tenant_id=%d",
        job_id, run_id, tenant_id,
    )

    return {
        "job_id":    job_id,
        "run_id":    run_id,
        "tenant_id": tenant_id,
        "message":   "Fake job dispatched to extraction_queue",
        "expected": {
            "extraction_messages": 1,
            "transform_messages":  20,
            "processor_messages":  20,
            "processor_ai_true":   10,
            "processor_ai_false":  10,
        },
    }
