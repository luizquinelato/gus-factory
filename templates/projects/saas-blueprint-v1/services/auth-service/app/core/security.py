import bcrypt
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()


def hash_password(password: str) -> str:
    """Gera hash bcrypt. Use no cadastro e na troca de senha."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica senha contra o hash armazenado no banco."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Cria um JWT access token (curto — padrão 5 min).

    O campo `sid` (session_id) deve estar em `data` para permitir
    revogação imediata sem blacklist de access tokens.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Decodifica e valida um JWT. Levanta JWTError se inválido ou expirado."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.ALGORITHM])


def create_refresh_token() -> str:
    """Gera um refresh token opaco (32 bytes hex = 64 chars). Não é JWT."""
    return secrets.token_hex(32)


def hash_refresh_token(token: str) -> str:
    """SHA-256 do refresh token — nunca armazenamos o token em texto claro."""
    return hashlib.sha256(token.encode()).hexdigest()
