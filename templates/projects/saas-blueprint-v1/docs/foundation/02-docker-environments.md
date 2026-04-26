<!-- blueprint: db_changes=false seed_data=false -->
# 02. Ambientes, Docker e Configuração

Este documento define a estrutura de containerização e variáveis de ambiente para desenvolvimento e produção.

## 🐳 1. Containerização (Docker Compose)

### ⚠️ Regra Fundamental: Docker é para Infraestrutura, NÃO para Aplicações

O Docker Compose gerencia **exclusivamente os serviços de infraestrutura**. Os serviços de aplicação rodam diretamente no host (máquina do desenvolvedor ou servidor), fora do Docker.

| Serviço | Onde roda |
|---|---|
| PostgreSQL (DB) | ✅ Docker |
| Redis (Cache) | ✅ Docker |
| RabbitMQ (Queue) | ✅ Docker |
| Qdrant (Vector DB) | ✅ Docker |
| **Backend Service** | ❌ Host (uvicorn nativo) |
| **Auth Service** | ❌ Host (uvicorn nativo) |
| **Frontend** | ❌ Host (npm run dev nativo) |

**Nunca crie containers Docker para o Backend, Auth Service ou Frontend.** Esses serviços devem ser iniciados diretamente via `make dev` ou seus respectivos comandos nativos.

O `docker-compose.db.yml` é a única fonte de verdade para subir a infraestrutura.

### Convenção de nomes de containers

```
Docker project name:  gus-{alias}        (PROD)   gus-{alias}-dev   (DEV)
Container name:       {alias}-{serviço}  (PROD)   {alias}-{serviço}-dev (DEV)
```

Exemplo com alias `blueprint`:

| Serviço | Container PROD | Container DEV |
|---|---|---|
| PostgreSQL | `blueprint-postgres` | `blueprint-postgres-dev` |
| Réplica | `blueprint-postgres-replica` | `blueprint-postgres-replica-dev` |
| Redis | `blueprint-redis` | `blueprint-redis-dev` |
| RabbitMQ | `blueprint-rabbitmq` | `blueprint-rabbitmq-dev` |
| Qdrant | `blueprint-qdrant` | `blueprint-qdrant-dev` |

> O prefixo `gus-` fica **apenas no project name** (agrupador no Docker Desktop). Os containers individuais usam `{alias}-{serviço}` sem o prefixo `gus-`.

### `docker-compose.db.yml` (Infraestrutura PROD)

```yaml
# docker-compose.db.yml — APENAS infraestrutura (DB, Cache, Vector DB, Queue)
# NÃO adicione serviços de aplicação aqui.

name: gus-blueprint   # gus-{alias} — agrupador no Docker Desktop

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

### `docker-compose.db.dev.yml` (Infraestrutura DEV)

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

## 🔐 2. Variáveis de Ambiente (.env)

São **obrigatórios três arquivos** na raiz do projeto. Crie todos antes de iniciar qualquer serviço.

### Mecanismo de seleção de ambiente

O PS Profile injeta `APP_ENV` antes de iniciar cada serviço:

```powershell
# PROD
$env:APP_ENV = "prod"; python -m uvicorn app.main:app --reload --port <BACKEND_PORT>

# DEV
$env:APP_ENV = "dev";  python -m uvicorn app.main:app --reload --port <BACKEND_PORT_DEV>
```

O `Settings` de cada serviço lê `APP_ENV` e carrega o arquivo correto:

```python
import os
_env = os.getenv("APP_ENV", "prod")   # "prod" ou "dev"

model_config = SettingsConfigDict(
    env_file=[f"../../.env.{_env}", f".env.{_env}"],  # raiz primeiro, serviço faz override
    env_file_encoding="utf-8",
    extra="ignore"
)
```

> **Nunca crie um `.env` genérico.** Os únicos arquivos válidos são `.env.dev`, `.env.prod` e `.env.example`.

---

### `.env.dev` — Desenvolvimento (criar obrigatoriamente)

```env
# .env.dev — Ambiente de Desenvolvimento
# ⚠️ NÃO commitar — já está no .gitignore

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
JWT_SECRET_KEY=dev-secret-inseguro-nao-usar-em-prod
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Portas dos serviços (DEV)
BACKEND_PORT={{ BACKEND_PORT_DEV }}
AUTH_PORT={{ AUTH_PORT_DEV }}
FRONTEND_PORT={{ FRONTEND_PORT_DEV }}

# URLs dos serviços (DEV)
AUTH_SERVICE_URL=http://localhost:{{ AUTH_PORT_DEV }}
FRONTEND_URL=http://localhost:{{ FRONTEND_PORT_DEV }}
BACKEND_CORS_ORIGINS=["http://localhost:{{ FRONTEND_PORT_DEV }}"]
```

---

### `.env.prod` — Produção (criar obrigatoriamente)

```env
# .env.prod — Ambiente de Produção
# ⚠️ NUNCA commitar — já está no .gitignore

