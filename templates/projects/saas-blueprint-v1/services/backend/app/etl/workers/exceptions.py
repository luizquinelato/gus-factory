"""
exceptions.py
=============
Exceções tipadas para o pipeline ETL.

Uso nos workers concretos (subclasses de ProcessorWorker):

    def embed(self, message):
        config = get_ai_config(message["tenant_id"])
        if not config:
            raise ProcessorConfigError(
                "ai_integration_not_configured",
                "No active AI integration found for tenant",
            )
        try:
            call_embedding_api(config, message)
        except TimeoutError:
            raise ProcessorTransientError(
                "embedding_api_timeout",
                "Embedding API timed out after 30s",
            )

ProcessorConfigError  → falha de configuração → sem retry
ProcessorTransientError → falha operacional → com retry (base faz 3 tentativas)
"""


class ProcessorConfigError(Exception):
    """
    Falha de configuração — não deve ser re-tentada.
    O erro é registrado no error_log e o processamento do item é abortado.

    Exemplos:
      - AI integration não configurada
      - Schema mismatch no banco (coluna ausente)
      - API key inválida (4xx permanente)
    """
    def __init__(self, error_code: str, detail: str):
        super().__init__(detail)
        self.error_code = error_code
        self.detail     = detail


class ProcessorTransientError(Exception):
    """
    Falha operacional — pode ser re-tentada (até MAX_RETRIES vezes).
    Após esgotar as tentativas, é registrada no error_log.

    Exemplos:
      - Timeout de API externa
      - Rate limit temporário (429)
      - Falha de conexão com o banco
    """
    def __init__(self, error_code: str, detail: str):
        super().__init__(detail)
        self.error_code = error_code
        self.detail     = detail
