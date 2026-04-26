import logging
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

engine = create_async_engine(
    settings.async_database_url,
    echo=False,          # nunca usar echo=True — adiciona handler próprio e duplica logs
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# expire_on_commit=False evita lazy-load de atributos expirados após commit
# (não funciona em contexto async sem await explícito).
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async DB session and closes it after the request."""
    async with AsyncSessionLocal() as session:
        yield session


async def ping_database() -> bool:
    """Verifica conectividade com o banco."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("Database ping failed: %s", exc)
        return False
