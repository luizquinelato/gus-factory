import json
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.database import ping_database
from app.core.logging_config import setup_logging
from app.routers import api_router

settings = get_settings()

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Backend iniciando (env=%s)...", settings.ENVIRONMENT)
    if ping_database():
        logger.info("✅ Database conectado.")
    else:
        logger.error("❌ Database NÃO conectado.")
    yield
    logger.info("🛑 Backend encerrando.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
origins = settings.BACKEND_CORS_ORIGINS
if isinstance(origins, str):
    try:
        origins = json.loads(origins)
    except ValueError:
        origins = [origins]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Internal-Key"],
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


app.include_router(api_router, prefix=settings.API_V1_STR)

# ── Static files (avatars, uploads) ───────────────────────────────────────────
_uploads_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(os.path.join(_uploads_dir, "avatars"), exist_ok=True)
app.mount("/static", StaticFiles(directory=_uploads_dir), name="static")
