<!-- blueprint: db_changes=true seed_data=false -->
# Módulo 02 — Estoque

Controle completo do ciclo de vida dos produtos em estoque: entradas, saídas, ajustes, inventário físico e múltiplos depósitos.

---

## 1. Cadastro de Itens de Estoque

- Cada produto (módulo Cadastros) pode ter variações (cor, tamanho, sabor)
- Cada variação é uma SKU independente com saldo próprio
- Unidade de medida: `un`, `kg`, `lt`, `cx`, `m`, `m²`, etc.
- Estoque mínimo e estoque de segurança configuráveis por SKU por depósito
- Custo médio e custo FIFO calculados automaticamente

---

## 2. Métodos de Custeio

### Preço Médio Ponderado (padrão)
- `custo_medio = (saldo_atual × custo_atual + qtd_entrada × custo_entrada) / (saldo_atual + qtd_entrada)`
- Recalculado a cada entrada no estoque
- Usado para calcular CMV (Custo das Mercadorias Vendidas) no DRE

### FIFO — First In, First Out (opcional, habilitado por tenant)
- Cada lote de entrada registra quantidade, custo unitário e data
- Saídas consomem os lotes mais antigos primeiro
- Relatório de lotes em estoque com custo individual
- Útil para produtos com validade ou rastreabilidade exigida

