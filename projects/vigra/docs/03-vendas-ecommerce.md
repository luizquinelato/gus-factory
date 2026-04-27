<!-- blueprint: db_changes=true seed_data=false -->
# Módulo 03 — Vendas & E-Commerce

Gerencia todo o ciclo de vendas: do pedido à expedição. Inclui loja virtual própria e integração com marketplaces externos.

---

## 1. Gestão de Pedidos

### Ciclo de vida do pedido
```
rascunho → confirmado → pagamento_pendente → pago → em_separacao → expedido → entregue
                                                                              → devolvido (parcial/total)
                                     → cancelado (qualquer etapa até expedido)
```

- Pedido pode conter N itens de produtos diferentes com variações
- Desconto por item ou por pedido total (valor fixo ou percentual)
- Frete calculado no pedido (módulo Logística)
- Múltiplos status de pagamento por pedido (parcial, total)
- Histórico completo de mudanças de status com usuário e timestamp

### Tabelas
```sql
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    order_number VARCHAR(30) NOT NULL UNIQUE,  -- gerado: ORD-2026-000001
    client_id INTEGER REFERENCES clients(id),
    salesperson_id INTEGER REFERENCES users(id),   -- vendedor responsável (para comissão)
    channel VARCHAR(30) NOT NULL DEFAULT 'manual',  -- 'manual','store','mercadolivre','amazon'
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    subtotal NUMERIC(15,2) NOT NULL DEFAULT 0,
    discount_amount NUMERIC(15,2) DEFAULT 0,
    shipping_amount NUMERIC(15,2) DEFAULT 0,
    total_amount NUMERIC(15,2) NOT NULL DEFAULT 0,
    notes TEXT,
    warehouse_id INTEGER REFERENCES warehouses(id),
    shipping_address JSONB,
    marketplace_order_id VARCHAR(100),          -- ID do pedido no marketplace externo
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_variation_id INTEGER NOT NULL REFERENCES product_variations(id),
    quantity NUMERIC(15,3) NOT NULL,
    unit_price NUMERIC(15,2) NOT NULL,
    discount_amount NUMERIC(15,2) DEFAULT 0,
    total_price NUMERIC(15,2) NOT NULL,
    cost_at_sale NUMERIC(15,4),                 -- custo médio no momento da venda
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE order_status_history (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    from_status VARCHAR(30),
    to_status VARCHAR(30) NOT NULL,
    changed_by INTEGER REFERENCES users(id),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 2. E-Commerce Próprio (Loja Virtual)

O tenant pode criar e publicar sua própria loja virtual sem código, dentro do Vigra.

### Configurações da loja
- Nome, logo, domínio customizado (CNAME ou subdomínio `{slug}.vigra.shop`)
- Tema de cores (integrado ao sistema de Color Schema do tenant)
- Banners, categorias em destaque, produtos em destaque
- Página de produto com fotos, descrição, variações, estoque em tempo real
- Checkout: endereço de entrega + cálculo de frete + forma de pagamento
- Integração com gateway de pagamento (Stripe / Mercado Pago / Pagar.me)

### Tabelas
```sql
CREATE TABLE stores (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(50) NOT NULL UNIQUE,
    custom_domain VARCHAR(200),
    logo_url TEXT,
    banner_url TEXT,
    primary_color VARCHAR(7),
    meta_title VARCHAR(200),                -- SEO: título da loja nas buscas
    meta_description VARCHAR(500),          -- SEO: descrição da loja nas buscas
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE store_products (
    id SERIAL PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES stores(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    is_featured BOOLEAN DEFAULT FALSE,
    display_order INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 3. Integração com Marketplaces

### Mercado Livre
- OAuth2: tenant autoriza a conta ML dentro do Vigra
- Sync de produtos: publica/atualiza anúncios automaticamente a partir do catálogo
- Sync de pedidos: pedidos do ML entram no Vigra como `channel = 'mercadolivre'`
- Sync de estoque: saída por ML atualiza o saldo em tempo real
- Preço por canal: produto pode ter preço diferente no ML vs loja própria

### Amazon
- API MWS / SP-API: mesmo fluxo do Mercado Livre
- ASIN vinculado ao produto do catálogo
- Relatório de desempenho por ASIN

### Tabela de integrações de marketplace
```sql
CREATE TABLE marketplace_accounts (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    marketplace VARCHAR(30) NOT NULL,     -- 'mercadolivre', 'amazon'
    access_token TEXT,                    -- encriptado
    refresh_token TEXT,                   -- encriptado
    seller_id VARCHAR(100),
    token_expires_at TIMESTAMPTZ,
    last_sync_at TIMESTAMPTZ,
    sync_status VARCHAR(20) DEFAULT 'idle',
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE marketplace_listings (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    marketplace_account_id INTEGER NOT NULL REFERENCES marketplace_accounts(id),
    product_variation_id INTEGER NOT NULL REFERENCES product_variations(id),
    marketplace_sku VARCHAR(100),
    marketplace_listing_id VARCHAR(100),  -- MLB123456 no ML, ASIN na Amazon
    price NUMERIC(15,2),
    status VARCHAR(20) DEFAULT 'active',
    last_sync_at TIMESTAMPTZ,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 4. Formas de Pagamento

- Dinheiro, cartão (crédito/débito), PIX, boleto, link de pagamento
- Parcelamento com ou sem juros (configurável por tenant)
- Pagamento gateway integrado: cada forma de pagamento tem taxa configurável (impacta DRE)
- Conciliação automática: confirmação de pagamento via webhook atualiza status do pedido

---

## 5. Carrinhos Abandonados

Rastreamento de sessões de compra na loja própria que não foram finalizadas. Alimenta o módulo de CRM/IA para campanhas de recuperação automáticas via WhatsApp.

- Carrinho criado ao primeiro item adicionado; atualizado a cada mudança
- Carrinho abandonado: cliente saiu sem finalizar o pedido (sem checkout concluído)
- Job a cada hora marca carrinhos inativos há mais de 30 min como `abandoned`
- Agente de IA ou campanha manual dispara mensagem de recuperação (configurável: 1h, 6h, 24h após abandono)
- Ao finalizar o pedido, o carrinho é marcado como `converted` e vinculado ao pedido

```sql
CREATE TABLE abandoned_carts (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    client_id INTEGER REFERENCES clients(id),
    session_token VARCHAR(100),                -- para visitantes não identificados
    items JSONB NOT NULL,                      -- [{variation_id, quantity, unit_price}]
    subtotal NUMERIC(15,2) NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active', 'abandoned', 'converted', 'expired'
    recovery_sent_at TIMESTAMPTZ,              -- timestamp do último disparo de recuperação
    recovery_attempts INTEGER DEFAULT 0,
    converted_order_id INTEGER REFERENCES orders(id),
    last_activity_at TIMESTAMPTZ DEFAULT NOW(),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 6. Comissões de Vendedores

Para tenants que trabalham com representantes ou vendedores externos, o sistema calcula comissões automaticamente com base nos pedidos finalizados.

- Regras de comissão configuradas por produto, categoria ou global
- Comissão calculada sobre o valor líquido do pedido (após descontos, antes de impostos)
- Gerada automaticamente quando o pedido entra em status `entregue`
- Consolidação mensal: relatório de comissões a pagar por vendedor

```sql
CREATE TABLE commission_rules (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(100) NOT NULL,
    salesperson_id INTEGER REFERENCES users(id),   -- null = regra global para todos
    applies_to VARCHAR(20) DEFAULT 'all',           -- 'all', 'product', 'category'
    target_ids INTEGER[],
    commission_pct NUMERIC(5,2) NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE order_commissions (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    order_id INTEGER NOT NULL REFERENCES orders(id),
    salesperson_id INTEGER NOT NULL REFERENCES users(id),
    base_amount NUMERIC(15,2) NOT NULL,            -- valor base para cálculo
    commission_pct NUMERIC(5,2) NOT NULL,
    commission_amount NUMERIC(15,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- 'pending', 'approved', 'paid'
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 7. Devoluções (RMA)

- Solicitação de devolução por cliente ou iniciada pelo operador
- Motivo obrigatório: defeito, arrependimento, erro de envio, produto errado
- Devolução total ou parcial (por item)
- Ao confirmar devolução: estoque retorna, conta a receber é estornada
- Relatório de taxa de devolução por produto e por canal

---

## 8. Regras de Negócio

- Número do pedido gerado sequencialmente por tenant: `ORD-{ANO}-{SEQUENCIAL}`
- Baixa de estoque ocorre na transição `em_separacao`; não no momento do pagamento
- Reserva de estoque (`reserved_quantity`) ocorre ao entrar em `pagamento_pendente`; liberada no cancelamento
- Cancelamento após expedição gera RMA automático
- Preço no `order_item` é fixado no momento da venda (não muda se catálogo mudar)
- CMV calculado com base em `cost_at_sale` (custo médio no momento da saída do estoque)
- Pedidos de marketplace são importados via fila assíncrona (evita timeout na API)
- Carrinho abandonado: session_token identifica visitantes anônimos; ao logar, carrinho é vinculado ao cliente
- Comissão só é gerada para pedidos com `salesperson_id` preenchido e status `entregue`
