<!-- blueprint: db_changes=false seed_data=false -->
# 04. Sistema de Migrations

> ✅ **Pré-gerado automaticamente** pelo `create_project.py`.
> Os arquivos `0001_initial_schema.py`, `0002_seed_data.py` e `migration_runner.py` já estão em
> `services/backend/scripts/`. **Não recriar.** Use este doc apenas como referência de padrões.
> Para tabelas de negócio, crie novas migrations a partir de `0003_`.

Este documento define o sistema customizado de migrations para o banco de dados.

## 🗃️ 1. Estrutura de Migrations

As migrations são scripts Python puros, organizados em uma pasta específica:

```text
/services/backend/scripts/
├── migration_runner.py
└── migrations/
    ├── 0001_initial_schema.py
    ├── 0002_seed_data.py
    └── 0003_add_new_feature.py
```

## 📜 2. Padrão de Migration

Cada arquivo de migration deve implementar duas funções: `apply(conn)` e `rollback(conn)`.

```python
# scripts/migrations/0001_initial_schema.py
import logging

logger = logging.getLogger(__name__)

def apply(conn):
    """Aplica a migration."""
    logger.info("Aplicando migration 0001_initial_schema...")
    with conn.cursor() as cursor:
        # Tabela de Histórico de Migrations (Obrigatória)
        # Ordem: [id] → [campos próprios] → [created_at] (sem tenant_id — tabela de sistema)
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

        # Tabela de Tenants
        # Ordem: [id] → [campos próprios] → [active, created_at, last_updated_at]
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
        
        # Registra a migration
        cursor.execute(
            "INSERT INTO migration_history (version, name) VALUES (%s, %s)",
            ("0001", "initial_schema")
        )
    logger.info("Migration 0001_initial_schema aplicada com sucesso.")

def rollback(conn):
    """Reverte a migration."""
    logger.info("Revertendo migration 0001_initial_schema...")
    with conn.cursor() as cursor:
        cursor.execute("DROP TABLE IF EXISTS tenants CASCADE;")
        cursor.execute("DELETE FROM migration_history WHERE version = '0001';")
    logger.info("Migration 0001_initial_schema revertida com sucesso.")
```

## 🌱 3. Seed Data (Migration 0002)

A migration `0002_seed_data.py` é obrigatória para criar os dados iniciais necessários para o ambiente de desenvolvimento funcionar.

```python
# scripts/migrations/0002_seed_data.py
import logging
import bcrypt

logger = logging.getLogger(__name__)

def apply(conn):
    logger.info("Aplicando migration 0002_seed_data...")
    with conn.cursor() as cursor:
        # 1. Tenant Padrão
        cursor.execute(
            "INSERT INTO tenants (name, tier) VALUES (%s, %s) RETURNING id",
            ("Tenant Default", "premium")
        )
        tenant_id = cursor.fetchone()[0]

        # 2. Usuário Admin
        hashed_password = bcrypt.hashpw("{{ ADMIN_PASSWORD }}".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        cursor.execute(
            """
            INSERT INTO users (tenant_id, name, username, email, password_hash, role, is_admin)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (tenant_id, "{{ ADMIN_NAME }}", "{{ ADMIN_USERNAME }}", "{{ ADMIN_EMAIL }}", hashed_password, "admin", True)
        )
        
        # 3. Configurações de Sistema
        cursor.execute(
            """
            INSERT INTO system_settings (tenant_id, setting_key, setting_value)
            VALUES (%s, %s, %s)
            """,
            (tenant_id, "font_contrast_threshold", "0.5")
        )

        # 3b. Cores padrão do tenant (mode='default') — Light e Dark
        # Seed para color_schema_mode='default' (paleta do sistema)
        default_colors = [
            # theme_mode, color_schema_mode, color_name, hex_value
            ("light", "default", "color1", "#2862EB"),
            ("light", "default", "color2", "#763DED"),
            ("light", "default", "color3", "#059669"),
            ("light", "default", "color4", "#0EA5E9"),
            ("light", "default", "color5", "#F59E0B"),
            ("dark",  "default", "color1", "#3B82F6"),
            ("dark",  "default", "color2", "#8B5CF6"),
            ("dark",  "default", "color3", "#10B981"),
            ("dark",  "default", "color4", "#38BDF8"),
            ("dark",  "default", "color5", "#FBBF24"),
        ]
        # Seed para color_schema_mode='custom' (idêntico ao default no início — admin personaliza depois)
        custom_colors = [
            ("light", "custom", "color1", "#2862EB"),
            ("light", "custom", "color2", "#763DED"),
            ("light", "custom", "color3", "#059669"),
            ("light", "custom", "color4", "#0EA5E9"),
            ("light", "custom", "color5", "#F59E0B"),
            ("dark",  "custom", "color1", "#3B82F6"),
            ("dark",  "custom", "color2", "#8B5CF6"),
            ("dark",  "custom", "color3", "#10B981"),
            ("dark",  "custom", "color4", "#38BDF8"),
            ("dark",  "custom", "color5", "#FBBF24"),
        ]
        for theme_mode, schema_mode, color_name, hex_value in default_colors + custom_colors:
            cursor.execute(
                """
                INSERT INTO tenant_colors
                    (tenant_id, theme_mode, color_schema_mode, color_name, hex_value)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, color_schema_mode, theme_mode, color_name)
                DO UPDATE SET hex_value = EXCLUDED.hex_value
                """,
                (tenant_id, theme_mode, schema_mode, color_name, hex_value)
            )
        
        # Registra a migration (upsert — idempotente em re-execuções)
        cursor.execute(
            """
            INSERT INTO migration_history (version, name, status)
            VALUES (%s, %s, 'applied')
            ON CONFLICT (version) DO UPDATE SET status = 'applied', rollback_at = NULL
            """,
            ("0002", "seed_data")
        )
    logger.info("Migration 0002_seed_data aplicada com sucesso.")

def rollback(conn):
    logger.info("Revertendo migration 0002_seed_data...")
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM users WHERE email = '{{ ADMIN_EMAIL }}';")
        cursor.execute("DELETE FROM tenants WHERE name = 'Tenant Default';")
        cursor.execute("DELETE FROM migration_history WHERE version = '0002';")
    logger.info("Migration 0002_seed_data revertida com sucesso.")
```

