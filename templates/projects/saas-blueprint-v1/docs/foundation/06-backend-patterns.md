<!-- blueprint: db_changes=false seed_data=false -->
# 06. Padrões de Código do Backend

Este documento define os padrões obrigatórios para o desenvolvimento do Backend Service em FastAPI.

## 📦 0. Dependências (requirements.txt)

**Duas regras sem exceção:**

1. **Nunca pinie versões** — escreva apenas o nome do pacote, sem `==`, `>=` ou `~=`.
   A IA não sabe qual versão está disponível no momento da execução; versões pinadas de memória de treinamento geram incompatibilidades com o Python instalado.

2. **Use exatamente o que o documento pede** — não introduza bibliotecas de abstração não solicitadas.
   Se o doc diz `bcrypt`, escreva `bcrypt`, não `passlib[bcrypt]`.
   Se o doc diz `SQLAlchemy`, escreva `sqlalchemy`, não `databases` ou outro wrapper.

**Stack base (copie sem modificar as versões — não adicione `==x.y.z`):**

```
fastapi
uvicorn[standard]
psycopg2-binary
pydantic-settings
python-jose[cryptography]
bcrypt
httpx
redis
python-multipart
aiofiles
```

> **Nota sobre ORM:** O blueprint atual usa `SQLAlchemy` síncrono. A direção arquitetural é migrar para `psycopg2` assíncrono (`psycopg` v3 ou `asyncpg`) + queries SQL puras — eliminando a camada ORM. Os exemplos de código neste documento usam o modelo async como **padrão alvo**. Enquanto a migração não ocorrer, adapte os exemplos para `Session` síncrono do SQLAlchemy conforme o blueprint v1.

## ⚙️ 1. Settings e Configuração (BaseSettings)

Todas as variáveis de ambiente devem ser tipadas e validadas via `pydantic-settings`. Nunca use `os.getenv()` diretamente no código de negócio.

```python
# app/core/config.py
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

# APP_ENV é injetado pelo PS Profile antes de iniciar o uvicorn:
#   $env:APP_ENV = "prod"  → carrega .env.prod
#   $env:APP_ENV = "dev"   → carrega .env.dev
_env = os.getenv("APP_ENV", "prod")

class Settings(BaseSettings):
    PROJECT_NAME: str = "{{ PROJECT_NAME }}"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = _env

    # Database (variáveis separadas — nunca concatene manualmente em código de negócio)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DATABASE: str = "{{ DB_NAME_PROD }}"
    SQL_ECHO: bool = False

    # Security
    JWT_SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 5        # Token curto — auto-refresh mantém a sessão ativa
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7         # Refresh token — rotacionado a cada uso
    INTERNAL_API_KEY: str                      # Chave de comunicação inter-serviços (Backend → Auth Service)

    # Cache
    REDIS_URL: str = "redis://localhost:6379/0"

    # URLs de serviços — sempre localhost (serviços rodam no host, não em containers)
    AUTH_SERVICE_URL: str = "http://localhost:{{ AUTH_PORT }}"
    FRONTEND_URL: str = "http://localhost:{{ FRONTEND_PORT }}"

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:{{ FRONTEND_PORT }}"]

    model_config = SettingsConfigDict(
        env_file=[f"../../.env.{_env}", f".env.{_env}"],  # raiz primeiro, serviço faz override
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

## 🚀 2. Padrão do main.py

O arquivo principal deve incluir:
1. `lifespan` para inicialização/teardown — banco, OutboxProcessor, ETL workers.
2. Global Exception Handler para formatar erros 500.
3. CORS restritivo baseado no `get_settings()`.
4. Middleware de logging para registrar tempo de resposta.
5. `ModuleRegistry.include_all()` para carregar os routers dos módulos de negócio.

```python
# app/main.py
import logging, time, json, os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.database import ping_database
from app.core.logging_config import setup_logging
from app.core.outbox_processor import outbox_processor   # background task — entrega eventos confiáveis
from app.modules import ModuleRegistry
from app.routers import api_router

# ── Módulos de negócio ────────────────────────────────────────────────────────
# Cada import registra o módulo no ModuleRegistry e seus handlers no EventBus.
# Para adicionar: `import app.modules.meu_modulo  # noqa`
import app.modules.demo  # noqa — remova em produção

