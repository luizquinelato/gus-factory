# Arquitetura Modular Monolith — Vigra

> **Status**: Aprovado (decisão arquitetural)
> **Data**: 2026-04-27
> **Revisão**: 2026-04-27 — Outbox Pattern, error isolation no Event Bus, import enforcement
> **Escopo**: Backend (`services/backend/app/`) + Frontend (`services/frontend/src/`)

---

## 1. Problema

A estrutura atual do backend é um monolito clássico: routers, services e schemas vivem em pastas planas e compartilhadas. Todos os módulos de negócio (Cadastros, Estoque, Vendas, Financeiro, etc.) coexistiriam no mesmo nível, importando livremente uns dos outros.

Consequências inevitáveis desse caminho:

- **Acoplamento crescente**: Estoque importa de Vendas que importa de Financeiro. Qualquer mudança em um módulo quebra os outros.
- **Deploy monolítico**: não é possível entregar uma correção em Estoque sem rodar os testes de todos os módulos.
- **Propriedade de código diluída**: no futuro, times diferentes não conseguem trabalhar em módulos diferentes sem pisar uns nos outros.
- **Impossibilidade de ativar/desativar módulos por tenant**: um MEI de serviços não precisa de Estoque nem Logística, mas pagaria o custo cognitivo e de performance de carregá-los.

---

## 2. Decisão: Modular Monolith

Um único processo deployável (FastAPI), mas internamente organizado como **módulos independentes** com fronteiras claras e comunicação controlada.

| Aspecto | Monolito Clássico | Modular Monolith | Microserviços |
|---|---|---|---|
| Complexidade operacional | Baixa | Baixa | Alta |
| Isolamento de módulos | Nenhum | Forte (por convenção + lint) | Total (por rede) |
| Custo de infraestrutura | Mínimo | Mínimo | Alto |
| Facilidade de refatorar para microserviço | Difícil | Fácil (módulo já isolado) | N/A |
| Adequação ao estágio atual | ❌ escala errada | ✅ equilíbrio ideal | ❌ overengineering |

**Microserviços agora seriam overengineering.** O Vigra é operado por um time pequeno e não tem volume que justifique a complexidade de rede, service discovery e observability distribuída. O Modular Monolith entrega o isolamento necessário sem o custo operacional.

---

## 3. Estrutura de Diretórios

```
services/backend/app/
├── core/                         # Shared Kernel — usado por TODOS os módulos
│   ├── config.py
│   ├── database.py
│   ├── logging_config.py
│   └── event_bus.py              # Event Bus in-process
├── dependencies/                 # Auth, pagination — infraestrutura transversal
├── schemas/                      # APENAS schemas compartilhados (common.py)
├── modules/                      # UM diretório por módulo de negócio
│   ├── __init__.py               # Module Registry (descobre e carrega módulos ativos)
│   ├── cadastros/
│   │   ├── __init__.py           # register_module(): registra router + eventos
│   │   ├── router.py             # Endpoints REST deste módulo
│   │   ├── schemas.py            # Pydantic models (request/response)
│   │   ├── service.py            # Lógica de negócio + interface pública
│   │   └── events.py             # Eventos emitidos e handlers consumidos
│   ├── clientes/
│   │   ├── __init__.py
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   └── events.py
│   ├── estoque/
│   ├── compras/
│   ├── vendas/
│   ├── financeiro/
│   ├── logistica/
│   ├── contabilidade/
│   └── ia/
├── routers/                      # Routers do Core (auth, users, health, colors)
├── services/                     # Services do Core (color, user)
└── main.py
```

### Regras de organização

1. **Cada módulo é uma pasta autossuficiente** dentro de `modules/`. Contém router, schemas, service e events.
2. **Migrations ficam centralizadas** em `scripts/migrations/` (runner único), mas cada arquivo pertence a um módulo e é prefixado adequadamente.
3. **Routers e services do Core** (auth, users, health, colors, settings) permanecem em `app/routers/` e `app/services/` — são infraestrutura compartilhada, não módulos de negócio.


---

## 4. Três Pilares do Desacoplamento

### 4.1. Isolamento de Imports

**Regra absoluta**: código dentro de `modules/estoque/` **nunca importa** de `modules/vendas/` (ou qualquer outro módulo).

Imports permitidos:

