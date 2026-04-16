import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import ping_database
from app.core.logging_config import setup_logging
from app.routers import api_router

settings = get_settings()

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Auth Service iniciando (env=%s)...", settings.ENVIRONMENT)
    if ping_database():
        logger.info("✅ Database conectado.")
    else:
        logger.error("❌ Database NÃO conectado — verifique o PostgreSQL.")
    yield
    logger.info("🛑 Auth Service encerrando.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

# CORS — o Auth Service só é chamado pelo Backend (localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:10000", "http://localhost:10010"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    ms = (time.time() - start) * 1000
    logger.info("%s %s — %s — %.2fms", request.method, request.url.path, response.status_code, ms)
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Erro não tratado: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Erro interno do servidor."},
    )


@app.get("/health", tags=["health"])
def health():
    return {"status": "healthy", "service": "saas-blueprint-v1-auth"}


@app.get("/health/database", tags=["health"])
def health_database():
    ok = ping_database()
    return {"status": "healthy" if ok else "unhealthy", "database": "connected" if ok else "disconnected"}


app.include_router(api_router, prefix=settings.API_V1_STR)