settings = get_settings()
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Backend iniciando (env=%s)...", settings.ENVIRONMENT)

    if await ping_database():
        logger.info("✅ Database conectado.")
    else:
        logger.error("❌ Database NÃO conectado.")

    # Outbox Processor — entrega eventos do emit_reliable() após commit
    outbox_processor.start()

    # ETL Workers — omita se a feature `etl` estiver desligada
    try:
        from app.etl.queue_manager import QueueManager
        from app.etl.worker_manager import WorkerManager
        QueueManager.get_instance().declare_all_queues()
        WorkerManager.get_instance().start_all()
        logger.info("✅ ETL workers iniciados.")
    except Exception as exc:
        logger.warning("⚠️  ETL indisponível: %s", exc)

    yield

    outbox_processor.stop()
    try:
        from app.etl.worker_manager import WorkerManager
        WorkerManager.get_instance().stop()
    except Exception:
        pass
    logger.info("🛑 Backend encerrando.")

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION, lifespan=lifespan)

# Rate limiting — veja seção 11
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.limiter import limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
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
    logger.error("Erro não tratado: %s", exc, exc_info=True)
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={"detail": "Erro interno do servidor."})

# Módulos de negócio + routers do core
ModuleRegistry.include_all(api_router)
app.include_router(api_router, prefix=settings.API_V1_STR)

# Arquivos estáticos (avatars, uploads)
_uploads = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(os.path.join(_uploads, "avatars"), exist_ok=True)
app.mount("/static", StaticFiles(directory=_uploads), name="static")
```

## 🛣️ 3. Padrão de Router e Endpoints

Todo endpoint deve:
1. Receber `db: Session = Depends(get_db_session)`.
2. Receber `current_user = Depends(require_authentication)`.
3. Usar schemas Pydantic separados para Request e Response.
4. Tratar erros de negócio com `HTTPException`.

```python
# app/routers/users_router.py          ← pasta correta: app/routers/ (não app/api/v1/endpoints/)
from fastapi import APIRouter, Depends, HTTPException, status
import logging

from app.core.database import get_db_session
from app.dependencies.auth import require_authentication, require_page_access
from app.schemas.user_schemas import UserCreate, UserResponse

router = APIRouter(prefix="/users", tags=["Users"])
logger = logging.getLogger(__name__)

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    db = Depends(get_db_session),
    current_user: dict = Depends(require_page_access("users"))  # ← page_key, não resource×action
):
    """Cria um novo usuário no tenant atual."""
    try:
        async with db.cursor() as cur:
            # O tenant_id vem do usuário autenticado, NUNCA do payload
            await cur.execute(
                "INSERT INTO users (name, email, role, tenant_id) VALUES (%s, %s, %s, %s) RETURNING id",
                (user_in.name, user_in.email, user_in.role, current_user["tenant_id"])
            )
            new_id = (await cur.fetchone())["id"]
        return UserResponse(id=new_id, **user_in.dict(), tenant_id=current_user["tenant_id"])
    except ValueError as e:
        logger.warning(f"Erro de validação ao criar usuário: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro inesperado ao criar usuário: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao criar usuário")
```

## 📄 4. Paginação e Filtros Padrão

Endpoints de listagem (GET) devem sempre implementar paginação e filtros padronizados.

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

# Uso no router:
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
    # Implementação...
```

## 📝 5. Padrão de Logging Estruturado

O sistema utiliza um logger centralizado configurado no startup da aplicação. Nunca use `print()`.

```python
# app/core/logging_config.py
import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

# Configuração global
LOG_LEVEL = logging.INFO
DISABLE_LOG_FILTERS = False

def setup_logging(force_reconfigure=False):
    """Configura o logger raiz da aplicação."""
    root_logger = logging.getLogger()
    if root_logger.handlers and not force_reconfigure:
        return

    # Limpa handlers existentes
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(LOG_LEVEL)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File Handler (Opcional para produção)
    # file_handler = RotatingFileHandler("app.log", maxBytes=10485760, backupCount=5)
    # file_handler.setFormatter(formatter)
    # root_logger.addHandler(file_handler)

    root_logger.setLevel(LOG_LEVEL)

def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Retorna uma instância de logger limpa para o módulo."""
    if name is None:
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get('__name__', 'unknown')
        else:
            name = 'unknown'
    return logging.getLogger(name)
```

**Uso nos módulos:**
```python
from app.core.logging_config import get_logger

logger = get_logger(__name__)

def minha_funcao():
    logger.debug("Mensagem de debug (desenvolvimento)")
    logger.info("Ação concluída com sucesso")
    logger.warning("Algo inesperado aconteceu, mas o fluxo continua")
    logger.error("Erro crítico que impede a execução", exc_info=True)
```

## 👤 7. Endpoint `/users/me` (Obrigatório)

Todo backend deve expor `GET /api/v1/users/me` e `PATCH /api/v1/users/me/preferences` para que o frontend possa carregar e atualizar as preferências do usuário autenticado (tema, acessibilidade, etc).

