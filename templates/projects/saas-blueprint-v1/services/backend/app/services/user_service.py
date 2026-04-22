import logging
from typing import Any, Dict, Optional

import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_user_by_id(db: AsyncSession, user_id: int, tenant_id: int) -> Optional[Dict[str, Any]]:
    result = await db.execute(
        text(
            "SELECT id, tenant_id, name, username, email, role, is_admin, "
            "auth_provider, theme_mode, avatar_url, "
            "accessibility_level, high_contrast_mode, reduce_motion, colorblind_safe_palette, "
            "active, created_at "
            "FROM users WHERE id = :uid AND tenant_id = :tid AND active = TRUE"
        ),
        {"uid": user_id, "tid": tenant_id},
    )
    row = result.fetchone()
    return dict(row._mapping) if row else None


async def update_user_avatar(db: AsyncSession, user_id: int, tenant_id: int, avatar_url: str) -> bool:
    """Salva o path relativo do avatar no banco."""
    result = await db.execute(
        text(
            "UPDATE users SET avatar_url = :url, last_updated_at = NOW() "
            "WHERE id = :uid AND tenant_id = :tid AND active = TRUE"
        ),
        {"url": avatar_url, "uid": user_id, "tid": tenant_id},
    )
    await db.commit()
    return result.rowcount > 0


async def remove_user_avatar(db: AsyncSession, user_id: int, tenant_id: int) -> Optional[str]:
    """Remove o avatar do banco e retorna o path anterior (para deletar o arquivo)."""
    result = await db.execute(
        text("SELECT avatar_url FROM users WHERE id = :uid AND tenant_id = :tid AND active = TRUE"),
        {"uid": user_id, "tid": tenant_id},
    )
    row = result.fetchone()
    old_url = row.avatar_url if row else None

    await db.execute(
        text(
            "UPDATE users SET avatar_url = NULL, last_updated_at = NOW() "
            "WHERE id = :uid AND tenant_id = :tid AND active = TRUE"
        ),
        {"uid": user_id, "tid": tenant_id},
    )
    await db.commit()
    return old_url


async def update_user_profile(
    db: AsyncSession, user_id: int, tenant_id: int, name: str
) -> bool:
    """Atualiza o nome do usuário (soft-update)."""
    result = await db.execute(
        text(
            "UPDATE users SET name = :name, last_updated_at = NOW() "
            "WHERE id = :uid AND tenant_id = :tid AND active = TRUE"
        ),
        {"name": name, "uid": user_id, "tid": tenant_id},
    )
    await db.commit()
    return result.rowcount > 0


async def update_user_password(
    db: AsyncSession, user_id: int, tenant_id: int, current_password: str, new_password: str
) -> bool:
    """Altera a senha após verificar a senha atual."""
    result = await db.execute(
        text(
            "SELECT password_hash FROM users "
            "WHERE id = :uid AND tenant_id = :tid AND active = TRUE AND auth_provider = 'local'"
        ),
        {"uid": user_id, "tid": tenant_id},
    )
    row = result.fetchone()

    if not row:
        return False

    if not bcrypt.checkpw(current_password.encode(), row.password_hash.encode()):
        return False

    new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    await db.execute(
        text(
            "UPDATE users SET password_hash = :ph, last_updated_at = NOW() "
            "WHERE id = :uid AND tenant_id = :tid"
        ),
        {"ph": new_hash, "uid": user_id, "tid": tenant_id},
    )
    await db.commit()
    logger.info("Password updated for user_id=%s", user_id)
    return True


async def update_user_preferences(
    db: AsyncSession,
    user_id: int,
    tenant_id: int,
    theme_mode: Optional[str] = None,
    accessibility_level: Optional[str] = None,
    high_contrast_mode: Optional[bool] = None,
    reduce_motion: Optional[bool] = None,
    colorblind_safe_palette: Optional[bool] = None,
) -> bool:
    """Atualiza preferências do usuário (tema + acessibilidade)."""
    updates: Dict[str, Any] = {}
    if theme_mode is not None:
        updates["theme_mode"] = theme_mode
    if accessibility_level is not None:
        updates["accessibility_level"] = accessibility_level
    if high_contrast_mode is not None:
        updates["high_contrast_mode"] = high_contrast_mode
    if reduce_motion is not None:
        updates["reduce_motion"] = reduce_motion
    if colorblind_safe_palette is not None:
        updates["colorblind_safe_palette"] = colorblind_safe_palette

    if not updates:
        return False

    set_clause = ", ".join(f"{col} = :{col}" for col in updates)
    params = {**updates, "uid": user_id, "tid": tenant_id}
    await db.execute(
        text(f"UPDATE users SET {set_clause}, last_updated_at = NOW() "
             "WHERE id = :uid AND tenant_id = :tid AND active = TRUE"),
        params,
    )
    await db.commit()
    return True
