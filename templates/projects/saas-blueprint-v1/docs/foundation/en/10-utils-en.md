<!-- blueprint: db_changes=false seed_data=false -->
# 10. Utility Scripts (Utils)

This document defines the utility scripts that should reside at the project root.

## 🏁 Workflow

| Step | Direct command |
|---|---|
| Install Python dependencies | `python scripts/setup_venvs.py` |
| Install Frontend dependencies | `cd services/frontend && npm install` |
| Start Docker infra (PROD) | `docker compose -f docker-compose.db.yml up -d` |
| Start Docker infra (DEV) | `docker compose -f docker-compose.db.dev.yml up -d` |
| Start Auth Service | `cd services/auth-service && python -m uvicorn app.main:app --reload --port {{ AUTH_PORT }}` |
| Start Backend | `cd services/backend && python -m uvicorn app.main:app --reload --port {{ BACKEND_PORT }}` |
| Start Frontend | `cd services/frontend && npm run dev` |
| Apply migrations | `python services/backend/scripts/migration_runner.py --apply-all` |
| Migration status | `python services/backend/scripts/migration_runner.py --status` |
| Stop Docker | `docker compose -f docker-compose.db.yml down` |

> **Note:** The commands above should appear in the generated project's `README.md` as a quick reference.

## 🐍 1. Python Environment Setup (`scripts/setup_venvs.py`)

Create this script at `scripts/setup_venvs.py` in the project root. It centralizes venv creation and dependency installation for all Python services, cross-platform (Windows and Linux/macOS).

```python
#!/usr/bin/env python3
"""
scripts/setup_venvs.py
======================
Creates venvs and installs dependencies for all Python services.

Usage:
    python scripts/setup_venvs.py                  # all services
    python scripts/setup_venvs.py --service backend
    python scripts/setup_venvs.py --service auth-service
"""
import argparse
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).parent.parent  # project root

PYTHON_SERVICES = [
    {"name": "backend",      "path": ROOT / "services" / "backend"},
    {"name": "auth-service", "path": ROOT / "services" / "auth-service"},
]

def python_bin(venv_dir: Path) -> Path:
    """Returns the venv Python executable (cross-platform)."""
    return venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / (
        "python.exe" if sys.platform == "win32" else "python"
    )

def setup_service(service: dict) -> bool:
    name        = service["name"]
    service_dir = service["path"]
    venv_dir    = service_dir / ".venv"
    requirements = service_dir / "requirements.txt"

    print(f"\n📦 {name}")

    if not service_dir.exists():
        print(f"   ⚠️  Folder not found: {service_dir} — skipping.")
        return False

    if not requirements.exists():
        print(f"   ⚠️  requirements.txt not found in {service_dir} — skipping.")
        return False

    if not venv_dir.exists():
        print("   Creating venv...")
        venv.create(venv_dir, with_pip=True, clear=False)
    else:
        print("   venv already exists — skipping creation.")

    py = python_bin(venv_dir)

    print("   Upgrading pip...")
    subprocess.run([str(py), "-m", "pip", "install", "--upgrade", "pip", "--quiet"], check=True)

    print("   Installing requirements.txt...")
    subprocess.run([str(py), "-m", "pip", "install", "-r", str(requirements)], check=True)

    print(f"   ✅ {name} ready.")
    return True

def main():
    parser = argparse.ArgumentParser(description="Setup Python service venvs.")
    parser.add_argument("--service", choices=[s["name"] for s in PYTHON_SERVICES],
                        help="Install only the specified service (default: all)")
    args = parser.parse_args()

    services = [s for s in PYTHON_SERVICES if not args.service or s["name"] == args.service]

    print(f"🚀 Python environment setup — root: {ROOT}")
    for service in services:
        setup_service(service)

    print("\n✅ Setup complete.")

if __name__ == "__main__":
    main()
```

## 🛠️ 2. Default `.env` Generator

```bash
#!/bin/bash
# scripts/setup_env.sh

echo "🔧 Configuring local environment..."

if [ -f ".env" ]; then
    echo "⚠️ .env file already exists. Overwrite it? (y/n)"
    read answer
    if [ "$answer" != "y" ]; then
        echo "❌ Operation cancelled."
        exit 1
    fi
fi

if [ -f ".env.dev" ]; then
    cp .env.dev .env
    echo "✅ .env created from .env.dev"
elif [ -f ".env.example" ]; then
    cp .env.example .env
    echo "✅ .env created from .env.example"
else
    echo "❌ No .env.dev or .env.example found!"
    exit 1
fi

echo "🎉 Environment configured successfully!"
```

## 🧹 3. Environment Cleanup (Clean)

```bash
#!/bin/bash
# scripts/clean.sh

echo "🧹 Cleaning environment..."

find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type d -name ".pytest_cache" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete

rm -rf services/frontend/dist
rm -rf services/frontend/node_modules/.vite

echo "Remove orphaned Docker volumes? (y/n)"
read answer
if [ "$answer" == "y" ]; then
    docker volume prune -f
    echo "✅ Orphaned volumes removed."
fi

echo "✨ Cleanup complete!"
```

## 📄 4. `.gitignore` Template (Mandatory)

```gitignore
# Blueprint project variables (contains credentials)
docs/00-variables.md

# Python / FastAPI
__pycache__/
*.py[cod]
*.pyo
*.pyd
*.egg
*.egg-info/
dist/
build/
.venv/
venv/
env/
.env
.env.*
!.env.example
*.log
.mypy_cache/
.pytest_cache/
.coverage
htmlcov/

# Node / React / Vite
node_modules/
dist/
dist-ssr/
*.local
.cache/
.eslintcache

# Docker
docker-compose.override.yml

# Database / volumes
postgres_data/
redis_data/
qdrant_data/
*.sql.bak
*.dump

# IDEs and editors
.vscode/
.idea/
*.DS_Store
Thumbs.db

# Secrets / Certificates
*.pem
*.key
*.crt
secrets/

# Generated logs
logs/
*.log
```

## 📋 5. Commands README (Mandatory)

The agent must create a `README.md` at the generated project root with a **"Development Commands"** section containing the direct manual commands to operate the project.

**Initial setup**
```bash
python scripts/setup_venvs.py
cd services/frontend && npm install
```

**Infrastructure (Docker)**
```bash
# PROD
docker compose -f docker-compose.db.yml up -d
docker compose -f docker-compose.db.yml down

# DEV
docker compose -f docker-compose.db.dev.yml up -d
docker compose -f docker-compose.db.dev.yml down
```

**Services (each in a separate terminal)**
```bash
# Auth Service  — port {{ AUTH_PORT }}
cd services/auth-service
python -m uvicorn app.main:app --reload --port {{ AUTH_PORT }}

# Backend       — port {{ BACKEND_PORT }}
cd services/backend
python -m uvicorn app.main:app --reload --port {{ BACKEND_PORT }}

# Frontend
cd services/frontend
npm run dev
```

**Database**
```bash
# Apply migrations
python services/backend/scripts/migration_runner.py --apply-all

# Status
python services/backend/scripts/migration_runner.py --status

# Rollback everything
python services/backend/scripts/migration_runner.py --rollback-to 0000 --confirm
```

> Replace `{{ AUTH_PORT }}` and `{{ BACKEND_PORT }}` with values defined in `docs/00-variables.md`.
