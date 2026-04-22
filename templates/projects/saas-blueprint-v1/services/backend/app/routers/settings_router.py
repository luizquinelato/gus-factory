"""
settings_router.py
==================
GET  /api/v1/settings               → lista todas as settings do tenant
GET  /api/v1/settings/{key}         → uma setting específica
PUT  /api/v1/settings/{key}         → atualiza o valor de uma setting

As settings são lidas/gravadas na tabela system_settings.
Tenant é inferido do token JWT (current_user.tenant_id).

Nota: as queries tentam incluir setting_type (adicionada pela migration 0003).
Se a coluna ainda não existir (migration pendente), fazem fallback para 'string'.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.dependencies.auth import require_admin
from app.etl.worker_manager import WorkerManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["ETL — Settings"])


class SettingUpdate(BaseModel):
    value: str | int | float | bool | dict | None


# ── helpers ───────────────────────────────────────────────────────────────────

async def _query_settings(db: AsyncSession, tid: int) -> list[dict]:
    """
    Tenta buscar settings com setting_type.
    Faz fallback para 'string' se a coluna ainda não existir (migration 0003 pendente).
    """
    try:
        rows = await db.execute(
            text("""
                SELECT setting_key, setting_value,
                       COALESCE(setting_type, 'string') AS setting_type,
                       description
                FROM   system_settings
                WHERE  tenant_id = :tid AND active = true
                ORDER  BY setting_key
            """),
            {"tid": tid},
        )
        return [
            {"key": r.setting_key, "value": r.setting_value,
             "type": r.setting_type, "description": r.description}
            for r in rows.fetchall()
        ]
    except ProgrammingError:
        await db.rollback()
        rows = await db.execute(
            text("""
                SELECT setting_key, setting_value, description
                FROM   system_settings
                WHERE  tenant_id = :tid AND active = true
                ORDER  BY setting_key
            """),
            {"tid": tid},
        )
        return [
            {"key": r.setting_key, "value": r.setting_value,
             "type": "string", "description": r.description}
            for r in rows.fetchall()
        ]


async def _query_setting(db: AsyncSession, tid: int, key: str) -> dict | None:
    """
    Tenta buscar uma setting com setting_type.
    Faz fallback para 'string' se a coluna ainda não existir.
    """
    try:
        row = await db.execute(
            text("""
                SELECT setting_key, setting_value,
                       COALESCE(setting_type, 'string') AS setting_type,
                       description
                FROM   system_settings
                WHERE  tenant_id = :tid AND setting_key = :key AND active = true
            """),
            {"tid": tid, "key": key},
        )
        r = row.fetchone()
        if not r:
            return None
        return {"key": r.setting_key, "value": r.setting_value,
                "type": r.setting_type, "description": r.description}
    except ProgrammingError:
        await db.rollback()
        row = await db.execute(
            text("""
                SELECT setting_key, setting_value, description
                FROM   system_settings
                WHERE  tenant_id = :tid AND setting_key = :key AND active = true
            """),
            {"tid": tid, "key": key},
        )
        r = row.fetchone()
        if not r:
            return None
        return {"key": r.setting_key, "value": r.setting_value,
                "type": "string", "description": r.description}


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("", summary="List all settings for current tenant")
async def list_settings(
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    settings = await _query_settings(db, user["tenant_id"])
    return {"settings": settings}


@router.get("/{key}", summary="Get a specific setting")
async def get_setting(
    key: str,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    setting = await _query_setting(db, user["tenant_id"], key)
    if not setting:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    return setting


_WORKER_SETTING_MAP = {
    "extraction_workers": "extraction",
    "transform_workers":  "transform",
    "processor_workers":  "processor",
}


@router.put("/{key}", summary="Update a setting value")
async def update_setting(
    key: str,
    body: SettingUpdate,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    value_str = str(body.value) if not isinstance(body.value, str) else body.value

    result = await db.execute(
        text("""
            UPDATE system_settings
            SET    setting_value = :val, last_updated_at = NOW()
            WHERE  tenant_id = :tid AND setting_key = :key AND active = true
            RETURNING setting_key
        """),
        {"val": value_str, "tid": user["tenant_id"], "key": key},
    )
    updated = result.fetchone()
    if not updated:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found or not editable")

    await db.commit()
    logger.info("Setting '%s' updated for tenant %d", key, user["tenant_id"])

    # If a worker-count setting changed, scale the live pool immediately.
    if key in _WORKER_SETTING_MAP:
        worker_type = _WORKER_SETTING_MAP[key]
        try:
            count = int(float(value_str))
            WorkerManager.get_instance().set_count(worker_type, count)
            logger.info("WorkerManager: scaled %s pool to %d", worker_type, count)
        except (ValueError, TypeError) as exc:
            logger.warning("Could not scale %s pool: %s", worker_type, exc)

    return {"key": key, "value": body.value, "message": "Setting updated"}
