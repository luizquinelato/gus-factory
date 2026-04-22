"""
extraction_worker.py
====================
Worker genérico de extração — base extensível para integrações específicas.

Fluxo:
  1. Recebe mensagem da 'extraction_queue'
  2. Chama extract(message) → list[dict]  ← subclasse implementa
  3. Para cada item retornado, publica uma mensagem na 'transform_queue'
     preservando tenant_id, job_id, ai_enabled e adicionando item_index

Exemplo de extensão:
    class JiraExtractionWorker(ExtractionWorker):
        def extract(self, message: dict) -> list[dict]:
            jira = JiraClient(message["integration_config"])
            return jira.fetch_issues(project=message["project_key"])

    class GitHubExtractionWorker(ExtractionWorker):
        def extract(self, message: dict) -> list[dict]:
            gh = GitHubClient(message["token"])
            return gh.list_pull_requests(repo=message["repo"])
"""
import logging
from abc import abstractmethod

from app.etl.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class ExtractionWorker(BaseWorker):
    """
    Base genérica para workers de extração.
    Subclasses devem implementar extract() — retorna lista de itens brutos.
    """

    def __init__(self, worker_id: int, settings):
        super().__init__("extraction_queue", worker_id, settings)

    # ── pipeline orchestration (não sobrescrever) ─────────────────────────────

    def process(self, message: dict) -> None:
        from app.etl.queue_manager import QueueManager

        job_id     = message.get("job_id", 0)
        tenant_id  = message.get("tenant_id", 1)
        ai_enabled = message.get("ai_enabled", False)

        logger.info(
            "ExtractionWorker-%d: starting extraction job=%s tenant=%s ai_enabled=%s",
            self.worker_id, job_id, tenant_id, ai_enabled,
        )

        items = self.extract(message)

        qm = QueueManager.get_instance()
        for i, raw_item in enumerate(items):
            qm.publish("transform_queue", {
                "tenant_id":  tenant_id,
                "job_id":     job_id,
                "type":       "transform_item",
                "ai_enabled": ai_enabled,   # stamped at job start — propagated as-is
                "item_index": i,
                "step":       "transform",
                "raw_data":   raw_item,
            })

        logger.info(
            "ExtractionWorker-%d: job=%s — extracted %d items → transform_queue",
            self.worker_id, job_id, len(items),
        )

    # ── extension point ───────────────────────────────────────────────────────

    @abstractmethod
    def extract(self, message: dict) -> list[dict]:
        """
        Implementar em subclasses.
        Retorna lista de dicts com os dados brutos extraídos da fonte.
        Cada item vira uma mensagem independente na transform_queue.
        """
