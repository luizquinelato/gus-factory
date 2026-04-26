<!-- blueprint: db_changes=false seed_data=false -->
# 03. Camada de Banco de Dados

> ✅ **Schema base pré-gerado** em `services/backend/scripts/migrations/0001_initial_schema.py`.
> **Não recriar as tabelas base.** Use este doc como referência de padrões e convenções.
> Tabelas de negócio do projeto são criadas em migrations customizadas a partir de `0003_`.

Este documento define a arquitetura multi-tenant, o padrão de soft delete e as tabelas base obrigatórias do sistema.

## 🗄️ Arquitetura Multi-Tenant

O sistema utiliza o padrão de **Isolamento Lógico (Row-Level Security)**. Todas as tabelas de negócio devem herdar de `BaseEntity` e possuir a coluna `tenant_id`.

### Padrão BaseEntity (SQLAlchemy)

```python
from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class BaseEntity(Base):
    """Classe base para todas as tabelas do sistema."""
    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class AccountBaseEntity(BaseEntity):
    """Classe base para tabelas multi-tenant (vinculadas a uma conta/tenant)."""
    __abstract__ = True

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
```

## 📐 Convenção de Ordem de Colunas (Obrigatório)

Toda tabela do sistema deve seguir esta ordem de colunas, sem exceção:

```
[id] → [campos próprios] → [tenant_id] → [active] → [created_at] → [last_updated_at]
```

| Grupo | Colunas | Regra |
|---|---|---|
| **ID** | `id SERIAL PRIMARY KEY` | Sempre primeiro |
| **Campos próprios** | Todos os campos específicos da entidade | Ordem lógica de negócio |
| **Campos herdados** | `tenant_id`, `active`, `created_at`, `last_updated_at` | Sempre ao final, nesta ordem |

### Exceções previstas
- **Tabelas de auditoria/log imutáveis** (ex: `stock_movements`, `journal_entries`, `order_status_history`): omitem `active` e `last_updated_at` — registros nunca são editados nem desativados
- **Tabelas de junção simples** (ex: `client_segment_members`): mantêm `id` + campos FK + `active` + `created_at`
- **Tabelas de sistema** sem `tenant_id` (ex: `migration_history`, `user_sessions`): seguem `[id] → [campos próprios] → [active] → [created_at] → [last_updated_at]`