| De | Para | Permitido? |
|---|---|---|
| `modules/vendas/` | `core/*` | ✅ Sim |
| `modules/vendas/` | `dependencies/*` | ✅ Sim |
| `modules/vendas/` | `schemas/common.py` | ✅ Sim |
| `modules/vendas/` | `modules/cadastros/service.py` | ✅ Sim (via interface pública) |
| `modules/vendas/` | `modules/estoque/service.py` | ❌ **Não** (usa Event Bus) |
| `modules/vendas/` | `modules/estoque/router.py` | ❌ **Nunca** |

A única exceção é quando o módulo B expõe uma **interface pública de leitura** (métodos do service) que o módulo A precisa para compor dados. Mesmo assim, o módulo A depende do contrato (assinatura do método), não da implementação.

#### Enforcement automático (pre-commit hook)

Sem automação, essa regra degrada em semanas. O hook abaixo rejeita commits com imports cruzados proibidos:

```python
# scripts/check_module_imports.py  (rodado no pre-commit)
import ast, sys
from pathlib import Path

MODULES_DIR = Path("services/backend/app/modules")
errors = []

for py_file in MODULES_DIR.rglob("*.py"):
    module_name = py_file.parts[py_file.parts.index("modules") + 1]
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        name = getattr(node, "module", "") or ""
        # Detecta import de outro módulo que não seja via service.py
        if "app.modules." in name:
            target = name.split("app.modules.")[1].split(".")[0]
            allowed = name.endswith(".service")
            if target != module_name and not allowed:
                errors.append(f"{py_file}:{node.lineno} — import proibido: {name}")

if errors:
    print("❌ Imports cruzados proibidos entre módulos:")
    for e in errors: print(f"  {e}")
    sys.exit(1)
```

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: check-module-imports
        name: Verifica isolamento de módulos
        entry: python scripts/check_module_imports.py
        language: python
        pass_filenames: false
        always_run: true
```

### 4.2. Comunicação por Eventos (Event Bus)

Quando um módulo precisa **reagir** a algo que aconteceu em outro, usa eventos assíncronos:

```
Vendas confirma pedido → emite evento "order.confirmed"
    ├── Estoque escuta → reserva estoque
    ├── Financeiro escuta → cria conta a receber
    └── Logística escuta → prepara expedição
```

#### Dois modos de emissão

| Modo | Método | Garantia | Quando usar |
|---|---|---|---|
| **Best-effort** | `EventBus.emit()` | In-process, sem retry | Eventos de UI, cache, notificações |
| **Confiável** | `EventBus.emit_reliable()` | Transacional via Outbox | Eventos financeiros, estoque, contabilidade |

#### Implementação: in-process com isolamento de falha por handler

```python
# core/event_bus.py
import asyncio, json, logging
from collections.abc import Callable
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

class EventBus:
    _handlers: dict[str, list[Callable]] = {}

    @classmethod
    def subscribe(cls, event_name: str, handler: Callable) -> None:
        cls._handlers.setdefault(event_name, []).append(handler)

    @classmethod
    async def emit(cls, event_name: str, payload: dict) -> None:
        """Best-effort: erros num handler NÃO bloqueiam os demais."""
        for handler in cls._handlers.get(event_name, []):
            try:
                await handler(payload)
            except Exception as exc:
                logger.error(
                    "EventBus handler '%s' falhou para '%s': %s",
                    handler.__name__, event_name, exc, exc_info=True,
                )

    @classmethod
    async def emit_reliable(
        cls,
        event_name: str,
        payload: dict,
        db: AsyncSession,
        tenant_id: int,              # obrigatório — isola eventos por tenant
    ) -> None:
        """Transacional: grava o evento na mesma transação do chamador.
        O OutboxProcessor entrega após o commit — garante consistência.
        tenant_id é OBRIGATÓRIO — nunca omitir."""
        await db.execute(
            text("""
                INSERT INTO events_outbox (event_name, payload, tenant_id)
                VALUES (:name, CAST(:payload AS jsonb), :tenant_id)
            """),
            {"name": event_name, "payload": json.dumps(payload), "tenant_id": tenant_id},
        )
        # NÃO faz commit — a transação do chamador controla isso.
```

**Exemplo de uso em um módulo de negócio:**

```python
# modules/vendas/router.py
@router.post("/orders/{order_id}/confirm")
async def confirm_order(
    order_id: int,
    db: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_authentication),
):
    tenant_id = user["tenant_id"]

    # 1. Atualiza o pedido (mesmo db session = mesma transação)
    await db.execute(
        text("UPDATE orders SET status = 'confirmed' WHERE id = :id AND tenant_id = :tid"),
        {"id": order_id, "tid": tenant_id},
    )

    # 2. Grava o evento no outbox dentro da MESMA transação
    await EventBus.emit_reliable(
        "order.confirmed",
        {"order_id": order_id, "tenant_id": tenant_id},
        db,
        tenant_id=tenant_id,   # ← obrigatório, nunca omitir
    )

    # 3. Commit único — pedido + evento persistem juntos (ou rollback juntos)
    await db.commit()
    return {"detail": "Pedido confirmado."}
