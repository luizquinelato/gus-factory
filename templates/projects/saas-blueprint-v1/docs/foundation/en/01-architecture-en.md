<!-- blueprint: db_changes=false seed_data=false -->
# 01. Architecture and Directory Structure

This document defines the base SaaS architecture and the mandatory directory structure.

## 🏗️ Service Architecture

The platform is divided into microservices to ensure scalability and separation of concerns:

1. **Frontend Application**: SPA in React (Vite + TypeScript + Tailwind).
2. **Backend Service**: Main API in FastAPI (Python 3.11). Responsible for business logic.
3. **Auth Service**: Isolated FastAPI service for identity management and JWT tokens.
4. **Data Layer**: PostgreSQL 18 (with pgvector if `{{ DB_ENABLE_ML }}` = true).
5. **Cache & Queue**: Redis and RabbitMQ (if `{{ ENABLE_ETL }}` = true).

## 📁 Directory Structure

The project root must strictly follow this structure:

```text
/
├── docs/                   # Technical and architectural documentation
├── plans/                  # Roadmap, backlog and ADRs (Architecture Decision Records)
├── services/
│   ├── auth-service/       # Authentication Service (Port {{ AUTH_PORT }})
│   │   ├── app/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── backend/            # Main API (Port {{ BACKEND_PORT }})
│   │   ├── app/
│   │   │   ├── ai/         # (If {{ ENABLE_AI_LAYER }} = true)
│   │   │   ├── etl/        # (If {{ ENABLE_ETL }} = true)
│   │   │   ├── core/
│   │   │   ├── models/
│   │   │   ├── routers/
│   │   │   ├── schemas/
│   │   │   └── services/
│   │   ├── scripts/        # Migration runner and maintenance scripts
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── frontend/           # React SPA (Port {{ FRONTEND_PORT }})
│       ├── src/
│       │   ├── components/
│       │   ├── contexts/
│       │   ├── hooks/
│       │   ├── pages/
│       │   └── services/
│       ├── Dockerfile
│       └── package.json
├── docker-compose.dev.yml  # Development environment
├── docker-compose.prod.yml # Production environment
├── .env.example            # Environment variables template
└── README.md
```

## 📜 Organization Rules

1. **Dependency Isolation**: Each service inside `/services/` must have its own `requirements.txt` or `package.json` and its own `Dockerfile`.
2. **No Code at Root**: The project root must contain only global configuration files (Docker Compose, `.env`, `.gitignore`, `README.md`).
3. **Living Documentation**: Any architectural decision must be recorded in `/plans/`.
4. **Conditional Modules**: The `ai/` and `etl/` folders must only exist inside `/services/backend/app/` if their respective variables are active.
