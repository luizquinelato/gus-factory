<!-- blueprint: db_changes=false seed_data=false -->
# 11. Camada de ETL (Extraction, Transform, Load)

Este documento detalha a arquitetura da camada de ETL, ativa quando `{{ ENABLE_ETL }} = true`.

## 🔄 1. Arquitetura de Filas e Workers

O sistema utiliza o `{{ QUEUE_LAYER }}` (ex: RabbitMQ) para orquestrar o fluxo de dados em 3 estágios isolados:

1. **Extraction Queue**: Recebe jobs para buscar dados brutos de APIs externas (ex: notas fiscais, extratos bancários).
2. **Transform Queue**: Processa os dados brutos, limpa, normaliza e salva nas tabelas de negócio.
3. **Embedding Queue** (se `{{ ENABLE_AI_LAYER }} = true`): Gera vetores dos dados transformados e salva no `{{ EMBEDDING_DB }}`.

## ⚙️ 2. Configuração de Workers e Buffer

A quantidade de workers e o tamanho do lote (batch/buffer) **não devem ser hardcoded**. Eles devem ser lidos da tabela `system_settings` para permitir ajuste fino em produção sem deploy.

```json
// Exemplo de configuração na tabela system_settings
[
  {
    "setting_key": "extraction_workers_count",
    "setting_value": "5"
  },
  {
    "setting_key": "etl_batch_size",
    "setting_value": "100"
  }
]
```

O `WorkerManager` é responsável por ler essas configurações e instanciar a quantidade correta de processos. O `prefetch_count` do RabbitMQ deve ser configurado com base no `batch_size` para otimizar o consumo de memória.

## 📊 3. Worker Status Manager

Para evitar herança complexa, utilize o padrão de Composição com um `WorkerStatusManager`. Ele é injetado nos workers e é responsável por:

1. Atualizar o status do job no banco de dados (tabela `etl_jobs`).
2. Disparar eventos via WebSocket para o frontend atualizar a UI em tempo real.

```python
# services/backend/app/etl/workers/status_manager.py
class WorkerStatusManager:
    def __init__(self, db_session, websocket_manager):
        self.db = db_session
        self.ws = websocket_manager

    def update_status(self, job_id: int, status: str, progress: int = 0):
        # Atualiza no banco
        job = self.db.query(EtlJob).filter(EtlJob.id == job_id).first()
        if job:
            job.status = status
            job.progress = progress
            self.db.commit()
            
        # Notifica o frontend
        self.ws.broadcast_to_tenant(
            tenant_id=job.tenant_id,
            message={"type": "ETL_STATUS", "job_id": job_id, "status": status, "progress": progress}
        )
```

## 🔑 4. Frontend ETL — Autenticação e Deep Link

O frontend ETL (porta `3344` prod / `3345` dev) não tem login próprio. Todo acesso é feito via **One-Time Token (OTT)** gerado pelo backend após autenticação no frontend principal.

### Fluxo de acesso direto a uma rota do ETL

```
Usuário abre http://localhost:3344/pipelines  (sem sessão)
      │
      ▼ OttBootstrap detecta: sem ?ott, sem token
sessionStorage.set('etl_return_path', '/pipelines')
window.location → http://localhost:5177/login?etl=1
      │
      ▼ Usuário loga
POST /api/v1/auth/ott → { ott, etl_url: 'http://localhost:3344' }
window.location → http://localhost:3344/?ott=<uuid>
      │
      ▼ OttBootstrap no ETL
replaceState('/') → OTT removido da URL
POST /auth/exchange-ott → sessão estabelecida
sessionStorage.get('etl_return_path') → '/pipelines'
useLayoutEffect → navigate('/pipelines')
      │
      ▼ URL final (sem flash de tela)
http://localhost:3344/pipelines  ✓
```

### Regras do mecanismo

- **`?etl=1`** é o único parâmetro passado ao login — sem URL do ETL ou porta expostas
- O path desejado fica no `sessionStorage` do próprio ETL (origin isolado por porta)
- O OTT é removido da URL pelo `window.history.replaceState` antes do primeiro paint
- A navegação interna usa `useLayoutEffect` (antes do paint) → zero flash de tela
- Em caso de 401 durante sessão ativa, o `apiClient` do ETL repete o mesmo fluxo, preservando o path atual no `sessionStorage`

> Ver `05-security-auth.md` seção 7 para os detalhes dos endpoints e propriedades de segurança do OTT.
> Ver `07-frontend-patterns.md` seção 13 para o código completo do `OttBootstrap`.