ENVIRONMENT=prod
LOG_LEVEL=INFO
SQL_ECHO=false

# Database (PROD)
POSTGRES_HOST=localhost
POSTGRES_PORT={{ DB_PORT_PROD }}
POSTGRES_USER={{ DB_USER }}
POSTGRES_PASSWORD={{ DB_PASSWORD_PROD }}
POSTGRES_DATABASE={{ DB_NAME_PROD }}

# Security — TROQUE antes de ir a produção real
JWT_SECRET_KEY=TROQUE-PARA-VALOR-SEGURO-python-c-import-secrets-print-secrets.token_hex-32
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Portas dos serviços (PROD)
BACKEND_PORT={{ BACKEND_PORT }}
AUTH_PORT={{ AUTH_PORT }}
FRONTEND_PORT={{ FRONTEND_PORT }}

# URLs dos serviços (PROD)
AUTH_SERVICE_URL=http://localhost:{{ AUTH_PORT }}
FRONTEND_URL=http://localhost:{{ FRONTEND_PORT }}
BACKEND_CORS_ORIGINS=["http://localhost:{{ FRONTEND_PORT }}"]
```

---

### `.env.example` — Template público (commitar no Git)

```env
# .env.example — Template de referência
# Crie .env.dev e .env.prod a partir deste modelo. Não preencha valores reais aqui.

ENVIRONMENT=dev                      # dev | prod
LOG_LEVEL=DEBUG                      # DEBUG | INFO
SQL_ECHO=true                        # true | false

POSTGRES_HOST=localhost
POSTGRES_PORT=                       # DB_PORT_DEV ou DB_PORT_PROD (ver 00-variables.md)
POSTGRES_USER={{ DB_USER }}
POSTGRES_PASSWORD=                   # DB_PASSWORD_DEV ou DB_PASSWORD_PROD
POSTGRES_DATABASE=                   # DB_NAME_DEV ou DB_NAME_PROD

JWT_SECRET_KEY=                      # gere: python -c "import secrets; print(secrets.token_hex(32))"
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

BACKEND_PORT=                        # BACKEND_PORT_DEV ou BACKEND_PORT
AUTH_PORT=                           # AUTH_PORT_DEV ou AUTH_PORT
FRONTEND_PORT=                       # FRONTEND_PORT_DEV ou FRONTEND_PORT

AUTH_SERVICE_URL=http://localhost:<AUTH_PORT>
FRONTEND_URL=http://localhost:<FRONTEND_PORT>
BACKEND_CORS_ORIGINS=["http://localhost:<FRONTEND_PORT>"]
```

---

### Regras de Ambiente

1. **`.env.dev`**: Desenvolvimento local. Senhas fracas permitidas, `SQL_ECHO=true`, `LOG_LEVEL=DEBUG`.
2. **`.env.prod`**: Produção. **NUNCA** commitar no Git. `SQL_ECHO=false`, `LOG_LEVEL=INFO`, senha forte no `JWT_SECRET_KEY`.
3. **`.env.example`**: Único arquivo de `.env` que vai para o Git — sem valores sensíveis.
4. **Serviços fora do Docker**: `POSTGRES_HOST=localhost` — Backend e Auth Service rodam no host, não em containers.
5. **Migration runner**: recebe `DATABASE_URL` injetado diretamente pelo PS Profile via `$env:DATABASE_URL=...` — não lê os arquivos `.env.*`.

---

## 📂 3. Hierarquia de .env

```
.env.prod / .env.dev          → raiz do projeto (variáveis globais compartilhadas)
services/<svc>/.env.prod      → serviço específico (override da raiz, se necessário)
services/<svc>/.env.dev       → serviço específico DEV (override da raiz, se necessário)
```

> Na maioria dos projetos, os arquivos na raiz são suficientes. Crie `.env.*` por serviço apenas se um serviço precisar sobrescrever alguma variável global.

### Regra: uma chave existe em APENAS UM nível

| | Variável | Nível | Motivo |
|---|---|---|---|
| ✅ | `JWT_SECRET_KEY` | raiz | todos os serviços precisam validar o mesmo token |
| ✅ | `ENVIRONMENT`, `LOG_LEVEL`, `SQL_ECHO` | raiz | contexto global |
| ✅ | `POSTGRES_*`, `BACKEND_PORT`, `AUTH_PORT` | raiz | compartilhado entre backend e auth |
| ❌ | qualquer chave em raiz **e** no serviço | — | duplicidade — defina apenas em um nível |

> **Nunca declare a mesma chave nos dois níveis.** Se uma variável migrar de serviço para global, remova-a dos `.env.*` individuais.