```

#### Regra de escolha: emit vs emit_reliable

```
├── O evento cruza fronteira financeira?         → emit_reliable
│     ex: order.confirmed, payment.confirmed, purchase.received
├── O evento modifica estoque efetivamente?      → emit_reliable
│     ex: order.paid, order.cancelled, order.delivered
└── O evento é informativo/cache/notificação?    → emit (best-effort)
      ex: product.updated, client.created, stock.low (alerta)
```

#### Evolução futura: RabbitMQ

Quando o volume justificar, `OutboxProcessor` troca a entrega local por publish no RabbitMQ. **Nenhum módulo muda** — só o transporte interno do processor.

### 4.3. Outbox Pattern — Consistência Transacional

**Problema**: se `order.confirmed` chama Estoque e Financeiro via `emit()` em sequência e Financeiro falha após Estoque já ter commitado, o estado fica inconsistente. Para dados financeiros isso é inaceitável.

**Solução**: o `emit_reliable()` grava o evento na tabela `events_outbox` **dentro da mesma transação** que gerou o pedido. Se o pedido falhar, o evento some junto (rollback). Se confirmar, o evento persiste e será entregue com garantia.

```
┌─────────────────────────────────────────────────────┐
│  BEGIN TRANSACTION                                   │
│    INSERT INTO orders ...          (pedido)          │
│    INSERT INTO events_outbox ...   (evento)          │
│  COMMIT                                              │
│  ──────────────────────────────────────────────────  │
│  OutboxProcessor (background, a cada 2s):            │
│    SELECT ... FOR UPDATE SKIP LOCKED                 │
│    → EventBus.emit("order.confirmed", payload)       │
│    → UPDATE events_outbox SET processed_at = NOW()   │
└─────────────────────────────────────────────────────┘
```

#### Tabela `events_outbox`

Convenção de ordem: `[id] → [campos próprios] → [tenant_id] → [created_at]`.
Sem `active` nem `last_updated_at` — tabela append-only com timestamps explícitos.

```sql
CREATE TABLE events_outbox (
    -- 1. ID
    id           BIGSERIAL    PRIMARY KEY,
    -- 2. Campos próprios
    event_name   VARCHAR(100) NOT NULL,
    payload      JSONB        NOT NULL DEFAULT '{}',
    attempts     SMALLINT     NOT NULL DEFAULT 0,
    max_attempts SMALLINT     NOT NULL DEFAULT 3,
    last_error   TEXT,
    processed_at TIMESTAMPTZ,          -- NULL = pendente ou dead-letter
    failed_at    TIMESTAMPTZ,          -- NOT NULL = esgotou tentativas (dead-letter)
    -- 3. Campos herdados
    tenant_id    INTEGER      NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_events_outbox_tenant  ON events_outbox (tenant_id);
-- Índice parcial: cobre apenas pendentes — eficiente com histórico grande
CREATE INDEX idx_events_outbox_pending ON events_outbox (tenant_id, created_at)
    WHERE processed_at IS NULL AND failed_at IS NULL;
```

#### OutboxProcessor (background asyncio task)

Roda no lifespan do FastAPI. A cada `POLL_INTERVAL` segundos:
1. `SELECT FOR UPDATE SKIP LOCKED` — seguro para múltiplas instâncias
2. Entrega via `EventBus.emit()` (handlers in-process)
3. Marca `processed_at` ou incrementa `attempts` / seta `failed_at`

Eventos com `failed_at IS NOT NULL` ficam na tabela para auditoria e reprocessamento manual.

### 4.4. Contratos entre Módulos (Service Interface)

Se o módulo de Vendas precisa do preço de um produto, ele **não faz query na tabela `products`**. Ele chama o contrato público do módulo Cadastros:

```python
# modules/cadastros/service.py — interface pública
class CadastrosService:
    async def get_variation_price(self, variation_id: int, tenant_id: int) -> Decimal: ...
    async def get_product_summary(self, product_id: int, tenant_id: int) -> ProductSummaryDTO: ...
```

O módulo de Vendas depende da **assinatura**, não da implementação interna. Se Cadastros mudar a estrutura da tabela `products`, o contrato segue estável.

---

## 5. Mapa de Eventos

| Evento | Emitido por | Consumido por | Modo |
|---|---|---|---|
| `product.created` | Cadastros | Estoque (cria `stock_item` zerado) | `emit` |
| `product.updated` | Cadastros | Vendas (invalida cache de preço) | `emit` |
| `order.confirmed` | Vendas | Estoque (reserva qty), Financeiro (cria AR), Logística | `emit_reliable` ⚠️ |
| `order.paid` | Vendas | Estoque (baixa efetiva), Logística (habilita expedição) | `emit_reliable` ⚠️ |
| `order.cancelled` | Vendas | Estoque (libera reserva), Financeiro (cancela AR) | `emit_reliable` ⚠️ |
| `order.delivered` | Logística | Vendas (atualiza status), Financeiro (confirma receita) | `emit_reliable` ⚠️ |
| `purchase.received` | Compras | Estoque (entrada de NF), Financeiro (cria AP) | `emit_reliable` ⚠️ |
| `stock.low` | Estoque | IA/Agentes (alerta, gera rascunho de PO) | `emit` |
| `payment.confirmed` | Financeiro | Contabilidade (gera lançamento contábil) | `emit_reliable` ⚠️ |
| `client.created` | Clientes | IA (onboarding, segmentação automática) | `emit` |

> ⚠️ `emit_reliable` = grava em `events_outbox` dentro da transação → entregue pelo `OutboxProcessor`

---

## 6. Feature Flags por Tenant

Nem todo tenant precisa de todos os módulos. Um MEI de serviços não precisa de Estoque nem Logística.

O Module Registry lê os módulos habilitados para o tenant e:
- **Backend**: só registra os routers dos módulos ativos
- **Frontend**: só exibe as páginas e itens de sidebar dos módulos ativos
- **Event Bus**: handlers de módulos inativos não são registrados

```python
# Configuração por tenant (tabela system_settings)
# setting_key = "enabled_modules"
# setting_value = '["cadastros", "clientes", "vendas", "financeiro"]'
# Estoque, Compras, Logística, Contabilidade, IA → desativados para este tenant
```

---

## 7. Migrations

As migrations continuam centralizadas em `scripts/migrations/` (runner único), mas seguem uma convenção de prefixo por módulo:

| Faixa | Módulo |
|---|---|
| `0001`–`0002` | **Framework** — Core (schema base + seed) — **não modificar** |
| `0003` | **Framework** — ETL schema (`etl_job_errors`) — **não modificar** |
| `0004` | **Framework** — Event Bus (`events_outbox`) — **não modificar** |
| `0005`–`0009` | Cadastros |
| `0010`–`0019` | Clientes & CRM |
| `0020`–`0029` | Compras & Fornecedores |
| `0030`–`0039` | Estoque |
| `0040`–`0049` | Vendas & E-Commerce |
| `0050`–`0059` | Financeiro |
| `0060`–`0069` | Logística |
| `0070`–`0079` | Contabilidade |
| `0080`–`0089` | IA & Agentes |
| `0090`–`0099` | Reservado (futuro) |

Isso permite que times trabalhem em faixas diferentes sem conflito de numeração.

---

## 8. Ordem de Implementação (Jornada do Usuário)

| Fase | Módulo | Doc base | Depende de |
|---|---|---|---|
| **1** | Cadastros | `05-cadastros.md` | Core (já existe) |
| **2a** | Clientes & CRM | `04-clientes-crm.md` | Cadastros |
| **2b** | Compras & Fornecedores | `06-compras-fornecedores.md` | Cadastros |
| **3a** | Estoque | `02-estoque.md` | Cadastros, Compras |
| **3b** | Vendas & E-Commerce | `03-vendas-ecommerce.md` | Cadastros, Clientes, Estoque |
| **4a** | Financeiro | `01-financeiro.md` | Vendas, Compras, Clientes |
| **4b** | Logística | `08-logistica.md` | Vendas, Estoque |
| **5a** | Contabilidade | `07-contabilidade.md` | Financeiro |
| **5b** | IA & Agentes | `09-ia-agentes.md` | Todos (camada transversal) |

A ordem prioriza a jornada natural do MEI: primeiro cadastra o que vende, depois para quem vende, depois controla estoque e vende, depois controla o dinheiro, depois a contabilidade e por fim a inteligência sobre tudo.

---

## 9. Frontend — Organização Modular

O frontend espelha a estrutura modular do backend:

```
services/frontend/src/
├── components/             # Componentes globais (Sidebar, AppShell, etc.)
├── contexts/               # Contexts globais (Auth, Theme)
├── config/                 # Configurações globais
├── services/               # apiClient e services globais
├── utils/                  # Utilitários globais
├── modules/                # UM diretório por módulo de negócio
│   ├── cadastros/
│   │   ├── pages/          # CadastrosPage, ProductFormPage, etc.
│   │   ├── components/     # ProductCard, CategoryTree, etc.
│   │   ├── hooks/          # useProdutos, useCategorias, etc.
│   │   └── services/       # cadastrosApi.ts
│   ├── clientes/
│   ├── estoque/
│   ├── vendas/
│   ├── financeiro/
│   ├── logistica/
│   ├── contabilidade/
│   └── ia/
├── pages/                  # Páginas do Core (Login, Home, Profile, Colors, etc.)
└── types/                  # Tipos globais
```

A Sidebar e o React Router carregam rotas condicionalmente com base nos módulos ativos do tenant.

---

## 10. Resumo de Decisões

| Decisão | Escolha | Motivo |
|---|---|---|
| Topologia | Modular Monolith | Simples de operar agora; fatiável em microserviços depois |
| Eventos best-effort | `EventBus.emit()` | In-process, zero infra, erros isolados por handler |
| Eventos confiáveis | `EventBus.emit_reliable()` + Outbox | Consistência transacional para eventos financeiros |
| Transporte futuro | Substituir `OutboxProcessor` por RabbitMQ | Nenhum módulo muda — só o transporte interno |
| Comunicação de leitura | Service Interface (contrato público) | Módulo nunca acessa tabela de outro diretamente |
| Isolamento de imports | Pre-commit hook automático | Sem automação, a regra degrada em semanas |
| Migrations | Centralizadas, prefixo por módulo | Runner único, sem conflito de numeração entre times |
| Feature flags | Por tenant via `system_settings` | Nem todo MEI precisa de Logística ou IA |
| Frontend | Pasta `modules/` espelhando backend | Mesma fronteira de isolamento no client |

---

## 9. Pontos de Atenção e Dívidas Implícitas

Cinco áreas que a arquitetura assume mas que precisam de disciplina ativa para não virarem bugs silenciosos.

### 9.1. Tenant isolation nos handlers (⚠️ risco de cross-tenant leak)

Handlers in-process **não têm middleware automático de tenant**. O `OutboxProcessor` injeta `__tenant_id__` no payload antes de chamar o handler — mas o handler precisa usá-lo.

**Regra:** handlers de `emit_reliable` SEMPRE filtram queries por `payload["__tenant_id__"]`. Nunca por um `tenant_id` lido de outra fonte, nunca omitido.

```python
# ✅ Correto — usa o tenant injetado pelo OutboxProcessor
async def on_order_confirmed(payload: dict) -> None:
    tenant_id = payload["__tenant_id__"]  # fonte de verdade
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE stock_items SET reserved = reserved + :qty WHERE tenant_id = :tid"),
            {"qty": payload["qty"], "tid": tenant_id},
        )
        await db.commit()

