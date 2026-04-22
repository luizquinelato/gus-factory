"""
processor_worker.py
===================
Worker genérico de processamento — base extensível para embed ou load.

Fluxo:
  1. Recebe mensagem da 'processor_queue'
  2. Lê message["ai_enabled"] (stamped no publish, imutável)
  3. Se True  → chama embed(message)  ← subclasse implementa
  4. Se False → chama load(message)   ← subclasse implementa
  5. Exceções typed definem o comportamento:
       ProcessorConfigError   → sem retry — registra no error_log
       ProcessorTransientError → com retry (MAX_RETRIES) — registra se esgotar

Exemplo de extensão:
    class MyProcessorWorker(ProcessorWorker):
        def embed(self, message: dict) -> None:
            config = get_ai_integration(message["tenant_id"])
            if not config:
                raise ProcessorConfigError(
                    "ai_integration_not_configured",
                    "No active AI integration for tenant",
                )
            vector = openai_embed(config, message["transformed_data"])
            save_embedding(message["entity_id"], vector)

        def load(self, message: dict) -> None:
            db_upsert(message["table_name"], message["transformed_data"])
"""
import logging
import time
from abc import abstractmethod

from app.etl.workers.base_worker import BaseWorker
from app.etl.workers.exceptions import ProcessorConfigError, ProcessorTransientError

logger = logging.getLogger(__name__)

MAX_RETRIES   = 3
RETRY_DELAY_S = 0.5


class ProcessorWorker(BaseWorker):
    """
    Base genérica para workers de processamento.
    Subclasses devem implementar embed() e load().
    O roteamento entre eles é feito automaticamente por message["ai_enabled"].
    """

    def __init__(self, worker_id: int, settings, error_log: list):
        super().__init__("processor_queue", worker_id, settings)
        self._error_log = error_log   # shared list — injetado pelo WorkerManager

    # ── pipeline orchestration (não sobrescrever) ─────────────────────────────

    def process(self, message: dict) -> None:
        ai_enabled = message.get("ai_enabled", False)
        item_index = message.get("item_index", 0)
        job_id     = message.get("job_id", 0)

        logger.info(
            "ProcessorWorker-%d: processing job=%s item=%d ai_enabled=%s",
            self.worker_id, job_id, item_index, ai_enabled,
        )

        try:
            if ai_enabled:
                self.embed(message)
                logger.info("ProcessorWorker-%d: ✅ embedded item=%d job=%d", self.worker_id, item_index, job_id)
            else:
                self.load(message)
                logger.info("ProcessorWorker-%d: ✅ loaded item=%d job=%d", self.worker_id, item_index, job_id)

        except ProcessorConfigError as exc:
            self._record_error(message, exc.error_code, exc.detail, transient=False)

        except ProcessorTransientError as exc:
            self._handle_transient(message, exc)

    def _handle_transient(self, message: dict, exc: ProcessorTransientError) -> None:
        item_index = message.get("item_index", 0)
        for attempt in range(1, MAX_RETRIES + 1):
            time.sleep(RETRY_DELAY_S)
            logger.warning(
                "ProcessorWorker-%d: ⚠ transient error attempt %d/%d [%s] item=%d",
                self.worker_id, attempt, MAX_RETRIES, exc.error_code, item_index,
            )
            try:
                if message.get("ai_enabled"):
                    self.embed(message)
                else:
                    self.load(message)
                logger.info("ProcessorWorker-%d: ✅ recovered on attempt %d item=%d", self.worker_id, attempt, item_index)
                return
            except ProcessorTransientError as retry_exc:
                exc = retry_exc
            except ProcessorConfigError as config_exc:
                self._record_error(message, config_exc.error_code, config_exc.detail, transient=False)
                return

        self._record_error(message, exc.error_code, f"{exc.detail} ({MAX_RETRIES} retries exhausted)", transient=True)

    def _record_error(self, message: dict, error_code: str, detail: str, transient: bool) -> None:
        entry = {
            "tenant_id":    message.get("tenant_id", 1),
            "job_id":       message.get("job_id", 0),
            "worker_type":  "processor",
            "error_code":   error_code,
            "error_detail": detail,
            "entity_id":    message.get("entity_id", str(message.get("item_index", 0))),
            "item_index":   message.get("item_index", 0),
            "ai_enabled":   message.get("ai_enabled", False),
            "is_transient": transient,
            "created_at":   time.time(),
        }
        self._error_log.append(entry)
        logger.error(
            "ProcessorWorker-%d: ❌ FAILED item=%d [%s] ai=%s — %s",
            self.worker_id, message.get("item_index"), error_code, message.get("ai_enabled"), detail,
        )

    # ── extension points ──────────────────────────────────────────────────────

    @abstractmethod
    def embed(self, message: dict) -> None:
        """
        Gera e persiste embedding vetorial para o item.
        Lança ProcessorConfigError para falhas de configuração (sem retry).
        Lança ProcessorTransientError para falhas operacionais (com retry).
        """

    @abstractmethod
    def load(self, message: dict) -> None:
        """
        Grava os dados transformados diretamente no banco (sem embedding).
        Lança ProcessorConfigError para falhas de configuração (sem retry).
        Lança ProcessorTransientError para falhas operacionais (com retry).
        """
