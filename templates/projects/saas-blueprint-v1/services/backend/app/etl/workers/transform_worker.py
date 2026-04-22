"""
transform_worker.py
===================
Worker genérico de transformação — base extensível.

Fluxo:
  1. Recebe mensagem da 'transform_queue'
  2. Chama transform(message) → dict  ← subclasse implementa
  3. Publica resultado na 'processor_queue' com ai_enabled do job
     (ou _ai_enabled do resultado para override em casos específicos)

Extension point _ai_enabled:
  Se transform() retornar um dict com a chave '_ai_enabled',
  esse valor sobrescreve o ai_enabled do job para esta mensagem.
  Usado pelo FakeTransformWorker para demonstrar os dois caminhos.
  Remova o override em workers de produção.

Exemplo de extensão:
    class JiraTransformWorker(TransformWorker):
        def transform(self, message: dict) -> dict:
            raw = message["raw_data"]
            return {
                "issue_key":   raw["key"],
                "title":       raw["fields"]["summary"],
                "status":      raw["fields"]["status"]["name"],
                "assignee":    raw["fields"].get("assignee", {}).get("displayName"),
                "story_points": raw["fields"].get("story_points", 0),
            }
"""
import logging
from abc import abstractmethod

from app.etl.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class TransformWorker(BaseWorker):
    """
    Base genérica para workers de transformação.
    Subclasses devem implementar transform() — normaliza o raw_data para o domínio.
    """

    def __init__(self, worker_id: int, settings):
        super().__init__("transform_queue", worker_id, settings)

    # ── pipeline orchestration (não sobrescrever) ─────────────────────────────

    def process(self, message: dict) -> None:
        from app.etl.queue_manager import QueueManager

        job_id     = message.get("job_id", 0)
        tenant_id  = message.get("tenant_id", 1)
        item_index = message.get("item_index", 0)

        logger.info(
            "TransformWorker-%d: transforming job=%s item=%d",
            self.worker_id, job_id, item_index,
        )

        transformed = self.transform(message)

        # _ai_enabled in result allows per-item override (used by FakeTransformWorker)
        # In production workers: just don't include _ai_enabled in transform() result
        ai_enabled = transformed.pop("_ai_enabled", message.get("ai_enabled", False))

        QueueManager.get_instance().publish("processor_queue", {
            "tenant_id":        tenant_id,
            "job_id":           job_id,
            "type":             "embed_chunk" if ai_enabled else "load_direct",
            "ai_enabled":       ai_enabled,
            "item_index":       item_index,
            "step":             "processor",
            "entity_id":        message.get("entity_id", f"entity_{item_index}"),
            "table_name":       message.get("table_name", "items"),
            "transformed_data": transformed,
        })

        logger.info(
            "TransformWorker-%d: job=%s item=%d ai_enabled=%s → processor_queue",
            self.worker_id, job_id, item_index, ai_enabled,
        )

    # ── extension point ───────────────────────────────────────────────────────

    @abstractmethod
    def transform(self, message: dict) -> dict:
        """
        Implementar em subclasses.
        Recebe a mensagem com message["raw_data"] e retorna os dados normalizados.
        Pode incluir '_ai_enabled' (bool) para sobrescrever o ai_enabled do job.
        """
