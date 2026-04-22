"""
session_service.py
==================
Gerencia user_sessions. Cada row = uma sessão de login (um refresh token).

Estratégia de tokens:
  - Access token  : JWT de 5 min, validado por assinatura (stateless).
                    Contém `sid` = session.id para revogação imediata.
  - Refresh token : opaque hex (64 chars), armazenado hashed (SHA-256).
                    Expira em 7 dias. Rotacionado a cada refresh.
"""
import logging
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import create_refresh_token, hash_refresh_token

logger = logging.getLogger(__name__)


def create_session(
    db: Session,
    user_id: int,
    tenant_id: int,
    refresh_token: str,
    expires_at: datetime,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> int:
    """Registra nova sessão no login. Retorna o session_id (PK) para embutir no JWT."""
    row = db.execute(
        text("""
            INSERT INTO user_sessions
                (refresh_token_hash, ip_address, user_agent, expires_at, user_id, tenant_id, active)
            VALUES (:rth, :ip, :ua, :exp, :uid, :tid, TRUE)
            RETURNING id
        """),
        {
            "rth": hash_refresh_token(refresh_token),
            "ip": ip_address,
            "ua": user_agent,
            "exp": expires_at,
            "uid": user_id,
            "tid": tenant_id,
        },
    ).fetchone()
    db.commit()
    session_id = row[0]
    logger.info("Session created: id=%s user_id=%s tenant_id=%s ip=%s", session_id, user_id, tenant_id, ip_address)
    return session_id


def is_session_active_by_id(db: Session, session_id: int) -> bool:
    """Verifica se a sessão (pelo PK) está ativa e o refresh token não expirou.

    Chamado pelo /token/validate — acesso por PK é O(1).
    """
    row = db.execute(
        text("""
            SELECT id FROM user_sessions
            WHERE id = :sid
              AND active = TRUE
              AND expires_at > NOW()
        """),
        {"sid": session_id},
    ).fetchone()
    return row is not None


def rotate_refresh_token(db: Session, old_refresh_token: str, new_expires_at: datetime) -> Optional[Tuple[str, int]]:
    """Valida o refresh token antigo, gera um novo e rotaciona na sessão.

    Retorna (new_refresh_token, session_id) se válido, None se inválido/expirado.
    Token rotation: invalida o hash antigo, grava o novo — previne replay attacks.
    """
    old_hash = hash_refresh_token(old_refresh_token)
    row = db.execute(
        text("""
            SELECT id FROM user_sessions
            WHERE refresh_token_hash = :rth
              AND active = TRUE
              AND expires_at > NOW()
        """),
        {"rth": old_hash},
    ).fetchone()

    if not row:
        return None

    session_id = row[0]
    new_token = create_refresh_token()
    new_hash = hash_refresh_token(new_token)

    db.execute(
        text("""
            UPDATE user_sessions
            SET refresh_token_hash = :new_rth,
                expires_at         = :exp,
                last_updated_at    = NOW()
            WHERE id = :sid
        """),
        {"new_rth": new_hash, "exp": new_expires_at, "sid": session_id},
    )
    db.commit()
    logger.info("Refresh token rotated: session_id=%s", session_id)
    return new_token, session_id


def invalidate_session(db: Session, session_id: int) -> None:
    """Marca a sessão como inativa (logout)."""
    db.execute(
        text("UPDATE user_sessions SET active = FALSE, last_updated_at = NOW() WHERE id = :sid"),
        {"sid": session_id},
    )
    db.commit()
    logger.info("Session invalidated: id=%s", session_id)


def invalidate_session_by_refresh_token(db: Session, refresh_token: str) -> bool:
    """Invalida a sessão pelo refresh token (usado no logout).

    Retorna True se uma sessão foi encontrada e invalidada, False caso contrário.
    """
    row = db.execute(
        text("SELECT id FROM user_sessions WHERE refresh_token_hash = :rth AND active = TRUE"),
        {"rth": hash_refresh_token(refresh_token)},
    ).fetchone()
    if not row:
        return False
    invalidate_session(db, row[0])
    return True
