<!-- blueprint: db_changes=false seed_data=false -->
# 12. AI Layer and Agents (LangGraph)

This document details the Artificial Intelligence layer architecture, active when `{{ ENABLE_AI_LAYER }} = true`. The focus is on efficiency, performance and deep analysis capability.

## 🧠 1. Model Configuration via JSON (integrations table)

AI model credentials and settings **do not live in `.env`** (except master keys). They reside in the `integrations` table, allowing multiple providers and automatic fallback.

```json
// integrations table schema for AI
{
  "provider": "OpenAI",  // "Anthropic" | "Local Embeddings"
  "type": "AI",          // "Embedding"
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

A central manager (`HybridProviderManager`) reads the tenant's active integrations and initializes the correct clients. If the primary provider fails (e.g.: rate limit), it automatically routes to the `fallback_integration_id` configured in the database.

```python
# services/backend/app/ai/hybrid_provider.py
class HybridProviderManager:
    def __init__(self, db_session, tenant_id: int):
        self.db = db_session
        self.tenant_id = tenant_id
        self.active_provider = self._load_provider()

    def _load_provider(self):
        # Fetch tenant's active integration
        integration = self.db.query(Integration).filter(
            Integration.tenant_id == self.tenant_id,
            Integration.type == "AI",
            Integration.active == True
        ).first()

        if not integration:
            raise ValueError("No AI provider configured for this tenant.")

        return self._initialize_client(integration)

    def generate_response(self, prompt: str):
        try:
            return self.active_provider.generate(prompt)
        except RateLimitError:
            # Automatic fallback logic
            fallback = self._load_fallback_provider()
            return fallback.generate(prompt)
```

## 🕸️ 3. Multi-Agent Architecture with LangGraph

For deep analysis (e.g.: financial forecasting, sales analysis), use a graph-based architecture (LangGraph) with specialized agents, instead of a single giant prompt.

### Recommended Graph Structure

The multi-agent architecture is defined by the `{{ AI_AGENTS }}` variable. The standard includes:

1. **Orchestrator Agent (Router)**: Receives the user query, analyzes the intent and decides which flow to follow.
2. **Data Agent (Retriever)**: Specialist in fetching structured data from PostgreSQL (via generated SQL or internal APIs) and unstructured data from `{{ EMBEDDING_DB }}`.
3. **Analyst Agent (Analyzer)**: Receives raw data and applies business logic (e.g.: margin calculation, cash flow projection).
4. **Synthesizer Agent**: Formats the final response clearly and directly for the end user, without corporate jargon.

## ⚡ 4. Efficiency and Performance

To ensure fast responses:

- **Semantic Cache**: Store frequent queries in `{{ CACHE_LAYER }}` using the question's embeddings as the key.
- **Streaming**: Use Server-Sent Events (SSE) or WebSockets to send the response in chunks, improving perceived speed.
- **Restricted Tool Calling**: Limit the tools available to each specialized agent, reducing LLM reasoning time.
