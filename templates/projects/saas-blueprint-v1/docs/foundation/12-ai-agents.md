<!-- blueprint: db_changes=false seed_data=false -->
# 12. Camada de IA e Agentes (LangGraph)

Este documento detalha a arquitetura da camada de Inteligência Artificial, ativa quando `{{ ENABLE_AI_LAYER }} = true`. O foco é em eficiência, performance e capacidade de análise profunda.

## 🧠 1. Configuração de Modelos via JSON (Tabela integrations)

As credenciais e configurações dos modelos de IA **não ficam no `.env`** (exceto chaves master). Elas residem na tabela `integrations`, permitindo múltiplos provedores e fallback automático.

```json
// Schema da tabela integrations para IA
{
  "provider": "OpenAI", // "Anthropic" | "Local Embeddings"
  "type": "AI", // "Embedding"
  "settings": {
    "model": "{{ AI_MODEL }}",
    "model_config": {
      "temperature": 0.3,
      "max_tokens": 1000
    },
    "cost_config": {
      "max_monthly_cost": 100,
      "alert_threshold": 0.8
    }
  }
}
```

## 🔀 2. Hybrid Provider Manager

Um gerenciador central (`HybridProviderManager`) lê as integrações ativas do tenant e inicializa os clientes corretos. Se o provedor principal falhar (ex: rate limit), ele roteia automaticamente para o `fallback_integration_id` configurado no banco.

```python
# services/backend/app/ai/hybrid_provider.py
class HybridProviderManager:
    def __init__(self, db_session, tenant_id: int):
        self.db = db_session
        self.tenant_id = tenant_id
        self.active_provider = self._load_provider()

    def _load_provider(self):
        # Busca integração ativa do tenant
        integration = self.db.query(Integration).filter(
            Integration.tenant_id == self.tenant_id,
            Integration.type == "AI",
            Integration.active == True
        ).first()
        
        if not integration:
            raise ValueError("Nenhum provedor de IA configurado para este tenant.")
            
        return self._initialize_client(integration)

    def generate_response(self, prompt: str):
        try:
            return self.active_provider.generate(prompt)
        except RateLimitError:
            # Lógica de fallback automático
            fallback = self._load_fallback_provider()
            return fallback.generate(prompt)
```

## 🕸️ 3. Arquitetura Multi-Agente com LangGraph

Para análises profundas (ex: forecasting financeiro, análise de vendas), utilize uma arquitetura baseada em grafos (LangGraph) com agentes especializados, ao invés de um único prompt gigante.

### Estrutura Recomendada do Grafo:

A arquitetura multi-agente é definida pela variável `{{ AI_AGENTS }}`. O padrão inclui:

1. **Agente Orquestrador (Router)**: Recebe a query do usuário, analisa a intenção e decide qual fluxo seguir.
2. **Agente de Dados (Retriever)**: Especialista em buscar dados estruturados no PostgreSQL (via SQL gerado ou APIs internas) e dados não estruturados no `{{ EMBEDDING_DB }}`.
3. **Agente Analista (Analyzer)**: Recebe os dados brutos e aplica lógica de negócio (ex: cálculo de margem, projeção de fluxo de caixa).
4. **Agente Sintetizador (Synthesizer)**: Formata a resposta final de forma clara, simples e direta para o usuário final (MEI/Microempresário), sem jargões corporativos.

## ⚡ 4. Eficiência e Performance

Para garantir respostas rápidas:

- **Semantic Cache**: Armazene queries frequentes no `{{ CACHE_LAYER }}` usando embeddings da pergunta como chave.
- **Streaming**: Utilize Server-Sent Events (SSE) ou WebSockets para enviar a resposta em chunks, melhorando a percepção de velocidade.
- **Tool Calling Restrito**: Limite as ferramentas disponíveis para cada agente especializado, reduzindo o tempo de raciocínio do LLM.
