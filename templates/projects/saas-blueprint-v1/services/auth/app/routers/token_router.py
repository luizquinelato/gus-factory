import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.security import decode_token
from app.schemas.auth_schemas import TokenValidateRequest, TokenValidateResponse
from app.services.session_service import is_session_active_by_id

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


@router.post("/validate", response_model=TokenValidateResponse)
def validate_token(
    body: TokenValidateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
):
    """Valida um JWT e verifica se a sessão está ativa.

    Chamado exclusivamente pelo Backend Service (nunca diretamente pelo Frontend).
    Protegido por X-Internal-Key quando INTERNAL_API_KEY estiver configurado.
    """
    if settings.INTERNAL_API_KEY:
        key = request.headers.get("X-Internal-Key", "")
        if key != settings.INTERNAL_API_KEY:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado.")

    try:
        payload = decode_token(body.token)  # levanta JWTError se expirado ou inválido
        if not payload.get("sub") or not payload.get("tenant_id"):
            raise ValueError("Payload incompleto")

        # Verifica revogação pelo session_id (PK) embutido no JWT — O(1) por índice PK
        session_id = payload.get("sid")
        if session_id and not is_session_active_by_id(db, session_id):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sessão expirada ou revogada.",
            )

        return TokenValidateResponse(valid=True, payload=payload)
    except HTTPException:
        raise
    except (JWTError, ValueError) as exc:
        logger.warning("Token validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado.",
        )
