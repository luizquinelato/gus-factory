#!/usr/bin/env python3
"""
scripts/create_project.py
==========================
Cria um novo projeto no blueprint em 4 etapas:
  1. Clona todos os docs de /docs/ → /projects/<key>/
  2. Cria /projects/<key>/00-variables.md pré-preenchido
  3. Registra portas em helms/ports.yml
  4. Gera seção no helms/powershell_profile.ps1

Após criar, gere o prompt inicial com:
  python scripts/generate_prompt.py -f projects/<key>

Para gerar prompt dos arquivos customizados:
  python scripts/generate_prompt.py -f projects/<key>/custom

Uso:
    python scripts/create_project.py

Convenção de portas (definida em helms/ports.yml → meta):
  backend_prod  = next_backend_block * 1000   (ex: 9000, 10000 …)
  auth_prod     = backend_prod + 100          (ex: 9100, 10100 …)
  frontend_prod = next_frontend_prod          (+2 por projeto)
  backend_dev   = backend_prod + 10
  auth_dev      = backend_prod + 110
  frontend_dev  = frontend_prod + 1
  db_prod       = next_db_prod               (+4 por projeto)
  db_dev        = db_prod + 2
"""
from __future__ import annotations
import os
import shutil
import sys
from pathlib import Path

# Permite importar generate_prompt.py da mesma pasta scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import yaml
except ImportError:
    print("Instale PyYAML: pip install pyyaml")
    sys.exit(1)


# ── YAML helpers — entradas de shared_services em formato inline ─────────────
class _InlineDict(dict):
    """Marker: serializado como {port: N, project: k} em uma única linha."""


class _PortsDumper(yaml.Dumper):
    """Dumper customizado — _InlineDict usa flow_style=True."""


_PortsDumper.add_representer(
    _InlineDict,
    lambda d, v: d.represent_mapping("tag:yaml.org,2002:map", v.items(), flow_style=True),
)


ROOT               = Path(__file__).parent.parent
PORTS_FILE         = ROOT / "helms" / "ports.yml"
TEMPLATES_DIR      = ROOT / "templates"
VARIABLES_TEMPLATE = TEMPLATES_DIR / "docs" / "00-variables-template.md"
DOCS_DIR           = TEMPLATES_DIR / "docs"
REFERENCE_DIR      = TEMPLATES_DIR / "reference"
PROJECTS_DIR       = ROOT / "projects"
MIGRATIONS_TMPL    = TEMPLATES_DIR / "scripts"
DOCKER_TMPL        = TEMPLATES_DIR / "docker"

# Paleta de cores PS — ordem de prioridade ao auto-atribuir (Cyan/Magenta/Yellow reservadas)
PS_COLORS = ["Green", "Blue", "Red", "DarkCyan", "DarkGreen", "Gray", "White"]

# Serviços Docker extras disponíveis para seleção interativa
EXTRA_SERVICES = {
    "cache": {
        "question":   "Usar Redis como cache layer?",
        "yml_var":    "CACHE_LAYER",
        "yml_docker": "DOCKER_CACHE",
        "yml_value":  "Redis",
        "port_specs": [
            {"name": "redis", "anchor_keys": ["redis"], "base": 6379, "block": 1, "offset": 0, "proto": "tcp"},
        ],
        "port_specs_dev": [
            {"name": "redis_dev", "anchor_keys": ["redis_dev"], "base": 6379, "block": 1, "offset": 0, "proto": "tcp"},
        ],
    },
    "queue": {
        "question":   "Usar RabbitMQ como message queue?",
        "yml_var":    "QUEUE_LAYER",
        "yml_docker": "DOCKER_QUEUE",
        "yml_value":  "RabbitMQ",
        "port_specs": [
            {"name": "rabbitmq_amqp", "anchor_keys": ["rabbitmq_amqp"], "base": 5672,  "block": 1, "offset": 0, "proto": "amqp"},
            {"name": "rabbitmq_mgmt", "anchor_keys": ["rabbitmq_mgmt"], "base": 15672, "block": 1, "offset": 0, "proto": "http"},
        ],
        "port_specs_dev": [
            {"name": "rabbitmq_amqp_dev", "anchor_keys": ["rabbitmq_amqp_dev"], "base": 5672,  "block": 1, "offset": 0, "proto": "amqp"},
            {"name": "rabbitmq_mgmt_dev", "anchor_keys": ["rabbitmq_mgmt_dev"], "base": 15672, "block": 1, "offset": 0, "proto": "http"},
        ],
    },
    "embedding_db": {
        "question":   "Usar Qdrant como embedding DB?",
        "yml_var":    "EMBEDDING_DB",
        "yml_docker": "DOCKER_EMBEDDING_DB",
        "yml_value":  "Qdrant",
        "port_specs": [
            {"name": "qdrant",      "anchor_keys": ["qdrant", "qdrant_grpc"], "base": 6333, "block": 2, "offset": 0, "proto": "http"},
            {"name": "qdrant_grpc", "anchor_keys": ["qdrant", "qdrant_grpc"], "base": 6333, "block": 2, "offset": 1, "proto": "grpc"},
        ],
        "port_specs_dev": [
            {"name": "qdrant_dev",      "anchor_keys": ["qdrant_dev", "qdrant_grpc_dev"], "base": 6333, "block": 2, "offset": 0, "proto": "http"},
            {"name": "qdrant_grpc_dev", "anchor_keys": ["qdrant_dev", "qdrant_grpc_dev"], "base": 6333, "block": 2, "offset": 1, "proto": "grpc"},
        ],
    },
}


