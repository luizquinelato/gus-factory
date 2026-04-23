"""
auth_router.py
==============
POST /api/v1/auth/login        →  Proxy para o Auth Service + retorna cores do tenant.
POST /api/v1/auth/logout       →  Invalida sessão no Auth Service (stateful).
POST /api/v1/auth/ott          →  Gera One-Time Token para SSO → ETL (admin only).
POST /api/v1/auth/exchange-ott →  Troca OTT por JWT (ETL frontend, sem auth).
"""
import json
import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.limiter import limiter
# @IF etl
from app.core.redis_client import redis_get_and_delete, redis_set
# @ENDIF etl
from app.dependencies.auth import require_authentication
from app.schemas.auth_schemas import (
    LoginRequest, LoginResponse, UserResponse, TenantColorsPayload, ColorSchemeResponse
)
from app.services.color_service import get_all_colors_unified, get_tenant_color_schema_mode
from app.services.user_service import get_user_by_id

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(request: Request, credentials: LoginRequest, db: AsyncSession = Depends(get_db_session)):
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
    all_colors = await get_all_colors_unified(db, tenant_id)
    schema_mode = await get_tenant_color_schema_mode(db, tenant_id)

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
async def logout(request: Request):
    """Invalida a sessão no Auth Service.

    NÃO requer autenticação — logout deve funcionar mesmo com token expirado.
    O Auth Service valida a assinatura do JWT (sem verificar expiração) e
    invalida a sessão pelo `sid` embutido no payload.
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.split(" ", 1)[-1] if auth_header.startswith("Bearer ") else ""

    if not token:
        return {"detail": "Logout realizado com sucesso."}

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


# @IF etl
# ── OTT — SSO para ETL ────────────────────────────────────────────────────────

_OTT_TTL = 30  # segundos — janela para o ETL frontend trocar o OTT
_OTT_PREFIX = "ott:"


@router.post("/ott")
async def generate_ott(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user: dict = Depends(require_authentication),
):
    """Gera um One-Time Token para o admin abrir o módulo ETL.

    - Requer autenticação e perfil admin.
    - Armazena access_token + user + tenant_colors no Redis com TTL de 30s.
    - O ETL frontend troca o OTT pelo conjunto completo (mesmo shape do login).
    """
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a administradores.")

    auth_header = request.headers.get("Authorization", "")
    access_token = auth_header.split(" ", 1)[-1] if auth_header.startswith("Bearer ") else ""
    if not access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token não encontrado.")

    user_id   = current_user["id"]
    tenant_id = current_user["tenant_id"]

    # Busca user completo e cores do tenant para empacotar no OTT
    user_row    = await get_user_by_id(db, user_id, tenant_id)  # retorna dict
    schema_mode = await get_tenant_color_schema_mode(db, tenant_id)
    colors_raw  = await get_all_colors_unified(db, tenant_id)

    if not user_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    user_dict = {
        "id": user_row["id"], "tenant_id": user_row["tenant_id"],
        "name": user_row["name"], "username": user_row["username"],
        "email": user_row["email"], "role": user_row["role"],
        "is_admin": user_row["is_admin"], "theme_mode": user_row["theme_mode"],
        "avatar_url": user_row.get("avatar_url"),
        "accessibility_level": user_row["accessibility_level"],
        "high_contrast_mode": user_row["high_contrast_mode"],
        "reduce_motion": user_row["reduce_motion"],
        "colorblind_safe_palette": user_row["colorblind_safe_palette"],
    }
    tenant_colors = {"color_schema_mode": schema_mode, "colors": colors_raw}

    # Fingerprint por IP — OTT só é válido para o mesmo cliente que o gerou
    client_ip = request.client.host if request.client else "unknown"

    ott = str(uuid.uuid4())
    payload = json.dumps({
        "access_token": access_token,
        "user": user_dict,
        "tenant_colors": tenant_colors,
        "client_ip": client_ip,
    })
    await redis_set(f"{_OTT_PREFIX}{ott}", payload, _OTT_TTL)

    logger.info("OTT gerado para user_id=%s ip=%s", user_id, client_ip)
    return {"ott": ott, "etl_url": settings.ETL_FRONTEND_URL, "ttl": _OTT_TTL}


@router.post("/exchange-ott")
@limiter.limit("10/minute")
async def exchange_ott(request: Request, body: dict):
    """Troca um OTT por access_token + user + tenant_colors (mesmo shape do login).

    - OTT é de uso único — removido do Redis na primeira chamada.
    - Expira em 30s se não utilizado.
    - Não requer autenticação prévia (é o ponto de entrada do ETL).
    """
    ott = body.get("ott", "").strip()
    if not ott:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTT ausente.")

    raw = await redis_get_and_delete(f"{_OTT_PREFIX}{ott}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OTT inválido ou expirado.")

    data = json.loads(raw)

    # Valida fingerprint — rejeita se o IP não bate com quem gerou o OTT
    client_ip = request.client.host if request.client else "unknown"
    if data.get("client_ip") != client_ip:
        logger.warning("OTT IP mismatch — esperado=%s recebido=%s", data.get("client_ip"), client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OTT inválido ou expirado.")

    logger.info("OTT trocado — user_id=%s", data.get("user", {}).get("id"))
    return {
        "access_token": data["access_token"],
        "token_type":   "bearer",
        "user":         data["user"],
        "tenant_colors": data["tenant_colors"],
    }
# @ENDIF etl

