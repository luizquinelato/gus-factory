<!-- blueprint: db_changes=false seed_data=false -->
# 04. Migrations System

> ✅ **Pre-generated automatically** by `create_project.py`.
> The files `0001_initial_schema.py`, `0002_seed_data.py` and `migration_runner.py` are already in
> `services/backend/scripts/`. **Do not recreate.** Use this doc only as a reference for patterns.
> For business tables, create new migrations starting from `0003_`.

This document defines the custom migration system for the database.

## 🗃️ 1. Migration Structure

Migrations are pure Python scripts, organized in a specific folder:

```text
/services/backend/scripts/
├── migration_runner.py
└── migrations/
    ├── 0001_initial_schema.py
    ├── 0002_seed_data.py
    └── 0003_add_new_feature.py
```

## 📜 2. Migration Pattern

Each migration file must implement two functions: `apply(conn)` and `rollback(conn)`.

```python
# scripts/migrations/0001_initial_schema.py
import logging

logger = logging.getLogger(__name__)

def apply(conn):
    """Applies the migration."""
    logger.info("Applying migration 0001_initial_schema...")
    with conn.cursor() as cursor:
        # Migration History Table (Mandatory)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS migration_history (
                id SERIAL PRIMARY KEY,
                version VARCHAR(50) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'applied',
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                rollback_at TIMESTAMP WITH TIME ZONE
            );
        """)

        # Tenants Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                document VARCHAR(50),
                tier VARCHAR(50) DEFAULT 'free',
                color_schema_mode VARCHAR(20) DEFAULT 'default',
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)

        # Register the migration
        cursor.execute(
            "INSERT INTO migration_history (version, name) VALUES (%s, %s)",
            ("0001", "initial_schema")
        )
    logger.info("Migration 0001_initial_schema applied successfully.")

def rollback(conn):
    """Reverts the migration."""
    logger.info("Rolling back migration 0001_initial_schema...")
    with conn.cursor() as cursor:
        cursor.execute("DROP TABLE IF EXISTS tenants CASCADE;")
        cursor.execute("DELETE FROM migration_history WHERE version = '0001';")
    logger.info("Migration 0001_initial_schema rolled back successfully.")
```

## 🌱 3. Seed Data (Migration 0002)

The `0002_seed_data.py` migration is mandatory to create the initial data needed for the development environment to work.

```python
# scripts/migrations/0002_seed_data.py
import logging
import bcrypt

logger = logging.getLogger(__name__)

def apply(conn):
    logger.info("Applying migration 0002_seed_data...")
    with conn.cursor() as cursor:
        # 1. Default Tenant
        cursor.execute(
            "INSERT INTO tenants (name, tier) VALUES (%s, %s) RETURNING id",
            ("Default Tenant", "premium")
        )
        tenant_id = cursor.fetchone()[0]

        # 2. Admin User
        hashed_password = bcrypt.hashpw("{{ ADMIN_PASSWORD }}".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        cursor.execute(
            """
            INSERT INTO users (tenant_id, name, username, email, password_hash, role, is_admin)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (tenant_id, "{{ ADMIN_NAME }}", "{{ ADMIN_USERNAME }}", "{{ ADMIN_EMAIL }}", hashed_password, "admin", True)
        )

        # Register the migration (upsert — idempotent on re-runs)
        cursor.execute(
            """
            INSERT INTO migration_history (version, name, status)
            VALUES (%s, %s, 'applied')
            ON CONFLICT (version) DO UPDATE SET status = 'applied', rollback_at = NULL
            """,
            ("0002", "seed_data")
        )
    logger.info("Migration 0002_seed_data applied successfully.")

def rollback(conn):
    logger.info("Rolling back migration 0002_seed_data...")
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM users WHERE email = '{{ ADMIN_EMAIL }}';")
        cursor.execute("DELETE FROM tenants WHERE name = 'Default Tenant';")
        cursor.execute("DELETE FROM migration_history WHERE version = '0002';")
    logger.info("Migration 0002_seed_data rolled back successfully.")
```

## 🏃 4. Migration Runner CLI

The `migration_runner.py` supports the following commands:

- `--status`: Lists applied and pending migrations.
- `--apply-all`: Applies all pending migrations in order.
- `--new "name"`: Creates a new migration file with the base template.
- `--rollback-to NNNN`: Rolls back migrations to the specified version.
- `--rollback-to 0000 --confirm`: Rolls back all migrations **and** auto-triggers external cleanups.
- `--qdrant-cleanup [--confirm]`: Deletes all Qdrant collections. Reads `QDRANT_URL` from env (default: `http://localhost:6333`).
- `--rabbit-cleanup [--confirm]`: Deletes all RabbitMQ queues. Primary: Management API. Fallback: blueprint standard.

> Via `gus.ps1`: `gus qdc {proj}` and `gus rbc {proj}` — read ports from `extra_ports` in `ports.yml` and pass `--confirm` automatically.

## 🤖 5. Integration Seed Data (AI and Embeddings)

The `0002_seed_data.py` migration must also include default AI and Embeddings integrations, with `active = false` if `{{ ENABLE_AI_LAYER }}` is disabled.

```python
        # 4. AI Integrations (OpenAI + Fallback)
        import json

        # OpenAI (Primary)
        openai_settings = {
            "model": "{{ AI_MODEL }}",
            "model_config": {"temperature": 0.3, "max_tokens": 1000}
        }
        cursor.execute(
            "INSERT INTO integrations (tenant_id, provider, type, settings, active) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (tenant_id, "OpenAI", "AI", json.dumps(openai_settings), {{ ENABLE_AI_LAYER }})
        )
        openai_id = cursor.fetchone()[0]

        # Anthropic (Fallback)
        anthropic_settings = {
            "model": "claude-3-haiku-20240307",
            "model_config": {"temperature": 0.3, "max_tokens": 1000}
        }
        cursor.execute(
            "INSERT INTO integrations (tenant_id, provider, type, settings, fallback_integration_id, active) VALUES (%s, %s, %s, %s, %s, %s)",
            (tenant_id, "Anthropic", "AI", json.dumps(anthropic_settings), openai_id, {{ ENABLE_AI_LAYER }})
        )
```
