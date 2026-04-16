#!/usr/bin/env python3
"""
Migration 0002: Seed Data
==========================
Project : SaaS Blueprint V1
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


def _on_color(bg: str, threshold: float = 0.5) -> str:
    """Return #FFFFFF or #000000 based on WCAG 2.1 luminance threshold.

    Idêntico a ColorCalculationService.pick_on_color():
      lum < threshold → fundo escuro → texto BRANCO
      lum >= threshold → fundo claro → texto PRETO
    """
    return "#FFFFFF" if _luminance(bg) < threshold else "#000000"


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
        # Paleta Blue/Navy/Pink — 5 tokens do Design System (usuário definiu explicitamente).
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
_ACCESS_LEVELS = ["regular", "AA", "AAA"]


def _on_gradient(c1: str, c2: str, threshold: float = 0.5) -> str:
    """WCAG-safe text color for a gradient between c1 and c2 (uses average luminance).

    Mesma lógica do pick_gradient_on_color() do ColorCalculationService:
    se on(c1) == on(c2), retorna esse; caso contrário, usa média de luminância
    contra o threshold (padrão 0.5).
    """
    on1 = _on_color(c1, threshold)
    on2 = _on_color(c2, threshold)
    if on1 == on2:
        return on1
    avg_lum = (_luminance(c1) + _luminance(c2)) / 2
    return "#FFFFFF" if avg_lum < threshold else "#000000"

ENABLE_AI_LAYER: bool = True   # substituted by create_project.py


def apply(conn):
    """Insert default tenant, admin user, colors and AI integrations."""
    logger.info("Applying 0002_seed_data...")
    with conn.cursor() as cur:

        # 1. Default tenant
        cur.execute(
            "INSERT INTO tenants (name, document, tier, color_schema_mode, active) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id;",
            ("SaaS Blueprint V1", None, "premium", "default", True)
        )
        tenant_id = cur.fetchone()["id"]
        logger.info(f"  Tenant created: id={tenant_id}")

        # 2. Base roles (system roles — is_system=True, não podem ser deletados via UI)
        # can_read/can_write/can_delete: admin é sempre total (bloqueado na UI)
        base_roles = [
            # name,    description,                                   is_system, can_read, can_write, can_delete
            ("admin", "Administrador do sistema — acesso total",      True,      True,     True,      True),
            ("user",  "Usuário padrão — acesso operacional",          True,      True,     True,      False),
            ("view",  "Visualizador — somente leitura",               True,      True,     False,     False),
        ]
        for name, description, is_system, can_read, can_write, can_delete in base_roles:
            cur.execute(
                """
                INSERT INTO roles (name, description, is_system, can_read, can_write, can_delete, tenant_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, name) DO NOTHING;
                """,
                (name, description, is_system, can_read, can_write, can_delete, tenant_id)
            )
        logger.info("  Base roles seeded: admin, user, view")

        # 4. Admin user
        # theme_mode='light' é o padrão explícito (não depender do DEFAULT da coluna).
        # O usuário pode alterar via UI → persistido em users.theme_mode no banco.
        password_hash = _hash_password("Gus@2026!")
        cur.execute(
            """
            INSERT INTO users (tenant_id, name, username, email, password_hash,
                               role, is_admin, auth_provider, theme_mode)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
            """,
            (tenant_id, "Luiz Gustavo Quinelato", "gustavoquinelato",
             "gustavoquinelato@gmail.com", password_hash, "admin", True, "local", "light")
        )
        user_id = cur.fetchone()["id"]
        logger.info(f"  Admin user created: id={user_id}  email=gustavoquinelato@gmail.com")

        # 5. System settings
        settings = [
            ("font_contrast_threshold", "0.5",   "WCAG font contrast threshold"),
            ("default_language",        "pt-BR", "Default UI language"),
            ("default_timezone",        "America/Sao_Paulo", "Default timezone"),
        ]
        for key, value, desc in settings:
            cur.execute(
                "INSERT INTO system_settings (tenant_id, setting_key, setting_value, description) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (tenant_id, setting_key) DO NOTHING;",
                (tenant_id, key, value, desc)
            )

        # 6. Color palette — 12 linhas por tenant
        # Estrutura: color_schema_mode × theme_mode × accessibility_level (2×2×3)
        # Todas as 3 accessibility levels recebem as mesmas cores base no seed.
        # O admin pode ajustar AA/AAA via UI → colorCalculations.ts calcula os valores WCAG.
        for schema_mode, themes in _BASE_COLORS.items():
            for theme_mode, colors in themes.items():
                c1, c2, c3, c4, c5 = colors
                on_c1, on_c2, on_c3 = _on_color(c1), _on_color(c2), _on_color(c3)
                on_c4, on_c5        = _on_color(c4), _on_color(c5)
                on_g12 = _on_gradient(c1, c2)
                on_g23 = _on_gradient(c2, c3)
                on_g34 = _on_gradient(c3, c4)
                on_g45 = _on_gradient(c4, c5)
                on_g51 = _on_gradient(c5, c1)

                for access_level in _ACCESS_LEVELS:
                    cur.execute(
                        """
                        INSERT INTO tenant_colors (
                            tenant_id, color_schema_mode, theme_mode, accessibility_level,
                            color1, color2, color3, color4, color5,
                            on_color1, on_color2, on_color3, on_color4, on_color5,
                            on_gradient_1_2, on_gradient_2_3, on_gradient_3_4,
                            on_gradient_4_5, on_gradient_5_1
                        ) VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (tenant_id, color_schema_mode, accessibility_level, theme_mode)
                        DO UPDATE SET
                            color1 = EXCLUDED.color1, color2 = EXCLUDED.color2,
                            color3 = EXCLUDED.color3, color4 = EXCLUDED.color4,
                            color5 = EXCLUDED.color5,
                            on_color1 = EXCLUDED.on_color1, on_color2 = EXCLUDED.on_color2,
                            on_color3 = EXCLUDED.on_color3, on_color4 = EXCLUDED.on_color4,
                            on_color5 = EXCLUDED.on_color5,
                            on_gradient_1_2 = EXCLUDED.on_gradient_1_2,
                            on_gradient_2_3 = EXCLUDED.on_gradient_2_3,
                            on_gradient_3_4 = EXCLUDED.on_gradient_3_4,
                            on_gradient_4_5 = EXCLUDED.on_gradient_4_5,
                            on_gradient_5_1 = EXCLUDED.on_gradient_5_1,
                            last_updated_at = NOW();
                        """,
                        (
                            tenant_id, schema_mode, theme_mode, access_level,
                            c1, c2, c3, c4, c5,
                            on_c1, on_c2, on_c3, on_c4, on_c5,
                            on_g12, on_g23, on_g34, on_g45, on_g51,
                        )
                    )
        logger.info("  Color palette seeded: 12 rows (2 schemas × 2 themes × 3 access levels)")

        # 7. Pages — controle de acesso por página
        # min_role define o nível mínimo para acessar: 'view' < 'user' < 'admin'
        # group_label: menu pai da página (ex: "Configurações") ou None se raiz.
        # Novas páginas devem ser adicionadas aqui e registradas no frontend (App.tsx).
        pages = [
            # page_key,  label,                  route,             group_label,      min_role
            ("home",     "Home",                 "/",               None,             "view"),
            ("profile",  "Perfil",               "/profile",        None,             "view"),
            ("cores",    "Cores",                "/color-settings", "Configurações",  "admin"),
            ("paginas",  "Páginas",              "/admin/pages",    "Configurações",  "admin"),
            ("roles",    "Papéis",                "/admin/roles",    "Configurações",  "admin"),
        ]
        for page_key, label, route, group_label, min_role in pages:
            cur.execute(
                """
                INSERT INTO pages (page_key, label, route, group_label, min_role, tenant_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, page_key) DO NOTHING;
                """,
                (page_key, label, route, group_label, min_role, tenant_id)
            )
        logger.info(f"  Pages seeded: {len(pages)} rows")

        # 8. AI integrations (active = ENABLE_AI_LAYER; always created so toggleable later)
        openai_cfg = json.dumps({
            "model": "gpt-4-turbo",
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

        embedding_cfg = json.dumps({"model": "text-embedding-3-small"})
        cur.execute(
            "INSERT INTO integrations (tenant_id, provider, type, settings, active) "
            "VALUES (%s, %s, %s, %s, %s);",
            (tenant_id, "OpenAI Embeddings", "Embedding", embedding_cfg, ENABLE_AI_LAYER)
        )
        logger.info(f"  AI integrations seeded (active={ENABLE_AI_LAYER})")

    logger.info("0002_seed_data applied.")
    logger.info("──────────────────────────────────────────────")
    logger.info(f"  Admin email   : gustavoquinelato@gmail.com")
    logger.info(f"  Admin password: Gus@2026!")
    logger.info("──────────────────────────────────────────────")


def rollback(conn):
    """Remove seed data (tenant cascade-deletes everything else)."""
    logger.info("Rolling back 0002_seed_data...")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM tenants WHERE name = 'SaaS Blueprint V1';")
    logger.info("0002_seed_data rolled back.")

