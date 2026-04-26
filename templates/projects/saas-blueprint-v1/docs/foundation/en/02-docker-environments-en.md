<!-- blueprint: db_changes=false seed_data=false -->
# 02. Environments, Docker and Configuration

This document defines the containerization structure and environment variables for development and production.

## 🐳 1. Containerization (Docker Compose)

### ⚠️ Fundamental Rule: Docker is for Infrastructure, NOT for Applications

Docker Compose manages **exclusively infrastructure services**. Application services run directly on the host (developer machine or server), outside Docker.

| Service | Where it runs |
|---|---|
| PostgreSQL (DB) | ✅ Docker |
| Redis (Cache) | ✅ Docker |
| RabbitMQ (Queue) | ✅ Docker |
| Qdrant (Vector DB) | ✅ Docker |
| **Backend Service** | ❌ Host (native uvicorn) |
| **Auth Service** | ❌ Host (native uvicorn) |
| **Frontend** | ❌ Host (native npm run dev) |

**Never create Docker containers for the Backend, Auth Service or Frontend.** These services must be started directly via `make dev` or their respective native commands.

The `docker-compose.db.yml` is the single source of truth for bringing up infrastructure.

### Container naming convention

```
Docker project name:  gus-{alias}        (PROD)   gus-{alias}-dev   (DEV)
Container name:       {alias}-{service}  (PROD)   {alias}-{service}-dev (DEV)
```

Example with alias `blueprint`:

| Service | PROD Container | DEV Container |
|---|---|---|
| PostgreSQL | `blueprint-postgres` | `blueprint-postgres-dev` |
| Replica | `blueprint-postgres-replica` | `blueprint-postgres-replica-dev` |
| Redis | `blueprint-redis` | `blueprint-redis-dev` |
| RabbitMQ | `blueprint-rabbitmq` | `blueprint-rabbitmq-dev` |
| Qdrant | `blueprint-qdrant` | `blueprint-qdrant-dev` |

> The `gus-` prefix exists **only in the project name** (Docker Desktop grouper). Individual containers use `{alias}-{service}` without the `gus-` prefix.

### `docker-compose.db.yml` (PROD Infrastructure)

```yaml
# docker-compose.db.yml — ONLY infrastructure (DB, Cache, Vector DB, Queue)
# DO NOT add application services here.

name: gus-blueprint   # gus-{alias} — Docker Desktop grouper

services:
  postgres:
    image: postgres:18
    container_name: blueprint-postgres   # {alias}-postgres
    environment:
      POSTGRES_USER: blueprint
      POSTGRES_PASSWORD: blueprint
      POSTGRES_DB: blueprint
    ports:
      - "5444:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  # Feature: replica
  postgres-replica:
    container_name: blueprint-postgres-replica
    # ...

  # Feature: redis
  redis:
    image: redis:alpine
    container_name: blueprint-redis
    ports:
      - "6385:6379"

  # Feature: rabbitmq
  rabbitmq:
    image: rabbitmq:3-management
    container_name: blueprint-rabbitmq
    ports:
      - "5675:5672"
      - "15675:15672"

  # Feature: qdrant
  qdrant:
    image: qdrant/qdrant
    container_name: blueprint-qdrant
    ports:
      - "6343:6333"
      - "6344:6334"

volumes:
  postgres_data:
```

### `docker-compose.db.dev.yml` (DEV Infrastructure)

```yaml
name: gus-blueprint-dev   # gus-{alias}-dev

services:
  postgres:
    container_name: blueprint-postgres-dev   # {alias}-postgres-dev
    ports:
      - "5446:5432"

  postgres-replica:
    container_name: blueprint-postgres-replica-dev   # {alias}-postgres-replica-dev
    ports:
      - "5447:5432"

  redis:
    container_name: blueprint-redis-dev
    ports:
      - "6383:6379"

  rabbitmq:
    container_name: blueprint-rabbitmq-dev
    ports:
      - "5674:5672"
      - "15674:15672"

  qdrant:
    container_name: blueprint-qdrant-dev
    ports:
      - "6341:6333"
      - "6342:6334"
```

## 🔐 2. Environment Variables (.env)

**Three files are mandatory** at the project root. Create all of them before starting any service.

### Environment selection mechanism

The PS Profile injects `APP_ENV` before starting each service:

```powershell
# PROD
$env:APP_ENV = "prod"; python -m uvicorn app.main:app --reload --port <BACKEND_PORT>

# DEV
$env:APP_ENV = "dev";  python -m uvicorn app.main:app --reload --port <BACKEND_PORT_DEV>
```

Each service's `Settings` reads `APP_ENV` and loads the correct file:

```python
import os
_env = os.getenv("APP_ENV", "prod")   # "prod" or "dev"

model_config = SettingsConfigDict(
    env_file=[f"../../.env.{_env}", f".env.{_env}"],  # root first, service overrides
    env_file_encoding="utf-8",
    extra="ignore"
)
```

> **Never create a generic `.env`.** The only valid files are `.env.dev`, `.env.prod` and `.env.example`.

---

### `.env.dev` — Development (mandatory)

