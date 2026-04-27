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
1. `lifespan` for initialization/teardown — db, OutboxProcessor, ETL workers.
2. Global Exception Handler to format 500 errors.
3. Restrictive CORS based on `get_settings()`.
4. Logging middleware to record response time.
5. `ModuleRegistry.include_all()` to load business module routers.

```python
# app/main.py
import logging, time, os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.database import ping_database
from app.core.logging_config import setup_logging
from app.core.outbox_processor import outbox_processor  # delivers reliable events
from app.modules import ModuleRegistry
from app.routers import api_router

# ── Business modules ──────────────────────────────────────────────────────────
# Each import registers the module in ModuleRegistry and its handlers in EventBus.
# To add a module: `import app.modules.my_module  # noqa`
import app.modules.demo  # noqa — remove in production

settings = get_settings()
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Backend starting (env=%s)...", settings.ENVIRONMENT)

    if await ping_database():
        logger.info("✅ Database connected.")
    else:
        logger.error("❌ Database NOT connected.")

    # Outbox Processor — delivers emit_reliable() events after commit
    outbox_processor.start()

    # ETL Workers — omit if `etl` feature is disabled
    try:
        from app.etl.queue_manager import QueueManager
        from app.etl.worker_manager import WorkerManager
        QueueManager.get_instance().declare_all_queues()
        WorkerManager.get_instance().start_all()
        logger.info("✅ ETL workers started.")
    except Exception as exc:
        logger.warning("⚠️  ETL unavailable: %s", exc)

    yield

    outbox_processor.stop()
    try:
        from app.etl.worker_manager import WorkerManager
        WorkerManager.get_instance().stop()
    except Exception:
        pass
    logger.info("🛑 Backend shutting down.")

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Internal-Key"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    logger.info("%s %s — %s — %.2fms",
                request.method, request.url.path, response.status_code,
                (time.time() - start) * 1000)
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error: %s", exc, exc_info=True)
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={"detail": "Internal server error."})

# Business modules + core routers
ModuleRegistry.include_all(api_router)
app.include_router(api_router, prefix=settings.API_V1_STR)

# Static files (avatars, uploads)
_uploads = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(os.path.join(_uploads, "avatars"), exist_ok=True)
app.mount("/static", StaticFiles(directory=_uploads), name="static")
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


## 📡 12. Event Bus — Inter-Module Communication

The backend follows the **Modular Monolith** architecture. Communication between modules uses the `EventBus` — never direct imports between business modules.

### Two emission modes

| Mode | Method | Guarantee | When to use |
|---|---|---|---|
| **Best-effort** | `EventBus.emit()` | In-process, no retry | Cache, notifications, UI |
| **Reliable** | `EventBus.emit_reliable()` | Transactional via Outbox | Finance, stock, accounting |

```python
# Best-effort (informational — failure is not critical)
await EventBus.emit("product.updated", {"id": product_id, "tenant_id": tenant_id})

# Reliable — MANDATORY for financial/stock data
# tenant_id is required — isolates events per tenant
await EventBus.emit_reliable(
    "order.confirmed",
    {"order_id": order_id, "total": total},
    db,
    tenant_id=current_user["tenant_id"],
)
await db.commit()   # commit persists the event together with the business data
```

### Rule: emit vs emit_reliable

```
├── Crosses a financial boundary?      → emit_reliable ⚠️
│     order.confirmed, payment.confirmed, purchase.received
├── Effectively modifies stock?        → emit_reliable ⚠️
│     order.paid, order.cancelled, order.delivered
└── Informational / cache / alert?     → emit
      product.updated, client.created, stock.low
```

### Registering handlers

```python
# modules/stock/events.py
from app.core.event_bus import EventBus

async def on_order_confirmed(payload: dict) -> None:
    """Reserve stock when an order is confirmed."""
    # reservation logic...

# modules/stock/__init__.py
from app.modules.stock.events import on_order_confirmed
from app.core.event_bus import EventBus

EventBus.subscribe("order.confirmed", on_order_confirmed)
```

### OutboxProcessor

Background task started in `main.py` lifespan. Every 2s:
1. `SELECT FOR UPDATE SKIP LOCKED` — safe for multiple instances
2. Injects `__event_id__` and `__tenant_id__` into the payload
3. Delivers via `EventBus.emit()` (in-process handlers)
4. Sets `processed_at` or increments `attempts` / sets `failed_at` (dead-letter)

**Monitoring:** `Settings → Outbox` (admin-only) — accessible in the main frontend.

### Metadata injected by OutboxProcessor

Every `emit_reliable` handler receives two system-injected keys in its `payload`:

| Key | Type | Usage |
|---|---|---|
| `__event_id__` | `int` | Idempotency key — use in `ON CONFLICT (outbox_event_id) DO NOTHING` |
| `__tenant_id__` | `int` | Tenant source of truth — ALWAYS use to filter queries, never `payload["tenant_id"]` |

```python
# idempotent handler with correct tenant isolation
async def on_order_confirmed(payload: dict) -> None:
    event_id  = payload["__event_id__"]   # idempotency key
    tenant_id = payload["__tenant_id__"]  # isolation — source of truth
    order_id  = payload["order_id"]

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("""
                INSERT INTO stock_reservations
                    (outbox_event_id, order_id, tenant_id, reserved_at)
                VALUES (:eid, :oid, :tid, NOW())
                ON CONFLICT (outbox_event_id) DO NOTHING
            """),
            {"eid": event_id, "oid": order_id, "tid": tenant_id},
        )
        await db.commit()
```

> **Tables affected by `emit_reliable`** should have `outbox_event_id BIGINT UNIQUE` to guarantee idempotency — the OutboxProcessor delivers *at-least-once*.
