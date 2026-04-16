#!/usr/bin/env python3
"""
Migration 0001: Initial Schema
================================
Project : SaaS Blueprint V1
Creates : migration_history, tenants, roles, users, user_sessions,
          user_permissions, role_permissions, system_settings, tenant_colors,
          pages, audit_logs, integrations

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

        # 3. roles (tabela de referência — define os roles disponíveis por tenant)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                id              SERIAL PRIMARY KEY,
                name            VARCHAR(50)  NOT NULL,
                description     TEXT,
                is_system       BOOLEAN      DEFAULT FALSE,
                can_read        BOOLEAN      DEFAULT TRUE,
                can_write       BOOLEAN      DEFAULT FALSE,
                can_delete      BOOLEAN      DEFAULT FALSE,
                tenant_id       INTEGER      NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                active          BOOLEAN      DEFAULT TRUE,
                created_at      TIMESTAMPTZ  DEFAULT NOW(),
                last_updated_at TIMESTAMPTZ  DEFAULT NOW(),
                UNIQUE(tenant_id, name)
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_roles_tenant_id ON roles(tenant_id);")

        # 5. users
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              SERIAL PRIMARY KEY,
                name            VARCHAR(255) NOT NULL,
                username        VARCHAR(100) NOT NULL,
                email           VARCHAR(255) NOT NULL,
                password_hash   VARCHAR(255),
                role            VARCHAR(50)  DEFAULT 'user',
                is_admin        BOOLEAN      DEFAULT FALSE,
                auth_provider   VARCHAR(50)  DEFAULT 'local',
                theme_mode      VARCHAR(10)  DEFAULT 'light'
                                    CHECK (theme_mode IN ('light', 'dark')),
                avatar_url      VARCHAR(500) DEFAULT NULL,
                -- Preferências de acessibilidade (padrão gus-pulse)
                accessibility_level     VARCHAR(10) DEFAULT 'regular'
                                            CHECK (accessibility_level IN ('regular', 'AA', 'AAA')),
                high_contrast_mode      BOOLEAN     DEFAULT FALSE,
                reduce_motion           BOOLEAN     DEFAULT FALSE,
                colorblind_safe_palette BOOLEAN     DEFAULT FALSE,
                tenant_id       INTEGER      NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
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

        # 6. user_sessions
        # Armazena REFRESH tokens (hash SHA-256). Access tokens são validados
        # apenas por assinatura JWT — não são armazenados. O campo `id` desta
        # tabela é embutido no payload do access token como `sid` para lookup
        # de revogação imediata sem precisar armazenar o access token hash.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id                  SERIAL PRIMARY KEY,
                refresh_token_hash  VARCHAR(255) NOT NULL UNIQUE,
                ip_address          VARCHAR(50),
                user_agent          TEXT,
                expires_at          TIMESTAMPTZ  NOT NULL,  -- expiração do REFRESH token (ex: 7 dias)
                user_id             INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                tenant_id           INTEGER      NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                active              BOOLEAN      DEFAULT TRUE,
                created_at          TIMESTAMPTZ  DEFAULT NOW(),
                last_updated_at     TIMESTAMPTZ  DEFAULT NOW()
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id           ON user_sessions(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_tenant_id         ON user_sessions(tenant_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_refresh_token     ON user_sessions(refresh_token_hash);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_active            ON user_sessions(active);")

        # 7. user_permissions
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_permissions (
                id              SERIAL PRIMARY KEY,
                resource        VARCHAR(100) NOT NULL,
                action          VARCHAR(50)  NOT NULL,
                is_allowed      BOOLEAN      NOT NULL,
                user_id         INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                tenant_id       INTEGER      NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                active          BOOLEAN      DEFAULT TRUE,
                created_at      TIMESTAMPTZ  DEFAULT NOW(),
                last_updated_at TIMESTAMPTZ  DEFAULT NOW(),
                UNIQUE(user_id, resource, action)
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_permissions_user_id   ON user_permissions(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_permissions_tenant_id ON user_permissions(tenant_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_permissions_resource  ON user_permissions(resource);")

        # 8. pages (controle de acesso por página — min_role define o mínimo para acessar)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                id              SERIAL PRIMARY KEY,
                page_key        VARCHAR(100) NOT NULL,
                label           VARCHAR(200) NOT NULL,
                route           VARCHAR(200) NOT NULL,
                group_label     VARCHAR(200),
                min_role        VARCHAR(50)  NOT NULL DEFAULT 'view'
                                    CHECK (min_role IN ('view', 'user', 'admin')),
                tenant_id       INTEGER      NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                active          BOOLEAN      DEFAULT TRUE,
                created_at      TIMESTAMPTZ  DEFAULT NOW(),
                last_updated_at TIMESTAMPTZ  DEFAULT NOW(),
                UNIQUE(tenant_id, page_key)
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pages_tenant_id ON pages(tenant_id);")

        # 9. system_settings
        cur.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                id              SERIAL PRIMARY KEY,
                setting_key     VARCHAR(100) NOT NULL,
                setting_value   TEXT         NOT NULL,
                description     TEXT,
                tenant_id       INTEGER      NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                active          BOOLEAN      DEFAULT TRUE,
                created_at      TIMESTAMPTZ  DEFAULT NOW(),
                last_updated_at TIMESTAMPTZ  DEFAULT NOW(),
                UNIQUE(tenant_id, setting_key)
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_settings_tenant_id ON system_settings(tenant_id);")

        # 10. tenant_colors
        # Cada linha = combinação color_schema_mode × theme_mode × accessibility_level
        # = 12 linhas por tenant (2 × 2 × 3). Ver doc 03 e doc 09.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tenant_colors (
                id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                color_schema_mode   VARCHAR(10) NOT NULL CHECK (color_schema_mode IN ('default', 'custom')),
                theme_mode          VARCHAR(10) NOT NULL CHECK (theme_mode IN ('light', 'dark')),
                accessibility_level VARCHAR(10) NOT NULL DEFAULT 'regular'
                                        CHECK (accessibility_level IN ('regular', 'AA', 'AAA')),
                color1  VARCHAR(7)  NOT NULL,
                color2  VARCHAR(7)  NOT NULL,
                color3  VARCHAR(7)  NOT NULL,
                color4  VARCHAR(7)  NOT NULL,
                color5  VARCHAR(7)  NOT NULL,
                on_color1 VARCHAR(7) NOT NULL,
                on_color2 VARCHAR(7) NOT NULL,
                on_color3 VARCHAR(7) NOT NULL,
                on_color4 VARCHAR(7) NOT NULL,
                on_color5 VARCHAR(7) NOT NULL,
                on_gradient_1_2 VARCHAR(7) NOT NULL,
                on_gradient_2_3 VARCHAR(7) NOT NULL,
                on_gradient_3_4 VARCHAR(7) NOT NULL,
                on_gradient_4_5 VARCHAR(7) NOT NULL,
                on_gradient_5_1 VARCHAR(7) NOT NULL,
                tenant_id       INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                active          BOOLEAN     DEFAULT TRUE,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                last_updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, color_schema_mode, accessibility_level, theme_mode)
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tenant_colors_tenant_id ON tenant_colors(tenant_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tenant_colors_lookup    ON tenant_colors(tenant_id, color_schema_mode, accessibility_level, theme_mode);")

        # 11. audit_logs — registro imutável de ações (quem, o quê, quando, de onde)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id          SERIAL      PRIMARY KEY,
                action      VARCHAR(100) NOT NULL,       -- 'user.created', 'role.updated', 'login.success'
                entity_type VARCHAR(100),                -- 'users', 'roles', 'pages', etc.
                entity_id   INTEGER,
                payload     JSONB        DEFAULT '{}',   -- dados relevantes do evento (sem senhas)
                ip_address  VARCHAR(50),
                user_id     INTEGER      REFERENCES users(id) ON DELETE SET NULL,
                tenant_id   INTEGER      NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                created_at  TIMESTAMPTZ  DEFAULT NOW()
                -- SEM active, SEM last_updated_at — audit log é imutável por design
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_id   ON audit_logs(tenant_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id     ON audit_logs(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_action      ON audit_logs(action);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at  ON audit_logs(created_at DESC);")

        # 12. integrations (always created; rows active/inactive controlled by seed)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS integrations (
                id                      SERIAL PRIMARY KEY,
                provider                VARCHAR(50)  NOT NULL,
                type                    VARCHAR(50)  NOT NULL,
                username                VARCHAR(255),
                password                VARCHAR(255),
                base_url                TEXT,
                settings                JSONB        DEFAULT '{}',
                fallback_integration_id INTEGER      REFERENCES integrations(id) ON DELETE SET NULL,
                logo_filename           VARCHAR(255),
                tenant_id               INTEGER      NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
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
        cur.execute("DROP TABLE IF EXISTS integrations       CASCADE;")
        cur.execute("DROP TABLE IF EXISTS audit_logs         CASCADE;")
        cur.execute("DROP TABLE IF EXISTS tenant_colors      CASCADE;")
        cur.execute("DROP TABLE IF EXISTS system_settings    CASCADE;")
        cur.execute("DROP TABLE IF EXISTS pages              CASCADE;")
        cur.execute("DROP TABLE IF EXISTS user_permissions   CASCADE;")
        cur.execute("DROP TABLE IF EXISTS user_sessions      CASCADE;")
        cur.execute("DROP TABLE IF EXISTS users              CASCADE;")
        cur.execute("DROP TABLE IF EXISTS roles              CASCADE;")
        cur.execute("DROP TABLE IF EXISTS tenants            CASCADE;")
        cur.execute("DROP TABLE IF EXISTS migration_history  CASCADE;")
    logger.info("0001_initial_schema rolled back.")
