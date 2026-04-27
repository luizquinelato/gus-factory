<!-- blueprint: db_changes=true seed_data=false -->
# Módulo 04 — Clientes & CRM

Gestão completa do relacionamento com clientes: cadastro, histórico, segmentação, atendimento via WhatsApp e campanhas de comunicação.

---

## 1. Cadastro de Clientes

- Pessoa Física (CPF) ou Jurídica (CNPJ)
- Validação de CPF/CNPJ no cadastro
- Múltiplos endereços (cobrança, entrega, principal)
- Múltiplos contatos (telefone, e-mail, WhatsApp)
- Tags livres para segmentação manual
- Score de cliente calculado automaticamente (frequência de compras + ticket médio + inadimplência)
- Histórico unificado: compras, conversas, campanhas recebidas, devoluções

### Tabelas
```sql
CREATE TABLE clients (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    type VARCHAR(2) NOT NULL DEFAULT 'pf' CHECK (type IN ('pf', 'pj')),
    name VARCHAR(200) NOT NULL,
    trade_name VARCHAR(200),                    -- nome fantasia para PJ
    document VARCHAR(18) NOT NULL,              -- CPF ou CNPJ formatado
    email VARCHAR(200),
    phone VARCHAR(20),
    whatsapp VARCHAR(20),
    score INTEGER DEFAULT 0,                    -- 0-100, calculado automaticamente
    notes TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, document)
);

CREATE TABLE client_addresses (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    client_id INTEGER NOT NULL REFERENCES clients(id),
    label VARCHAR(50),       -- 'Principal', 'Entrega', 'Cobrança'
    zip_code VARCHAR(9),
    street TEXT,
    number VARCHAR(20),
    complement VARCHAR(100),
    neighborhood VARCHAR(100),
    city VARCHAR(100),
    state VARCHAR(2),
    is_default BOOLEAN DEFAULT FALSE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE client_segments (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    rules JSONB,   -- ex: {"min_orders": 3, "min_total": 500, "last_days": 90}
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE client_segment_members (
    id SERIAL PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    segment_id INTEGER NOT NULL REFERENCES client_segments(id),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(client_id, segment_id)
);
```

---

## 2. Integração WhatsApp

Utiliza a **WhatsApp Business API** (via Meta ou provedor parceiro como Twilio / Z-API) para comunicação bidirecional com clientes.

### Atendimento (Suporte)
- Inbox centralizado de conversas no Vigra
- Operador responde diretamente pelo painel
- Histórico de mensagens vinculado ao cadastro do cliente
- Status da conversa: `aberta`, `em_atendimento`, `resolvida`, `arquivada`
- Roteamento por fila (ex: financeiro, suporte técnico, comercial)
- Tempo médio de resposta e resolução por operador (KPI)

### Campanhas (Advertisement)
- Envio de mensagens em massa para segmentos de clientes
- Templates aprovados pela Meta (HSM — Highly Structured Messages)
- Agendamento de envio por data/hora
- Taxa de entrega, leitura e resposta por campanha
- Opt-out automático: cliente responde SAIR → removido de futuras campanhas

