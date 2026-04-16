"""
ColorService
============
Camada de acesso a dados para tenant_colors (novo schema).

Novo schema: cada linha = color_schema_mode × theme_mode × accessibility_level
= 12 linhas por tenant, pré-computadas (color1-5, on_color1-5, on_gradient_*).

get_all_colors_unified  → lê as 12 linhas direto do DB (sem cálculo on-the-fly).
update_custom_colors    → recebe as 5 cores base (regular), calcula AA/AAA via
                          ColorCalculationService e upserta as 6 linhas custom.
"""
import logging
import re
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.color_calculation_service import ColorCalculationService

logger = logging.getLogger(__name__)
_calc = ColorCalculationService()

_HEX_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')

_COLOR_COLS = (
    "color1, color2, color3, color4, color5, "
    "on_color1, on_color2, on_color3, on_color4, on_color5, "
    "on_gradient_1_2, on_gradient_2_3, on_gradient_3_4, on_gradient_4_5, on_gradient_5_1"
)


def _sanitize_hex(raw: str) -> str:
    """Trunca e valida hex color. Levanta ValueError se inválido após sanitização."""
    v = str(raw).strip()
    if len(v) > 7:
        v = v[:7]
    if not _HEX_RE.match(v):
        raise ValueError(f"Hex inválido após sanitização: '{raw}' → '{v}'")
    return v.upper()


def get_all_colors_unified(
    db: Session, tenant_id: int, threshold: float = 0.5
) -> List[Dict[str, Any]]:
    """Retorna as 12 linhas pré-computadas do DB.

    Cada dict contém: color_schema_mode, theme_mode, accessibility_level,
    color1..5, on_color1..5, on_gradient_1_2..5_1.

    `threshold` não é mais usado (cálculo já ocorreu no save). Mantido por
    compatibilidade de assinatura com chamadores existentes.
    """
    rows = db.execute(
        text(
            f"SELECT color_schema_mode, theme_mode, accessibility_level, {_COLOR_COLS} "
            "FROM tenant_colors "
            "WHERE tenant_id = :tid AND active = TRUE "
            "ORDER BY color_schema_mode, theme_mode, accessibility_level"
        ),
        {"tid": tenant_id},
    ).fetchall()

    if not rows:
        logger.warning("Nenhuma cor encontrada para tenant=%s", tenant_id)
        return []

    return [dict(r._mapping) for r in rows]


def update_custom_colors(
    db: Session,
    tenant_id: int,
    light_colors: Dict[str, str],
    dark_colors: Dict[str, str],
    threshold: float = 0.5,
) -> None:
    """Salva as 6 linhas de cores custom (2 themes × 3 WCAG levels) via UPSERT.

    Recebe as 5 cores base (nível 'regular') para light e dark.
    ColorCalculationService calcula on_colors, on_gradients e variantes AA/AAA.
    """
    logger.info("update_custom_colors — light=%s dark=%s", light_colors, dark_colors)

    for theme_mode, raw_colors in [("light", light_colors), ("dark", dark_colors)]:
        # Valida e monta dict {color1..5: hex}
        base: Dict[str, str] = {}
        for n in range(1, 6):
            key = f"color{n}"
            if key not in raw_colors:
                logger.warning("update_custom_colors: %s ausente para theme=%s — abortando", key, theme_mode)
                return
            base[key] = _sanitize_hex(raw_colors[key])

        # Calcula 3 níveis: regular (original), AA (-5%), AAA (-10%)
        levels = _calc.build_all_levels(base, "custom", theme_mode, threshold)

        for level_data in levels:
            access_level = level_data["accessibility_level"]
            db.execute(
                text(
                    "INSERT INTO tenant_colors ("
                    "  tenant_id, color_schema_mode, theme_mode, accessibility_level,"
                    "  color1, color2, color3, color4, color5,"
                    "  on_color1, on_color2, on_color3, on_color4, on_color5,"
                    "  on_gradient_1_2, on_gradient_2_3, on_gradient_3_4,"
                    "  on_gradient_4_5, on_gradient_5_1"
                    ") VALUES ("
                    "  :tid, 'custom', :tm, :al,"
                    "  :c1, :c2, :c3, :c4, :c5,"
                    "  :oc1, :oc2, :oc3, :oc4, :oc5,"
                    "  :og12, :og23, :og34, :og45, :og51"
                    ") ON CONFLICT (tenant_id, color_schema_mode, accessibility_level, theme_mode)"
                    " DO UPDATE SET"
                    "  color1=EXCLUDED.color1, color2=EXCLUDED.color2,"
                    "  color3=EXCLUDED.color3, color4=EXCLUDED.color4,"
                    "  color5=EXCLUDED.color5,"
                    "  on_color1=EXCLUDED.on_color1, on_color2=EXCLUDED.on_color2,"
                    "  on_color3=EXCLUDED.on_color3, on_color4=EXCLUDED.on_color4,"
                    "  on_color5=EXCLUDED.on_color5,"
                    "  on_gradient_1_2=EXCLUDED.on_gradient_1_2,"
                    "  on_gradient_2_3=EXCLUDED.on_gradient_2_3,"
                    "  on_gradient_3_4=EXCLUDED.on_gradient_3_4,"
                    "  on_gradient_4_5=EXCLUDED.on_gradient_4_5,"
                    "  on_gradient_5_1=EXCLUDED.on_gradient_5_1,"
                    "  last_updated_at=NOW()"
                ),
                {
                    "tid": tenant_id, "tm": theme_mode, "al": access_level,
                    "c1": level_data["color1"], "c2": level_data["color2"],
                    "c3": level_data["color3"], "c4": level_data["color4"],
                    "c5": level_data["color5"],
                    "oc1": level_data["on_color1"], "oc2": level_data["on_color2"],
                    "oc3": level_data["on_color3"], "oc4": level_data["on_color4"],
                    "oc5": level_data["on_color5"],
                    "og12": level_data["on_gradient_1_2"], "og23": level_data["on_gradient_2_3"],
                    "og34": level_data["on_gradient_3_4"], "og45": level_data["on_gradient_4_5"],
                    "og51": level_data["on_gradient_5_1"],
                },
            )

    db.commit()
    logger.info("Custom colors updated for tenant=%s (6 rows: 2 themes × 3 WCAG levels)", tenant_id)


def update_color_schema_mode(db: Session, tenant_id: int, mode: str) -> None:
    """Atualiza color_schema_mode do tenant ('default' | 'custom')."""
    db.execute(
        text(
            "UPDATE tenants SET color_schema_mode = :mode, last_updated_at = NOW() "
            "WHERE id = :tid"
        ),
        {"mode": mode, "tid": tenant_id},
    )
    db.commit()
    logger.info("color_schema_mode updated: tenant=%s mode=%s", tenant_id, mode)


def get_tenant_color_schema_mode(db: Session, tenant_id: int) -> str:
    """Retorna o color_schema_mode atual do tenant."""
    row = db.execute(
        text("SELECT color_schema_mode FROM tenants WHERE id = :tid"), {"tid": tenant_id}
    ).fetchone()
    return row.color_schema_mode if row else "default"


def get_system_setting(db: Session, tenant_id: int, key: str, default: str = "0.5") -> str:
    """Lê um valor de system_settings."""
    row = db.execute(
        text(
            "SELECT setting_value FROM system_settings "
            "WHERE tenant_id = :tid AND setting_key = :key AND active = TRUE"
        ),
        {"tid": tenant_id, "key": key},
    ).fetchone()
    return row.setting_value if row else default