def load_ports() -> dict:
    with open(PORTS_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_ports(data: dict) -> None:
    """Salva ports.yml com entradas inline para shared_services, prod, dev e extra_ports."""
    out = dict(data)

    # shared_services: {port: N, project: k} em linha única
    if "shared_services" in out:
        out["shared_services"] = {
            svc: [_InlineDict(e) for e in entries]
            for svc, entries in out["shared_services"].items()
        }

    # projects.*.prod.svc / .prod.db / .dev.svc / .dev.db / .extra_ports em linha única
    if "projects" in out:
        compacted = {}
        for key, proj in out["projects"].items():
            p = dict(proj)
            for env in ("prod", "dev"):
                env_data = p.get(env)
                if isinstance(env_data, dict) and env_data:
                    e = dict(env_data)
                    if e.get("svc"):
                        e["svc"] = _InlineDict(e["svc"])
                    if e.get("db"):
                        e["db"] = _InlineDict(e["db"])
                    if e.get("rabbit"):
                        e["rabbit"] = _InlineDict(e["rabbit"])
                    p[env] = e
            if "extra_ports" in p:
                p["extra_ports"] = [_InlineDict(ep) for ep in p["extra_ports"]]
            if "extra_ports_dev" in p:
                p["extra_ports_dev"] = [_InlineDict(ep) for ep in p["extra_ports_dev"]]
            compacted[key] = p
        out["projects"] = compacted

    with open(PORTS_FILE, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(out, f, allow_unicode=True, sort_keys=False,
                  default_flow_style=False, Dumper=_PortsDumper)


def prompt(label: str, default: str = "") -> str:
    # Usa (↵ ...) em vez de [↵ ...] para evitar colchetes aninhados no terminal Windows
    # que podem injetar caracteres no buffer de input quando o default contém [ ou ]
    suffix = f" (↵ {default})" if default else ""
    val = input(f"  {label}{suffix}: ").strip()
    return val or default


def yesno(label: str, default: bool = True) -> bool:
    enter_hint = "↵=S" if default else "↵=N"
    val = input(f"  {label} [S/N  {enter_hint}]: ").strip().lower()
    if not val:
        return default
    return val in ("s", "sim", "y", "yes")


def build_registered_ports(data: dict, exclude_key: str = "") -> dict[int, str]:
    """Retorna {porta: projeto} para todas as portas registradas no ports.yml."""
    result: dict[int, str] = {}
    for key, proj in data.get("projects", {}).items():
        if key == exclude_key:
            continue
        for env in ("prod", "dev"):
            env_data = proj.get(env) or {}
            svc = env_data.get("svc") or {}
            db  = env_data.get("db")  or {}
            for port in (svc.get("backend"), svc.get("auth"), svc.get("frontend"), svc.get("etl_frontend")):
                if port:
                    result.setdefault(port, key)
            for port in (db.get("port"), db.get("replica")):
                if port:
                    result.setdefault(port, key)
        for ep in proj.get("extra_ports", []):
            result.setdefault(ep["port"], key)
    return result


def port_tag(port: int, registered: dict[int, str]) -> str:
    if port in registered:
        return f"⚠ yml:{registered[port]}"
    return "livre"


def next_clean_port(shared: dict, svc_keys: list[str], base: int, block: int) -> int:
    """Retorna a menor porta N tal que o bloco [N, N+block-1] não conflita com
    nenhuma porta registrada em qualquer uma das svc_keys informadas.
    - svc_keys: todas as listas relacionadas ao serviço (ex: db_prod, db_dev, db_prod_replica…)
    - block: quantas portas o serviço reserva de uma vez (db=4, frontend=2, redis=1)
    """
    all_ports: set[int] = set()
    for k in svc_keys:
        for e in shared.get(k, []):
            all_ports.add(e["port"])

    if not all_ports:
        return base

    candidate = max(all_ports) + 1
    while any((candidate + i) in all_ports for i in range(block)):
        candidate += 1
    return candidate


def next_backend_block(shared: dict, base: int = 9000) -> int:
    """Próximo bloco de 1000 portas para o backend, alinhado em múltiplo de 1000.
    Ex: plumo=8000 → próximo=9000, depois=10000.
    Garante separação visual e semântica entre projetos no PowerShell Profile.
    """
    entries = shared.get("backend_prod", [])
    if not entries:
        return base
    max_port = max(e["port"] for e in entries)
    return (max_port // 1000 + 1) * 1000


def resolve_extra_ports(svc: dict, shared: dict) -> list[dict]:
    """Calcula as portas reais de um serviço extra consultando shared_services.
    Portas que compartilham anchor_keys (ex: qdrant par http/grpc) reutilizam
    o mesmo resultado de next_clean_port para garantir par consecutivo.
    """
    anchor_cache: dict[tuple, int] = {}
    result = []
    for spec in svc["port_specs"]:
        cache_key = tuple(spec["anchor_keys"])
        if cache_key not in anchor_cache:
            anchor_cache[cache_key] = next_clean_port(shared, spec["anchor_keys"], spec["base"], spec["block"])
        result.append({
            "name":  spec["name"],
            "port":  anchor_cache[cache_key] + spec["offset"],
            "proto": spec["proto"],
        })
    return result


def auto_pick_color(data: dict) -> str:
    used = {p.get("color") for p in data.get("projects", {}).values()}
    return next((c for c in PS_COLORS if c not in used), PS_COLORS[0])


def collect_project_info(data: dict) -> dict:
    projects = data.get("projects", {})
    shared   = data.get("shared_services", {})

    # ── 1. Projeto ────────────────────────────────────────────────
    print("\n── 1. Projeto ──────────────────────────────────────────────")
    key = prompt("Chave (snake_case, ex: meu_erp)").lower().replace("-", "_").replace(" ", "_")
    if not key:
        print("Chave inválida."); sys.exit(1)

    # Detect update vs new project
    existing  = projects.get(key)
    is_update = existing is not None

    # Visão do shared_services excluindo o projeto atual (para upsert e para cálculo correto)
    shared_excl = {k: [e for e in v if e.get("project") != key] for k, v in shared.items()}

    if is_update:
        print(f"\n  ⚠️  Projeto '{key}' já existe — modo atualização.")
        print("     Os valores atuais serão usados como padrão (↵ para manter).")
        ex_prod     = existing.get("prod") or {}
        ex_dev      = existing.get("dev")  or {}
        ex_prod_svc = ex_prod.get("svc", {})
        ex_prod_db  = ex_prod.get("db",  {})
        ex_dev_svc  = ex_dev.get("svc",  {})
        ex_dev_db   = ex_dev.get("db",   {})
        ex_name, _, ex_desc = existing.get("label", f"{key} — ").partition(" — ")
        backend_prod  = ex_prod_svc.get("backend")  or next_backend_block(shared_excl)
        auth_prod     = ex_prod_svc.get("auth",      backend_prod + 100)
        frontend_prod = ex_prod_svc.get("frontend") or next_clean_port(shared_excl, ["frontend_prod", "frontend_dev"], 5175, 2)
        backend_dev   = ex_dev_svc.get("backend",    backend_prod + 10)
        auth_dev      = ex_dev_svc.get("auth",       backend_prod + 110)
        frontend_dev  = ex_dev_svc.get("frontend",   frontend_prod + 1)
        db_prod       = ex_prod_db.get("port")      or next_clean_port(shared_excl, ["db_prod", "db_prod_replica", "db_dev", "db_dev_replica"], 5436, 4)
        db_dev        = ex_dev_db.get("port",        db_prod + 2)
        color         = existing.get("color",        auto_pick_color(data))
        name_def      = ex_name.strip() or key.replace("_", " ").title()
        desc_def      = ex_desc.strip() or f"{name_def} — descrição"
        root_def      = existing.get("root", f"C:\\Workspace\\gus-{key}")
        alias_def     = existing.get("alias", key.replace("_", "-"))

    else:
        backend_prod  = next_backend_block(shared_excl)
        auth_prod     = backend_prod + 100
        backend_dev   = backend_prod + 10
        auth_dev      = backend_prod + 110
        frontend_prod = next_clean_port(shared_excl, ["frontend_prod", "frontend_dev"], 5175, 2)
        frontend_dev  = frontend_prod + 1
        db_prod       = next_clean_port(shared_excl, ["db_prod", "db_prod_replica", "db_dev", "db_dev_replica"], 5436, 4)
        db_dev        = db_prod + 2
        color         = auto_pick_color(data)
        name_def      = key.replace("_", " ").title()
        desc_def      = f"{name_def} — descrição"
        root_def      = f"C:\\Workspace\\gus-{key}"
        alias_def     = key.replace("_", "-")


    name        = prompt("Nome do projeto", name_def)
    description = prompt("Descrição curta", desc_def)
    root        = prompt("Caminho raiz (Windows)", root_def)
    print(f"\n  Cor PS sugerida : {color}  (próxima livre na paleta)")
    color       = prompt("Cor PS", color)

    print(f"\n  Alias CLI — apelido curto para usar no gus (ex: gus rat {alias_def})")
    print( "  Não pode terminar em '-dev' (reservado para sufixo de ambiente).")
    alias = prompt("Alias CLI", alias_def)
    while alias.lower().endswith("-dev"):
        print("  ✗ O alias não pode terminar em '-dev'.")
        alias = prompt("Alias CLI", alias_def)

    # ── 2. Portas ─────────────────────────────────────────────────
    # Portas já reservadas em outros projetos (fonte de verdade: yml)
    registered = build_registered_ports(data, exclude_key=key)

    print("\n── 2. Portas (↵ aceita o valor sugerido) ───────────────────")
    has_replica      = yesno("Usar réplica de leitura (read replica)?")
    has_etl_frontend = yesno("Usar Frontend ETL (painel React/Vite de gestão ETL — sem backend próprio)?", default=True)
    print()

    def pport(label: str, val: int) -> int:
        return int(prompt(f"{label:<30} [{port_tag(val, registered)}]", str(val)))

    backend_prod    = pport("backend          PROD",       backend_prod)
    backend_dev     = pport("backend          DEV ",       backend_dev)
    auth_prod       = pport("auth             PROD",       auth_prod)
    auth_dev        = pport("auth             DEV ",       auth_dev)
    frontend_prod   = pport("frontend         PROD",       frontend_prod)
    frontend_dev    = pport("frontend         DEV ",       frontend_dev)

    etl_frontend_prod = None
    etl_frontend_dev  = None
    if has_etl_frontend:
        _etl_base    = next_clean_port(shared_excl, ["etl_frontend_prod", "etl_frontend_dev"], 5177, 2)
        if is_update:
            _etl_base = ex_prod_svc.get("etl_frontend") or _etl_base
        _etl_dev_def = ex_dev_svc.get("etl_frontend", _etl_base + 1) if is_update else _etl_base + 1
        etl_frontend_prod = pport("frontend-etl (ETL) PROD", _etl_base)
        etl_frontend_dev  = pport("frontend-etl (ETL) DEV ", _etl_dev_def)

    db_prod         = pport("db               PROD (main)",    db_prod)
    db_prod_replica = pport("db               PROD (replica)", db_prod + 1) if has_replica else None
    db_dev          = pport("db               DEV  (main)",    db_dev)
    db_dev_replica  = pport("db               DEV  (replica)", db_dev + 1)  if has_replica else None

    # ── 3. Banco de Dados ─────────────────────────────────────────
    print("\n── 3. Banco de Dados ────────────────────────────────────────")
    _ex_db  = ((existing.get("prod") or {}).get("db") or {}) if is_update else {}
    db_name = prompt("Nome do banco PROD", _ex_db.get("name", key))
    db_user = prompt("Usuário do banco",   _ex_db.get("user", key))
    db_pass = prompt("Senha do banco",     _ex_db.get("pass", key))

    # ── 4. Serviços Docker Extras ─────────────────────────────────
    print("\n── 4. Serviços Docker Extras ────────────────────────────────")
    extra_ports:     list[dict] = []
    extra_ports_dev: list[dict] = []
    extra_vars:      dict       = {}
    rabbit_user_prod = rabbit_pass_prod = rabbit_vhost_prod = ""
    rabbit_user_dev  = rabbit_pass_dev  = rabbit_vhost_dev  = ""
    shared_svc = data.get("shared_services", {})
    # Em modo update, remove entradas antigas deste projeto para recalcular
    if is_update:
        shared_svc = {
            k: [e for e in v if e.get("project") != key]
            for k, v in shared_svc.items()
        }
    for svc in EXTRA_SERVICES.values():
        ports     = resolve_extra_ports(svc, shared_svc)
        ports_dev = resolve_extra_ports({"port_specs": svc["port_specs_dev"]}, shared_svc)
        hints = "  ".join(f"{spec['name']}:{p['port']}" for spec, p in zip(svc["port_specs"], ports))
        if yesno(f"{svc['question']} ({hints})"):
            extra_ports.extend(ports)
            extra_ports_dev.extend(ports_dev)
            extra_vars[svc["yml_var"]]    = svc["yml_value"]
            extra_vars[svc["yml_docker"]] = "true"
            # RabbitMQ — credenciais por env (padrão: project_key / project_key)
            if svc["yml_var"] == "QUEUE_LAYER":
                print()
                rabbit_user_prod  = prompt("RABBITMQ_USER_PROD",  key)
                rabbit_pass_prod  = prompt("RABBITMQ_PASS_PROD",  key)
                rabbit_vhost_prod = prompt("RABBITMQ_VHOST_PROD", f"{key}_etl")
                rabbit_user_dev   = prompt("RABBITMQ_USER_DEV",   key)
                rabbit_pass_dev   = prompt("RABBITMQ_PASS_DEV",   key)
                rabbit_vhost_dev  = prompt("RABBITMQ_VHOST_DEV",  f"{key}_etl_dev")
            # Registra prod e dev no shared_svc para que o próximo serviço veja as portas
            for p in ports:
                shared_svc.setdefault(p["name"], []).append({"port": p["port"], "project": key})
            for p in ports_dev:
                shared_svc.setdefault(p["name"], []).append({"port": p["port"], "project": key})
        else:
            extra_vars[svc["yml_var"]]    = ""
            extra_vars[svc["yml_docker"]] = "false"

    # ── 4b. Camada de IA ──────────────────────────────────────────
    print()
    qdrant_on = extra_vars.get("DOCKER_EMBEDDING_DB") == "true"
    enable_ai = yesno("Habilitar camada de IA? (LLM + Agentes)", default=qdrant_on)
    ai_model  = ""
    ai_agents = ""
    if enable_ai:
        ai_model  = prompt("AI_MODEL",  "gpt-4-turbo")
        ai_agents = prompt("AI_AGENTS", '["Orquestrador", "Retriever", "Analyzer", "Synthesizer"]')

    # ── 5. Usuários e Admin ───────────────────────────────────────
    print("\n── 5. Usuários e Admin ──────────────────────────────────────")
    user_roles    = prompt("USER_ROLES",    '["admin", "user", "view"]')
    auth_provider = prompt("AUTH_PROVIDER", "local")
    print()
    admin_name     = prompt("ADMIN_NAME",     "Luiz Gustavo Quinelato")
    admin_username = prompt("ADMIN_USERNAME", "gustavoquinelato")
    admin_email    = prompt("ADMIN_EMAIL",    "gustavoquinelato@gmail.com")
    admin_password = prompt("ADMIN_PASSWORD", "Gus@2026!")

    return {
        "key": key, "alias": alias, "name": name, "description": description,
        "root": root, "color": color,
        "is_update": is_update,
        "has_replica": has_replica,
        "has_etl_frontend": has_etl_frontend,
        "db_name": db_name, "db_user": db_user, "db_pass": db_pass,
        "extra_ports": extra_ports, "extra_ports_dev": extra_ports_dev, "extra_vars": extra_vars,
        "rabbit_user_prod": rabbit_user_prod, "rabbit_pass_prod": rabbit_pass_prod, "rabbit_vhost_prod": rabbit_vhost_prod,
        "rabbit_user_dev":  rabbit_user_dev,  "rabbit_pass_dev":  rabbit_pass_dev,  "rabbit_vhost_dev":  rabbit_vhost_dev,
        "enable_ai": enable_ai, "ai_model": ai_model, "ai_agents": ai_agents,
        "user_roles": user_roles, "auth_provider": auth_provider,
        "admin_name": admin_name, "admin_username": admin_username,
        "admin_email": admin_email, "admin_password": admin_password,
        "ports": {
            "backend_prod": backend_prod, "backend_dev": backend_dev,
            "auth_prod": auth_prod,       "auth_dev": auth_dev,
            "frontend_prod": frontend_prod, "frontend_dev": frontend_dev,
            "etl_frontend_prod": etl_frontend_prod, "etl_frontend_dev": etl_frontend_dev,
            "db_prod": db_prod, "db_prod_replica": db_prod_replica,
            "db_dev": db_dev,   "db_dev_replica":  db_dev_replica,
        },
    }


import re as _re


def substitute_vars(content: str, values: dict, as_python: bool = False) -> str:
    """Substitui {{ VAR }} pelo valor correspondente em values.
    Se as_python=True, converte 'true'/'false' para 'True'/'False' (Python booleans).
    Vars não encontradas são mantidas como {{ VAR }}.
    """
    def _replace(m):
        key = m.group(1).strip()
        val = values.get(key)
        if val is None:
            return m.group(0)  # mantém {{ VAR }} se não encontrado
        val = str(val)
        if as_python and val.lower() in ("true", "false"):
            return val.capitalize()
        return val
    return _re.sub(r'\{\{\s*([A-Z0-9_]+)\s*\}\}', _replace, content)


def apply_conditionals(content: str, extra_vars: dict) -> str:
    """Processa marcadores # @IF VAR / # @ENDIF VAR nos templates docker.
    - Se extra_vars[VAR] == 'true': descomenta as linhas do bloco (remove '  # ' inicial)
    - Se extra_vars[VAR] != 'true': mantém linhas comentadas, remove apenas os marcadores
    """
    lines   = content.splitlines(keepends=True)
    result  = []
    in_block: str | None = None
    active  = False

    for line in lines:
        if_m  = _re.match(r'^# @IF\s+(\w+)\s*$', line)
        end_m = _re.match(r'^# @ENDIF\s+\w+\s*$', line)

        if if_m:
            in_block = if_m.group(1)
            active   = extra_vars.get(in_block, "").lower() == "true"
            continue   # descarta linha do marcador

        if end_m:
            in_block = None
            active   = False
            continue   # descarta linha do marcador

        if in_block and active:
            # Descomenta: remove o primeiro '# ' após espaços iniciais
            line = _re.sub(r'^(\s*)# ?', r'\1', line, count=1)

        result.append(line)

    return "".join(result)


def check_and_prepare_project_root(info: dict) -> None:
    """Verifica se PROJECT_ROOT já existe. Se sim, alerta e pede confirmação para limpar.
    Depois cria toda a estrutura de diretórios necessária no projeto destino.
    """
    root = Path(info["root"])

    if root.exists():
        print()
        print("  ⚠️  🔴  ATENÇÃO!")
        print(f"  A pasta já existe:  {root}")
        print("  Todo o conteúdo será APAGADO e reconstruído pelo blueprint.")
        print()
        confirm = input("  Digite 'APAGAR' para confirmar a limpeza total: ").strip()
        if confirm != "APAGAR":
            print("  Operação cancelada.")
            sys.exit(0)
        shutil.rmtree(root)
        print(f"  🗑️  {root} removida.")

    # Cria estrutura base
    dirs = [
        root / "docs" / "initial",
        root / "docs" / "prompts",
        root / "docs" / "reference",
        root / "services" / "backend" / "scripts" / "migrations",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    print(f"[OK] Estrutura criada em {root}")


def deploy_docs_to_project(project_root: Path, values: dict) -> None:
    """Substitui {{ VARS }} nos docs base e copia para PROJECT_ROOT/docs/initial/."""
    dest    = project_root / "docs" / "initial"
    skip    = {"00-variables-template.md"}
    count   = 0

    for src in sorted(DOCS_DIR.glob("*.md")):
        if src.name in skip:
            continue
        content = substitute_vars(src.read_text(encoding="utf-8"), values)
        (dest / src.name).write_text(content, encoding="utf-8")
        count += 1

    print(f"[OK] {count} docs → {dest.relative_to(project_root.parent)}")


def deploy_references_to_project(project_root: Path) -> None:
    """Copia todos os arquivos de docs/reference/ → PROJECT_ROOT/docs/reference/.
    Arquivos de referência visual (HTML) para o agente de implementação.
    """
    dest  = project_root / "docs" / "reference"
    count = 0

    for src in sorted(REFERENCE_DIR.iterdir()):
        if src.is_file():
            shutil.copy2(src, dest / src.name)
            count += 1

    print(f"[OK] {count} references → {dest.relative_to(project_root.parent)}")


def deploy_migrations_to_project(project_root: Path, values: dict) -> None:
    """Substitui {{ VARS }} nas migrations e copia para services/backend/scripts/migrations/.
    Copia o runner (estático) para services/backend/scripts/.
    """
    scripts_dir    = project_root / "services" / "backend" / "scripts"
    migrations_dir = scripts_dir / "migrations"

    # 1. Runner — estático, sem substituição
    runner_src = MIGRATIONS_TMPL / "migration_runner.py"
    shutil.copy2(runner_src, scripts_dir / "migration_runner.py")
    print(f"[OK] migration_runner.py → services/backend/scripts/")

    # 2. Migrations — com substituição de vars (as_python=True para booleans)
    count = 0
    for src in sorted(MIGRATIONS_TMPL.glob("0*.py")):
        content = substitute_vars(src.read_text(encoding="utf-8"), values, as_python=True)
        (migrations_dir / src.name).write_text(content, encoding="utf-8")
        count += 1

    print(f"[OK] {count} migrations → services/backend/scripts/migrations/")


def deploy_docker_to_project(project_root: Path, values: dict, extra_vars: dict) -> None:
    """Renderiza docker-compose.db.j2 duas vezes (PROD e DEV) e grava em PROJECT_ROOT/.

    Um único template é suficiente: ENV_SUFFIX ("" / "-dev"), ENV_LABEL ("prod" / "dev")
    e as vars de porta genéricas controlam todas as diferenças entre os dois ambientes.
    """
    tmpl = (DOCKER_TMPL / "docker-compose.db.j2").read_text(encoding="utf-8")

    envs = [
        {
            # ── PROD ──────────────────────────────────────────────────
            "out":              "docker-compose.db.yml",
            "ENV_SUFFIX":       "",
            "ENV_LABEL":        "prod",
            "ENV_LABEL_UPPER":  "PROD",
            "DB_NAME":          values["DB_NAME_PROD"],
            "DB_PORT":          values["DB_PORT_PROD"],
            "DB_PASSWORD":      values["DB_PASSWORD_PROD"],
            "REDIS_PORT":       values.get("REDIS_PORT_PROD", ""),
            "RABBITMQ_AMQP_PORT": values.get("RABBITMQ_AMQP_PORT_PROD", ""),
            "RABBITMQ_MGMT_PORT": values.get("RABBITMQ_MGMT_PORT_PROD", ""),
            "QDRANT_PORT":      values.get("QDRANT_PORT_PROD", ""),
            "QDRANT_GRPC_PORT": values.get("QDRANT_GRPC_PORT_PROD", ""),
        },
        {
            # ── DEV ───────────────────────────────────────────────────
            "out":              "docker-compose.db.dev.yml",
            "ENV_SUFFIX":       "-dev",
            "ENV_LABEL":        "dev",
            "ENV_LABEL_UPPER":  "DEV",
            "DB_NAME":          values["DB_NAME_DEV"],
            "DB_PORT":          values["DB_PORT_DEV"],
            "DB_PASSWORD":      values["DB_PASSWORD_DEV"],
            "REDIS_PORT":       values.get("REDIS_PORT_DEV", ""),
            "RABBITMQ_AMQP_PORT": values.get("RABBITMQ_AMQP_PORT_DEV", ""),
            "RABBITMQ_MGMT_PORT": values.get("RABBITMQ_MGMT_PORT_DEV", ""),
            "QDRANT_PORT":      values.get("QDRANT_PORT_DEV", ""),
            "QDRANT_GRPC_PORT": values.get("QDRANT_GRPC_PORT_DEV", ""),
        },
    ]

    for env in envs:
        out_name = env.pop("out")
        content  = substitute_vars(tmpl, {**values, **env})
        content  = apply_conditionals(content, extra_vars)
        (project_root / out_name).write_text(content, encoding="utf-8")

    print(f"[OK] 2 docker-compose files → {project_root.name}/")


def _extra_port_vars(extra_ports: list, extra_ports_dev: list) -> dict:
    """Monta as variáveis de porta dos serviços extras (prod e dev) para o 00-variables.md."""
    prod = {e["name"]: e["port"] for e in extra_ports}
    dev  = {e["name"]: e["port"] for e in extra_ports_dev}
    result = {}
    # Redis
    if "redis" in prod:
        result["REDIS_PORT_PROD"] = str(prod["redis"])
    if "redis_dev" in dev:
        result["REDIS_PORT_DEV"] = str(dev["redis_dev"])
    # RabbitMQ
    if "rabbitmq_amqp" in prod:
        result["RABBITMQ_AMQP_PORT_PROD"] = str(prod["rabbitmq_amqp"])
        result["RABBITMQ_MGMT_PORT_PROD"] = str(prod.get("rabbitmq_mgmt", ""))
    if "rabbitmq_amqp_dev" in dev:
        result["RABBITMQ_AMQP_PORT_DEV"] = str(dev["rabbitmq_amqp_dev"])
        result["RABBITMQ_MGMT_PORT_DEV"] = str(dev.get("rabbitmq_mgmt_dev", ""))
    # Qdrant
    if "qdrant" in prod:
        result["QDRANT_PORT_PROD"]      = str(prod["qdrant"])
        result["QDRANT_GRPC_PORT_PROD"] = str(prod.get("qdrant_grpc", ""))
    if "qdrant_dev" in dev:
        result["QDRANT_PORT_DEV"]      = str(dev["qdrant_dev"])
        result["QDRANT_GRPC_PORT_DEV"] = str(dev.get("qdrant_grpc_dev", ""))
    return result


def build_values(info: dict) -> dict:
    """Constrói o dicionário de variáveis para substituição em todos os templates."""
    p         = info["ports"]
    ev        = info["extra_vars"]
    prefix    = "".join(w[0] for w in info["key"].split("_"))[:3].upper()
    enable_ai = info["enable_ai"]
    qdrant_on = ev.get("DOCKER_EMBEDDING_DB") == "true"

    return {
        # ── 1. Projeto ───────────────────────────────────────────────
        "PROJECT_NAME":         info["name"],
        "PROJECT_KEY":          info["key"],
        "PROJECT_DESCRIPTION":  info["description"],
        "LANGUAGE":             "pt-BR",
        "TIMEZONE":             "America/Sao_Paulo",
        "PROJECT_PREFIX":       prefix,
        "PROJECT_ROOT":         info["root"],
        # ── 2. Usuários e Acesso ─────────────────────────────────────
        "USER_ROLES":           info["user_roles"],
        "AUTH_PROVIDER":        info["auth_provider"],
        # ── 2.1. Admin Inicial ───────────────────────────────────────
        "ADMIN_NAME":           info["admin_name"],
        "ADMIN_USERNAME":       info["admin_username"],
        "ADMIN_EMAIL":          info["admin_email"],
        "ADMIN_PASSWORD":       info["admin_password"],
        # ── 3. Infraestrutura Base ───────────────────────────────────
        "USE_DOCKER":              "true",
        "BACKEND_PORT":            str(p["backend_prod"]),
        "BACKEND_PORT_DEV":        str(p["backend_dev"]),
        "AUTH_PORT":               str(p["auth_prod"]),
        "AUTH_PORT_DEV":           str(p["auth_dev"]),
        "FRONTEND_PORT":           str(p["frontend_prod"]),
        "FRONTEND_PORT_DEV":       str(p["frontend_dev"]),
        "FRONTEND_ETL_PORT":       str(p["etl_frontend_prod"]) if info.get("has_etl_frontend") else "",
        "FRONTEND_ETL_PORT_DEV":   str(p["etl_frontend_dev"])  if info.get("has_etl_frontend") else "",
        # ── 4. Banco de Dados ────────────────────────────────────────
        "DB_VERSION":           "17",
        "DB_LANGUAGE":          "pt_BR.UTF-8",
        "DB_ENABLE_ML":         "false",
        "DB_ENABLE_REPLICA":    "true" if info["has_replica"] else "false",
        "DB_PORT_PROD":         str(p["db_prod"]),
        "DB_PORT_PROD_REPLICA": str(p["db_prod_replica"]) if info["has_replica"] else "",
        "DB_PORT_DEV":          str(p["db_dev"]),
        "DB_PORT_DEV_REPLICA":  str(p["db_dev_replica"])  if info["has_replica"] else "",
        "DOCKER_DB":            "true",
        "DB_NAME_PROD":         info["db_name"],
        "DB_NAME_DEV":          info["db_name"] + "_dev",
        "DB_USER":              info["db_user"],
        "DB_PASSWORD_PROD":     info["db_pass"],
        "DB_PASSWORD_DEV":      info["db_pass"],
        # ── 5. Cache e Mensageria ────────────────────────────────────
        **ev,  # CACHE_LAYER, DOCKER_CACHE, QUEUE_LAYER, DOCKER_QUEUE, EMBEDDING_DB, DOCKER_EMBEDDING_DB
        **_extra_port_vars(info["extra_ports"], info["extra_ports_dev"]),
        "RABBITMQ_USER_PROD":  info.get("rabbit_user_prod", ""),
        "RABBITMQ_PASS_PROD":  info.get("rabbit_pass_prod", ""),
        "RABBITMQ_VHOST_PROD": info.get("rabbit_vhost_prod", ""),
        "RABBITMQ_USER_DEV":   info.get("rabbit_user_dev", ""),
        "RABBITMQ_PASS_DEV":   info.get("rabbit_pass_dev", ""),
        "RABBITMQ_VHOST_DEV":  info.get("rabbit_vhost_dev", ""),
        # ── 6. IA e ETL ──────────────────────────────────────────────
        "ENABLE_ETL":      "true" if info.get("has_etl_frontend") else "false",
        "ENABLE_AI_LAYER": "true" if enable_ai else "false",
        "EMBEDDING_MODEL": "text-embedding-3-small" if (enable_ai and qdrant_on) else "",
        "AI_MODEL":        info.get("ai_model", ""),
        "AI_AGENTS":       info.get("ai_agents", ""),
    }


def fill_variables_template(info: dict, values: dict, project_root: Path) -> None:
    """Escreve 00-variables.md em dois destinos:

    1. PROJECT_ROOT/docs/initial/00-variables.md  — completo, junto com todos os docs.
       Usado pelo agente que implementa o projeto.

    2. projects/<key>/00-variables.md (blueprint) — minimalista, só o que
       generate_prompt.py precisa para gerar o PROMPT_CUSTOM. Sem infra, sem senhas.
    """
    # Variáveis consumidas por generate_prompt.py no custom prompt
    BLUEPRINT_KEYS = {
        'PROJECT_NAME', 'PROJECT_DESCRIPTION', 'PROJECT_ROOT',
        'LANGUAGE', 'TIMEZONE', 'PROJECT_PREFIX',
        'USER_ROLES', 'ENABLE_ETL', 'ENABLE_AI_LAYER',
    }

    blueprint_proj_dir = PROJECTS_DIR / info["key"]
    blueprint_proj_dir.mkdir(parents=True, exist_ok=True)

    lines_out = []
    for line in VARIABLES_TEMPLATE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            var = stripped.partition("=")[0].strip()
            if var in values:
                lines_out.append(f"{var}={values[var]}")
                continue
        lines_out.append(line)
    full_content = "\n".join(lines_out) + "\n"

    # 1. Completo → docs/initial/ do projeto destino
    (project_root / "docs" / "initial" / "00-variables.md").write_text(full_content, encoding="utf-8")
    print(f"[OK] 00-variables.md → docs/initial/  (completo)")

    # 2. Minimalista → projects/<key>/ do blueprint
    minimal_lines = [f"{k}={values[k]}" for k in BLUEPRINT_KEYS if k in values]
    (blueprint_proj_dir / "00-variables.md").write_text("\n".join(minimal_lines) + "\n", encoding="utf-8")
    print(f"[OK] 00-variables.md → projects/{info['key']}/  (blueprint, {len(minimal_lines)} vars)")
    print(f"[OK] projects/{info['key']}/ pronto  ← adicione docs de módulo aqui")


def update_ports_yml(data: dict, info: dict) -> None:
    p   = info["ports"]
    rep = info["has_replica"]

    def _svc(env: str) -> dict:
        d = {"backend": p[f"backend_{env}"], "auth": p[f"auth_{env}"], "frontend": p[f"frontend_{env}"]}
        if info.get("has_etl_frontend") and p.get(f"etl_frontend_{env}"):
            d["etl_frontend"] = p[f"etl_frontend_{env}"]
        return d

    def _db(env: str) -> dict:
        d: dict = {"port": p[f"db_{env}"]}
        if rep:
            d["replica"] = p[f"db_{env}_replica"]
        d["name"] = info["db_name"] + ("_dev" if env == "dev" else "")
        d["user"] = info["db_user"]
        d["pass"] = info["db_pass"]
        return d

    proj = {"label": f"{info['name']} — {info['description']}"}
    if info.get("alias") and info["alias"] != info["key"]:
        proj["alias"] = info["alias"]
    proj.update({
        "root": info["root"], "color": info["color"],
        "legacy": False, "conflicts_with": [],
        "prod": {"svc": _svc("prod"), "db": _db("prod"), **( {"rabbit": {"user": info["rabbit_user_prod"], "pass": info["rabbit_pass_prod"], "vhost": info["rabbit_vhost_prod"]}} if info.get("rabbit_user_prod") else {} )},
        "dev":  {"svc": _svc("dev"),  "db": _db("dev"),  **( {"rabbit": {"user": info["rabbit_user_dev"],  "pass": info["rabbit_pass_dev"],  "vhost": info["rabbit_vhost_dev"]}}  if info.get("rabbit_user_dev")  else {} )},
        "extra_ports":     info["extra_ports"],
        "extra_ports_dev": info["extra_ports_dev"],
    })
    data["projects"][info["key"]] = proj

    # ── Sincroniza shared_services (app ports + docker extras) ────────────
    shared = data.setdefault("shared_services", {})
    key    = info["key"]
    p      = info["ports"]

    # Remove todas as entradas antigas deste projeto
    for svc_list in shared.values():
        svc_list[:] = [e for e in svc_list if e.get("project") != key]

    # App ports — todos os ports alocados (prod + dev + replicas)
    def reg(svc: str, port: int | None) -> None:
        if port:
            shared.setdefault(svc, []).append({"port": port, "project": key})

    reg("backend_prod",       p["backend_prod"])
    reg("backend_dev",        p["backend_dev"])
    reg("auth_prod",          p["auth_prod"])
    reg("auth_dev",           p["auth_dev"])
    reg("frontend_prod",      p["frontend_prod"])
    reg("frontend_dev",       p["frontend_dev"])
    reg("etl_frontend_prod",  p.get("etl_frontend_prod"))
    reg("etl_frontend_dev",   p.get("etl_frontend_dev"))
    reg("db_prod",            p["db_prod"])
    reg("db_prod_replica",    p["db_prod_replica"])
    reg("db_dev",             p["db_dev"])
    reg("db_dev_replica",     p["db_dev_replica"])

    # Docker extra ports prod (redis, qdrant, rabbitmq…)
    for ep in info["extra_ports"]:
        shared.setdefault(ep["name"], []).append({"port": ep["port"], "project": key})
    # Docker extra ports dev
    for ep in info["extra_ports_dev"]:
        shared.setdefault(ep["name"], []).append({"port": ep["port"], "project": key})

    # Remove chaves vazias
    data["shared_services"] = {k: v for k, v in shared.items() if v}
    # Remove meta se vier de um yml antigo com next_* (migração automática)
    data.pop("meta", None)

    save_ports(data)
    action = "atualizado" if info["is_update"] else "adicionado"
    print(f"[OK] helms/ports.yml {action} com projeto '{info['key']}'")


def ps_db_url(info: dict, env: str) -> str:
    p = info["ports"]
    db_port = p[f"db_{env}"]
    db_name = info["db_name"] + ("_dev" if env == "dev" else "")
    return f"postgresql://{info['db_user']}:{info['db_pass']}@localhost:{db_port}/{db_name}"


def generate_ps_section(info: dict) -> str:
    k    = info["key"]
    K    = k.upper()
    p    = info["ports"]
    c    = info["color"]
    root = info["root"]
    has_etl  = info.get("has_etl_frontend", False)
    prod_url = ps_db_url(info, "prod")
    dev_url  = ps_db_url(info, "dev")

    extra_ports     = info.get("extra_ports", [])
    extra_ports_dev = info.get("extra_ports_dev", [])

    all_prod_ports = [p["backend_prod"], p["auth_prod"], p["frontend_prod"]]
    all_dev_ports  = [p["backend_dev"],  p["auth_dev"],  p["frontend_dev"]]
    if has_etl:
        all_prod_ports.append(p["etl_frontend_prod"])
        all_dev_ports.append(p["etl_frontend_dev"])
    ports_prod_str = ",".join(str(x) for x in all_prod_ports)
    ports_dev_str  = ",".join(str(x) for x in all_dev_ports)
    db_all = [p["db_prod"], p["db_dev"]]
    if info["has_replica"]:
        db_all += [p["db_prod_replica"], p["db_dev_replica"]]
    db_ports     = ",".join(str(x) for x in db_all)
    extra_ports_str     = ("," + ",".join(str(e["port"]) for e in extra_ports))     if extra_ports     else ""
    extra_ports_dev_str = ("," + ",".join(str(e["port"]) for e in extra_ports_dev)) if extra_ports_dev else ""
    replica_prod = f" / :{p['db_prod_replica']}" if info["has_replica"] else ""
    replica_dev  = f" / :{p['db_dev_replica']}"  if info["has_replica"] else ""
    etl_prod_line = (f"\n#          Frontend ETL :{p['etl_frontend_prod']}  (React/Vite — painel ETL, sem backend próprio)" if has_etl else "")
    etl_dev_line  = (f"\n#          Frontend ETL :{p['etl_frontend_dev']}  (React/Vite — painel ETL, sem backend próprio)" if has_etl else "")
    extra_comment_prod = ("\n#          " + " | ".join(f"{e['name']}:{e['port']}" for e in extra_ports)) if extra_ports else ""
    extra_comment_dev  = ("\n#          " + " | ".join(f"{e['name']}:{e['port']}" for e in extra_ports_dev)) if extra_ports_dev else ""
    install_extra = f"; {k}-frontend-etl; npm install" if has_etl else ""

    lines = [
        "",
        f"# START {k}",
        "# " + "=" * 65,
        f"# {K} — {info['name']}",
        f"# Root   : {root}",
        f"# PROD   : Backend :{p['backend_prod']} | Auth :{p['auth_prod']} | Frontend :{p['frontend_prod']} | DB :{p['db_prod']}{replica_prod}{etl_prod_line}{extra_comment_prod}",
        f"# DEV    : Backend :{p['backend_dev']} | Auth :{p['auth_dev']} | Frontend :{p['frontend_dev']} | DB :{p['db_dev']}{replica_dev}{etl_dev_line}{extra_comment_dev}",
        "# " + "=" * 65,
        f'${K}_ROOT     = "{root}"',
        f'${K}_PROD_URL = "{prod_url}"',
        f'${K}_DEV_URL  = "{dev_url}"',
        "",
        f'function {k}              {{ Set-Location ${K}_ROOT;                               Write-Host "[{K}] Root"         -ForegroundColor {c} }}',
        f'function {k}-backend      {{ Set-Location "${K}_ROOT\\services\\backend";            Write-Host "[{K}] Backend"      -ForegroundColor Blue }}',
        f'function {k}-auth         {{ Set-Location "${K}_ROOT\\services\\auth-service";       Write-Host "[{K}] Auth"         -ForegroundColor Blue }}',
        f'function {k}-frontend     {{ Set-Location "${K}_ROOT\\services\\frontend";           Write-Host "[{K}] Frontend"     -ForegroundColor Blue }}',
    ]
    if has_etl:
        lines.append(
            f'function {k}-frontend-etl {{ Set-Location "${K}_ROOT\\services\\frontend-etl";      Write-Host "[{K}] Frontend-ETL" -ForegroundColor Blue }}'
        )

    lines += [
        "",
        "# Docker",
        f'function {k}-dkup       {{ {k}; docker compose -f docker-compose.db.yml up -d;     Write-Host "[{K}] PROD DB :{p["db_prod"]} up" -ForegroundColor Green  }}',
        f'function {k}-dkdown     {{ {k}; docker compose -f docker-compose.db.yml down;       Write-Host "[{K}] PROD DB stopped"  -ForegroundColor Red    }}',
        f'function {k}-dkup-dev   {{ {k}; docker compose -f docker-compose.db.dev.yml up -d;  Write-Host "[{K}] DEV DB :{p["db_dev"]} up"  -ForegroundColor Yellow }}',
        f'function {k}-dkdown-dev {{ {k}; docker compose -f docker-compose.db.dev.yml down;   Write-Host "[{K}] DEV DB stopped"   -ForegroundColor Red    }}',
        "",
        "# Services — PROD",
        f'function {k}-run-auth {{',
        f'    {k}-auth; Write-Host "[{K}-PROD] Auth :{p["auth_prod"]}" -ForegroundColor Green',
        f'    if (Test-Path ".\\.venv\\Scripts\\Activate.ps1") {{ .\\.venv\\Scripts\\Activate.ps1 }}',
        f'    $env:APP_ENV = "prod"; python -m uvicorn app.main:app --reload --port {p["auth_prod"]}',
        f'}}',
        f'function {k}-run-backend {{',
        f'    {k}-backend; Write-Host "[{K}-PROD] Backend :{p["backend_prod"]}" -ForegroundColor Green',
        f'    if (Test-Path ".\\.venv\\Scripts\\Activate.ps1") {{ .\\.venv\\Scripts\\Activate.ps1 }}',
        f'    $env:APP_ENV = "prod"; python -m uvicorn app.main:app --reload --port {p["backend_prod"]}',
        f'}}',
        f'function {k}-run-frontend {{ {k}-frontend; Write-Host "[{K}-PROD] Frontend :{p["frontend_prod"]}" -ForegroundColor Green; npm run dev -- --port {p["frontend_prod"]} }}',
    ]
    if has_etl:
        lines.append(
            f'function {k}-run-frontend-etl {{ {k}-frontend-etl; Write-Host "[{K}-PROD] Frontend-ETL :{p["etl_frontend_prod"]}" -ForegroundColor Green; npm run dev -- --port {p["etl_frontend_prod"]} }}'
        )

    rat_tabs = [
        f'    wt -w 0 new-tab --title "{K}-Auth"         powershell.exe -NoExit -Command "{k}-run-auth"',
        f'    wt -w 0 new-tab --title "{K}-Backend"      powershell.exe -NoExit -Command "{k}-run-backend"',
        f'    wt -w 0 new-tab --title "{K}-Frontend"     powershell.exe -NoExit -Command "{k}-run-frontend"',
    ]
    if has_etl:
        rat_tabs.append(f'    wt -w 0 new-tab --title "{K}-Frontend-ETL" powershell.exe -NoExit -Command "{k}-run-frontend-etl"')
    lines += [
        f'function {k}-rat {{',
        f'    {k}-dkup',
        *rat_tabs,
        f'    Write-Host "[{K}] PROD aberto!" -ForegroundColor Green',
        f'}}',
        "",
        "# Services — DEV",
        f'function {k}-run-auth-dev {{',
        f'    {k}-auth; Write-Host "[{K}-DEV] Auth :{p["auth_dev"]}" -ForegroundColor Yellow',
        f'    if (Test-Path ".\\.venv\\Scripts\\Activate.ps1") {{ .\\.venv\\Scripts\\Activate.ps1 }}',
        f'    $env:APP_ENV = "dev"; python -m uvicorn app.main:app --reload --port {p["auth_dev"]}',
        f'}}',
        f'function {k}-run-backend-dev {{',
        f'    {k}-backend; Write-Host "[{K}-DEV] Backend :{p["backend_dev"]}" -ForegroundColor Yellow',
        f'    if (Test-Path ".\\.venv\\Scripts\\Activate.ps1") {{ .\\.venv\\Scripts\\Activate.ps1 }}',
        f'    $env:APP_ENV = "dev"; python -m uvicorn app.main:app --reload --port {p["backend_dev"]}',
        f'}}',
        f'function {k}-run-frontend-dev {{ {k}-frontend; Write-Host "[{K}-DEV] Frontend :{p["frontend_dev"]}" -ForegroundColor Yellow; npm run dev -- --port {p["frontend_dev"]} }}',
    ]
    if has_etl:
        lines.append(
            f'function {k}-run-frontend-etl-dev {{ {k}-frontend-etl; Write-Host "[{K}-DEV] Frontend-ETL :{p["etl_frontend_dev"]}" -ForegroundColor Yellow; npm run dev -- --port {p["etl_frontend_dev"]} }}'
        )

    rat_dev_tabs = [
        f'    wt -w 0 new-tab --title "{K}-Auth-DEV"         powershell.exe -NoExit -Command "{k}-run-auth-dev"',
        f'    wt -w 0 new-tab --title "{K}-Backend-DEV"      powershell.exe -NoExit -Command "{k}-run-backend-dev"',
        f'    wt -w 0 new-tab --title "{K}-Frontend-DEV"     powershell.exe -NoExit -Command "{k}-run-frontend-dev"',
    ]
    if has_etl:
        rat_dev_tabs.append(f'    wt -w 0 new-tab --title "{K}-Frontend-ETL-DEV" powershell.exe -NoExit -Command "{k}-run-frontend-etl-dev"')
    lines += [
        f'function {k}-rat-dev {{',
        f'    {k}-dkup-dev',
        *rat_dev_tabs,
        f'    Write-Host "[{K}] DEV aberto!" -ForegroundColor Yellow',
        f'}}',
        "",
        "# DB — PROD",
        f'function {k}-db-migrate     {{ {k}; python services\\backend\\scripts\\migration_runner.py --apply-all }}',
        f'function {k}-db-rollback    {{ {k}; python services\\backend\\scripts\\migration_runner.py --rollback-to 0000 --confirm }}',
        f'function {k}-db-status      {{ {k}; python services\\backend\\scripts\\migration_runner.py --status }}',
        "# DB — DEV",
        f'function {k}-db-migrate-dev  {{ {k}; $env:DATABASE_URL=${K}_DEV_URL; python services\\backend\\scripts\\migration_runner.py --apply-all }}',
        f'function {k}-db-rollback-dev {{ {k}; $env:DATABASE_URL=${K}_DEV_URL; python services\\backend\\scripts\\migration_runner.py --rollback-to 0000 --confirm }}',
        f'function {k}-db-status-dev   {{ {k}; $env:DATABASE_URL=${K}_DEV_URL; python services\\backend\\scripts\\migration_runner.py --status }}',
        "",
        "# Utilities",
        f'function {k}-kill    {{ Write-Host "[{K}] Parando..." -ForegroundColor Red; Stop-PortProcess @({ports_prod_str},{ports_dev_str}) }}',
        f'function {k}-ports   {{ @({ports_prod_str},{ports_dev_str},{db_ports}{extra_ports_str}{extra_ports_dev_str})|ForEach-Object{{$c=Get-NetTCPConnection -LocalPort $_ -ErrorAction SilentlyContinue;if($c){{Write-Host "  [OK]  :$_" -ForegroundColor Green}}else{{Write-Host "  [---] :$_" -ForegroundColor DarkGray}}}} }}',
        f'function {k}-health  {{ Write-Host "[{K}] Health check..." -ForegroundColor Cyan; {k}-ports; {k}; git status --short }}',
        f'function {k}-install {{ {k}; python scripts/setup_venvs.py; {k}-frontend; npm install{install_extra} }}',
        "",
        f'# Aliases — {K}',
        f'Set-Alias -Name rat-{k}      -Value {k}-rat',
        f'Set-Alias -Name rat-{k}-dev  -Value {k}-rat-dev',
        f'Set-Alias -Name dbm-{k}      -Value {k}-db-migrate',
        f'Set-Alias -Name dbr-{k}      -Value {k}-db-rollback',
        f'Set-Alias -Name dbs-{k}      -Value {k}-db-status',
        f'Set-Alias -Name dbm-{k}-dev  -Value {k}-db-migrate-dev',
        f'Set-Alias -Name dbr-{k}-dev  -Value {k}-db-rollback-dev',
        f'Set-Alias -Name dbs-{k}-dev  -Value {k}-db-status-dev',
        f'Set-Alias -Name dkup-{k}       -Value {k}-dkup',
        f'Set-Alias -Name dkdown-{k}     -Value {k}-dkdown',
        f'Set-Alias -Name dkup-{k}-dev   -Value {k}-dkup-dev',
        f'Set-Alias -Name dkdown-{k}-dev -Value {k}-dkdown-dev',
        f'Set-Alias -Name kill-{k}       -Value {k}-kill',
        f"# END {k}",
    ]
    return "\n".join(lines)


def update_ps_summary(profile: str, info: dict) -> str:
    k = info["key"]
    K = k.upper()
    c = info["color"]

    new_block = (
        f'Write-Host ""\n'
        f'Write-Host "  [{K}]" -ForegroundColor {c}\n'
        f'Write-Host "    rat-{k} / rat-{k}-dev" -ForegroundColor {c}\n'
        f'Write-Host "    dkup-{k} / dkdown-{k} / dkup-{k}-dev / dkdown-{k}-dev" -ForegroundColor {c}\n'
        f'Write-Host "    dbm-{k} / dbr-{k} / dbs-{k} / dbm-{k}-dev / dbr-{k}-dev / dbs-{k}-dev" -ForegroundColor {c}\n'
        f'Write-Host "    kill-{k}  {k}-ports  {k}-health  {k}-install" -ForegroundColor {c}\n'
    )
    # Insert before the last blank Write-Host (closing line of SUMMARY)
    end_marker = '\nWrite-Host ""\n'
    idx = profile.rfind(end_marker)
    if idx >= 0:
        profile = profile[:idx + 1] + new_block + profile[idx + 1:]
    else:
        profile = profile.rstrip("\n") + "\n" + new_block

    # Increment the "N projetos" counter
    for n in range(50, 0, -1):
        old = f"carregado - {n} projeto"
        if old in profile:
            profile = profile.replace(old, f"carregado - {n + 1} projeto", 1)
            break

    return profile


def remove_project_from_profile(profile: str, k: str) -> str:
    """Remove a seção de um projeto do PS profile usando marcadores # START/END {key}."""
    K = k.upper()

    # ── Seção principal (START/END markers) ──────────────────────
    start_marker = f"\n# START {k}\n"
    end_marker   = f"\n# END {k}\n"
    idx_s = profile.find(start_marker)
    if idx_s >= 0:
        idx_e = profile.find(end_marker, idx_s)
        if idx_e >= 0:
            profile = profile[:idx_s] + profile[idx_e + len(end_marker):]

    # ── Bloco no SUMMARY ────────────────────────────────────────
    sum_start = f'Write-Host "  [{K}]'
    idx_sum   = profile.find(sum_start)
    if idx_sum >= 0:
        close     = '\nWrite-Host ""\n'
        idx_close = profile.find(close, idx_sum)
        if idx_close >= 0:
            profile = profile[:idx_sum] + profile[idx_close + len(close):]
        # Decrement project count
        for n in range(50, 1, -1):
            if f"carregado - {n} projeto" in profile:
                profile = profile.replace(
                    f"carregado - {n} projeto", f"carregado - {n - 1} projeto", 1
                )
                break

    # ── Linha no cabeçalho de aliases ───────────────────────────
    header_line = f"#   rat-{k} / rat-{k}-dev    dbm-{k} / dbm-{k}-dev    kill-{k}\n"
    profile = profile.replace(header_line, "")

    return profile


def append_to_profile(info: dict) -> None:
    with open(PROFILE_FILE, encoding="utf-8-sig") as f:
        content = f.read()

    k = info["key"]

    # On update: wipe existing section/summary/header before re-inserting
    if info["is_update"]:
        content = remove_project_from_profile(content, k)

    # Insert new section before SUMMARY block
    summary_marker = "\n# " + "=" * 65 + "\n# SUMMARY\n"
    if summary_marker not in content:
        content += generate_ps_section(info) + "\n"
    else:
        idx = content.index(summary_marker)
        content = content[:idx] + generate_ps_section(info) + "\n" + content[idx:]
        content = update_ps_summary(content, info)

    # Add alias line to top header — only if not already there
    header_line = f"#   rat-{k} / rat-{k}-dev    dbm-{k} / dbm-{k}-dev    kill-{k}"
    if header_line not in content:
        content = content.replace(
            "#   rat-pulse                    dbm-pulse                    kill-pulse\n# ===",
            f"#   rat-pulse                    dbm-pulse                    kill-pulse\n"
            f"{header_line}\n# ===",
        )

    with open(PROFILE_FILE, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write(content)
    action = "atualizado" if info["is_update"] else "adicionado"
    print(f"[OK] helms/powershell_profile.ps1 {action} com seção '{k}'")


def main() -> None:
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 65)
    print("  create_project.py — Novo Projeto no Blueprint")
    print("=" * 65)

    data = load_ports()
    info = collect_project_info(data)
    p    = info["ports"]

    print("\n── Resumo ──────────────────────────────────────────────────")
    print(f"  Projeto : {info['key']}  ({info['name']})")
    print(f"  Desc    : {info['description']}")
    print(f"  Root    : {info['root']}")
    print(f"  Cor PS  : {info['color']}")
    print(f"  PROD    : backend={p['backend_prod']}  auth={p['auth_prod']}  frontend={p['frontend_prod']}  db={p['db_prod']}")
    if info["has_replica"]:
        print(f"           db_replica={p['db_prod_replica']}")
    if info.get("has_etl_frontend"):
        print(f"           etl_frontend={p['etl_frontend_prod']}  (React/Vite — painel ETL, sem backend próprio)")
    print(f"  DEV     : backend={p['backend_dev']}  auth={p['auth_dev']}  frontend={p['frontend_dev']}  db={p['db_dev']}")
    if info["has_replica"]:
        print(f"           db_replica={p['db_dev_replica']}")
    if info.get("has_etl_frontend"):
        print(f"           etl_frontend={p['etl_frontend_dev']}  (React/Vite — painel ETL, sem backend próprio)")
    if info["extra_ports"]:
        print(f"  Extras  : {', '.join(e['name'] for e in info['extra_ports'])}")
    print("────────────────────────────────────────────────────────────")

    if not yesno("\nConfirmar e criar projeto?", default=True):
        print("Cancelado.")
        sys.exit(0)

    # Constrói o dicionário de variáveis (usado por todos os deployers)
    values      = build_values(info)
    extra_vars  = info["extra_vars"]
    project_root = Path(info["root"])

    print()

    # 1. Verifica/limpa PROJECT_ROOT e cria estrutura de diretórios
    check_and_prepare_project_root(info)

    # 2. Copia docs base (com vars substituídas) → PROJECT_ROOT/docs/initial/
    deploy_docs_to_project(project_root, values)

    # 2b. Copia referências visuais (HTML) → PROJECT_ROOT/docs/reference/
    deploy_references_to_project(project_root)

    # 3. Copia migrations (com vars) + runner (estático) → PROJECT_ROOT/services/backend/scripts/
    deploy_migrations_to_project(project_root, values)

    # 4. Gera docker-compose files (com vars + condicionais) → PROJECT_ROOT/
    deploy_docker_to_project(project_root, values, extra_vars)

    # 5. Escreve 00-variables.md no projeto destino (não mais no blueprint)
    fill_variables_template(info, values, project_root)

    # 6. Atualiza helms/ports.yml
    update_ports_yml(data, info)

    # 7. Atualiza helms/powershell_profile.ps1
    append_to_profile(info)

    # 8. Gera o prompt inicial (PROMPT_INICIAL_<KEY>.md) no projeto destino
    print()
    print("── Gerando prompt inicial ───────────────────────────────────")
    try:
        from generate_prompt import generate_base_prompt  # noqa: PLC0415
        generate_base_prompt(info["key"], values, project_root)
    except Exception as exc:
        print(f"⚠️  Prompt inicial não gerado ({exc})")
        print(f"   Rode manualmente após criar o projeto.")

    key    = info["key"]
    root   = info["root"]
    action = "atualizado" if info["is_update"] else "criado"
    print(f"\n✅  Projeto '{key}' {action}!")
    print(f"\n   📁 Blueprint (referência):")
    print(f"      projects/{key}/            ← adicione docs de módulo aqui")
    print(f"\n   📁 Projeto destino ({root}):")
    print(f"      docs/initial/                  ← todos os docs base + 00-variables.md")
    print(f"      docs/reference/                ← login.html + color-settings.html")
    print(f"      docs/prompts/PROMPT_INICIAL_{key.upper()}.md  ← prompt inicial ✅")
    print(f"      services/backend/scripts/      ← migration_runner.py")
    print(f"      services/backend/scripts/migrations/  ← 0001_initial_schema + 0002_initial_seed_data")
    print(f"      docker-compose.db.yml          ← PROD (valores hardcoded de prod)")
    print(f"      docker-compose.db.dev.yml      ← DEV  (valores hardcoded de dev)")
    print(f"\n   📋 Próximos passos:")
    print(f"      1. Recarregue o PS : . $PROFILE")
    print(f"      2. Adicione docs de módulo em  projects/{key}/")
    print(f"      3. Gere o prompt   : python scripts/generate_prompt.py {key}")
    print(f"\n   🖥️  GUS CLI (após recarregar o PS):")
    print(f"      gus dkup {key}              ← sobe DB PROD")
    print(f"      gus dkup-dev {key}          ← sobe DB DEV")
    print(f"      gus run back {key} dev      ← roda backend em DEV")
    print(f"      gus run rat {key}           ← sobe tudo em PROD (wt)")
    print(f"      gus help                     ← lista todos os projetos e comandos")
    print(f"")
    print(f"      (se ainda nao configurado: adicione ao `$PROFILE)")
    print(f"       . C:\\Workspace\\gus-factory\\helms\\gus.ps1")


if __name__ == "__main__":
    main()
