"""
fake_extraction_worker.py
=========================
Implementação de simulação do ExtractionWorker.
Substitua por um worker concreto (ex: JiraExtractionWorker).

Comportamento:
  - Recebe 1 mensagem de extração
  - Simula latência de extração (0.3s)
  - Retorna FAKE_ITEMS_COUNT itens sintéticos
  → ExtractionWorker.process() publica cada item na transform_queue
"""
import time

from app.etl.workers.extraction_worker import ExtractionWorker

FAKE_ITEMS_COUNT = 20   # total de itens gerados por job fake


class FakeExtractionWorker(ExtractionWorker):
    """
    Simula a extração de dados sem conectar a nenhuma fonte real.
    Gera FAKE_ITEMS_COUNT itens sintéticos para exercitar o pipeline completo.
    """

    def extract(self, message: dict) -> list[dict]:
        time.sleep(0.3)   # simula latência de rede/API

        return [
            {
                "fake_id":     i,
                "field1":      f"extracted_value_{i}",
                "field2":      i * 10,
                "source":      "fake_integration",
                "source_type": message.get("type", "fake_full_sync"),
            }
            for i in range(FAKE_ITEMS_COUNT)
        ]