### Tabelas
```sql
CREATE TABLE warehouses (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(100) NOT NULL,   -- 'Depósito Principal', 'Loja Física'
    address TEXT,
    is_default BOOLEAN DEFAULT FALSE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE stock_items (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    product_variation_id INTEGER NOT NULL REFERENCES product_variations(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    quantity NUMERIC(15,3) NOT NULL DEFAULT 0,
    reserved_quantity NUMERIC(15,3) NOT NULL DEFAULT 0,  -- reservado por pedidos pendentes (boleto, etc.)
    min_quantity NUMERIC(15,3) DEFAULT 0,       -- estoque mínimo (alerta)
    safety_quantity NUMERIC(15,3) DEFAULT 0,    -- estoque de segurança
    avg_cost NUMERIC(15,4) DEFAULT 0,           -- preço médio ponderado
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(product_variation_id, warehouse_id)
);

CREATE TABLE stock_movements (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    product_variation_id INTEGER NOT NULL REFERENCES product_variations(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    type VARCHAR(20) NOT NULL CHECK (type IN (
        'entry',        -- compra, devolução de cliente
        'exit',         -- venda, devolução a fornecedor
        'adjustment',   -- ajuste de inventário
        'transfer'      -- transferência entre depósitos
    )),
    quantity NUMERIC(15,3) NOT NULL,
    unit_cost NUMERIC(15,4),
    avg_cost_after NUMERIC(15,4),               -- custo médio após o movimento
    reference_type VARCHAR(30),                 -- 'purchase_order', 'order', 'inventory_count'
    reference_id INTEGER,
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE stock_fifo_lots (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    product_variation_id INTEGER NOT NULL REFERENCES product_variations(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    entry_date DATE NOT NULL,
    initial_quantity NUMERIC(15,3) NOT NULL,
    remaining_quantity NUMERIC(15,3) NOT NULL,
    unit_cost NUMERIC(15,4) NOT NULL,
    purchase_order_id INTEGER REFERENCES purchase_orders(id),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 3. Entradas de Estoque

- **Por compra**: gerada automaticamente ao confirmar recebimento de PO (módulo Compras)
- **Devolução de cliente**: estorna a saída original, recria o lote FIFO se aplicável
- **Ajuste manual**: com motivo obrigatório (perda, doação, uso interno, erro de contagem)

---

## 4. Saídas de Estoque

- **Por venda**: gerada automaticamente ao confirmar expedição do pedido
- **Devolução a fornecedor**: diminui estoque e gera crédito no AP
- **Baixa por perda**: categoria de ajuste; impacta CMV no DRE
- **Transferência**: saída de um depósito + entrada em outro na mesma operação (atômica)

---

## 5. Inventário Físico

- Abre uma contagem: congela o saldo atual como "esperado"
- Operador informa quantidade real por SKU/depósito
- Sistema calcula diferença e gera ajustes automáticos com motivo `inventory_count`
- Histórico de inventários por depósito

### Tabela
```sql
CREATE TABLE inventory_counts (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    status VARCHAR(20) DEFAULT 'open',    -- 'open', 'in_progress', 'closed'
    started_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    created_by INTEGER REFERENCES users(id),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE inventory_count_items (
    id SERIAL PRIMARY KEY,
    inventory_count_id INTEGER NOT NULL REFERENCES inventory_counts(id),
    product_variation_id INTEGER NOT NULL REFERENCES product_variations(id),
    expected_quantity NUMERIC(15,3),
    counted_quantity NUMERIC(15,3),
    difference NUMERIC(15,3) GENERATED ALWAYS AS (counted_quantity - expected_quantity) STORED,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 6. Alertas e Relatórios

- Alerta de estoque mínimo → push notification + item na IA dashboard
- Relatório de giro de estoque (quantidade vendida / saldo médio no período)
- Curva ABC de produtos por valor em estoque
- Projeção de ruptura: baseada no giro médio dos últimos 30 dias
- Rastreabilidade: para qualquer SKU, exibe todos os movimentos com origem

---

## 7. Kits e Combos (BOM — Bill of Materials)

Muitos MEIs vendem produtos em kits (ex: "Kit 3 Camisetas"). A venda de 1 Kit deve dar baixa automaticamente nas SKUs componentes, não no kit em si.

- Kit é um produto do tipo `bundle` no módulo Cadastros
- Cada kit tem N componentes com suas respectivas quantidades
- Ao vender 1 kit, o sistema expande os componentes e baixa o estoque de cada SKU individual
- Inventário físico conta os componentes individualmente; o saldo do kit é derivado (mínimo entre componentes)
- Custo do kit = Σ(custo_componente × quantidade); calculado automaticamente

```sql
CREATE TABLE product_bundles (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    bundle_variation_id INTEGER NOT NULL REFERENCES product_variations(id),   -- o kit em si
    component_variation_id INTEGER NOT NULL REFERENCES product_variations(id), -- SKU componente
    quantity NUMERIC(15,3) NOT NULL,                                           -- qtd do componente no kit
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(bundle_variation_id, component_variation_id)
);
```

---

## 8. Embalagens de Envio

Para calcular o frete corretamente, o sistema precisa saber em qual caixa o pedido será embalado. Ao montar um pedido, a IA sugere a menor caixa que comporte todos os itens.

- Tenant cadastra suas caixas disponíveis (dimensões e peso próprio)
- O sistema calcula o **peso cúbico** (`comprimento × largura × altura / 6000`) e usa o maior entre peso real e cúbico
- A caixa sugerida é a menor que comporta o volume total dos itens + folga mínima configurável
- Peso da embalagem somado ao peso dos produtos para cálculo de frete

```sql
CREATE TABLE packaging_boxes (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(100) NOT NULL,             -- 'Caixa P', 'Caixa M', 'Envelope'
    height_cm NUMERIC(8,2) NOT NULL,
    width_cm NUMERIC(8,2) NOT NULL,
    depth_cm NUMERIC(8,2) NOT NULL,
    own_weight_kg NUMERIC(8,3) NOT NULL DEFAULT 0,
    max_weight_kg NUMERIC(8,3),             -- limite de peso suportado pela caixa
    is_default BOOLEAN DEFAULT FALSE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 9. Regras de Negócio

- Saldo de estoque nunca vai negativo por padrão; configurável por tenant (permite negativo = sim/não)
- `reserved_quantity` é incrementado quando pedido entra em `pagamento_pendente` (ex: boleto gerado); decrementado na expedição ou cancelamento — o saldo **disponível real** = `quantity - reserved_quantity`
- Todo movimento gera um `stock_movement` — auditoria completa
- Transferência entre depósitos é transacional: ou ambos os lados ocorrem ou nenhum
- Custo médio é sempre positivo; se entrada com custo zero, usa o custo médio atual
- FIFO só ativo se `tenant.fifo_enabled = true`; caso contrário usa preço médio
- Kits do tipo `bundle` não têm saldo direto em `stock_items`; saldo é derivado dos componentes
- Embalagem sugerida pelo sistema pode ser sobrescrita pelo operador na expedição