# ❌ Errado — lê tenant_id do payload de negócio (pode estar ausente ou errado)
async def on_order_confirmed(payload: dict) -> None:
    tenant_id = payload.get("tenant_id")  # não use
```

Para handlers de `emit()` direto (sem Outbox), o chamador é responsável por incluir `tenant_id` no payload — o processor não injeta porque não existe linha no outbox.

### 9.2. Ordem de execução de handlers (fragilidade de import)

`EventBus._handlers` é um `dict[str, list[Callable]]` — a ordem é a de subscrição, determinada pela ordem de `import app.modules.*` em `main.py`.

**Consequência:** se dois handlers do mesmo evento assumem uma sequência, ela depende da ordem de import — frágil e sem enforcement.

**Postura correta:** handlers de um mesmo evento devem ser **totalmente independentes**. Estoque não pode assumir que Financeiro já rodou quando seu handler é chamado para `order.confirmed`. Cada handler responde ao mesmo fato de forma autônoma.

Se uma sequência real for necessária, modelar como dois eventos distintos: `order.confirmed` → `stock.reserved` → `financeiro.ar_created`.

### 9.3. Idempotência dos handlers (⚠️ at-least-once — efeito duplo é possível)

O `OutboxProcessor` garante **at-least-once delivery**. Se o processo crashar entre `EventBus.emit()` e `UPDATE events_outbox SET processed_at` (janela de milissegundos), o evento será entregue de novo no próximo ciclo.

**Consequência:** um handler não idempotente duplica o efeito — reserva estoque duas vezes, gera dois lançamentos financeiros, etc.

**O `OutboxProcessor` injeta `__event_id__`** (ID da linha em `events_outbox`) no payload. Use-o como chave de idempotência:

```python
async def on_order_confirmed(payload: dict) -> None:
    event_id  = payload["__event_id__"]   # chave de idempotência
    tenant_id = payload["__tenant_id__"]  # isolamento multi-tenant
    order_id  = payload["order_id"]

    async with AsyncSessionLocal() as db:
        # INSERT idempotente — segunda chamada com mesmo event_id é no-op
        await db.execute(
            text("""
                INSERT INTO stock_reservations (outbox_event_id, order_id, tenant_id, reserved_at)
                VALUES (:event_id, :order_id, :tenant_id, NOW())
                ON CONFLICT (outbox_event_id) DO NOTHING
            """),
            {"event_id": event_id, "order_id": order_id, "tenant_id": tenant_id},
        )
        await db.commit()
