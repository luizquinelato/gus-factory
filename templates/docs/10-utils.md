<!-- blueprint: db_changes=false seed_data=false -->
# 10. Scripts Utilitários (Utils)
`
Este documento define os scripts utilitários que devem residir na raiz do projeto.
`
## 🏁 Fluxo de trabalho
`
| Etapa | Comando direto |
|---|---|
| Instalar dependências Python | `python scripts/setup_venvs.py` |
| Instalar dependências Frontend | `cd services/frontend && npm install` |
| Subir infra Docker (PROD) | `docker compose -f docker-compose.db.yml up -d` |
| Subir infra Docker (DEV) | `docker compose -f docker-compose.db.dev.yml up -d` |
| Iniciar Auth Service | `cd services/auth-service && python -m uvicorn app.main:app --reload --port {{ AUTH_PORT }}` |
| Iniciar Backend | `cd services/backend && python -m uvicorn app.main:app --reload --port {{ BACKEND_PORT }}` |
| Iniciar Frontend | `cd services/frontend && npm run dev` |
| Aplicar migrations | `python services/backend/scripts/migration_runner.py --apply-all` |
| Status migrations | `python services/backend/scripts/migration_runner.py --status` |
| Parar Docker | `docker compose -f docker-compose.db.yml down` |
`
> **Nota:** Os comandos acima devem aparecer no `README.md` do projeto gerado como referência rápida. Consulte `helms/ports.yml` na raiz do blueprint para as portas de cada projeto.
`
## 🐍 1. Setup de Ambientes Python (`scripts/setup_venvs.py`)
`
Crie este script em `scripts/setup_venvs.py` na raiz do projeto. Ele centraliza a criação de venvs e instalação de dependências para todos os serviços Python, de forma cross-platform (Windows e Linux/macOS). Cada serviço mantém seu próprio `requirements.txt` — o script apenas aponta para eles.
`
```python
#!/usr/bin/env python3
"""
scripts/setup_venvs.py
======================
Cria os venvs e instala as dependências de todos os serviços Python do projeto.
`
Uso:
    python scripts/setup_venvs.py                  # todos os serviços
    python scripts/setup_venvs.py --service backend
    python scripts/setup_venvs.py --service auth-service
"""
import argparse
import subprocess
import sys
import venv
from pathlib import Path
`
ROOT = Path(__file__).parent.parent  # raiz do projeto
`
# Definição dos serviços Python. Adicione novos serviços aqui.
PYTHON_SERVICES = [
    {"name": "backend",      "path": ROOT / "services" / "backend"},
    {"name": "auth-service", "path": ROOT / "services" / "auth-service"},
]
`
`
def python_bin(venv_dir: Path) -> Path:
    """Retorna o executável Python do venv (cross-platform)."""
    return venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / (
        "python.exe" if sys.platform == "win32" else "python"
    )
`
`
def setup_service(service: dict) -> bool:
    name        = service["name"]
    service_dir = service["path"]
    venv_dir    = service_dir / ".venv"
    requirements = service_dir / "requirements.txt"
`
    print(f"\n📦 {name}")
`
    if not service_dir.exists():
        print(f"   ⚠️  Pasta não encontrada: {service_dir} — pulando.")
        return False
`
    if not requirements.exists():
        print(f"   ⚠️  requirements.txt não encontrado em {service_dir} — pulando.")
        return False
`
    if not venv_dir.exists():
        print("   Criando venv...")
        venv.create(venv_dir, with_pip=True, clear=False)
    else:
        print("   venv já existe — pulando criação.")
`
    py = python_bin(venv_dir)
`
    print("   Atualizando pip...")
    subprocess.run([str(py), "-m", "pip", "install", "--upgrade", "pip", "--quiet"], check=True)
`
    print("   Instalando requirements.txt...")
    subprocess.run([str(py), "-m", "pip", "install", "-r", str(requirements)], check=True)
`
    print(f"   ✅ {name} pronto.")
    return True
`
`
def main():
    parser = argparse.ArgumentParser(description="Setup venvs dos serviços Python.")
    parser.add_argument(
        "--service",
        choices=[s["name"] for s in PYTHON_SERVICES],
        help="Instala apenas o serviço especificado (default: todos)",
    )
    args = parser.parse_args()
`
    services = [s for s in PYTHON_SERVICES if not args.service or s["name"] == args.service]
`
    print(f"🚀 Setup de ambientes Python — raiz: {ROOT}")
    for service in services:
        setup_service(service)
`
    print("\n✅ Configuração concluída.")
    print("\n📌 Próximos passos:")
    print("   make infra    → sobe Docker (DB, Cache, Vector DB)")
    print("   make migrate  → aplica migrations")
    print("   make dev      → inicia todos os serviços")
`
`
if __name__ == "__main__":
    main()
```
`
> **Nota**: Para adicionar um novo serviço Python, basta incluir uma entrada em `PYTHON_SERVICES`. O `requirements.txt` de cada serviço permanece dentro da pasta do serviço — o script apenas referencia os caminhos.
`
## 🛠️ 2. Gerador de `.env` Padrão
`
O script `setup_env.sh` (ou `.ps1` no Windows) é responsável por criar o arquivo `.env` local copiando os valores do `.env.dev` ou `.env.example`, garantindo que novos desenvolvedores tenham um ambiente funcional imediatamente.
`
```bash
#!/bin/bash
# scripts/setup_env.sh
`
echo "🔧 Configurando ambiente local..."
`
# Verifica se o .env já existe
if [ -f ".env" ]; then
    echo "⚠️ O arquivo .env já existe. Deseja sobrescrevê-lo? (y/n)"
    read answer
    if [ "$answer" != "y" ]; then
        echo "❌ Operação cancelada."
        exit 1
    fi
fi
`
# Copia o .env.dev (prioridade) ou .env.example
if [ -f ".env.dev" ]; then
    cp .env.dev .env
    echo "✅ Arquivo .env criado a partir de .env.dev"
