"""
redis_client.py
===============
Cliente Redis assíncrono compartilhado.

Usado atualmente para OTT (One-Time Token) do fluxo SSO → ETL.
TTL curto (30s), chave descartada após primeiro uso.
"""
import logging

import redis.asyncio as aioredis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Instância única reutilizada entre requests (connection pool interno do redis-py).
_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Retorna (ou cria) o cliente Redis assíncrono."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis


async def redis_set(key: str, value: str, ttl_seconds: int) -> None:
    """Grava uma chave com TTL."""
    await get_redis().setex(key, ttl_seconds, value)


async def redis_get(key: str) -> str | None:
    """Lê uma chave. Retorna None se não existir ou expirada."""
    return await get_redis().get(key)


async def redis_delete(key: str) -> None:
    """Remove uma chave."""
    await get_redis().delete(key)


async def redis_get_and_delete(key: str) -> str | None:
    """Lê e remove atomicamente (uso único). Retorna None se não existir."""
    client = get_redis()
    value = await client.get(key)
    if value is not None:
        await client.delete(key)
    return value
