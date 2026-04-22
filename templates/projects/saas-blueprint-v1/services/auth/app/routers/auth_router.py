import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.security import create_refresh_token, decode_token_allow_expired
from app.providers.local_provider import LocalAuthProvider
from app.schemas.auth_schemas import (
    LoginRequest, LoginResponse, RefreshRequest, RefreshResponse, TokenValidateRequest, UserPayload
)
from app.services.session_service import (
    create_session, invalidate_session, rotate_refresh_token
)

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

_ACCESS_EXPIRE_SEC = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


@router.post("/login", response_model=LoginResponse)
def login(credentials: LoginRequest, request: Request, db: Session = Depends(get_db_session)):
    """
    Autentica o usuário e retorna access token (5 min) + refresh token (7 dias).

    - access_token : JWT curto, inclui `sid` para revogação imediata.
    - refresh_token: opaque hex, armazenado hashed no banco. Use POST /auth/refresh para renovar.
    """
    provider = LocalAuthProvider(db)
    try:
        user_data = provider.authenticate({"email": credentials.email, "password": credentials.password})
    except ValueError:
        logger.warning("Login failed for email: %s", credentials.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou senha inválidos.")

    # 1. Gera refresh token e registra a sessão
    refresh_token = create_refresh_token()
    refresh_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    session_id = create_session(
        db,
        user_id=user_data["id"],
        tenant_id=user_data["tenant_id"],
        refresh_token=refresh_token,
        expires_at=refresh_expires_at,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    # 2. Gera access token com session_id embutido
    access_token = provider.generate_access_token(user_data, session_id=session_id)

    logger.info("Login successful: user_id=%s session_id=%s", user_data["id"], session_id)
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=_ACCESS_EXPIRE_SEC,
        user=UserPayload(**user_data),
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db_session)):
    """
    Renova o access token usando o refresh token.

    - Valida o refresh token (ativo + não expirado).
    - Rotaciona o refresh token (token rotation — invalida o antigo).
    - Retorna novo access token (5 min) + novo refresh token (7 dias).
    """
    new_refresh_expires = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    result = rotate_refresh_token(db, old_refresh_token=body.refresh_token, new_expires_at=new_refresh_expires)

    if result is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido ou expirado.")

    new_refresh_token, session_id = result

    # Busca os dados do usuário para reemitir o access token
    row = db.execute(
        text("""
            SELECT u.id, u.tenant_id, u.name, u.username, u.email, u.role,
                   u.is_admin, u.theme_mode, u.avatar_url,
                   u.accessibility_level, u.high_contrast_mode, u.reduce_motion, u.colorblind_safe_palette
            FROM users u
            JOIN user_sessions s ON s.user_id = u.id
            WHERE s.id = :sid AND u.active = TRUE
        """),
        {"sid": session_id},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado.")

    provider = LocalAuthProvider(db)
    user_data = dict(row._mapping)
    new_access_token = provider.generate_access_token(user_data, session_id=session_id)

    logger.info("Token refreshed: session_id=%s", session_id)
    return RefreshResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_in=_ACCESS_EXPIRE_SEC,
    )


@router.post("/logout")
def logout(body: TokenValidateRequest, db: Session = Depends(get_db_session)):
    """
    Encerra a sessão a partir do access token (JWT).

    Extrai o `sid` (session_id) do JWT e invalida a sessão diretamente por PK.
    Usa decode sem verificação de expiração — logout deve funcionar mesmo com
    token expirado (ex: tab esquecida aberta). A assinatura ainda é verificada.
    O frontend deve descartar o access token — ele expirará sozinho em ≤5 min.
    """
    try:
        payload = decode_token_allow_expired(body.token)
        session_id = payload.get("sid")
        if session_id:
            invalidate_session(db, session_id)
        else:
            logger.warning("Logout: sid ausente no payload — nenhuma sessão invalidada")
    except Exception as exc:
        logger.warning("Logout: erro ao processar token: %s", exc)
    return {"detail": "Sessão encerrada."}
