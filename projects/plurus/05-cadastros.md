<!-- blueprint: db_changes=true seed_data=false -->
# Módulo 05 — Cadastros (Master Data)

Centraliza todos os dados mestres do sistema: produtos, variações, categorias, preços, campanhas e promoções. É a fonte da verdade que alimenta Estoque, Vendas, E-Commerce e Marketplaces.

---

## 1. Produtos

- Produto é a entidade pai; variações são as SKUs físicas
- Atributos globais: nome, descrição curta, descrição longa (rich text), marca, categoria, unidade de medida
- Fotos: múltiplas por produto e por variação (até 10 por SKU); ordem configurável
- Produto pode ser `simples` (sem variações) ou `variável`
- Código interno (SKU base) e código de barras (EAN/GTIN) por variação
- NCM (código fiscal) — necessário para futura emissão de NF
- Peso e dimensões para cálculo de frete (módulo Logística)

### Tabelas
```sql
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(250) NOT NULL,
    description TEXT,
    short_description TEXT,
    brand VARCHAR(100),
    category_id INTEGER REFERENCES product_categories(id),
    unit VARCHAR(20) NOT NULL DEFAULT 'un',
    type VARCHAR(20) NOT NULL DEFAULT 'simple',   -- 'simple', 'variable'
    ncm VARCHAR(10),
    weight_kg NUMERIC(10,3),
    height_cm NUMERIC(10,2),
    width_cm NUMERIC(10,2),
    depth_cm NUMERIC(10,2),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, slug)
);

CREATE TABLE product_attributes (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(50) NOT NULL,    -- 'Cor', 'Tamanho', 'Sabor'
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE product_attribute_values (
    id SERIAL PRIMARY KEY,
    attribute_id INTEGER NOT NULL REFERENCES product_attributes(id),
    value VARCHAR(100) NOT NULL,  -- 'Azul', 'P', 'M', 'G', 'Morango'
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE product_variations (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    sku VARCHAR(100) NOT NULL,
    barcode VARCHAR(50),
    attributes JSONB,             -- {"Cor": "Azul", "Tamanho": "M"}
    base_price NUMERIC(15,2) NOT NULL DEFAULT 0,
    cost_price NUMERIC(15,4) DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, sku)
);

CREATE TABLE product_categories (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(120) NOT NULL,
    parent_id INTEGER REFERENCES product_categories(id),
    image_url TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 2. Tabelas de Preço

- Preço base definido na variação do produto
- Tabelas de preço permitem preços diferentes por canal, grupo de clientes ou período
- Prioridade: promoção ativa > tabela de preço do cliente > tabela padrão > preço base

```sql
CREATE TABLE price_tables (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(100) NOT NULL,         -- 'Varejo', 'Atacado', 'VIP'
    type VARCHAR(20) DEFAULT 'fixed',   -- 'fixed', 'percentage_off'
    discount_pct NUMERIC(5,2) DEFAULT 0,
    is_default BOOLEAN DEFAULT FALSE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE price_table_items (
    id SERIAL PRIMARY KEY,
    price_table_id INTEGER NOT NULL REFERENCES price_tables(id),
    product_variation_id INTEGER NOT NULL REFERENCES product_variations(id),
    price NUMERIC(15,2) NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(price_table_id, product_variation_id)
);
```

---

## 3. Promoções

- Desconto por produto, categoria ou pedido total
- Condição: quantidade mínima, valor mínimo, período de validade
- Tipos: desconto percentual, desconto fixo, compre X leve Y, frete grátis
- Acumulável ou exclusiva com outras promoções (flag)
- Cupom de desconto: código alfanumérico, limite de uso total e por cliente

```sql
CREATE TABLE promotions (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(200) NOT NULL,
    type VARCHAR(30) NOT NULL,             -- 'pct_off', 'fixed_off', 'buy_x_get_y', 'free_shipping'
    value NUMERIC(10,2),                   -- percentual ou valor fixo
    min_order_amount NUMERIC(15,2),
    min_quantity INTEGER,
    applies_to VARCHAR(20) DEFAULT 'all',  -- 'all', 'product', 'category'
    target_ids INTEGER[],                  -- IDs de produtos ou categorias
    coupon_code VARCHAR(50),
    max_uses INTEGER,
    uses_count INTEGER DEFAULT 0,
    max_uses_per_client INTEGER DEFAULT 1,
    stackable BOOLEAN DEFAULT FALSE,
    starts_at TIMESTAMPTZ,
    ends_at TIMESTAMPTZ,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 4. Campanhas de Marketing

Diferente de promoção (que é desconto de preço), campanha é uma ação de comunicação com objetivo de vendas.

- Tipos: lançamento de produto, liquidação, data comemorativa, reativação de inativo
- Canal: WhatsApp, e-mail, marketplace (publicação de anúncio especial)
- Vínculo com promoção: campanha pode ativar uma promoção automaticamente
- Métricas: alcance, cliques, conversão, receita gerada
- Agente de IA pode gerar e publicar campanhas automaticamente (módulo IA)

```sql
CREATE TABLE campaigns (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(200) NOT NULL,
    type VARCHAR(30) NOT NULL,           -- 'launch', 'sale', 'reactivation', 'seasonal'
    channel VARCHAR(30) NOT NULL,        -- 'whatsapp', 'email', 'marketplace', 'store'
    promotion_id INTEGER REFERENCES promotions(id),
    segment_id INTEGER REFERENCES client_segments(id),
    status VARCHAR(20) DEFAULT 'draft',
    scheduled_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    reach_count INTEGER DEFAULT 0,
    conversion_count INTEGER DEFAULT 0,
    revenue_generated NUMERIC(15,2) DEFAULT 0,
    created_by_agent BOOLEAN DEFAULT FALSE,  -- true se gerada por IA
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 5. Regras de Negócio

- Slug do produto é único por tenant; gerado automaticamente do nome (com normalização de acentos)
- Variação sem atributos é válida para produtos simples
- Preço base nunca zero para produtos ativos (validação no backend)
- Promoção com `ends_at` no passado é desativada automaticamente por job diário
- Cupom de uso único por cliente verifica `uses_count` + `max_uses_per_client` atomicamente
- Produto deletado (soft) mantém histórico em `order_items` e `stock_movements`
- NCM é obrigatório para produtos destinados à emissão de NF (validação futura)
