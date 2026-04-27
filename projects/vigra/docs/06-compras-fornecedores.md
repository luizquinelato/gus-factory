<!-- blueprint: db_changes=true seed_data=false -->
# Módulo 06 — Compras & Fornecedores

Gerencia o relacionamento com fornecedores, o processo de aquisição de mercadorias e serviços, e a entrada de produtos no estoque.

---

## 1. Cadastro de Fornecedores

- Pessoa Jurídica (CNPJ) ou Física (CPF — MEI fornecedor de serviço)
- Múltiplos contatos: nome, e-mail, telefone, WhatsApp
- Múltiplos endereços (sede, filial, entrega)
- Condições comerciais padrão: prazo de pagamento, desconto habitual, moeda
- Histórico de compras: total gasto, volume, pontualidade de entrega
- Avaliação do fornecedor: prazo, qualidade, preço (1–5 estrelas por compra)

### Tabelas
```sql
CREATE TABLE suppliers (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    type VARCHAR(2) NOT NULL DEFAULT 'pj' CHECK (type IN ('pf', 'pj')),
    name VARCHAR(200) NOT NULL,
    trade_name VARCHAR(200),
    document VARCHAR(18) NOT NULL,
    email VARCHAR(200),
    phone VARCHAR(20),
    payment_terms_days INTEGER DEFAULT 30,   -- prazo padrão em dias
    discount_pct NUMERIC(5,2) DEFAULT 0,
    notes TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, document)
);

CREATE TABLE supplier_contacts (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    name VARCHAR(100),
    role VARCHAR(100),        -- 'Comercial', 'Financeiro', 'Logística'
    email VARCHAR(200),
    phone VARCHAR(20),
    is_primary BOOLEAN DEFAULT FALSE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE supplier_ratings (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    purchase_order_id INTEGER REFERENCES purchase_orders(id),
    delivery_rating INTEGER CHECK (delivery_rating BETWEEN 1 AND 5),
    quality_rating INTEGER CHECK (quality_rating BETWEEN 1 AND 5),
    price_rating INTEGER CHECK (price_rating BETWEEN 1 AND 5),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 2. Cotações (RFQ — Request for Quotation)

- Cria uma cotação para um ou mais produtos com quantidades desejadas
- Envia para múltiplos fornecedores (e-mail ou WhatsApp)
- Fornecedor responde com preço unitário, prazo de entrega e condições
- Sistema compara as cotações lado a lado e sugere o melhor custo/benefício
- Aprovação da cotação gera automaticamente um Pedido de Compra (PO)

```sql
CREATE TABLE purchase_quotations (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    status VARCHAR(20) DEFAULT 'open',    -- 'open', 'responded', 'approved', 'cancelled'
    notes TEXT,
    expires_at TIMESTAMPTZ,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE purchase_quotation_items (
    id SERIAL PRIMARY KEY,
    quotation_id INTEGER NOT NULL REFERENCES purchase_quotations(id),
    product_variation_id INTEGER NOT NULL REFERENCES product_variations(id),
    requested_quantity NUMERIC(15,3) NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE purchase_quotation_responses (
    id SERIAL PRIMARY KEY,
    quotation_id INTEGER NOT NULL REFERENCES purchase_quotations(id),
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    unit_price NUMERIC(15,4),
    delivery_days INTEGER,
    payment_terms TEXT,
    notes TEXT,
    responded_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 3. Pedido de Compra (PO — Purchase Order)

### Ciclo de vida
```
rascunho → aguardando_aprovacao → aprovado → enviado_fornecedor → parcialmente_recebido → recebido → cancelado
```

- PO pode ter múltiplos itens de produtos diferentes
- Vínculo com fornecedor e condições financeiras (prazo, desconto)
- Aprovação por hierarquia: compras abaixo de R$ X aprovadas pelo operador; acima, requer admin
- Ao confirmar recebimento: gera `stock_movement` (entrada) e `financial_account` (conta a pagar)

```sql
CREATE TABLE purchase_orders (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    po_number VARCHAR(30) NOT NULL UNIQUE,   -- PO-2026-000001
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    subtotal NUMERIC(15,2) DEFAULT 0,
    discount_amount NUMERIC(15,2) DEFAULT 0,
    shipping_amount NUMERIC(15,2) DEFAULT 0,
    total_amount NUMERIC(15,2) DEFAULT 0,
    payment_terms_days INTEGER,
    expected_delivery_date DATE,
    notes TEXT,
    approved_by INTEGER REFERENCES users(id),
    approved_at TIMESTAMPTZ,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE purchase_order_items (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id),
    product_variation_id INTEGER NOT NULL REFERENCES product_variations(id),
    quantity_ordered NUMERIC(15,3) NOT NULL,
    quantity_received NUMERIC(15,3) DEFAULT 0,
    unit_cost NUMERIC(15,4) NOT NULL,
    total_cost NUMERIC(15,2) NOT NULL,
    warehouse_id INTEGER REFERENCES warehouses(id),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 4. Recebimento de Mercadorias

- Recebimento pode ser parcial (parte dos itens ou quantidade menor)
- Cada recebimento gera um `stock_movement` de entrada por variação
- Divergências registradas: quantidade divergente, produto com dano, produto errado
- PO com divergência fica em `parcialmente_recebido` até regularização
- Recebimento final fecha o PO e cria a conta a pagar no módulo Financeiro

---

## 5. Credores e Contas a Pagar a Fornecedores

- Toda PO recebida gera automaticamente uma `financial_account` do tipo `payable`
- Vínculo direto entre `financial_account` e `purchase_order`
- Fornecedor é um credor: visão consolidada de quanto deve a cada um
- Relatório de aging: quanto vence nos próximos 7, 15, 30 e 60 dias por fornecedor

---

## 6. Importação de NF-e do Fornecedor (XML)

A forma mais rápida de dar entrada em compras no Brasil é importando o **XML da NF-e** do fornecedor. Isso elimina a digitação manual e garante precisão nos dados fiscais.

### Fluxo de importação
1. Usuário faz upload do arquivo XML da NF-e (padrão SEFAZ)
2. Sistema lê o XML e extrai: CNPJ do emitente, itens (código, descrição, NCM, qtd, preço, IPI, ICMS)
3. **De-para automático**: tenta associar cada item ao catálogo interno por código de barras ou SKU
4. Itens sem correspondência ficam pendentes para o usuário fazer o *de-para* manualmente (ou cadastrar)
5. Fornecedor é criado automaticamente se o CNPJ não existir no cadastro
6. Após confirmação, gera automaticamente: `purchase_order` + `purchase_order_items` + entrada em estoque + `financial_account` (contas a pagar) com vencimento baseado no prazo configurado do fornecedor

```sql
CREATE TABLE nfe_imports (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    nfe_key VARCHAR(44) NOT NULL,           -- chave de acesso da NF-e (44 dígitos)
    nfe_number VARCHAR(20),
    nfe_series VARCHAR(5),
    issue_date DATE,
    supplier_id INTEGER REFERENCES suppliers(id),
    supplier_cnpj VARCHAR(18) NOT NULL,
    total_amount NUMERIC(15,2),
    xml_content TEXT NOT NULL,              -- XML original armazenado para auditoria
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                                            -- 'pending', 'mapped', 'imported', 'cancelled'
    purchase_order_id INTEGER REFERENCES purchase_orders(id),
    created_by INTEGER REFERENCES users(id),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, nfe_key)
);

CREATE TABLE nfe_import_items (
    id SERIAL PRIMARY KEY,
    nfe_import_id INTEGER NOT NULL REFERENCES nfe_imports(id),
    nfe_item_number INTEGER NOT NULL,
    nfe_product_code VARCHAR(60),           -- código do produto no sistema do fornecedor
    nfe_product_description TEXT NOT NULL,
    ncm VARCHAR(10),
    barcode VARCHAR(50),
    quantity NUMERIC(15,3) NOT NULL,
    unit VARCHAR(20),
    unit_price NUMERIC(15,4) NOT NULL,
    total_price NUMERIC(15,2) NOT NULL,
    mapped_variation_id INTEGER REFERENCES product_variations(id),  -- null = ainda não mapeado
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 7. Regras de Negócio

- CNPJ/CPF de fornecedor é único por tenant
- PO não pode ser editada após status `enviado_fornecedor` sem cancelar e recriar
- Recebimento parcial não fecha o PO automaticamente — requer ação do usuário
- Conta a pagar gerada tem vencimento = `data_recebimento + payment_terms_days`
- Avaliação do fornecedor é opcional mas incentivada; influencia o ranking nas cotações
- Soft delete em tudo — histórico de compras preservado mesmo se fornecedor for desativado
- Chave NF-e (`nfe_key`) é única por tenant — evita importação duplicada da mesma nota
- XML da NF-e é armazenado integralmente em `nfe_imports.xml_content` para fins de auditoria fiscal
- De-para de itens: sistema sugere correspondência por `barcode` ou `ncm`; usuário confirma antes da importação final
