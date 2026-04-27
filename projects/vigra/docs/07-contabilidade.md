<!-- blueprint: db_changes=true seed_data=false -->
# Módulo 07 — Contabilidade

Escrituração contábil integrada ao fluxo operacional do Vigra. Voltada para MEI e MPE que precisam entregar relatórios ao contador ou acompanhar a saúde contábil do negócio. Não inclui emissão de Nota Fiscal nesta versão.

---

## 1. Plano de Contas

- Estrutura hierárquica baseada no padrão CFC (Conselho Federal de Contabilidade)
- Grupos principais: Ativo, Passivo, Patrimônio Líquido, Receita, Despesa, Custo
- Plano padrão pré-carregado no seed; tenant pode criar contas filhas customizadas
- Contas analíticas (recebem lançamentos) vs. contas sintéticas (apenas agrupamento)
- Código contábil: `1.1.01.001` — hierarquia por pontos

```sql
CREATE TABLE chart_of_accounts (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    code VARCHAR(20) NOT NULL,
    name VARCHAR(200) NOT NULL,
    type VARCHAR(20) NOT NULL CHECK (type IN (
        'asset',       -- Ativo
        'liability',   -- Passivo
        'equity',      -- Patrimônio Líquido
        'revenue',     -- Receita
        'expense',     -- Despesa
        'cost'         -- Custo
    )),
    nature VARCHAR(10) NOT NULL CHECK (nature IN ('debit', 'credit')),
    classification VARCHAR(20) NOT NULL CHECK (classification IN ('synthetic', 'analytical')),
    parent_id INTEGER REFERENCES chart_of_accounts(id),
    is_system BOOLEAN DEFAULT FALSE,   -- TRUE = gerado pelo seed, não pode ser deletado
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, code)
);
```

---

## 2. Lançamentos Contábeis

- Todo evento financeiro gera lançamentos contábeis automaticamente (partidas dobradas)
- O sistema respeita a equação contábil: Débitos = Créditos
- Lançamentos manuais permitidos para ajustes, depreciação e provisões
- Período contábil: mensal; fechamento de período impede lançamentos retroativos (configurável)
- Regime suportado: **Caixa** (data do pagamento) e **Competência** (data do fato gerador)

### Geração automática de lançamentos
| Evento | Débito | Crédito |
|---|---|---|
| Venda à vista | Caixa/Banco | Receita de Vendas |
| Venda a prazo | Contas a Receber | Receita de Vendas |
| Recebimento de venda | Caixa/Banco | Contas a Receber |
| Compra à vista | Estoque / CMV | Caixa/Banco |
| Compra a prazo | Estoque / CMV | Contas a Pagar |
| Pagamento de fornecedor | Contas a Pagar | Caixa/Banco |
| Despesa operacional | Conta de Despesa | Caixa/Banco |

```sql
CREATE TABLE accounting_periods (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    status VARCHAR(20) DEFAULT 'open',   -- 'open', 'closed'
    closed_at TIMESTAMPTZ,
    closed_by INTEGER REFERENCES users(id),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, year, month)
);

CREATE TABLE journal_entries (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    period_id INTEGER NOT NULL REFERENCES accounting_periods(id),
    entry_date DATE NOT NULL,
    description TEXT NOT NULL,
    reference_type VARCHAR(30),   -- 'order', 'purchase_order', 'financial_account', 'manual'
    reference_id INTEGER,
    regime VARCHAR(15) NOT NULL DEFAULT 'cash' CHECK (regime IN ('cash', 'accrual')),
    is_manual BOOLEAN DEFAULT FALSE,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE journal_entry_lines (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    entry_id INTEGER NOT NULL REFERENCES journal_entries(id),
    account_id INTEGER NOT NULL REFERENCES chart_of_accounts(id),
    type VARCHAR(10) NOT NULL CHECK (type IN ('debit', 'credit')),
    amount NUMERIC(15,2) NOT NULL CHECK (amount > 0),
    cost_center_id INTEGER REFERENCES cost_centers(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 3. Centros de Custo

- Permite alocar receitas e despesas por área, projeto ou produto
- Exemplos: `Vendas Online`, `Loja Física`, `Marketing`, `Logística`
- DRE pode ser visualizado por centro de custo individualmente
- Lançamento pode ter custo rateado entre múltiplos centros

```sql
CREATE TABLE cost_centers (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 4. Relatórios Contábeis

### DRE — Demonstrativo de Resultado do Exercício
- Período: mensal, trimestral, anual
- Regimes: Caixa e Competência (lado a lado ou separado)
- Drill-down por conta contábil
- Comparativo: mesmo período do ano anterior

### Balanço Patrimonial
- Posição em qualquer data
- Ativo (Circulante + Não Circulante) vs Passivo + PL
- Indicadores: liquidez corrente, liquidez geral, endividamento

### Livro Caixa
- Relatório de todas as entradas e saídas em ordem cronológica
- Exigido para MEI na declaração anual (DASN-SIMEI)
- Exportação em PDF e CSV

### LAJIDA / EBITDA
- Calculado automaticamente a partir da DRE
- Margem EBITDA sobre receita líquida

---

## 5. Exportação para Contador

- Exportação dos lançamentos em formato SPED Contábil (ECD) — simplificado
- CSV com todos os lançamentos do período selecionado
- Relatórios em PDF prontos para envio ao contador
- Acesso read-only para o contador via convite (role `contador`)

---

## 6. Regras de Negócio

- Toda `journal_entry` deve ter soma de débitos = soma de créditos (validado no backend)
- Período fechado: nenhum lançamento pode ser inserido, editado ou excluído retroativamente
- Lançamentos automáticos não podem ser editados manualmente — apenas estornados
- Estorno de lançamento cria uma nova `journal_entry` com os valores invertidos
- Conta sintética não aceita lançamentos — apenas analíticas
- Tenant MEI tem plano de contas simplificado; regime de caixa é o padrão
- Role `contador` tem acesso de leitura ao módulo Contabilidade mas não pode lançar