### Exemplo canônico
```sql
CREATE TABLE exemplo (
    -- 1. ID
    id SERIAL PRIMARY KEY,
    -- 2. Campos próprios
    name VARCHAR(200) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    parent_id INTEGER REFERENCES exemplo(id),
    notes TEXT,
    -- 3. Campos herdados (sempre ao final, nesta ordem)
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## 🗑️ Soft Delete

Nenhum registro é deletado fisicamente do banco de dados. A exclusão é lógica, utilizando a coluna `active` (herdada de `BaseEntity`).

- **Exclusão**: `UPDATE tabela SET active = false WHERE id = X`
- **Busca**: `SELECT * FROM tabela WHERE active = true`

## 📊 Tabelas Base do Sistema

As tabelas abaixo são obrigatórias e devem ser criadas na migration `0001_initial_schema.py`.

### 1. tenants
Gerencia as contas (empresas) do sistema.
```sql
CREATE TABLE tenants (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    document VARCHAR(50), -- CNPJ/CPF
    tier VARCHAR(50) DEFAULT 'free', -- free, basic, premium, enterprise
    color_schema_mode VARCHAR(20) DEFAULT 'default', -- default, custom
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 2. roles
Tabela de referência que define os roles disponíveis por tenant. Roles com `is_system=true` não podem ser deletados via UI.
`can_read`, `can_write`, `can_delete` são flags de conveniência para exibição na UI de admin — o controle de acesso real é feito pela hierarquia `role_level` via `require_page_access`.
```sql
CREATE TABLE roles (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(50)  NOT NULL,
    description     TEXT,
    is_system       BOOLEAN      DEFAULT FALSE,
    can_read        BOOLEAN      DEFAULT TRUE,
    can_write       BOOLEAN      DEFAULT FALSE,
    can_delete      BOOLEAN      DEFAULT FALSE,
    tenant_id       INTEGER      NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    active          BOOLEAN      DEFAULT TRUE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, name)
);
```
Roles de sistema criados no seed: `admin` (read+write+delete), `user` (read+write), `view` (read).

### 4. users
Gerencia os usuários, suas preferências e preferências de acessibilidade.
As colunas de acessibilidade ficam na tabela `users` (padrão do gus-pulse) — não em tabela separada.
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255),           -- Null se usar SSO
    role VARCHAR(50) DEFAULT 'user',      -- admin, user, view
    is_admin BOOLEAN DEFAULT FALSE,
    auth_provider VARCHAR(50) DEFAULT 'local',  -- local, google, microsoft
    theme_mode VARCHAR(10) DEFAULT 'light',     -- light, dark
    avatar_url VARCHAR(500) DEFAULT NULL,
    -- === Preferências de acessibilidade ===
    accessibility_level VARCHAR(10) DEFAULT 'regular',  -- 'regular', 'AA', 'AAA'
    high_contrast_mode BOOLEAN DEFAULT FALSE,
    reduce_motion BOOLEAN DEFAULT FALSE,
    colorblind_safe_palette BOOLEAN DEFAULT FALSE,
    -- === Campos base ===
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, username),
    UNIQUE(tenant_id, email)
);
CREATE INDEX idx_users_tenant_id ON users(tenant_id);
```

> **`accessibility_level`** é o campo-chave que seleciona qual linha da `tenant_colors` aplicar.
> Ao carregar as cores ativas, use: `WHERE accessibility_level = user.accessibility_level AND theme_mode = user.theme_mode`.

### 5. user_sessions
Gerencia as sessões ativas. Inclui `tenant_id` para permitir queries admin como "matar todas as sessões de um tenant" sem join.
```sql
CREATE TABLE user_sessions (
    id SERIAL PRIMARY KEY,
    token_hash VARCHAR(255) NOT NULL UNIQUE, -- Hash do JWT (nunca o token bruto)
    ip_address VARCHAR(50),
    user_agent TEXT,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 6. user_permissions
Override granular de permissões por usuário (além da matriz de roles).
```sql
CREATE TABLE user_permissions (
    id SERIAL PRIMARY KEY,
    resource VARCHAR(100) NOT NULL, -- ex: 'users', 'reports'
    action VARCHAR(50) NOT NULL, -- ex: 'read', 'write', 'delete'
    is_allowed BOOLEAN NOT NULL, -- true para conceder, false para negar (override)
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, resource, action)
);
```

### 7. pages
Controle de acesso por página. `min_role` define o nível mínimo de role para acessar a página. Editável via UI em `/admin/pages`.

Hierarquia: `view (0) < user (1) < admin (2)` — um usuário acessa se `role_level(user.role) >= role_level(page.min_role)`.
`group_label` agrupa páginas na UI de admin (ex: "Administração", "Relatórios").
```sql
CREATE TABLE pages (
    id SERIAL PRIMARY KEY,
    page_key VARCHAR(100) NOT NULL,           -- identificador único: 'dashboard', 'users'
    label VARCHAR(200) NOT NULL,              -- nome exibido na UI
    route VARCHAR(200) NOT NULL,              -- rota do frontend: '/', '/users'
    group_label VARCHAR(100) DEFAULT NULL,    -- agrupador na UI admin: 'Administração', 'Relatórios'
    min_role VARCHAR(50) NOT NULL DEFAULT 'view'
              CHECK (min_role IN ('view', 'user', 'admin')),
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, page_key)
);
```
Páginas seedadas: `dashboard`, `users`, `reports` → `view`; `color_settings`, `roles`, `page_access` → `admin`.

### 8. system_settings
Configurações chave-valor tipadas por tenant.
```sql
CREATE TABLE system_settings (
    id SERIAL PRIMARY KEY,
    setting_key VARCHAR(100) NOT NULL,
    setting_value TEXT NOT NULL,
    description TEXT,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, setting_key)
);
```

### 9. tenant_colors
Paleta de cores do tenant. **Cada linha** representa uma combinação completa de `color_schema_mode × theme_mode × accessibility_level` — resultando em **12 linhas por tenant** (2 × 2 × 3).

> Nome correto da tabela: `tenant_colors` (blueprint) ou `tenants_colors` (pulse). Padronize no projeto conforme migration gerada.

```sql
CREATE TABLE tenant_colors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    color_schema_mode VARCHAR(10) NOT NULL CHECK (color_schema_mode IN ('default', 'custom')),
    theme_mode        VARCHAR(10) NOT NULL CHECK (theme_mode IN ('light', 'dark')),
    accessibility_level VARCHAR(10) NOT NULL DEFAULT 'regular'
                        CHECK (accessibility_level IN ('regular', 'AA', 'AAA')),
    -- 5 cores da paleta (valores WCAG-calculados para o nível de acessibilidade)
    color1  VARCHAR(7) NOT NULL,  -- #RRGGBB
    color2  VARCHAR(7) NOT NULL,
    color3  VARCHAR(7) NOT NULL,
    color4  VARCHAR(7) NOT NULL,
    color5  VARCHAR(7) NOT NULL,
    -- on-colors: cor do texto/ícone sobre cada cor (WCAG contrast-safe)
    on_color1 VARCHAR(7) NOT NULL,
    on_color2 VARCHAR(7) NOT NULL,
    on_color3 VARCHAR(7) NOT NULL,
    on_color4 VARCHAR(7) NOT NULL,
    on_color5 VARCHAR(7) NOT NULL,
    -- on-gradient: cor do texto sobre cada gradiente (par de cores adjacentes)
    on_gradient_1_2 VARCHAR(7) NOT NULL,
    on_gradient_2_3 VARCHAR(7) NOT NULL,
    on_gradient_3_4 VARCHAR(7) NOT NULL,
    on_gradient_4_5 VARCHAR(7) NOT NULL,
    on_gradient_5_1 VARCHAR(7) NOT NULL,
    -- campos base
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, color_schema_mode, accessibility_level, theme_mode)
);
CREATE INDEX idx_tenant_colors_tenant ON tenant_colors(tenant_id);
CREATE INDEX idx_tenant_colors_lookup ON tenant_colors(tenant_id, color_schema_mode, accessibility_level, theme_mode);
```

**Estrutura das 12 linhas por tenant:**

| `color_schema_mode` | `theme_mode` | `accessibility_level` |
|---|---|---|
| default | light | regular |
| default | light | AA |
| default | light | AAA |
| default | dark | regular |
| default | dark | AA |
| default | dark | AAA |
| custom | light | regular |
| custom | light | AA |
| custom | light | AAA |
| custom | dark | regular |
| custom | dark | AA |
| custom | dark | AAA |

> As cores `regular`, `AA` e `AAA` são calculadas automaticamente a partir das cores base do tenant pelo helper `colorCalculations.ts` (ver `09-color-schema.md`).

### 10. migration_history
Histórico de execuções do banco de dados. Tabela de sistema — sem `tenant_id`.
```sql
CREATE TABLE migration_history (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'applied', -- 'applied' | 'rolled_back'
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    rollback_at TIMESTAMP WITH TIME ZONE
);
```

## 💾 Backup e Restore

Scripts Python em `scripts/database/` fazem backup e restore via `pg_dump`/`pg_restore` usando o container Docker do projeto.

### Backup

```bash
# Da raiz do projeto ou via gus CLI:
python scripts/database/backup.py --prod          # dump PROD → backups/{alias}_prod_{ts}.backup
python scripts/database/backup.py --dev           # dump DEV  → backups/{alias}_dev_{ts}.backup
python scripts/database/backup.py --prod --sql    # + .sql plain text para inspeção

# Via gus CLI (preferencial):
gus dbbackup blueprint               # PROD
gus dbbackup blueprint-dev           # DEV
gus dbbackup all-prod --sql          # PROD de todos os projetos
```

- Formato: **Custom** (`-Fc`) — comprimido, suporta restore seletivo
- Saída: `backups/{alias}_{env}_{timestamp}.backup`
- A pasta `backups/` está no `.gitignore` — nunca commitada (pode conter dados sensíveis)

### Restore

```bash
python scripts/database/restore.py --dev          # lista backups disponíveis interativamente
python scripts/database/restore.py --prod arquivo.backup  # restore direto

# Via gus CLI:
gus dbrestore blueprint-dev          # lista interativa → restore no DEV
gus dbrestore blueprint              # lista interativa → restore no PROD
```

- Usa `--no-owner --no-acl` — permite restaurar backups PROD em ambiente DEV sem erros de permissão (cross-env seguro)
- Exige confirmação digitando o alias do projeto antes de executar o DROP/CREATE
- Detecta e avisa quando o backup é de ambiente diferente do destino (ex: `[PROD] → DEV`)

### 11. integrations
Gerencia as integrações de IA, Embeddings e sistemas externos por tenant.
```sql
CREATE TABLE integrations (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(50) NOT NULL, -- 'OpenAI', 'Anthropic', 'Local Embeddings'
    type VARCHAR(50) NOT NULL, -- 'AI', 'Embedding', 'Data'
    username VARCHAR(255),
    password VARCHAR(255), -- Tokens/passwords encriptados
    base_url TEXT,
    settings JSONB DEFAULT '{}', -- Configurações específicas (modelos, custos, etc)
    fallback_integration_id INTEGER REFERENCES integrations(id) ON DELETE SET NULL,
    logo_filename VARCHAR(255),
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, provider)
);
```
