<!-- blueprint: db_changes=true seed_data=false -->
# Módulo 01 — Financeiro

Núcleo financeiro do Plurus. Toda movimentação de dinheiro da empresa passa por aqui: receitas, despesas, contas bancárias, obrigações e projeções.

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

## 6. Regras de Negócio

- Todo lançamento financeiro tem `tenant_id` — isolamento total entre tenants
- Soft delete em todas as tabelas — nunca delete físico
- Pagamento registra `paid_at` e `paid_amount`; se parcial, status vira `paid_partial`
- Contas vinculadas a pedidos são criadas automaticamente pelo módulo Vendas
- Cancelamento de conta não gera estorno automático — requer lançamento manual de ajuste
- Saldo bancário é calculado em tempo real: `initial_balance + Σ(entradas) - Σ(saídas)`