### Tabelas
```sql
CREATE TABLE whatsapp_conversations (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    client_id INTEGER REFERENCES clients(id),
    phone VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'open',
    assigned_to INTEGER REFERENCES users(id),
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    last_message_at TIMESTAMPTZ,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE whatsapp_messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES whatsapp_conversations(id),
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    content TEXT,
    media_url TEXT,
    message_type VARCHAR(20) DEFAULT 'text',   -- 'text', 'image', 'document', 'template'
    status VARCHAR(20),                         -- 'sent', 'delivered', 'read', 'failed'
    wamid VARCHAR(200),                         -- ID da mensagem no WhatsApp
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE whatsapp_campaigns (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(200) NOT NULL,
    template_name VARCHAR(100) NOT NULL,
    segment_id INTEGER REFERENCES client_segments(id),
    scheduled_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'draft',
    total_recipients INTEGER DEFAULT 0,
    delivered_count INTEGER DEFAULT 0,
    read_count INTEGER DEFAULT 0,
    reply_count INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 3. Score e Segmentação Automática

### Cálculo do Score (0–100)
| Critério | Peso |
|---|---|
| Total gasto nos últimos 90 dias | 30% |
| Frequência de compras (últimos 90 dias) | 25% |
| Ticket médio | 20% |
| Dias desde a última compra | 15% |
| Ausência de inadimplência | 10% |

### Segmentos automáticos sugeridos
- **VIP**: score ≥ 80
- **Recorrente**: ≥ 3 compras nos últimos 60 dias
- **Em risco**: última compra há mais de 90 dias, era ativo antes
- **Inativo**: sem compra há mais de 180 dias
- **Novo**: primeira compra nos últimos 30 dias

---

## 4. Funil de Vendas (Pipeline B2B)

Para MEIs e MPEs que vendem serviços ou produtos de alto ticket, é essencial gerenciar *Leads* e *Oportunidades* **antes** de virarem clientes. O funil de vendas resolve esse gap.

- **Lead**: contato inicial (ainda não é cliente). Pode vir de formulário da loja, indicação, WhatsApp, evento
- **Oportunidade**: lead qualificado com produto/serviço de interesse, valor estimado e previsão de fechamento
- Estágios do funil customizáveis por tenant (ex: Prospecção → Qualificado → Proposta → Negociação → Fechado)
- Ao converter uma oportunidade, o lead é transformado em cliente (`clients`) e um pedido pode ser gerado
- Integrado ao Chat de IA: "Quais oportunidades vencem este mês?"

```sql
CREATE TABLE leads (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(200) NOT NULL,
    email VARCHAR(200),
    phone VARCHAR(20),
    whatsapp VARCHAR(20),
    company VARCHAR(200),
    source VARCHAR(50),              -- 'store_form', 'whatsapp', 'referral', 'event', 'manual'
    assigned_to INTEGER REFERENCES users(id),
    status VARCHAR(20) NOT NULL DEFAULT 'new',  -- 'new', 'contacted', 'qualified', 'disqualified'
    notes TEXT,
    converted_client_id INTEGER REFERENCES clients(id),
    converted_at TIMESTAMPTZ,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE pipeline_stages (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(100) NOT NULL,              -- 'Prospecção', 'Proposta', 'Negociação'
    order_position INTEGER NOT NULL,
    probability_pct INTEGER DEFAULT 0,       -- probabilidade estimada de fechamento
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE opportunities (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    lead_id INTEGER REFERENCES leads(id),
    client_id INTEGER REFERENCES clients(id),   -- se já for cliente existente
    title VARCHAR(200) NOT NULL,
    stage_id INTEGER NOT NULL REFERENCES pipeline_stages(id),
    estimated_value NUMERIC(15,2),
    expected_close_date DATE,
    assigned_to INTEGER REFERENCES users(id),
    status VARCHAR(20) NOT NULL DEFAULT 'open',  -- 'open', 'won', 'lost'
    lost_reason TEXT,
    converted_order_id INTEGER REFERENCES orders(id),
    notes TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE opportunity_activities (
    id SERIAL PRIMARY KEY,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
    type VARCHAR(30) NOT NULL,               -- 'call', 'email', 'whatsapp', 'meeting', 'note'
    description TEXT NOT NULL,
    scheduled_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 4. Histórico Unificado do Cliente

Visão 360° na ficha do cliente:
- Últimos N pedidos com status e valor
- Conversas abertas e resolvidas no WhatsApp
- Campanhas recebidas e respondidas
- Contas a receber em aberto
- Devoluções realizadas
- Tags e segmentos

---

## 5. Log de Consentimento LGPD

O Vigra registra explicitamente cada concessão e revogação de consentimento para comunicação, garantindo conformidade com a LGPD e rastreabilidade total.

- Opt-out via WhatsApp ("SAIR") registra automaticamente o consentimento como `revoked`
- Opt-in explícito registrado no cadastro do cliente ou no formulário da loja
- Exportação e exclusão de dados pessoais sob demanda (direitos do titular)

```sql
CREATE TABLE consent_logs (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    client_id INTEGER REFERENCES clients(id),
    lead_id INTEGER REFERENCES leads(id),
    channel VARCHAR(20) NOT NULL,            -- 'whatsapp', 'email', 'sms'
    action VARCHAR(10) NOT NULL,             -- 'opt_in', 'opt_out'
    source VARCHAR(50),                      -- 'store_form', 'whatsapp_reply', 'manual', 'import'
    ip_address INET,
    user_agent TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 6. Regras de Negócio

- CPF/CNPJ é único por tenant (não pode cadastrar o mesmo documento duas vezes)
- Opt-out de WhatsApp é respeitado em toda campanha subsequente — obrigatório por lei (LGPD); `consent_logs` é a fonte da verdade
- Score é recalculado em background diariamente via job agendado
- Dados de cliente são cobertos pela LGPD: exportação e exclusão sob demanda
- Exclusão de cliente é soft delete — histórico de pedidos é preservado para fins fiscais
- Mensagens WhatsApp ficam disponíveis por 90 dias na janela gratuita da Meta; após isso, apenas templates
- Lead convertido em cliente não perde o histórico de oportunidades e atividades do funil
- Estágio do funil é customizável por tenant; o Vigra oferece 5 estágios padrão no seed
