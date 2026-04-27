<!-- blueprint: db_changes=true seed_data=false -->
# Módulo 01 — Financeiro

Núcleo financeiro do Vigra. Toda movimentação de dinheiro da empresa passa por aqui: receitas, despesas, contas bancárias, obrigações e projeções.

---

## 1. Contas a Pagar e Receber (AP/AR)

### Contas a Pagar
- Cadastro de despesas únicas ou recorrentes (aluguel, assinatura, fornecedor)
- Vínculo com fornecedor (módulo Compras)
- Status: `pendente`, `pago_parcial`, `pago`, `vencido`, `cancelado`
- Alertas automáticos D-3 e D-1 do vencimento
- Parcelamento: uma conta pode ter N parcelas, cada uma com vencimento e status independente
- Pagamento parcial registra o saldo remanescente

### Contas a Receber
- Geradas automaticamente a partir de vendas (módulo Vendas)
- Podem ser criadas manualmente (serviços prestados, receitas avulsas)
- Status: `pendente`, `recebido_parcial`, `recebido`, `inadimplente`, `cancelado`
- Vínculo com cliente (módulo CRM)

### Tabelas
```sql
CREATE TABLE financial_accounts (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    type VARCHAR(10) NOT NULL CHECK (type IN ('payable', 'receivable')),
    description TEXT NOT NULL,
    total_amount NUMERIC(15,2) NOT NULL,
    paid_amount NUMERIC(15,2) NOT NULL DEFAULT 0,
    due_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    supplier_id INTEGER REFERENCES suppliers(id),
    client_id INTEGER REFERENCES clients(id),
    order_id INTEGER REFERENCES orders(id),
    category_id INTEGER REFERENCES financial_categories(id),
    recurrence VARCHAR(20), -- 'monthly', 'weekly', null
    notes TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE financial_account_installments (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    financial_account_id INTEGER NOT NULL REFERENCES financial_accounts(id),
    installment_number INTEGER NOT NULL,
    amount NUMERIC(15,2) NOT NULL,
    due_date DATE NOT NULL,
    paid_amount NUMERIC(15,2) DEFAULT 0,
    paid_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 2. Fluxo de Caixa

- Visão diária, semanal e mensal de entradas e saídas
- Saldo inicial configurável por período
- Projeção futura baseada em contas a pagar/receber pendentes
- Filtros por categoria, conta bancária, período
- Exportação para CSV/PDF

### Tabelas
```sql
CREATE TABLE bank_accounts (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(100) NOT NULL,       -- 'Conta Bradesco', 'Caixa Físico'
    bank_code VARCHAR(10),
    agency VARCHAR(20),
    account_number VARCHAR(30),
    initial_balance NUMERIC(15,2) DEFAULT 0,
    current_balance NUMERIC(15,2) DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE financial_categories (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(100) NOT NULL,
    type VARCHAR(10) NOT NULL CHECK (type IN ('income', 'expense')),
    parent_id INTEGER REFERENCES financial_categories(id),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 3. DRE — Demonstrativo de Resultado do Exercício

- Gerado por período (mensal, trimestral, anual)
- Estrutura: Receita Bruta → Deduções → Receita Líquida → CMV → Lucro Bruto → Despesas Operacionais → EBITDA → Resultado Líquido
- Regime de Caixa (data do pagamento) e Competência (data do fato gerador) — configurável
- Agrupamento por centro de custo

---

## 4. Balanço Patrimonial

- Ativo Circulante: caixa, contas a receber, estoque
- Ativo Não Circulante: imobilizado, investimentos
- Passivo Circulante: contas a pagar de curto prazo
- Passivo Não Circulante: dívidas de longo prazo
- Patrimônio Líquido: capital + lucros acumulados
- Integrado automaticamente com lançamentos contábeis (módulo Contabilidade)

---

## 5. Previsão de P&L (Forecast)

- Projeção de receitas e despesas para os próximos N meses
- Baseada em: histórico dos últimos 12 meses + sazonalidade + pedidos futuros + contas recorrentes
- Cenários: conservador, moderado e otimista (± desvio padrão)
- IA sugere ajustes baseados em tendências detectadas
- Alertas quando projeção indica resultado negativo em algum mês

---

## 6. Conciliação Bancária

Resolução da "dor mais comum" do MEI: saber se o saldo no sistema bate com o extrato real do banco.

- Importação de extrato via arquivo **OFX** (padrão exportado por todos os bancos) ou via **Open Finance** (futuro)
- Cada linha do extrato vira um `bank_transaction` com status `pending` até ser conciliada
- A IA sugere o *match* automático entre `bank_transaction` e `financial_account` (por valor + data próxima)
- Usuário confirma, rejeita ou ajusta a sugestão
- Transações não identificadas ficam em "não conciliadas" para lançamento manual
- Relatório de conciliação: diferença entre saldo sistema vs. saldo extrato por conta bancária

```sql
CREATE TABLE bank_transactions (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    bank_account_id INTEGER NOT NULL REFERENCES bank_accounts(id),
    transaction_date DATE NOT NULL,
    description TEXT NOT NULL,              -- descrição original do extrato
    amount NUMERIC(15,2) NOT NULL,          -- positivo = crédito, negativo = débito
    balance_after NUMERIC(15,2),            -- saldo após a transação (do extrato)
    external_id VARCHAR(100),               -- ID único do banco (evita duplicatas no OFX)
    reconciliation_status VARCHAR(20) NOT NULL DEFAULT 'pending',
                                            -- 'pending', 'matched', 'manual', 'ignored'
    financial_account_id INTEGER REFERENCES financial_accounts(id),
    matched_at TIMESTAMPTZ,
    matched_by INTEGER REFERENCES users(id),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(bank_account_id, external_id)
);
```

---

## 7. Taxas de Gateway de Pagamento

As taxas cobradas por Stripe, Mercado Pago e Pagar.me impactam diretamente o DRE e o fluxo de caixa líquido. Registrar essas taxas é essencial para o cálculo correto do lucro.

- Cada gateway tem alíquotas configuradas por forma de pagamento (PIX, cartão, boleto)
- Ao confirmar recebimento de um pedido, a taxa é calculada automaticamente e registrada
- Taxa aparece no DRE como dedução da Receita Bruta (ou despesa financeira, configurável)

```sql
CREATE TABLE payment_gateway_fees (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    gateway VARCHAR(30) NOT NULL,           -- 'stripe', 'mercadopago', 'pagarme'
    payment_method VARCHAR(30) NOT NULL,    -- 'pix', 'credit_card', 'boleto', 'debit_card'
    installments INTEGER DEFAULT 1,         -- número de parcelas (para cartão de crédito)
    fee_pct NUMERIC(5,4) NOT NULL,          -- ex: 2.99 para 2,99%
    fee_fixed NUMERIC(10,2) DEFAULT 0,      -- taxa fixa por transação (ex: R$ 0,40)
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, gateway, payment_method, installments)
);

CREATE TABLE order_gateway_fees (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    order_id INTEGER NOT NULL REFERENCES orders(id),
    gateway VARCHAR(30) NOT NULL,
    payment_method VARCHAR(30) NOT NULL,
    gross_amount NUMERIC(15,2) NOT NULL,    -- valor bruto recebido
    fee_amount NUMERIC(15,2) NOT NULL,      -- taxa cobrada pelo gateway
    net_amount NUMERIC(15,2) NOT NULL,      -- valor líquido = gross - fee
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 8. Provisão de Impostos (DAS / Simples Nacional)

Para MEIs e empresas do Simples Nacional, o sistema provisiona automaticamente o imposto mensal com base no faturamento acumulado.

- Alíquota configurada por tenant (MEI: valor fixo; Simples Nacional: tabela progressiva)
- A cada venda confirmada, o imposto proporcional é provisionado
- No dia 1 de cada mês, gera automaticamente uma `financial_account` do tipo `payable` para o DAS
- Relatório de faturamento acumulado vs. limite MEI (R$ 81.000/ano) com alerta ao atingir 80%

```sql
CREATE TABLE tax_settings (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    regime VARCHAR(20) NOT NULL,            -- 'mei', 'simples_nacional', 'lucro_presumido'
    das_fixed_amount NUMERIC(10,2),         -- para MEI: valor fixo mensal do DAS
    simples_aliquota NUMERIC(5,4),          -- para Simples: alíquota efetiva atual
    annual_revenue_limit NUMERIC(15,2),     -- limite de faturamento anual
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE tax_provisions (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    reference_month INTEGER NOT NULL,       -- mês de competência (1–12)
    reference_year INTEGER NOT NULL,
    gross_revenue NUMERIC(15,2) NOT NULL,   -- faturamento do mês
    tax_amount NUMERIC(15,2) NOT NULL,      -- imposto calculado
    regime VARCHAR(20) NOT NULL,
    financial_account_id INTEGER REFERENCES financial_accounts(id),
    status VARCHAR(20) DEFAULT 'open',      -- 'open', 'paid'
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, reference_year, reference_month)
);
```

---

## 9. Regras de Negócio

- Todo lançamento financeiro tem `tenant_id` — isolamento total entre tenants
- Soft delete em todas as tabelas — nunca delete físico
- Pagamento registra `paid_at` e `paid_amount`; se parcial, status vira `paid_partial`
- Contas vinculadas a pedidos são criadas automaticamente pelo módulo Vendas
- Cancelamento de conta não gera estorno automático — requer lançamento manual de ajuste
- Saldo bancário é calculado em tempo real: `initial_balance + Σ(entradas) - Σ(saídas)`
- Conciliação bancária: `external_id` garante idempotência na importação de OFX (sem duplicatas)
- Taxa de gateway é calculada e registrada no momento da confirmação do pagamento
- Provisão de DAS gerada no primeiro dia útil do mês seguinte; alertas de limite MEI enviados via WhatsApp
