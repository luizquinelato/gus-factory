"""
fake_transform_worker.py
========================
Implementação de simulação do TransformWorker.
Substitua por um worker concreto (ex: JiraTransformWorker).

Comportamento:
  - Simula latência de transformação (0.15s)
  - Normaliza os dados sintéticos do FakeExtractionWorker
  - Usa _ai_enabled para demonstrar os dois caminhos do ProcessorWorker:
      item_index < AI_SPLIT_AT  → ai_enabled=True  (embedding path)
      item_index >= AI_SPLIT_AT → ai_enabled=False (load path)

Nota: em workers de produção NÃO inclua _ai_enabled no retorno de transform().
O ai_enabled é propagado do job e sobrescrito apenas em casos excepcionais.
"""
import time

from app.etl.workers.transform_worker import TransformWorker

AI_SPLIT_AT = 10   # primeiros N itens → embed, restantes → load (só no fake)


class FakeTransformWorker(TransformWorker):
    """
    Simula a transformação de dados sem lógica de domínio real.
    Divide os itens em embedding/load para demonstrar ambos os caminhos.
    """

    def transform(self, message: dict) -> dict:
        time.sleep(0.15)   # simula latência de processamento

        raw        = message.get("raw_data", {})
        item_index = message.get("item_index", 0)

        return {
            # campos normalizados (domínio genérico)
            "entity_key":   f"FAKE-{item_index:03d}",
            "title":        raw.get("field1", f"Item {item_index}"),
            "value":        raw.get("field2", 0),
            "normalized":   True,
            "source":       raw.get("source", "fake"),

            # ── demo only ──────────────────────────────────────────────────────
            # _ai_enabled sobrescreve o ai_enabled do job para este item.
            # Permite demonstrar os dois caminhos sem precisar de dois jobs.
            # REMOVA esta chave em workers de produção.
            "_ai_enabled":  item_index < AI_SPLIT_AT,
        }
