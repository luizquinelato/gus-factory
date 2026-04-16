"""
auth_router.py
==============
POST /api/v1/auth/login  →  Proxy para o Auth Service + retorna cores do tenant.
POST /api/v1/auth/logout →  Invalida sessão no Auth Service (stateful).
"""
import logging
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db_session
from app.dependencies.auth import require_authentication
from app.schemas.auth_schemas import LoginRequest, LoginResponse, UserResponse, TenantColorsPayload, ColorSchemeResponse
from app.services.color_service import get_all_colors_unified, get_tenant_color_schema_mode

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest, db: Session = Depends(get_db_session)):
    """Delega autenticação ao Auth Service e retorna token + cores do tenant."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.post(
                f"{settings.AUTH_SERVICE_URL}/api/v1/auth/login",
                json={"email": credentials.email, "password": credentials.password},
            )
            if resp.status_code == 401:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou senha inválidos.")
            resp.raise_for_status()
        except httpx.RequestError as exc:
            logger.error("Auth service unreachable: %s", exc)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth service indisponível.")

    data = resp.json()
    user = data["user"]
    tenant_id = user["tenant_id"]

    # Busca as cores do tenant
    all_colors = get_all_colors_unified(db, tenant_id)
    schema_mode = get_tenant_color_schema_mode(db, tenant_id)

    # Filtra apenas as cores do schema_mode ativo
    colors = [c for c in all_colors if c["color_schema_mode"] == schema_mode]

    return LoginResponse(
        access_token=data["access_token"],
        token_type="bearer",
        user=UserResponse(**user),
        tenant_colors=TenantColorsPayload(
            color_schema_mode=schema_mode,
            colors=[ColorSchemeResponse(**c) for c in colors],
        ),
    )


@router.post("/logout")
async def logout(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_authentication),
):
    """Invalida a sessão no Auth Service e encerra a autenticação."""
    token = request.headers.get("Authorization", "").split(" ", 1)[-1]
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.post(
                f"{settings.AUTH_SERVICE_URL}/api/v1/auth/logout",
                json={"token": token},
                headers={"X-Internal-Key": settings.INTERNAL_API_KEY},
            )
            if resp.status_code != 200:
                logger.warning("Auth-service logout returned %s: %s", resp.status_code, resp.text)
        except Exception as exc:
            logger.warning("Could not reach auth-service on logout: %s", exc)
    return {"detail": "Logout realizado com sucesso."}

