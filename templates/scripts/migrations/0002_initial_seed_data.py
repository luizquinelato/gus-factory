#!/usr/bin/env python3
"""
Migration 0002: Seed Data
==========================
Project : {{ PROJECT_NAME }}
Creates : Default tenant, admin user, system settings,
          base color palette, AI integrations (if ENABLE_AI_LAYER=True).

Runner registers this migration in migration_history after apply() succeeds.
Do NOT register inside apply() — the runner handles it.
"""
import json
import logging

logger = logging.getLogger(__name__)

# ── Inline helpers (no external service dependency) ───────────────────────────

def _hash_password(plain: str) -> str:
    """Hash password with bcrypt."""
    import bcrypt
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    def lin(c): return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _on_color(bg: str) -> str:
    """Return #FFFFFF or #000000 based on WCAG contrast."""
    lum = _luminance(bg)
    contrast_white = (lum + 0.05) / 0.05
    contrast_black = (1.05) / (lum + 0.05)
    return "#FFFFFF" if contrast_white >= contrast_black else "#000000"


# ── Seed data ─────────────────────────────────────────────────────────────────

# Default color palette — referência: plumo (cores já validadas em produção).
# Estrutura: schema_mode → theme_mode → [color1..color5]
# Admin pode customizar depois via UI → tabela tenant_colors.
#
# Cálculo de on_color (WCAG):
#   pick_on_color(bg, threshold=0.5) → '#FFFFFF' se lum(bg) < 0.5 else '#000000'
#   Todas as cores abaixo foram validadas contra esse critério.
_BASE_COLORS = {
    "default": {
        # Paleta Blue/Navy/Pink — 5 tokens definidos pelo usuário.
        # Validadas com _luminance() + threshold=0.5 → todas on_color = #FFFFFF.
        #
        # Token → color#   Light        Dark         lum(light) lum(dark)
        # Primary  → c1    #1D4ED8      #60A5FA      0.107      0.363  → WHITE ✓
        # Surface  → c2    #1A1D2E      #252B42      0.013      0.025  → WHITE ✓
        # Accent   → c3    #BE185D      #F472B6      0.124      0.347  → WHITE ✓
        # Muted    → c4    #475569      #94A3B8      0.089      0.360  → WHITE ✓
        # Violet   → c5    #A78BFA      #A78BFA      0.336      0.336  → WHITE ✓
        "light": ["#1D4ED8", "#1A1D2E", "#BE185D", "#475569", "#A78BFA"],
        "dark":  ["#60A5FA", "#252B42", "#F472B6", "#94A3B8", "#A78BFA"],
    },
    "custom": {
        # Paleta Enterprise Teal/Gold — sólida, corporativa, diferenciada do default.
        # Indicada para contextos financeiros, saúde, jurídico.
        # Validadas com _luminance() + threshold=0.5 → todas on_color = #FFFFFF.
        #
        # Token → color#   Light        Dark         lum(light) lum(dark)
        # Primary  → c1    #0F766E      #14B8A6      0.142      0.259  → WHITE ✓
        # Surface  → c2    #0F172A      #1E293B      0.009      0.022  → WHITE ✓
        # Accent   → c3    #D97706      #F59E0B      0.280      0.439  → WHITE ✓
        # Muted    → c4    #374151      #6B7280      0.052      0.167  → WHITE ✓
        # Indigo   → c5    #6366F1      #818CF8      0.185      0.302  → WHITE ✓
        #
        # Nota: #2DD4BF (teal-400, lum=0.514) foi descartado → on_color = BLACK.
        # Substituído por #14B8A6 (teal-500, lum=0.259) → on_color = WHITE ✓
        "light": ["#0F766E", "#0F172A", "#D97706", "#374151", "#6366F1"],
        "dark":  ["#14B8A6", "#1E293B", "#F59E0B", "#6B7280", "#818CF8"],
    },
}
_COLOR_NAMES = ["color1", "color2", "color3", "color4", "color5"]

ENABLE_AI_LAYER: bool = {{ ENABLE_AI_LAYER }}   # substituted by create_project.py


