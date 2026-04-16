import logging
from typing import Any, Dict

import httpx
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.rbac import role_level

settings = get_settings()
logger = logging.getLogger(__name__)


async def require_authentication(request: Request) -> Dict[str, Any]:
    """Valida o JWT chamando o Auth Service. Retorna o payload do usuário autenticado."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente ou inválido.")

    token = auth_header.split(" ", 1)[1]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{settings.AUTH_SERVICE_URL}/api/v1/token/validate",
                json={"token": token},
                headers={"X-Internal-Key": settings.INTERNAL_API_KEY},
            )
            response.raise_for_status()
            payload = response.json().get("payload", {})
            payload["id"] = int(payload.get("sub", 0))
            return payload
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado.")
    except Exception as exc:
        logger.error("Auth service unreachable: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth service indisponível.")


def require_admin(current_user: Dict = Depends(require_authentication)):
    """Garante que o usuário é admin."""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requer privilégios de administrador.")
    return current_user


def require_page_access(page_key: str):
    """Fábrica de dependências para checar acesso a uma página.

    Lógica:
    1. is_admin → acesso total (bypass)
    2. Consulta `pages` no banco pelo page_key do tenant
    3. Compara role_level(user.role) >= role_level(page.min_role)
    4. Página não cadastrada no banco → acesso liberado (fail-open seguro para o blueprint)
    """
    def checker(
        current_user: Dict = Depends(require_authentication),
        db: Session = Depends(get_db_session),
    ):
        if current_user.get("is_admin"):
            return current_user

        role      = current_user.get("role", "view")
        tenant_id = current_user["tenant_id"]

        row = db.execute(
            text("SELECT min_role FROM pages WHERE tenant_id = :tid AND page_key = :key AND active = TRUE"),
            {"tid": tenant_id, "key": page_key},
        ).fetchone()

        if row is None:
            return current_user  # página não cadastrada → acesso liberado

        if role_level(role) < role_level(row.min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso negado. Requer role '{row.min_role}' ou superior.",
            )

        return current_user
    return checker
