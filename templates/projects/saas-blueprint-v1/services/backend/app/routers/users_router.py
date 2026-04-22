"""
users_router.py
===============
GET    /api/v1/users/me             → Perfil do usuário autenticado
PATCH  /api/v1/users/me             → Atualizar nome
PATCH  /api/v1/users/me/password    → Alterar senha
PATCH  /api/v1/users/me/preferences → Atualizar tema e preferências de acessibilidade
POST   /api/v1/users/me/avatar      → Upload de foto de perfil
DELETE /api/v1/users/me/avatar      → Remover foto de perfil
"""
import logging
import os
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.dependencies.auth import require_authentication
from app.schemas.user_schemas import UserResponse, UserUpdateRequest, UserPreferencesRequest
from app.services.user_service import (
    get_user_by_id,
    update_user_profile,
    update_user_password,
    update_user_preferences,
    update_user_avatar,
    remove_user_avatar,
)

AVATARS_BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "avatars")
AVATARS_URL_PREFIX = "/static/avatars"
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_SIZE_MB = 5


def _avatar_url_to_path(avatar_url: str) -> str:
    """Converte /static/avatars/{tenant_id}/{filename} → caminho absoluto no disco."""
    relative = avatar_url.removeprefix(AVATARS_URL_PREFIX + "/")
    return os.path.join(AVATARS_BASE_DIR, *relative.split("/"))

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_my_profile(
    current_user: Dict[str, Any] = Depends(require_authentication),
    db: AsyncSession = Depends(get_db_session),
):
    user = await get_user_by_id(db, current_user["id"], current_user["tenant_id"])
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    return UserResponse(**user)


@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
    body: UserUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_authentication),
    db: AsyncSession = Depends(get_db_session),
):
    if body.name:
        success = await update_user_profile(db, current_user["id"], current_user["tenant_id"], body.name)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    user = await get_user_by_id(db, current_user["id"], current_user["tenant_id"])
    return UserResponse(**user)


@router.patch("/me/password")
async def change_password(
    body: UserUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_authentication),
    db: AsyncSession = Depends(get_db_session),
):
    if not body.current_password or not body.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preencha senha atual e nova senha.")

    success = await update_user_password(
        db, current_user["id"], current_user["tenant_id"], body.current_password, body.new_password
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Senha atual incorreta ou usuário não encontrado.")

    return {"detail": "Senha alterada com sucesso."}


@router.patch("/me/preferences")
async def update_preferences(
    body: UserPreferencesRequest,
    current_user: Dict[str, Any] = Depends(require_authentication),
    db: AsyncSession = Depends(get_db_session),
):
    await update_user_preferences(
        db,
        user_id=current_user["id"],
        tenant_id=current_user["tenant_id"],
        theme_mode=body.theme_mode,
        accessibility_level=body.accessibility_level,
        high_contrast_mode=body.high_contrast_mode,
        reduce_motion=body.reduce_motion,
        colorblind_safe_palette=body.colorblind_safe_palette,
    )
    return {"detail": "Preferências atualizadas."}


@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(require_authentication),
    db: AsyncSession = Depends(get_db_session),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail="Formato inválido. Use JPEG, PNG, WebP ou GIF.")

    contents = await file.read()
    if len(contents) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"Arquivo muito grande. Limite: {MAX_SIZE_MB}MB.")

    tenant_id = current_user["tenant_id"]
    tenant_dir = os.path.join(AVATARS_BASE_DIR, str(tenant_id))
    os.makedirs(tenant_dir, exist_ok=True)

    ext = (file.filename or "avatar").rsplit(".", 1)[-1].lower()
    filename = f"{current_user['id']}_{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(tenant_dir, filename)

    # Remove avatar anterior se existir
    old_url = await remove_user_avatar(db, current_user["id"], tenant_id)
    if old_url:
        old_path = _avatar_url_to_path(old_url)
        if os.path.exists(old_path):
            os.remove(old_path)

    with open(filepath, "wb") as f:
        f.write(contents)

    avatar_url = f"{AVATARS_URL_PREFIX}/{tenant_id}/{filename}"
    await update_user_avatar(db, current_user["id"], tenant_id, avatar_url)
    logger.info("Avatar updated for user_id=%s tenant_id=%s → %s", current_user["id"], tenant_id, avatar_url)
    return {"avatar_url": avatar_url}


@router.delete("/me/avatar")
async def delete_avatar(
    current_user: Dict[str, Any] = Depends(require_authentication),
    db: AsyncSession = Depends(get_db_session),
):
    old_url = await remove_user_avatar(db, current_user["id"], current_user["tenant_id"])
    if old_url:
        old_path = _avatar_url_to_path(old_url)
        if os.path.exists(old_path):
            os.remove(old_path)
    return {"detail": "Avatar removido."}
