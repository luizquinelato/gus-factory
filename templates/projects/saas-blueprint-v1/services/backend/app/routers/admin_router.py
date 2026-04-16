"""
admin_router.py
===============
Endpoints exclusivos para administradores do tenant.

GET   /api/v1/admin/roles            → lista os roles do tenant
PATCH /api/v1/admin/roles/{name}     → atualiza can_read/can_write/can_delete de um role
GET   /api/v1/admin/pages            → lista todas as páginas e seus min_role
PATCH /api/v1/admin/pages/{page_key} → atualiza o min_role de uma página
"""
import logging
from typing import Any, Dict, List
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db_session
from app.dependencies.auth import require_admin

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

MinRole = Literal["view", "user", "admin"]


class RoleResponse(BaseModel):
    name: str
    description: str | None
    is_system: bool
    can_read: bool
    can_write: bool
    can_delete: bool


class RoleCapabilitiesUpdate(BaseModel):
    can_read: bool
    can_write: bool
    can_delete: bool


class PageResponse(BaseModel):
    page_key: str
    label: str
    route: str
    group_label: str | None = None
    min_role: str


class PageMinRoleUpdate(BaseModel):
    min_role: MinRole


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/roles", response_model=List[RoleResponse])
async def list_roles(
    current_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db_session),
):
    """Lista os roles do tenant em ordem hierárquica."""
    rows = db.execute(
        text("""
            SELECT name, description, is_system, can_read, can_write, can_delete
            FROM roles
            WHERE tenant_id = :tid AND active = TRUE
            ORDER BY CASE name WHEN 'admin' THEN 0 WHEN 'user' THEN 1 WHEN 'view' THEN 2 ELSE 9 END
        """),
        {"tid": current_user["tenant_id"]},
    ).fetchall()
    return [dict(r._mapping) for r in rows]


@router.patch("/roles/{name}", status_code=status.HTTP_200_OK)
async def update_role_capabilities(
    name: str,
    body: RoleCapabilitiesUpdate,
    current_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db_session),
):
    """Atualiza can_read/can_write/can_delete de um role. Admin é protegido."""
    tenant_id = current_user["tenant_id"]

    # Admin é sempre total — não pode ser alterado
    if name == "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="O role admin não pode ser alterado.")

    result = db.execute(
        text("""
            UPDATE roles
            SET can_read = :cr, can_write = :cw, can_delete = :cd, last_updated_at = NOW()
            WHERE tenant_id = :tid AND name = :name AND active = TRUE
        """),
        {"cr": body.can_read, "cw": body.can_write, "cd": body.can_delete, "tid": tenant_id, "name": name},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role não encontrado.")

    db.commit()
    logger.info("Role '%s' capabilities updated by user_id=%s tenant_id=%s", name, current_user["id"], tenant_id)
    return {"detail": f"Role '{name}' atualizado."}


@router.get("/pages", response_model=List[PageResponse])
async def list_pages(
    current_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db_session),
):
    """Lista todas as páginas do tenant com seus níveis de acesso."""
    rows = db.execute(
        text("""
            SELECT page_key, label, route, group_label, min_role
            FROM pages
            WHERE tenant_id = :tid AND active = TRUE
            ORDER BY group_label NULLS FIRST, label
        """),
        {"tid": current_user["tenant_id"]},
    ).fetchall()
    return [dict(r._mapping) for r in rows]


@router.patch("/pages/{page_key}", status_code=status.HTTP_200_OK)
async def update_page_min_role(
    page_key: str,
    body: PageMinRoleUpdate,
    current_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db_session),
):
    """Atualiza o min_role de uma página (admin, user ou view)."""
    tenant_id = current_user["tenant_id"]
    result = db.execute(
        text("""
            UPDATE pages
            SET min_role = :min_role, last_updated_at = NOW()
            WHERE tenant_id = :tid AND page_key = :key AND active = TRUE
        """),
        {"min_role": body.min_role, "tid": tenant_id, "key": page_key},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Página não encontrada.")
    db.commit()
    logger.info(
        "Page '%s' min_role updated to '%s' by user_id=%s tenant_id=%s",
        page_key, body.min_role, current_user["id"], tenant_id,
    )
    return {"detail": f"Página '{page_key}' atualizada para min_role='{body.min_role}'."}