```python
# app/routers/users_router.py           ← pasta correta: app/routers/
from fastapi import APIRouter, Depends
from app.dependencies.auth import require_authentication

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me")
async def get_current_user(current_user: dict = Depends(require_authentication)):
    """Retorna os dados do usuário autenticado."""
    return current_user  # payload direto — sem envelope {"success": true}

@router.patch("/me/preferences")
async def update_preferences(
    payload: dict,
    current_user: dict = Depends(require_authentication),
    db = Depends(get_db_session)
):
    """
    Atualiza preferências do usuário autenticado (tema, acessibilidade).

    Campos permitidos (tabela users — ver doc 03):
      - theme_mode: 'light' | 'dark'
      - accessibility_level: 'regular' | 'AA' | 'AAA'
      - high_contrast_mode: bool
      - reduce_motion: bool
      - colorblind_safe_palette: bool
    """
    user_id = current_user["id"]
    tenant_id = current_user["tenant_id"]
    allowed_fields = {"theme_mode", "accessibility_level", "high_contrast_mode",
                      "reduce_motion", "colorblind_safe_palette"}
    updates = {k: v for k, v in payload.items() if k in allowed_fields}
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nenhum campo válido para atualizar.")
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [user_id, tenant_id]
    async with db.cursor() as cur:
        await cur.execute(
            f"UPDATE users SET {set_clause} WHERE id = %s AND tenant_id = %s AND active = TRUE",
            values
        )
    logger.info(f"Preferências do usuário {user_id} atualizadas: {list(updates.keys())}")
    return {"updated": list(updates.keys())}
```

## 🖼️ 7b. Upload de Avatar (Obrigatório no blueprint)

O blueprint expõe endpoints de upload e remoção de avatar. Arquivos são servidos via `StaticFiles`.

```python
# app/routers/users_router.py — endpoints de avatar
from fastapi import UploadFile, File
from fastapi.staticfiles import StaticFiles
import uuid, os, aiofiles

UPLOAD_DIR = "uploads/avatars"
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB

@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_authentication),
    db = Depends(get_db_session)
):
    """Upload de avatar. Substitui o anterior se existir."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de arquivo não permitido. Use JPEG, PNG ou WebP.")
    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Arquivo maior que 2 MB.")
    ext = file.filename.rsplit(".", 1)[-1].lower()
    tenant_id = current_user["tenant_id"]
    filename = f"{uuid.uuid4()}.{ext}"
    folder = os.path.join(UPLOAD_DIR, str(tenant_id))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    async with aiofiles.open(path, "wb") as f:
        await f.write(content)
    avatar_url = f"/uploads/avatars/{tenant_id}/{filename}"
    async with db.cursor() as cur:
        await cur.execute(
            "UPDATE users SET avatar_url = %s WHERE id = %s AND tenant_id = %s",
            (avatar_url, current_user["id"], tenant_id)
        )
    return {"avatar_url": avatar_url}

@router.delete("/me/avatar", status_code=204)
async def delete_avatar(current_user: dict = Depends(require_authentication), db = Depends(get_db_session)):
    """Remove o avatar do usuário e o arquivo físico."""
    async with db.cursor() as cur:
        await cur.execute("SELECT avatar_url FROM users WHERE id = %s AND tenant_id = %s",
                          (current_user["id"], current_user["tenant_id"]))
        row = await cur.fetchone()
    if row and row["avatar_url"]:
        path = row["avatar_url"].lstrip("/")
        if os.path.exists(path):
            os.remove(path)
        async with db.cursor() as cur:
            await cur.execute("UPDATE users SET avatar_url = NULL WHERE id = %s AND tenant_id = %s",
                              (current_user["id"], current_user["tenant_id"]))
```

**Montar os arquivos estáticos no `main.py`:**
```python
from fastapi.staticfiles import StaticFiles
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
```

## 🎨 8. Login Response — Cores no Payload

O endpoint `POST /api/auth/login` **deve incluir as cores do tenant** na resposta. Isso elimina uma chamada extra ao backend (sem `GET /api/tenant/colors/unified` no startup) e garante que o frontend aplique as cores corretas imediatamente após o login.

