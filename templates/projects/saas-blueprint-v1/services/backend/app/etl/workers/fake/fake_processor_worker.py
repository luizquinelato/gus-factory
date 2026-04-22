"""
fake_processor_worker.py
========================
Implementação de simulação do ProcessorWorker.
Substitua por um worker concreto (ex: OpenAIProcessorWorker).

Demonstra TODOS os cenários possíveis de falha do processor:

  ai_enabled=True  (embed path) — 10 itens:
  ┌──────┬────────────────────────────────────┬─────────────────┐
  │ item │ error_code                         │ tipo            │
  ├──────┼────────────────────────────────────┼─────────────────┤
  │  0-2 │ (sucesso)                          │ —               │
  │  3-4 │ ai_integration_not_configured      │ config (no retry│
  │  5-6 │ embedding_api_timeout              │ transient       │
  │  7-8 │ embedding_api_rate_limit           │ transient       │
  │    9 │ embedding_api_invalid_response     │ config (no retry│
  └──────┴────────────────────────────────────┴─────────────────┘

  ai_enabled=False (load path) — 10 itens:
  ┌──────┬────────────────────────────────────┬─────────────────┐
  │ item │ error_code                         │ tipo            │
  ├──────┼────────────────────────────────────┼─────────────────┤
  │  0-6 │ (sucesso)                          │ —               │
  │  7-8 │ load_db_connection_failed          │ transient       │
  │    9 │ load_schema_mismatch               │ config (no retry│
  └──────┴────────────────────────────────────┴─────────────────┘
"""
import time

from app.etl.workers.processor_worker import ProcessorWorker
from app.etl.workers.exceptions import ProcessorConfigError, ProcessorTransientError

# ── scenario tables ───────────────────────────────────────────────────────────
# (error_code | None, detail | None, is_transient)

_EMBED_SCENARIOS = [
    (None, None, False),                                                                        # 0
    (None, None, False),                                                                        # 1
    (None, None, False),                                                                        # 2
    ("ai_integration_not_configured", "No active AI integration found for tenant",      False), # 3
    ("ai_integration_not_configured", "AI integration config missing: api_key is null", False), # 4
    ("embedding_api_timeout",         "Embedding API timed out after 30s",              True),  # 5
    ("embedding_api_timeout",         "Embedding API timed out after 30s",              True),  # 6
    ("embedding_api_rate_limit",      "Rate limit exceeded: 60 req/min",                True),  # 7
    ("embedding_api_rate_limit",      "Rate limit exceeded: 60 req/min",                True),  # 8
    ("embedding_api_invalid_response","Expected float[] from API, got null",            False), # 9
]

_LOAD_SCENARIOS = [
    (None, None, False),                                                                              # 0
    (None, None, False),                                                                              # 1
    (None, None, False),                                                                              # 2
    (None, None, False),                                                                              # 3
    (None, None, False),                                                                              # 4
    (None, None, False),                                                                              # 5
    (None, None, False),                                                                              # 6
    ("load_db_connection_failed", "Could not acquire DB connection after 3 retries",    True),        # 7
    ("load_db_connection_failed", "Could not acquire DB connection after 3 retries",    True),        # 8
    ("load_schema_mismatch",      "Column 'embedding_vector' not found in target table",False),       # 9
]


class FakeProcessorWorker(ProcessorWorker):
    """
    Simula todos os cenários de falha do processor usando item_index % 10
    para selecionar o cenário. Não conecta a nenhum serviço real.
    """

    def embed(self, message: dict) -> None:
        time.sleep(0.2)   # simula latência de chamada à API de embedding
        code, detail, transient = _EMBED_SCENARIOS[message.get("item_index", 0) % 10]
        if code:
            if transient:
                raise ProcessorTransientError(code, detail)
            raise ProcessorConfigError(code, detail)

    def load(self, message: dict) -> None:
        time.sleep(0.1)   # simula latência de escrita no banco
        code, detail, transient = _LOAD_SCENARIOS[message.get("item_index", 0) % 10]
        if code:
            if transient:
                raise ProcessorTransientError(code, detail)
            raise ProcessorConfigError(code, detail)
