"""
tenant_colors_router.py
=======================
GET  /api/v1/tenant/colors/unified   → Todas as 12 combinações de cores
PUT  /api/v1/tenant/colors/unified   → Salva cores custom (light + dark)
POST /api/v1/tenant/colors/mode      → Troca entre 'default' e 'custom'
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db_session
from app.dependencies.auth import require_admin, require_authentication
from app.schemas.color_schemas import (
    UnifiedColorsResponse,
    UnifiedColorUpdate,
    ColorModeUpdate,
    ColorSchemeResponse,
)
from app.services.color_service import (
    get_all_colors_unified,
    get_tenant_color_schema_mode,
    update_custom_colors,
    update_color_schema_mode,
    get_system_setting,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_threshold(db: Session, tenant_id: int) -> float:
    """Lê o threshold de contraste do tenant (padrão: 0.5)."""
    val = get_system_setting(db, tenant_id, "color_contrast_threshold", "0.5")
    try:
        return float(val)
    except ValueError:
        return 0.5


@router.get("/unified", response_model=UnifiedColorsResponse)
async def get_unified_colors(
    current_user: Dict[str, Any] = Depends(require_authentication),
    db: Session = Depends(get_db_session),
):
    """Retorna todas as 12 combinações: 2 modes × 2 themes × 3 WCAG levels."""
    tenant_id = current_user["tenant_id"]
    threshold = _get_threshold(db, tenant_id)
    all_colors = get_all_colors_unified(db, tenant_id, threshold)
    schema_mode = get_tenant_color_schema_mode(db, tenant_id)

    return UnifiedColorsResponse(
        color_schema_mode=schema_mode,
        colors=[ColorSchemeResponse(**c) for c in all_colors],
    )


@router.put("/unified", response_model=UnifiedColorsResponse)
async def save_unified_colors(
    body: UnifiedColorUpdate,
    current_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db_session),
):
    """Salva as cores custom e retorna as 12 combinações atualizadas."""
    tenant_id = current_user["tenant_id"]

    # Valida que todas as 5 cores foram enviadas
    for label, colors in [("light_colors", body.light_colors), ("dark_colors", body.dark_colors)]:
        for n in range(1, 6):
            if f"color{n}" not in colors:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"'{label}' deve conter color1..color5.",
                )

    update_custom_colors(db, tenant_id, body.light_colors, body.dark_colors)
    threshold = _get_threshold(db, tenant_id)
    all_colors = get_all_colors_unified(db, tenant_id, threshold)
    schema_mode = get_tenant_color_schema_mode(db, tenant_id)

    return UnifiedColorsResponse(
        color_schema_mode=schema_mode,
        colors=[ColorSchemeResponse(**c) for c in all_colors],
    )


@router.post("/mode")
async def switch_color_mode(
    body: ColorModeUpdate,
    current_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db_session),
):
    """Troca o color_schema_mode do tenant entre 'default' e 'custom'."""
    if body.mode not in ("default", "custom"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="mode deve ser 'default' ou 'custom'.",
        )
    update_color_schema_mode(db, current_user["tenant_id"], body.mode)
    return {"detail": f"Modo atualizado para '{body.mode}'.", "color_schema_mode": body.mode}