```python
# Payload de resposta do login (schema Pydantic)
class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse           # inclui theme_mode do usuário
    tenant_colors: TenantColorsPayload

class TenantColorsPayload(BaseModel):
    color_schema_mode: str       # 'default' | 'custom' — modo ativo do tenant
    colors: list[ColorSchemeResponse]  # as 12 combinações (2 modos × 2 temas × 3 níveis WCAG)

# No router de autenticação:
@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginCredentials, db = Depends(get_db_session)):
    user = await authenticate_user(credentials.email, credentials.password, db)
    token = create_access_token({"sub": str(user.id), "tenant_id": user.tenant_id})

    # Inclui todas as 12 linhas de tenant_colors na resposta
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

**Frontend — cache imediato após login:**
```typescript
// Após receber a resposta do login:
const { access_token, user, tenant_colors } = response.data
localStorage.setItem('access_token',      access_token)
localStorage.setItem('user_data',         JSON.stringify(user))
localStorage.setItem('color_data',        JSON.stringify(tenant_colors.colors))      // 12 objetos
localStorage.setItem('color_schema_mode', tenant_colors.color_schema_mode)           // 'default'|'custom'
// Aplica as cores no DOM imediatamente (sem reload, sem extra API call)
applyColorsToDOM(getActiveColorRow(tenant_colors.colors, user.theme_mode))
```

**Estrutura do cache (`color_data` no localStorage):**
```json
[
  { "color_schema_mode": "default", "theme_mode": "light",  "accessibility_level": "regular",
    "color1": "#297BFF", "color2": "#0CC02A", "color3": "#005F61", "color4": "#6F74B8", "color5": "#220080",
    "on_color1": "#FFFFFF", "on_color2": "#000000", "on_color3": "#FFFFFF", "on_color4": "#FFFFFF", "on_color5": "#FFFFFF",
    "on_gradient_1_2": "#FFFFFF", "on_gradient_2_3": "#FFFFFF", "on_gradient_3_4": "#FFFFFF",
    "on_gradient_4_5": "#FFFFFF", "on_gradient_5_1": "#FFFFFF" },
  { "color_schema_mode": "default", "theme_mode": "dark",   "accessibility_level": "regular", "..." },
  { "color_schema_mode": "default", "theme_mode": "light",  "accessibility_level": "AA",      "..." },
  ... // 12 linhas no total: 2 color_schema_mode × 2 theme_mode × 3 accessibility_level
]
```

**Para ler as cores ativas (helper obrigatório):**
```typescript
function getActiveColorRow(colors: ColorRow[], themeMode: string): ColorRow | undefined {
  const mode  = localStorage.getItem('color_schema_mode') ?? 'default'
  const level = 'regular'   // mudar para 'AA'/'AAA' via preferência do usuário
  return colors.find(c =>
    c.color_schema_mode === mode &&
    c.theme_mode        === themeMode &&
    c.accessibility_level === level
  )
}
```

## 🏥 9. Health Check (Obrigatório)

Todo serviço deve expor um endpoint `/health` para verificações de saúde por orquestradores e load balancers.

```python
# app/routers/health_router.py         ← pasta correta: app/routers/ (não app/api/v1/endpoints/)
from fastapi import APIRouter, Depends
from app.core.database import get_db_session
import logging

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)

@router.get("/health")
async def health_check():
    """Health check básico — sempre retorna 200 se o serviço está de pé."""
    return {"status": "healthy", "service": "{{ PROJECT_NAME }}-backend"}

@router.get("/health/database")
async def health_database(db = Depends(get_db_session)):
    """Verifica conectividade com o banco de dados."""
    try:
        async with db.cursor() as cur:
            await cur.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}
```

Registre os routers no `main.py`:
```python
from app.routers import health_router, users_router
app.include_router(health_router.router, prefix="/api/v1")
app.include_router(users_router.router, prefix="/api/v1")
```


## 📋 10. Padrão de Resposta da API (Envelope)

Regra simples e consistente em todo o projeto:

| Situação | Formato | Exemplo |
|---|---|---|
| Sucesso com objeto | Pydantic model direto | `UserResponse` |
| Sucesso com lista paginada | `{"items": [...], "total": N}` | `PaginatedResponse` |
| Erro | `{"detail": "..."}` | FastAPI default |
| Operação sem retorno | `{"detail": "..."}` | `{"detail": "Preferências atualizadas."}` |

**Proibido:** `{"success": true, "data": ...}` — envelopes manuais não padronizados.

```python
# ✅ Objeto direto
@router.get("/me", response_model=UserResponse)
async def get_me(current_user = Depends(require_authentication)):
    return get_user_by_id(db, current_user["id"], current_user["tenant_id"])

# ✅ Lista paginada
from pydantic import BaseModel
from typing import Generic, List, TypeVar
T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int

@router.get("/users", response_model=PaginatedResponse[UserResponse])
async def list_users(...):
    return PaginatedResponse(items=rows, total=count)