def apply(conn):
    """Insert default tenant, admin user, colors and AI integrations."""
    logger.info("Applying 0002_seed_data...")
    with conn.cursor() as cur:

        # 1. Default tenant
        cur.execute(
            "INSERT INTO tenants (name, document, tier, color_schema_mode, active) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id;",
            ("{{ PROJECT_NAME }}", None, "premium", "default", True)
        )
        tenant_id = cur.fetchone()["id"]
        logger.info(f"  Tenant created: id={tenant_id}")

        # 2. Admin user
        # theme_mode='light' é o padrão explícito (não depender do DEFAULT da coluna).
        # O usuário pode alterar via UI → persistido em users.theme_mode no banco.
        password_hash = _hash_password("{{ ADMIN_PASSWORD }}")
        cur.execute(
            """
            INSERT INTO users (tenant_id, name, username, email, password_hash,
                               role, is_admin, auth_provider, theme_mode)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
            """,
            (tenant_id, "{{ ADMIN_NAME }}", "{{ ADMIN_USERNAME }}",
             "{{ ADMIN_EMAIL }}", password_hash, "admin", True, "{{ AUTH_PROVIDER }}", "light")
        )
        user_id = cur.fetchone()["id"]
        logger.info(f"  Admin user created: id={user_id}  email={{ ADMIN_EMAIL }}")

        # 3. System settings
        settings = [
            ("font_contrast_threshold", "0.5",              "WCAG font contrast threshold"),
            ("default_language",        "{{ LANGUAGE }}",   "Default UI language"),
            ("default_timezone",        "{{ TIMEZONE }}",   "Default timezone"),
        ]
        for key, value, desc in settings:
            cur.execute(
                "INSERT INTO system_settings (tenant_id, setting_key, setting_value, description) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (tenant_id, setting_key) DO NOTHING;",
                (tenant_id, key, value, desc)
            )

        # 3b. RabbitMQ queue worker counts — blueprint standard convention:
        #     key = {tier}_{queue_type}_workers  |  tiers × queue_types define all ETL queues.
        #     Used by migration_runner.py --rabbit-cleanup fallback.
        _TIERS       = ["free", "basic", "premium", "enterprise"]
        _QUEUE_TYPES = ["extraction", "transform", "embedding"]
        for tier in _TIERS:
            for qt in _QUEUE_TYPES:
                cur.execute(
                    "INSERT INTO system_settings (tenant_id, setting_key, setting_value, description) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (tenant_id, setting_key) DO NOTHING;",
                    (tenant_id, f"{tier}_{qt}_workers", "1",
                     f"Worker count: {qt} queue / {tier} tier")
                )
        logger.info("  Queue worker settings seeded (4 tiers × 3 queue types)")

        # 4. Color palette (default + custom × light + dark)
        for schema_mode, themes in _BASE_COLORS.items():
            for theme_mode, colors in themes.items():
                for color_name, hex_value in zip(_COLOR_NAMES, colors):
                    cur.execute(
                        """
                        INSERT INTO tenant_colors
                            (tenant_id, color_schema_mode, theme_mode, color_name, hex_value)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (tenant_id, color_schema_mode, theme_mode, color_name)
                        DO UPDATE SET hex_value = EXCLUDED.hex_value;
                        """,
                        (tenant_id, schema_mode, theme_mode, color_name, hex_value)
                    )
        logger.info("  Color palette seeded (default+custom × light+dark)")

        # 5. AI integrations (active = ENABLE_AI_LAYER; always created so toggleable later)
        openai_cfg = json.dumps({
            "model": "{{ AI_MODEL }}",
            "model_config": {"temperature": 0.3, "max_tokens": 4096}
        })
        cur.execute(
            "INSERT INTO integrations (tenant_id, provider, type, settings, active) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id;",
            (tenant_id, "OpenAI", "AI", openai_cfg, ENABLE_AI_LAYER)
        )
        openai_id = cur.fetchone()["id"]

        anthropic_cfg = json.dumps({
            "model": "claude-3-haiku-20240307",
            "model_config": {"temperature": 0.3, "max_tokens": 4096}
        })
        cur.execute(
            "INSERT INTO integrations (tenant_id, provider, type, settings, fallback_integration_id, active) "
            "VALUES (%s, %s, %s, %s, %s, %s);",
            (tenant_id, "Anthropic", "AI", anthropic_cfg, openai_id, ENABLE_AI_LAYER)
        )

        embedding_cfg = json.dumps({"model": "{{ EMBEDDING_MODEL }}"})
        cur.execute(
            "INSERT INTO integrations (tenant_id, provider, type, settings, active) "
            "VALUES (%s, %s, %s, %s, %s);",
            (tenant_id, "OpenAI Embeddings", "Embedding", embedding_cfg, ENABLE_AI_LAYER)
        )
        logger.info(f"  AI integrations seeded (active={ENABLE_AI_LAYER})")

    logger.info("0002_seed_data applied.")
    logger.info("──────────────────────────────────────────────")
    logger.info(f"  Admin email   : {{ ADMIN_EMAIL }}")
    logger.info(f"  Admin password: {{ ADMIN_PASSWORD }}")
    logger.info("──────────────────────────────────────────────")


def rollback(conn):
    """Remove seed data (tenant cascade-deletes everything else)."""
    logger.info("Rolling back 0002_seed_data...")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM tenants WHERE name = '{{ PROJECT_NAME }}';")
    logger.info("0002_seed_data rolled back.")