```

**Convenção:** tabelas afetadas por `emit_reliable` devem ter coluna `outbox_event_id BIGINT UNIQUE` e o `INSERT ... ON CONFLICT (outbox_event_id) DO NOTHING`.

### 9.4. AsyncSession no Service Interface

Quando Vendas chama `CadastrosService.get_variation_price(variation_id, tenant_id)`, a sessão de banco precisa ser passada pelo chamador:

```python
# modules/vendas/router.py
@router.post("/orders")
async def create_order(db: AsyncSession = Depends(get_db_session), ...):
    price = await CadastrosService(db).get_variation_price(variation_id, tenant_id)
```

**Implicações:**
- A query de Cadastros roda **dentro da transação de Vendas** — cuidado com locks longos.
- Se Cadastros precisar de uma transação separada (ex: leitura em réplica), deve receber sua própria sessão.
- Para leituras simples (sem escrita), isso é aceitável e sem risco de deadlock.

**Regra:** Service Interfaces usadas por outros módulos são **somente leitura** (métodos `get_*`). Escrita entre módulos sempre via `emit_reliable`, nunca via chamada direta de service.

### 9.5. Module Registry: import-time vs runtime

Registrar módulos via `import app.modules.X` em `main.py` é simples e correto para a escala atual (~9 módulos). O módulo inteiro é carregado no processo independente das feature flags do tenant.

**Trade-off aceito:** a feature flag por tenant filtra rotas e handlers em runtime, mas o código continua na memória. Para 9 módulos em Python, o custo de memória é negligível.

**Limitação:** habilitar ou desabilitar um módulo para um tenant específico exige deploy (ou restart). Não há hot-reload de módulos. Aceitável para V1 — reavalie quando ultrapassar ~20 módulos ou quando a necessidade de ativação dinâmica por tenant for frequente.

---

## 10. Caminho de Evolução Documentado

A arquitetura pavimenta dois saltos explícitos sem reescrita de módulos:

| De | Para | O que muda |
|---|---|---|
| `EventBus.emit_reliable` (in-process) | RabbitMQ publish | Apenas o transporte interno do `OutboxProcessor` — módulos não mudam |
| `modules/<x>/` (in-process) | Microsserviço extraído | A pasta vira repo próprio; chamadas a `<x>Service` viram HTTP/gRPC; eventos passam pela fila |

O custo dessa flexibilidade é disciplina diária: se o pre-commit hook for desativado por uma semana, imports cruzados aparecem e a possibilidade de extração some. O documento é categórico:

> *"Sem automação, essa regra degrada em semanas."*

---

## 11. O Que Torna Este Modular Monolith Funcional

Três decisões fazem o sistema funcionar como prometido:

1. **Outbox Pattern transacional** — torna eventos confiáveis sem broker externo, garantindo ACID em toda fronteira financeira. Sem isso, `emit_reliable` é apenas `emit` com outro nome.

2. **Pre-commit hook de imports** — torna a regra de isolamento *enforced*, não aspiracional. Sem automação, a fronteira entre módulos some em semanas.

3. **Service Interface estrita** — única ponte síncrona entre módulos, com contrato versionado pela assinatura do método. Sem isso, módulos acessam tabelas uns dos outros e a possibilidade de extração futura desaparece.

Sem qualquer uma das três, a arquitetura colapsa de volta no monolito clássico que ela explicitamente rejeita na seção 1.