# ✅ Confirmação de ação
@router.patch("/me/preferences")
async def update_preferences(...):
    ...
    return {"detail": "Preferências atualizadas."}

# ❌ Proibido
return {"success": True, "data": user}    # envelopes manuais
return {"status": "ok", "result": items}  # inconsistente com FastAPI
```

## 🚦 11. Rate Limiting (slowapi)

Proteção mínima obrigatória nos endpoints de autenticação. Use `slowapi` para FastAPI.

**Instalação:**
```
slowapi
```

```python
# app/main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

```python
# auth-service/app/routers/auth_router.py — aplicar no login
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/login")
@limiter.limit("5/minute")   # máximo 5 tentativas por minuto por IP
async def login(request: Request, credentials: LoginRequest, ...):
    ...

@router.post("/refresh")
@limiter.limit("30/minute")  # refresh pode ser mais permissivo
async def refresh(request: Request, body: RefreshRequest, ...):
    ...
```

> **Regra:** Endpoints `/auth/login` e `/auth/refresh` **sempre** têm rate limit.
> Para outros endpoints sensíveis (ex: reset de senha, upload), avalie caso a caso.

## 📡 12. Event Bus — Comunicação entre Módulos

O backend segue a arquitetura **Modular Monolith** (ver `06-backend-patterns.md` + doc de arquitetura do projeto). A comunicação entre módulos usa o `EventBus` — nunca imports diretos entre módulos de negócio.

### Dois modos de emissão

| Modo | Método | Garantia | Quando usar |
|---|---|---|---|
| **Best-effort** | `EventBus.emit()` | In-process, sem retry | Cache, notificações, UI |
| **Confiável** | `EventBus.emit_reliable()` | Transacional via Outbox | Finanças, estoque, contabilidade |

```python
# core/event_bus.py — uso nos módulos

# Best-effort (informativo — falha não é crítica)
await EventBus.emit("product.updated", {"id": product_id, "tenant_id": tenant_id})

# Confiável — OBRIGATÓRIO para dados financeiros/estoque
# tenant_id é obrigatório — isola eventos por tenant
await EventBus.emit_reliable(
    "order.confirmed",
    {"order_id": order_id, "total": total},
    db,
    tenant_id=current_user["tenant_id"],
)
await db.commit()   # o commit persiste o evento junto com o dado de negócio
```

### Regra: emit vs emit_reliable

```
├── Cruza fronteira financeira?        → emit_reliable ⚠️
│     order.confirmed, payment.confirmed, purchase.received
├── Modifica estoque efetivamente?     → emit_reliable ⚠️
│     order.paid, order.cancelled, order.delivered
└── Informativo / cache / alerta?      → emit
      product.updated, client.created, stock.low
```

### Registrar handlers

```python
# modules/estoque/events.py
from app.core.event_bus import EventBus

async def on_order_confirmed(payload: dict) -> None:
    """Reserva estoque quando pedido é confirmado."""
    # lógica de reserva...

# modules/estoque/__init__.py
from app.modules.estoque.events import on_order_confirmed
from app.core.event_bus import EventBus

EventBus.subscribe("order.confirmed", on_order_confirmed)
```

### OutboxProcessor

Background task iniciado no `lifespan` do `main.py`. A cada 2s:
1. `SELECT FOR UPDATE SKIP LOCKED` — seguro para múltiplas instâncias
2. Injeta `__event_id__` e `__tenant_id__` no payload
3. Entrega via `EventBus.emit()` (handlers in-process)
4. Marca `processed_at` ou incrementa `attempts` / seta `failed_at` (dead-letter)

**Monitoramento:** `Configurações → Outbox` (admin-only) — acessível no frontend principal.

### Metadados injetados pelo OutboxProcessor

Todo handler de `emit_reliable` recebe no `payload` duas chaves injetadas pelo sistema:

| Chave | Tipo | Uso |
|---|---|---|
| `__event_id__` | `int` | Chave de idempotência — use em `ON CONFLICT (outbox_event_id) DO NOTHING` |
| `__tenant_id__` | `int` | Fonte de verdade de tenant — use SEMPRE para filtrar queries, nunca `payload["tenant_id"]` |

```python
# handler idempotente e com isolamento correto de tenant
async def on_order_confirmed(payload: dict) -> None:
    event_id  = payload["__event_id__"]   # chave de idempotência
    tenant_id = payload["__tenant_id__"]  # isolamento — fonte de verdade
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

> **Tabelas afetadas por `emit_reliable`** devem ter `outbox_event_id BIGINT UNIQUE` para garantir idempotência — o OutboxProcessor entrega *at-least-once*.
