<!-- blueprint: db_changes=false seed_data=false -->
# 03. Database Layer

> ✅ **Base schema pre-generated** in `services/backend/scripts/migrations/0001_initial_schema.py`.
> **Do not recreate the base tables.** Use this doc as a reference for patterns and conventions.
> Project business tables are created in custom migrations starting from `0003_`.

This document defines the multi-tenant architecture, the soft delete pattern and the mandatory base tables.

## 🗄️ Multi-Tenant Architecture

The system uses the **Logical Isolation (Row-Level Security)** pattern. All business tables must inherit from `BaseEntity` and have the `tenant_id` column.

### BaseEntity Pattern (SQLAlchemy)

```python
from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class BaseEntity(Base):
    """Base class for all system tables."""
    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class AccountBaseEntity(BaseEntity):
    """Base class for multi-tenant tables (linked to an account/tenant)."""
    __abstract__ = True

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
```

## 📐 Column Order Convention (Mandatory)

Every system table must follow this column order, without exception:

```
[id] → [tenant_id] → [own fields] → [active] → [created_at] → [last_updated_at]
```

| Group | Columns | Rule |
|---|---|---|
| **ID** | `id SERIAL PRIMARY KEY` | Always first |
| **Tenant** | `tenant_id INTEGER NOT NULL REFERENCES tenants(id)` | Always second, when applicable |
| **Own fields** | All entity-specific fields | Logical business order |
| **Inherited fields** | `active`, `created_at`, `last_updated_at` | Always at the end, in this order |

### Allowed exceptions
- **Immutable audit/log tables** (e.g.: `stock_movements`, `journal_entries`): omit `active` and `last_updated_at`
- **Simple join tables** (e.g.: `client_segment_members`): keep `id` + FK fields + `active` + `created_at`
- **System tables** without `tenant_id` (e.g.: `migration_history`): follow `[id] → [own fields] → [created_at]`

### Canonical example
```sql
CREATE TABLE example (
    -- 1. ID
    id SERIAL PRIMARY KEY,
    -- 2. Tenant
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    -- 3. Own fields
    name VARCHAR(200) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    parent_id INTEGER REFERENCES example(id),
    notes TEXT,
    -- 4. Inherited fields (always at the end, in this order)
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## 🗑️ Soft Delete

No record is physically deleted from the database. Deletion is logical, using the `active` column (inherited from `BaseEntity`).

- **Deletion**: `UPDATE table SET active = false WHERE id = X`
- **Query**: `SELECT * FROM table WHERE active = true`

## 📊 Base System Tables

The 7 tables below are mandatory and must be created in the `0001_initial_schema.py` migration.

### 1. tenants
Manages the accounts (companies) in the system.
```sql
CREATE TABLE tenants (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    document VARCHAR(50), -- CNPJ/CPF
    tier VARCHAR(50) DEFAULT 'free', -- free, basic, premium, enterprise
    color_schema_mode VARCHAR(20) DEFAULT 'default',
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 2. users
Manages users and their preferences.
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255), -- Null if using SSO
    role VARCHAR(50) DEFAULT 'user', -- admin, user, manager
    is_admin BOOLEAN DEFAULT FALSE,
    auth_provider VARCHAR(50) DEFAULT 'local', -- local, google, microsoft
    theme_mode VARCHAR(20) DEFAULT 'system', -- light, dark, system
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_users_tenant_id ON users(tenant_id);
```

### 3. user_sessions
Manages active sessions (refresh tokens).
```sql
CREATE TABLE user_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    ip_address VARCHAR(50),
    user_agent TEXT,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 4. user_permissions
Granular permission overrides per user (beyond the roles matrix).
```sql
CREATE TABLE user_permissions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    resource VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    is_allowed BOOLEAN NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, resource, action)
);
```

### 5. system_settings
Typed key-value settings per tenant.
```sql
CREATE TABLE system_settings (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    setting_key VARCHAR(100) NOT NULL,
    setting_value TEXT NOT NULL,
    description TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, setting_key)
);
```

### 6. tenant_colors
Custom color palette per tenant.
```sql
CREATE TABLE tenant_colors (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    color_schema_mode VARCHAR(20) NOT NULL, -- default, custom
    theme_mode VARCHAR(20) NOT NULL, -- light, dark
    color_name VARCHAR(50) NOT NULL,
    hex_value VARCHAR(7) NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, color_schema_mode, theme_mode, color_name)
);
```

### 7. migration_history
Database execution history.
```sql
CREATE TABLE migration_history (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'applied',
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    rollback_at TIMESTAMP WITH TIME ZONE
);
```

### 8. integrations
Manages AI, Embeddings and external system integrations per tenant.
```sql
CREATE TABLE integrations (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    type VARCHAR(50) NOT NULL, -- 'AI', 'Embedding', 'Data'
    username VARCHAR,
    password VARCHAR,
    base_url TEXT,
    settings JSONB DEFAULT '{}',
    fallback_integration_id INTEGER REFERENCES integrations(id) ON DELETE SET NULL,
    logo_filename VARCHAR(255),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, provider)
);
```

## 💾 Backup and Restore

Python scripts in `scripts/database/` perform backup and restore via `pg_dump`/`pg_restore` using the project's Docker container.

### Backup

```bash
# From the project root or via gus CLI:
python scripts/database/backup.py --prod          # PROD dump → backups/{alias}_prod_{ts}.backup
python scripts/database/backup.py --dev           # DEV dump  → backups/{alias}_dev_{ts}.backup
python scripts/database/backup.py --prod --sql    # + plain .sql for inspection

# Via gus CLI (preferred):
gus dbbackup blueprint               # PROD
gus dbbackup blueprint-dev           # DEV
gus dbbackup all-prod --sql          # PROD of all projects
```

- Format: **Custom** (`-Fc`) — compressed, supports selective restore
- Output: `backups/{alias}_{env}_{timestamp}.backup`
- The `backups/` folder is in `.gitignore` — never committed (may contain sensitive data)

### Restore

```bash
python scripts/database/restore.py --dev          # interactive list of available backups
python scripts/database/restore.py --prod file.backup  # direct restore

# Via gus CLI:
gus dbrestore blueprint-dev          # interactive list → restore to DEV
gus dbrestore blueprint              # interactive list → restore to PROD
```

- Uses `--no-owner --no-acl` — allows restoring PROD backups to a DEV environment without permission errors (safe cross-env)
- Requires confirmation by typing the project alias before DROP/CREATE is executed
- Detects and warns when the backup is from a different environment than the target (e.g., `[PROD] → DEV`)
