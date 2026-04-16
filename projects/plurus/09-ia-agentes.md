<!-- blueprint: db_changes=true seed_data=false -->
# Módulo 09 — IA & Agentes Autônomos

IA integrada ao Plurus em duas camadas: **Chat** para análise rápida do negócio em linguagem natural, e **Agentes Autônomos** para execução de tarefas complexas e multi-step sem intervenção manual.

---

## 1. Chat de IA (Análise Rápida)

Interface de chat dentro do dashboard do Plurus. O usuário faz perguntas sobre o próprio negócio e recebe respostas contextualizadas com os dados reais do tenant.

### Exemplos de perguntas suportadas
- "Qual meu produto mais vendido esse mês?"
- "Quanto devo a fornecedores até o fim do mês?"
- "Meu estoque de X vai durar quantos dias?"
- "Quais clientes não compram há mais de 60 dias?"
- "Como está meu fluxo de caixa para a próxima semana?"

### Arquitetura
- Modelo LLM: configurável via `system_settings` (OpenAI GPT-4 / Anthropic Claude)
- Acesso ao banco via **Function Calling** (tools): cada ferramenta é uma query segura no banco do tenant
- Contexto multi-tenant: todas as tools recebem `tenant_id` automaticamente — nenhuma consulta é global
- Histórico de conversa armazenado por sessão; contexto enviado ao LLM limitado a últimas N mensagens
- Streaming de resposta via SSE (Server-Sent Events)

```sql
CREATE TABLE ai_conversations (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    title VARCHAR(200),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_message_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ai_messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES ai_conversations(id),
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content TEXT,
    tool_calls JSONB,          -- chamadas de função feitas pelo LLM
    tool_results JSONB,        -- resultados das functions retornados ao LLM
    tokens_used INTEGER,
    model_used VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 2. Agentes Autônomos

Agentes são fluxos multi-step que o usuário dispara com uma instrução de alto nível. O agente planeja, executa ações e reporta o resultado. Construídos com **LangGraph**.

### Agente de Campanhas
**Trigger**: usuário solicita "gera uma campanha de vendas para este mês"

**Fluxo do agente:**
1. Analisa histórico de vendas do mês atual vs. mês anterior
2. Identifica produtos com estoque alto e baixo giro (oportunidade de promoção)
3. Identifica segmento de clientes mais receptivo ao produto
4. Gera texto da campanha (descrição, CTA, promoção sugerida)
5. Cria a promoção no banco (módulo Cadastros)
6. Publica anúncio atualizado nos marketplaces configurados (Mercado Livre / Amazon)
7. Agenda mensagem WhatsApp para o segmento selecionado
8. Reporta ao usuário: "Campanha criada. 3 produtos promovidos. 247 clientes serão notificados."

### Agente de Previsão de Resultados (P&L Forecast)
**Trigger**: automático mensal ou sob demanda

**Fluxo:**
1. Coleta dados de vendas e despesas dos últimos 12 meses
2. Aplica modelo de séries temporais + sazonalidade
3. Projeta receita, CMV, despesas e lucro líquido para os próximos 3 meses
4. Identifica meses com risco de resultado negativo
5. Sugere ações corretivas (reduzir estoque X, antecipar campanha Y)
6. Salva forecast na tabela e atualiza o painel financeiro

### Agente de Reposição de Estoque
**Trigger**: job diário que verifica estoque vs. estoque mínimo

**Fluxo:**
1. Lista todos os SKUs abaixo do estoque mínimo
2. Para cada SKU, identifica o fornecedor preferido (melhor rating + menor preço histórico)
3. Calcula quantidade sugerida de reposição (baseada no giro médio dos últimos 30 dias)
4. Cria rascunho de PO (Purchase Order) por fornecedor
5. Notifica o comprador: "3 POs geradas aguardando sua aprovação"

### Agente de Alertas Proativos
Roda em background e detecta anomalias sem trigger do usuário:
- Venda abaixo da média dos últimos 7 dias → alerta
- Cliente VIP sem compra há 45 dias → sugere ação de reativação
- Conta a pagar vencendo em 2 dias sem saldo suficiente no caixa → alerta urgente
- Produto com alto retorno → sugere investigação de qualidade

### Tabelas de Agentes
```sql
CREATE TABLE agent_executions (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    user_id INTEGER REFERENCES users(id),       -- null se disparado automaticamente
    agent_type VARCHAR(50) NOT NULL,            -- 'campaign', 'forecast', 'restock', 'alert'
    trigger_type VARCHAR(20) DEFAULT 'manual',  -- 'manual', 'scheduled', 'threshold'
    input_payload JSONB,                        -- instrução original do usuário
    status VARCHAR(20) DEFAULT 'running',       -- 'running','completed','failed','cancelled'
    steps JSONB,                                -- log de cada passo executado
    output_summary TEXT,                        -- resumo final apresentado ao usuário
    error_message TEXT,
    tokens_used INTEGER,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
```

---

## 3. Function Calling — Tools disponíveis para o Chat

Cada tool é uma função Python que o LLM pode invocar. Todas são read-only por padrão; agentes têm tools de escrita adicionais.

| Tool | Descrição |
|---|---|
| `get_sales_summary` | Vendas por período, canal, produto |
| `get_stock_levels` | Saldo atual por SKU e depósito |
| `get_cash_flow` | Entradas e saídas por período |
| `get_overdue_payables` | Contas a pagar vencidas ou vencendo |
| `get_top_clients` | Clientes por volume de compras |
| `get_low_stock_items` | SKUs abaixo do estoque mínimo |
| `get_sales_forecast` | Projeção de vendas gerada pelo agente |
| `create_promotion` | (Agente) Cria promoção no catálogo |
| `create_campaign` | (Agente) Cria campanha de marketing |
| `sync_marketplace_listing` | (Agente) Atualiza anúncio no marketplace |
| `create_purchase_order_draft` | (Agente) Cria PO rascunho |

---

## 4. Regras de Negócio

- Toda tool recebe `tenant_id` implicitamente — impossível acessar dados de outro tenant
- Agentes que escrevem no banco (create/update) sempre criam em status `draft` ou `pending`; nunca publicam sem confirmação, exceto quando o usuário explicitamente autorizou "execute automaticamente"
- Histórico de execuções de agentes preservado indefinidamente para auditoria
- Custo de tokens é registrado por execução; relatório mensal de uso de IA disponível para o admin
- Fallback de modelo: se OpenAI indisponível → usa Anthropic Claude; configurado em `system_settings`
- Agente de alertas respeita horário comercial para notificações não urgentes (configurável por tenant)