elif [ -f ".env.example" ]; then
    cp .env.example .env
    echo "✅ Arquivo .env criado a partir de .env.example"
else
    echo "❌ Nenhum arquivo .env.dev ou .env.example encontrado!"
    exit 1
fi
`
echo "🎉 Ambiente configurado com sucesso!"
```
`
## 🧹 3. Limpeza de Ambiente (Clean)
`
O script `clean.sh` remove containers parados, volumes órfãos, caches do Python e builds do frontend.
`
```bash
#!/bin/bash
# scripts/clean.sh
`
echo "🧹 Limpando ambiente..."
`
# Remove caches do Python
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type d -name ".pytest_cache" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
`
# Remove builds do frontend
rm -rf services/frontend/dist
rm -rf services/frontend/node_modules/.vite
`
# Limpa Docker (opcional, pede confirmação)
echo "Deseja remover volumes órfãos do Docker? (y/n)"
read answer
if [ "$answer" == "y" ]; then
    docker volume prune -f
    echo "✅ Volumes órfãos removidos."
fi
`
echo "✨ Limpeza concluída!"
```
`
## 📄 4. Template `.gitignore` (Obrigatório)
`
Crie este `.gitignore` na raiz do projeto gerado. Sem ele, credenciais e caches vão parar no repositório.
`
```gitignore
# ===========================
# Blueprint - variáveis do projeto (contém credenciais)
# ===========================
docs/00-variables.md
`
# ===========================
# Python / FastAPI
# ===========================
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
`
# ===========================
# Node / React / Vite
# ===========================
node_modules/
dist/
dist-ssr/
*.local
.cache/
.eslintcache
`
# ===========================
# Docker
# ===========================
docker-compose.override.yml
`
# ===========================
# Banco de dados / volumes
# ===========================
postgres_data/
redis_data/
qdrant_data/
*.sql.bak
*.dump
`
# ===========================
# IDEs e editores
# ===========================
.vscode/
.idea/
*.DS_Store
Thumbs.db
`
# ===========================
# Secrets / Certificados
# ===========================
*.pem
*.key
*.crt
secrets/
`
# ===========================
# Logs gerados
# ===========================
logs/
*.log
```

## 📋 5. README de Comandos (Obrigatório)

### ⚙️ Instrução para o Agente

O agente deve criar um `README.md` na raiz do projeto gerado com uma seção **"Comandos de Desenvolvimento"** contendo os comandos manuais diretos para operar o projeto — sem depender de ferramenta externa como PowerShell Profile ou Makefile.

O `README.md` deve cobrir os seguintes grupos de comandos:

| Grupo | Comandos |
|---|---|
| **Setup** | `python scripts/setup_venvs.py` · `cd services/frontend && npm install` |
| **Docker PROD** | `docker compose -f docker-compose.db.yml up -d` / `down` |
| **Docker DEV** | `docker compose -f docker-compose.db.dev.yml up -d` / `down` |
| **Auth** | `cd services/auth-service && python -m uvicorn app.main:app --reload --port {{ AUTH_PORT }}` |
| **Backend** | `cd services/backend && python -m uvicorn app.main:app --reload --port {{ BACKEND_PORT }}` |
| **Frontend** | `cd services/frontend && npm run dev` |
| **Migrations** | `python services/backend/scripts/migration_runner.py --apply-all` |
| **DB Status** | `python services/backend/scripts/migration_runner.py --status` |

O README deve ser commitado no repositório. As portas de cada projeto estão definidas em `helms/ports.yml` no repositório do blueprint (`gus-factory`).

### Estrutura mínima do README

O agente deve gerar o `README.md` com ao menos as seguintes seções:

**Setup inicial**
```bash
python scripts/setup_venvs.py
cd services/frontend && npm install
```

**Infraestrutura (Docker)**
```bash
# PROD
docker compose -f docker-compose.db.yml up -d
docker compose -f docker-compose.db.yml down

# DEV
docker compose -f docker-compose.db.dev.yml up -d
docker compose -f docker-compose.db.dev.yml down
```

**Serviços (cada um em terminal separado)**
```bash
# Auth Service  — porta {{ AUTH_PORT }}
cd services/auth-service
python -m uvicorn app.main:app --reload --port {{ AUTH_PORT }}

# Backend       — porta {{ BACKEND_PORT }}
cd services/backend
python -m uvicorn app.main:app --reload --port {{ BACKEND_PORT }}

# Frontend
cd services/frontend
npm run dev
```

**Banco de Dados**
```bash
# Aplicar migrations
python services/backend/scripts/migration_runner.py --apply-all

# Status
python services/backend/scripts/migration_runner.py --status

# Reverter tudo
python services/backend/scripts/migration_runner.py --rollback-to 0000 --confirm
```

> Substitua `{{ AUTH_PORT }}` e `{{ BACKEND_PORT }}` pelos valores definidos em `docs/00-variables.md`.
