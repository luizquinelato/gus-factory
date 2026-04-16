#!/usr/bin/env python3
"""
Migration 0001: Initial Schema
================================
Project : {{ PROJECT_NAME }}
Creates : migration_history, tenants, users, user_sessions,
          user_permissions, system_settings, tenant_colors
          + integrations table (always created; rows activated by ENABLE_AI_LAYER)

Runner registers this migration in migration_history after apply() succeeds.
Do NOT register inside apply() — the runner handles it.
"""
import logging

logger = logging.getLogger(__name__)


def apply(conn):
    """Create all base tables."""
    logger.info("Applying 0001_initial_schema...")
    with conn.cursor() as cur:

        # 1. migration_history (no tenant_id — system table)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS migration_history (
                id          SERIAL PRIMARY KEY,
                version     VARCHAR(50)  NOT NULL UNIQUE,
                name        VARCHAR(255) NOT NULL,
                status      VARCHAR(20)  NOT NULL DEFAULT 'applied',
                applied_at  TIMESTAMPTZ  DEFAULT NOW(),
                rollback_at TIMESTAMPTZ
            );
        """)

        # 2. tenants
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                id                SERIAL PRIMARY KEY,
                name              VARCHAR(255) NOT NULL,
                document          VARCHAR(50),
                tier              VARCHAR(50)  DEFAULT 'free',
                color_schema_mode VARCHAR(20)  DEFAULT 'default',
                active            BOOLEAN      DEFAULT TRUE,
                created_at        TIMESTAMPTZ  DEFAULT NOW(),
                last_updated_at   TIMESTAMPTZ  DEFAULT NOW()
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tenants_active ON tenants(active);")

        # 3. users
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              SERIAL PRIMARY KEY,
                tenant_id       INTEGER      NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                name            VARCHAR(255) NOT NULL,
                username        VARCHAR(100) NOT NULL,
                email           VARCHAR(255) NOT NULL,
                password_hash   VARCHAR(255),
                role            VARCHAR(50)  DEFAULT 'user',
                is_admin        BOOLEAN      DEFAULT FALSE,
                auth_provider   VARCHAR(50)  DEFAULT 'local',
                theme_mode      VARCHAR(20)  DEFAULT 'system',
                active          BOOLEAN      DEFAULT TRUE,
                created_at      TIMESTAMPTZ  DEFAULT NOW(),
                last_updated_at TIMESTAMPTZ  DEFAULT NOW(),
                UNIQUE(tenant_id, username),
                UNIQUE(tenant_id, email)
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email     ON users(email);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_active    ON users(active);")

        # 4. user_sessions
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id              SERIAL PRIMARY KEY,
                user_id         INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash      VARCHAR(255) NOT NULL UNIQUE,
                ip_address      VARCHAR(50),
                user_agent      TEXT,
                expires_at      TIMESTAMPTZ  NOT NULL,
                active          BOOLEAN      DEFAULT TRUE,
                created_at      TIMESTAMPTZ  DEFAULT NOW(),
                last_updated_at TIMESTAMPTZ  DEFAULT NOW()
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id    ON user_sessions(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_token_hash ON user_sessions(token_hash);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_active     ON user_sessions(active);")

        # 5. user_permissions
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_permissions (
                id              SERIAL PRIMARY KEY,
                user_id         INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                resource        VARCHAR(100) NOT NULL,
                action          VARCHAR(50)  NOT NULL,
                is_allowed      BOOLEAN      NOT NULL,
                active          BOOLEAN      DEFAULT TRUE,
                created_at      TIMESTAMPTZ  DEFAULT NOW(),
                last_updated_at TIMESTAMPTZ  DEFAULT NOW(),
                UNIQUE(user_id, resource, action)
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_permissions_user_id  ON user_permissions(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_permissions_resource ON user_permissions(resource);")

        # 6. system_settings
        cur.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                id              SERIAL PRIMARY KEY,
                tenant_id       INTEGER      NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                setting_key     VARCHAR(100) NOT NULL,
                setting_value   TEXT         NOT NULL,
                description     TEXT,
                active          BOOLEAN      DEFAULT TRUE,
                created_at      TIMESTAMPTZ  DEFAULT NOW(),
                last_updated_at TIMESTAMPTZ  DEFAULT NOW(),
                UNIQUE(tenant_id, setting_key)
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_settings_tenant_id ON system_settings(tenant_id);")

        # 7. tenant_colors
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tenant_colors (
                id                SERIAL PRIMARY KEY,
                tenant_id         INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                color_schema_mode VARCHAR(20) NOT NULL,
                theme_mode        VARCHAR(20) NOT NULL,
                color_name        VARCHAR(50) NOT NULL,
                hex_value         VARCHAR(7)  NOT NULL,
                active            BOOLEAN     DEFAULT TRUE,
                created_at        TIMESTAMPTZ DEFAULT NOW(),
                last_updated_at   TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, color_schema_mode, theme_mode, color_name)
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tenant_colors_tenant_id ON tenant_colors(tenant_id);")

        # 8. integrations (always created; rows active/inactive controlled by seed)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS integrations (
                id                      SERIAL PRIMARY KEY,
                tenant_id               INTEGER      NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                provider                VARCHAR(50)  NOT NULL,
                type                    VARCHAR(50)  NOT NULL,
                username                VARCHAR(255),
                password                VARCHAR(255),
                base_url                TEXT,
                settings                JSONB        DEFAULT '{}',
                fallback_integration_id INTEGER      REFERENCES integrations(id) ON DELETE SET NULL,
                logo_filename           VARCHAR(255),
                active                  BOOLEAN      DEFAULT TRUE,
                created_at              TIMESTAMPTZ  DEFAULT NOW(),
                last_updated_at         TIMESTAMPTZ  DEFAULT NOW(),
                UNIQUE(tenant_id, provider)
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_integrations_tenant_id ON integrations(tenant_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_integrations_type      ON integrations(type);")

    logger.info("0001_initial_schema applied.")


def rollback(conn):
    """Drop all base tables in reverse FK order."""
    logger.info("Rolling back 0001_initial_schema...")
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS integrations      CASCADE;")
        cur.execute("DROP TABLE IF EXISTS tenant_colors     CASCADE;")
        cur.execute("DROP TABLE IF EXISTS system_settings  CASCADE;")
        cur.execute("DROP TABLE IF EXISTS user_permissions CASCADE;")
        cur.execute("DROP TABLE IF EXISTS user_sessions    CASCADE;")
        cur.execute("DROP TABLE IF EXISTS users             CASCADE;")
        cur.execute("DROP TABLE IF EXISTS tenants           CASCADE;")
        cur.execute("DROP TABLE IF EXISTS migration_history CASCADE;")
    logger.info("0001_initial_schema rolled back.")
