<!-- blueprint: db_changes=false seed_data=false -->
# 06. Backend Code Patterns

This document defines the mandatory patterns for Backend Service development in FastAPI.

## 📦 0. Dependencies (requirements.txt)

**Two rules without exception:**

1. **Never pin versions** — write only the package name, without `==`, `>=` or `~=`.
   The AI does not know which version is available at execution time; versions pinned from training memory generate incompatibilities with the installed Python.

2. **Use exactly what the document specifies** — do not introduce unsolicited abstraction libraries.
   If the doc says `bcrypt`, write `bcrypt`, not `passlib[bcrypt]`.
   If the doc says `SQLAlchemy`, write `sqlalchemy`, not `databases` or another wrapper.

**Base stack (copy without modifying versions — do not add `==x.y.z`):**

```
fastapi
uvicorn[standard]
sqlalchemy
psycopg2-binary
pydantic-settings
python-jose[cryptography]
bcrypt
httpx
redis
```

## ⚙️ 1. Settings and Configuration (BaseSettings)

All environment variables must be typed and validated via `pydantic-settings`. Never use `os.getenv()` directly in business code.

```python
# app/core/config.py
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

_env = os.getenv("APP_ENV", "prod")

class Settings(BaseSettings):
    PROJECT_NAME: str = "{{ PROJECT_NAME }}"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = _env

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DATABASE: str = "{{ DB_NAME_PROD }}"
    SQL_ECHO: bool = False

    JWT_SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 5
    SESSION_EXPIRE_MINUTES: int = 60

    REDIS_URL: str = "redis://localhost:6379/0"
    AUTH_SERVICE_URL: str = "http://localhost:{{ AUTH_PORT }}"
    FRONTEND_URL: str = "http://localhost:{{ FRONTEND_PORT }}"
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:{{ FRONTEND_PORT }}"]

    model_config = SettingsConfigDict(
        env_file=[f"../../.env.{_env}", f".env.{_env}"],
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DATABASE}"
        )

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

## 🚀 2. main.py Pattern

The main file must include:
1. `lifespan` for initialization/teardown (db, cache).
2. Global Exception Handler to format 500 errors.
3. Restrictive CORS based on `get_settings()`.
4. Logging middleware to record response time.

```python
# app/main.py
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import time, logging

from app.core.config import get_settings
from app.core.database import get_database
from app.routers import api_router

settings = get_settings()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting services...")
    db = get_database()
    db.connect()
    yield
    logger.info("🛑 Shutting down services...")
    db.disconnect()

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    logger.info(f"{request.method} {request.url.path} - {response.status_code} - {process_time:.2f}ms")
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error. Please try again later."}
    )

app.include_router(api_router, prefix=settings.API_V1_STR)
```

## 🛣️ 3. Router and Endpoint Pattern

Every endpoint must:
1. Receive `db: Session = Depends(get_db_session)`.
2. Receive `current_user = Depends(require_authentication)`.
3. Use separate Pydantic schemas for Request and Response.
4. Handle business errors with `HTTPException`.

```python
# app/routers/users_router.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import logging

from app.core.database import get_db_session
from app.dependencies.auth import require_authentication, require_permission
from app.schemas.user_schemas import UserCreate, UserResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])
logger = logging.getLogger(__name__)

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_permission("users", "write"))
):
    """Creates a new user in the current tenant."""
    try:
        service = UserService(db)
        user = service.create(user_in, tenant_id=current_user["tenant_id"])
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating user: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating user")
```

## 📄 4. Pagination and Standard Filters

Listing endpoints (GET) must always implement standardized pagination and filters.

```python
# app/schemas/common.py
from pydantic import BaseModel
from typing import Generic, TypeVar, List

T = TypeVar('T')

class PaginatedResponse(BaseModel, Generic[T]):
    data: List[T]
    total: int
    page: int
    size: int
    pages: int

@router.get("/", response_model=PaginatedResponse[UserResponse])
def list_users(
    page: int = 1,
    size: int = 50,
    search: str = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_authentication)
):
    # Implementation...
```

## 👤 7. `/users/me` Endpoint (Mandatory)

Every backend must expose `GET /api/v1/users/me` and `PATCH /api/v1/users/me/preferences`.

```python
router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me")
async def get_current_user(current_user: dict = Depends(require_authentication)):
    """Returns the authenticated user's data."""
    return {"success": True, "user": current_user}

@router.patch("/me/preferences")
async def update_preferences(
    payload: dict,
    current_user: dict = Depends(require_authentication),
    db = Depends(get_db)
):
    """Updates user preferences (theme, accessibility, etc.)."""
    user_id = current_user["id"]
    tenant_id = current_user["tenant_id"]
    allowed_fields = {"theme_mode", "use_accessible_colors"}
    updates = {k: v for k, v in payload.items() if k in allowed_fields}
    if not updates:
        return {"success": False, "message": "No valid fields to update."}
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [user_id, tenant_id]
    async with db.cursor() as cur:
        await cur.execute(
            f"UPDATE users SET {set_clause} WHERE id = %s AND tenant_id = %s AND active = TRUE",
            values
        )
    return {"success": True, "updated": list(updates.keys())}
```

## 🎨 8. Login Response — Colors in Payload

The `POST /api/auth/login` endpoint **must include tenant colors** in the response.

```python
class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    tenant_colors: TenantColorsPayload

class TenantColorsPayload(BaseModel):
    color_schema_mode: str       # 'default' | 'custom'
    colors: list[ColorSchemeResponse]

@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginCredentials, db = Depends(get_db_session)):
    user = await authenticate_user(credentials.email, credentials.password, db)
    token = create_access_token({"sub": str(user.id), "tenant_id": user.tenant_id})
    color_rows = await color_service.get_all_colors_for_tenant(user.tenant_id, db)
    tenant = await tenant_service.get_by_id(user.tenant_id, db)
    return LoginResponse(
        access_token=token,
        user=UserResponse.from_orm(user),
        tenant_colors=TenantColorsPayload(
            color_schema_mode=tenant.color_schema_mode,
            colors=color_rows
        )
    )
```

## 🏥 9. Health Check (Mandatory)

Every service must expose a `/health` endpoint.

```python
@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "{{ PROJECT_NAME }}-backend"}

@router.get("/health/database")
async def health_database(db = Depends(get_db)):
    try:
        async with db.cursor() as cur:
            await cur.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}
```
