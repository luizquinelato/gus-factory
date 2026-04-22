"""
worker_manager.py
=================
Singleton que gerencia os três pools de workers:
  - extraction_workers  (lista de ExtractionWorker)
  - transform_workers   (lista de TransformWorker)
  - processor_workers   (lista de ProcessorWorker)

Operações suportadas:
  start / stop / kill / restart — global, por tipo ou por worker_id
  scale(worker_type, delta)     — adiciona / remove workers do pool
  set_count(worker_type, n)     — ajusta pool para exatamente N workers
  status()                      — estado completo de todos os pools
"""
import logging
from typing import Literal, Optional

from app.core.config import get_settings

# ── Fake workers (blueprint default — substitua pelos workers da sua integração) ──
# Exemplo de swap para produção:
#   from myapp.workers.jira_extraction_worker import JiraExtractionWorker as ExtractionImpl
#   from myapp.workers.jira_transform_worker  import JiraTransformWorker  as TransformImpl
#   from myapp.workers.openai_processor_worker import OpenAIProcessorWorker as ProcessorImpl
from app.etl.workers.fake.fake_extraction_worker import FakeExtractionWorker as ExtractionImpl
from app.etl.workers.fake.fake_transform_worker  import FakeTransformWorker  as TransformImpl
from app.etl.workers.fake.fake_processor_worker  import FakeProcessorWorker  as ProcessorImpl

logger = logging.getLogger(__name__)

WorkerType = Literal["extraction", "transform", "processor"]

DEFAULT_COUNTS = {"extraction": 2, "transform": 2, "processor": 3}


class WorkerManager:
    _instance: Optional["WorkerManager"] = None

    def __init__(self):
        self.settings   = get_settings()
        self.error_log: list[dict] = []   # shared with all ProcessorWorkers
        self._pools: dict[str, list] = {
            "extraction": [],
            "transform":  [],
            "processor":  [],
        }

    @classmethod
    def get_instance(cls) -> "WorkerManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── startup ───────────────────────────────────────────────────────────────

    def start_all(self, counts: Optional[dict] = None):
        counts = counts or DEFAULT_COUNTS
        for wtype, n in counts.items():
            self.set_count(wtype, n)
        logger.info("WorkerManager: all pools started %s", counts)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self, worker_type: Optional[WorkerType] = None):
        for pool_type, pool in self._iter_pools(worker_type):
            for w in pool:
                if not w.is_alive:
                    w.start()

    def stop(self, worker_type: Optional[WorkerType] = None):
        for pool_type, pool in self._iter_pools(worker_type):
            for w in pool:
                w.stop()

    def kill(self, worker_type: Optional[WorkerType] = None):
        for pool_type, pool in self._iter_pools(worker_type):
            for w in pool:
                w.kill()

    def restart(self, worker_type: Optional[WorkerType] = None):
        """
        Para os workers existentes e cria um pool completamente novo.
        Não reutiliza threads antigas (que podem ainda estar no meio do stop),
        garantindo que o status volta a 'alive' imediatamente.
        """
        types = [worker_type] if worker_type else list(self._pools.keys())
        for pool_type in types:
            old_pool = self._pools[pool_type]
            count    = len(old_pool)
            # Sinaliza parada aos workers antigos (eles morrem sozinhos)
            for w in old_pool:
                w.stop()
            # Cria pool fresco com workers novos
            new_pool = []
            for i in range(count):
                w = self._create_worker(pool_type, i)
                w.start()
                new_pool.append(w)
            self._pools[pool_type] = new_pool
            logger.info("WorkerManager: restarted %s pool (%d workers)", pool_type, count)

    # ── scaling ───────────────────────────────────────────────────────────────

    def scale(self, worker_type: WorkerType, delta: int):
        """delta > 0 → adiciona workers; delta < 0 → remove do final."""
        pool    = self._pools[worker_type]
        current = len(pool)
        target  = max(0, current + delta)
        self.set_count(worker_type, target)

    def set_count(self, worker_type: WorkerType, count: int):
        pool    = self._pools[worker_type]
        current = len(pool)

        if count > current:
            for i in range(current, count):
                w = self._create_worker(worker_type, i)
                w.start()
                pool.append(w)
                logger.info("WorkerManager: added %s worker id=%d", worker_type, i)
        elif count < current:
            to_remove = pool[count:]
            self._pools[worker_type] = pool[:count]
            for w in to_remove:
                w.stop()
                logger.info("WorkerManager: removed %s worker id=%d", worker_type, w.worker_id)

    # ── status ────────────────────────────────────────────────────────────────

    def status(self, worker_type: Optional[WorkerType] = None) -> dict:
        result = {}
        for wt, pool in self._iter_pools(worker_type):
            result[wt] = {
                "count":   len(pool),
                "alive":   sum(1 for w in pool if w.is_alive),
                "workers": [w.get_status() for w in pool],
            }
        return result

    def get_error_log(self, limit: int = 100) -> list[dict]:
        return self.error_log[-limit:]

    def clear_error_log(self):
        self.error_log.clear()

    # ── internals ─────────────────────────────────────────────────────────────

    def _create_worker(self, worker_type: WorkerType, worker_id: int):
        if worker_type == "extraction":
            return ExtractionImpl(worker_id, self.settings)
        if worker_type == "transform":
            return TransformImpl(worker_id, self.settings)
        if worker_type == "processor":
            return ProcessorImpl(worker_id, self.settings, self.error_log)
        raise ValueError(f"Unknown worker_type: {worker_type}")

    def _iter_pools(self, worker_type: Optional[WorkerType]):
        if worker_type:
            yield worker_type, self._pools[worker_type]
        else:
            yield from self._pools.items()
