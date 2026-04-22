import logging
from typing import Any, Dict

from jose import JWTError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import verify_password, create_access_token, decode_token
from app.providers.base import AuthProvider

logger = logging.getLogger(__name__)


class LocalAuthProvider(AuthProvider):
    """Autenticação local via email/senha armazenados no PostgreSQL."""

    def __init__(self, db: Session):
        self.db = db

    def authenticate(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Busca o usuário no banco e valida a senha com bcrypt."""
        email = credentials.get("email", "").lower().strip()
        password = credentials.get("password", "")

        row = self.db.execute(
            text(
                "SELECT id, tenant_id, name, username, email, password_hash, role, "
                "is_admin, auth_provider, theme_mode, avatar_url, "
                "accessibility_level, high_contrast_mode, reduce_motion, colorblind_safe_palette, "
                "active "
                "FROM users WHERE email = :email AND active = TRUE AND auth_provider = 'local'"
            ),
            {"email": email},
        ).fetchone()

        if not row:
            raise ValueError("Credenciais inválidas")

        if not verify_password(password, row.password_hash):
            raise ValueError("Credenciais inválidas")

        return {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "name": row.name,
            "username": row.username,
            "email": row.email,
            "role": row.role,
            "is_admin": row.is_admin,
            "theme_mode": row.theme_mode,
            "avatar_url": row.avatar_url,
            "accessibility_level": row.accessibility_level,
            "high_contrast_mode": row.high_contrast_mode,
            "reduce_motion": row.reduce_motion,
            "colorblind_safe_palette": row.colorblind_safe_palette,
        }

    def generate_access_token(self, user_data: Dict[str, Any], session_id: int) -> str:
        """Gera JWT access token (5 min). Inclui `sid` para revogação imediata."""
        payload = {
            "sub": str(user_data["id"]),
            "sid": session_id,                        # session_id para revogação via PK
            "tenant_id": user_data["tenant_id"],
            "email": user_data["email"],
            "role": user_data["role"],
            "is_admin": user_data["is_admin"],
            "name": user_data["name"],
            "username": user_data.get("username", ""),
            "theme_mode": user_data.get("theme_mode", "light"),
        }
        return create_access_token(payload)

    def generate_tokens(self, user_data: Dict[str, Any]) -> Dict[str, str]:
        """Compat: gera access token sem session_id. Prefira generate_access_token()."""
        return {"access_token": self.generate_access_token(user_data, session_id=0), "token_type": "bearer"}

    def validate_token(self, token: str) -> Dict[str, Any]:
        """Decodifica e valida um JWT. Retorna payload ou levanta ValueError."""
        try:
            payload = decode_token(token)
            return payload
        except JWTError as exc:
            raise ValueError(f"Token inválido: {exc}") from exc
