<!-- blueprint: db_changes=true seed_data=false -->
# Módulo 08 — Logística

Gerencia o processo de expedição e entrega de pedidos: cálculo de frete, despacho, rastreamento e devoluções (reversa).

---

## 1. Transportadoras

- Cadastro de transportadoras parceiras
- Tipos: Correios, transportadora privada (Jadlog, Loggi, Total Express), motoboy, retirada na loja
- Credenciais de API por transportadora (para cálculo automático de frete e rastreamento)
- Prazo médio de entrega por CEP de origem/destino
- Faixas de preço: por peso, por valor declarado, por região

```sql
CREATE TABLE carriers (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name VARCHAR(100) NOT NULL,         -- 'Correios', 'Jadlog', 'Motoboy SP'
    type VARCHAR(30) NOT NULL,          -- 'correios', 'private', 'motoboy', 'pickup'
    api_key TEXT,                       -- encriptado
    api_url TEXT,
    tracking_url TEXT,                  -- URL de rastreamento com {codigo} como placeholder
    avg_delivery_days INTEGER,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE shipping_rates (
    id SERIAL PRIMARY KEY,
    carrier_id INTEGER NOT NULL REFERENCES carriers(id),
    service_code VARCHAR(50),           -- '04510' para PAC Correios, etc.
    service_name VARCHAR(100),          -- 'PAC', 'SEDEX', 'Econômico'
    origin_state VARCHAR(2),
    destination_state VARCHAR(2),
    min_weight_kg NUMERIC(8,3) DEFAULT 0,
    max_weight_kg NUMERIC(8,3),
    price NUMERIC(10,2) NOT NULL,
    delivery_days INTEGER,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 2. Cálculo de Frete

- Calculado no checkout da loja própria e nos pedidos manuais
- Integração com API dos Correios (e-PAC, Sedex) via credenciais do tenant
- Integração com Jadlog, Loggi (APIs REST)
- Fallback: tabela manual de fretes por estado quando API indisponível
- Frete grátis: por valor mínimo de pedido ou por promoção (módulo Cadastros)
- Retorna múltiplas opções com preço e prazo para o cliente escolher

---

## 3. Expedição

### Fluxo de expedição
```
pedido_pago → separação → embalagem → despacho → em_trânsito → entregue
```

- Operador seleciona transportadora e serviço no pedido
- Sistema gera etiqueta de envio (via API da transportadora)
- Código de rastreio registrado no pedido
- Data de despacho registrada automaticamente
- Pedidos agrupados por depósito para facilitar separação em lote

```sql
CREATE TABLE shipments (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    order_id INTEGER NOT NULL REFERENCES orders(id),
    carrier_id INTEGER NOT NULL REFERENCES carriers(id),
    service_code VARCHAR(50),
    tracking_code VARCHAR(100),
    label_url TEXT,                     -- URL da etiqueta gerada
    shipping_cost NUMERIC(10,2),
    declared_value NUMERIC(15,2),
    status VARCHAR(30) DEFAULT 'pending',
    dispatched_at TIMESTAMPTZ,
    estimated_delivery DATE,
    delivered_at TIMESTAMPTZ,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 4. Rastreamento

- Consulta automática do status de rastreamento via API da transportadora
- Job agendado: atualiza todos os envios em trânsito a cada 2 horas
- Notificação automática ao cliente (WhatsApp ou e-mail) nas transições:
  - Pedido despachado
  - Saiu para entrega
  - Entregue
  - Tentativa de entrega frustrada
- Histórico completo de eventos de rastreamento

```sql
CREATE TABLE shipment_tracking_events (
    id SERIAL PRIMARY KEY,
    shipment_id INTEGER NOT NULL REFERENCES shipments(id),
    status VARCHAR(50) NOT NULL,        -- 'Em trânsito', 'Saiu para entrega', 'Entregue'
    location TEXT,
    description TEXT,
    event_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 5. Logística Reversa (Devoluções)

- Iniciada pelo módulo Vendas (RMA aprovado)
- Tenant gera etiqueta de devolução (via transportadora parceira)
- Envia etiqueta ao cliente por WhatsApp ou e-mail
- Ao receber o produto: inspecção registrada (motivo, condição, fotos)
- Resultado da inspeção: reabastece estoque / descarta / envia para conserto
- Reembolso ou troca liberado apenas após inspeção aprovada

```sql
CREATE TABLE return_requests (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    order_id INTEGER NOT NULL REFERENCES orders(id),
    client_id INTEGER REFERENCES clients(id),
    reason VARCHAR(50) NOT NULL,          -- 'defect', 'regret', 'wrong_item', 'damaged'
    items JSONB NOT NULL,                 -- [{variation_id, quantity}]
    status VARCHAR(30) DEFAULT 'pending', -- 'pending','approved','label_sent','received','inspected','resolved'
    return_label_url TEXT,
    inspection_result VARCHAR(20),        -- 'restock', 'discard', 'repair'
    inspection_notes TEXT,
    resolution VARCHAR(20),               -- 'refund', 'exchange', 'store_credit'
    return_shipment_id INTEGER REFERENCES shipments(id),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 6. Relatórios

- Prazo médio de entrega por transportadora e por região
- Taxa de entrega no prazo (On-Time Delivery Rate)
- Taxa de devolução por transportadora (identifica problemas)
- Custo médio de frete por pedido e por canal de venda
- Pedidos em atraso (despachados mas não entregues após prazo estimado)

---

## 7. Regras de Negócio

- Expedição só disponível para pedidos com status `em_separacao` ou posterior
- Código de rastreio registrado imediatamente após despacho; notificação disparada em background
- Tentativa de entrega frustrada → alerta para operador verificar endereço com cliente
- Produto devolvido só retorna ao estoque após `inspection_result = 'restock'`
- Custo do frete de devolução: configurável por tenant (absorve o custo ou cobra do cliente)
- Entregas para retirada na loja: status vai direto de `em_separacao` para `entregue` ao confirmar retirada