```env
# .env.dev — Development Environment
# ⚠️ DO NOT commit — already in .gitignore

ENVIRONMENT=dev
LOG_LEVEL=DEBUG
SQL_ECHO=true

# Database (DEV)
POSTGRES_HOST=localhost
POSTGRES_PORT={{ DB_PORT_DEV }}
POSTGRES_USER={{ DB_USER }}
POSTGRES_PASSWORD={{ DB_PASSWORD_DEV }}
POSTGRES_DATABASE={{ DB_NAME_DEV }}

# Security
JWT_SECRET_KEY=dev-secret-insecure-do-not-use-in-prod
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Service ports (DEV)
BACKEND_PORT={{ BACKEND_PORT_DEV }}
AUTH_PORT={{ AUTH_PORT_DEV }}
FRONTEND_PORT={{ FRONTEND_PORT_DEV }}

# Service URLs (DEV)
AUTH_SERVICE_URL=http://localhost:{{ AUTH_PORT_DEV }}
FRONTEND_URL=http://localhost:{{ FRONTEND_PORT_DEV }}
BACKEND_CORS_ORIGINS=["http://localhost:{{ FRONTEND_PORT_DEV }}"]
```

---

### `.env.prod` — Production (mandatory)

```env
# .env.prod — Production Environment
# ⚠️ NEVER commit — already in .gitignore

ENVIRONMENT=prod
LOG_LEVEL=INFO
SQL_ECHO=false

# Database (PROD)
POSTGRES_HOST=localhost
POSTGRES_PORT={{ DB_PORT_PROD }}
POSTGRES_USER={{ DB_USER }}
POSTGRES_PASSWORD={{ DB_PASSWORD_PROD }}
POSTGRES_DATABASE={{ DB_NAME_PROD }}

# Security — REPLACE before going to real production
JWT_SECRET_KEY=REPLACE-WITH-SECURE-VALUE-python-c-import-secrets-print-secrets.token_hex-32
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Service ports (PROD)
BACKEND_PORT={{ BACKEND_PORT }}
AUTH_PORT={{ AUTH_PORT }}
FRONTEND_PORT={{ FRONTEND_PORT }}

# Service URLs (PROD)
AUTH_SERVICE_URL=http://localhost:{{ AUTH_PORT }}
FRONTEND_URL=http://localhost:{{ FRONTEND_PORT }}
BACKEND_CORS_ORIGINS=["http://localhost:{{ FRONTEND_PORT }}"]
```

---

### `.env.example` — Public template (commit to Git)

```env
# .env.example — Reference template
# Create .env.dev and .env.prod from this model. Do not fill real values here.

ENVIRONMENT=dev                      # dev | prod
LOG_LEVEL=DEBUG                      # DEBUG | INFO
SQL_ECHO=true                        # true | false

POSTGRES_HOST=localhost
POSTGRES_PORT=                       # DB_PORT_DEV or DB_PORT_PROD (see 00-variables.md)
POSTGRES_USER={{ DB_USER }}
POSTGRES_PASSWORD=                   # DB_PASSWORD_DEV or DB_PASSWORD_PROD
POSTGRES_DATABASE=                   # DB_NAME_DEV or DB_NAME_PROD

JWT_SECRET_KEY=                      # generate: python -c "import secrets; print(secrets.token_hex(32))"
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

BACKEND_PORT=                        # BACKEND_PORT_DEV or BACKEND_PORT
AUTH_PORT=                           # AUTH_PORT_DEV or AUTH_PORT
FRONTEND_PORT=                       # FRONTEND_PORT_DEV or FRONTEND_PORT

AUTH_SERVICE_URL=http://localhost:<AUTH_PORT>
FRONTEND_URL=http://localhost:<FRONTEND_PORT>
BACKEND_CORS_ORIGINS=["http://localhost:<FRONTEND_PORT>"]
```

---

### Environment Rules

1. **`.env.dev`**: Local development. Weak passwords allowed, `SQL_ECHO=true`, `LOG_LEVEL=DEBUG`.
2. **`.env.prod`**: Production. **NEVER** commit to Git. `SQL_ECHO=false`, `LOG_LEVEL=INFO`, strong `JWT_SECRET_KEY`.
3. **`.env.example`**: The only `.env` file that goes to Git — no sensitive values.
4. **Services outside Docker**: `POSTGRES_HOST=localhost` — Backend and Auth Service run on the host, not in containers.
5. **Migration runner**: receives `DATABASE_URL` injected directly by the PS Profile via `$env:DATABASE_URL=...` — does not read `.env.*` files.

---

## 📂 3. .env Hierarchy

```
.env.prod / .env.dev          → project root (shared global variables)
services/<svc>/.env.prod      → specific service (root override, if needed)
services/<svc>/.env.dev       → specific service DEV (root override, if needed)
```

> In most projects, root files are sufficient. Create `.env.*` per service only if a service needs to override a global variable.

### Rule: one key exists in ONLY ONE level

| | Variable | Level | Reason |
|---|---|---|---|
| ✅ | `JWT_SECRET_KEY` | root | all services need to validate the same token |
| ✅ | `ENVIRONMENT`, `LOG_LEVEL`, `SQL_ECHO` | root | global context |
| ✅ | `POSTGRES_*`, `BACKEND_PORT`, `AUTH_PORT` | root | shared between backend and auth |
| ❌ | any key at root **and** in the service | — | duplication — define in only one level |

> **Never declare the same key at both levels.** If a variable moves from service to global, remove it from the individual `.env.*` files.