## 🏃 4. Migration Runner CLI

O `migration_runner.py` suporta os seguintes comandos:

- `--status`: Lista as migrations aplicadas e pendentes.
- `--apply-all`: Aplica todas as migrations pendentes em ordem.
- `--new "nome"`: Cria um novo arquivo de migration com o template base.
- `--rollback-to NNNN`: Reverte as migrations até a versão especificada.
- `--rollback-to 0000 --confirm`: Reverte todas as migrations **e** auto-aciona os cleanups externos.
- `--qdrant-cleanup [--confirm]`: Deleta todas as Qdrant collections. Lê `QDRANT_URL` do env (padrão: `http://localhost:6333`).
- `--rabbit-cleanup [--confirm]`: Deleta todas as filas RabbitMQ. Primário: Management API. Fallback: blueprint standard (`{queue_type}_queue_{tier}`, 4 tiers × 3 tipos = 12 filas).

> Via `gus.ps1`: `gus qdc {proj}` e `gus rbc {proj}` — lêem as portas de `extra_ports` no `ports.yml` e passam `--confirm` automaticamente.

## 🤖 4. Seed Data de Integrações (IA e Embeddings)

A migration `0002_seed_data.py` também deve incluir as integrações padrão de IA e Embeddings, com `active = false` se a variável `{{ ENABLE_AI_LAYER }}` estiver desabilitada.

```python
        # 4. Integrações de IA (OpenAI + Fallback)
        import json
        
        # OpenAI (Principal)
        openai_settings = {
            "model": "{{ AI_MODEL }}",
            "model_config": {
                "temperature": 0.3,
                "max_tokens": 1000
            }
        }
        cursor.execute(
            """
            INSERT INTO integrations (tenant_id, provider, type, settings, active)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """,
            (tenant_id, "OpenAI", "AI", json.dumps(openai_settings), {{ ENABLE_AI_LAYER }})
        )
        openai_id = cursor.fetchone()[0]
        
        # Anthropic (Fallback)
        anthropic_settings = {
            "model": "claude-3-haiku-20240307",
            "model_config": {
                "temperature": 0.3,
                "max_tokens": 1000
            }
        }
        cursor.execute(
            """
            INSERT INTO integrations (tenant_id, provider, type, settings, fallback_integration_id, active)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (tenant_id, "Anthropic", "AI", json.dumps(anthropic_settings), openai_id, {{ ENABLE_AI_LAYER }})
        )
        
        # 5. Integração de Embeddings
        embedding_settings = {
            "model": "{{ EMBEDDING_MODEL }}"
        }
        cursor.execute(
            """
            INSERT INTO integrations (tenant_id, provider, type, settings, active)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (tenant_id, "OpenAI Embeddings", "Embedding", json.dumps(embedding_settings), {{ ENABLE_AI_LAYER }})
        )
```
