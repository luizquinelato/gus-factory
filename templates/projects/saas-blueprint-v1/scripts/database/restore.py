#!/usr/bin/env python3
"""
scripts/database/restore.py — Database Restore
===============================================
Restaura um .backup no banco PROD ou DEV.
Usa --no-owner --no-acl para restaures cross-env seguros (ex: PROD → DEV).

Uso (da raiz do projeto):
    python scripts/database/restore.py --prod [arquivo.backup]
    python scripts/database/restore.py --dev  [arquivo.backup]

Sem arquivo: exibe lista interativa de todos os backups em backups/*.backup.
"""
import argparse
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKUPS_DIR  = PROJECT_ROOT / "backups"

RED    = "\033[31m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_env(path: Path) -> dict:
    result: dict = {}
    if not path.exists():
        return result
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def load_env(env: str) -> dict:
    path = PROJECT_ROOT / f".env.{env}"
    if not path.exists():
        print(f"{RED}❌  {path} não encontrado.{RESET}")
        sys.exit(1)
    data = _parse_env(path)
    print(f"{DIM}   config: {path}{RESET}")
    return data


def get_alias(override: str) -> str:
    if override:
        return override
    return PROJECT_ROOT.name.removeprefix("gus-")


def check_container(container: str) -> None:
    r = subprocess.run(
        ["docker", "ps", "--filter", f"name={container}", "--format", "{{.Names}}"],
        capture_output=True, text=True,
    )
    if container not in r.stdout.split():
        print(f"{RED}❌  Container '{container}' não está rodando.{RESET}")
        print(f"{DIM}   Inicie o banco com: gus dkup <projeto>{RESET}")
        sys.exit(1)


def _env_tag_from_name(stem: str) -> str:
    """Extract 'prod' or 'dev' from backup filename stem (alias_prod_ts or alias_dev_ts)."""
    for part in stem.split("_"):
        if part in ("prod", "dev"):
            return part
    return ""


def list_and_pick() -> Path:
    if not BACKUPS_DIR.exists():
        print(f"{YELLOW}⚠️   Pasta backups/ não encontrada.{RESET}")
        sys.exit(1)
    files = sorted(BACKUPS_DIR.glob("*.backup"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print(f"{YELLOW}⚠️   Nenhum .backup encontrado em backups/{RESET}")
        sys.exit(1)
    print(f"  Backups disponíveis:\n")
    for i, f in enumerate(files, 1):
        tag  = _env_tag_from_name(f.stem)
        color = CYAN if tag == "dev" else YELLOW
        label = f"  [{color}{tag.upper()}{RESET}]" if tag else ""
        size_kb = f.stat().st_size // 1024
        print(f"  [{BOLD}{i}{RESET}]  {f.name}{label}  {DIM}{size_kb} KB{RESET}")
    print()
    raw = input("  Número do backup (0 = cancelar): ").strip()
    if not raw or raw == "0":
        print("  Cancelado.")
        sys.exit(0)
    try:
        idx = int(raw) - 1
        if not (0 <= idx < len(files)):
            raise ValueError
    except ValueError:
        print(f"{RED}❌  Escolha inválida.{RESET}")
        sys.exit(1)
    return files[idx]


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Restaura backup no banco (PROD ou DEV)")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--prod", action="store_true", help="Restaurar no banco PROD")
    grp.add_argument("--dev",  action="store_true", help="Restaurar no banco DEV")
    ap.add_argument("file",  nargs="?", help="Arquivo .backup (opcional)")
    ap.add_argument("--alias", default="", help="Alias do projeto (padrão: nome da pasta)")
    args = ap.parse_args()

    env       = "dev" if args.dev else "prod"
    alias     = get_alias(args.alias)
    cfg       = load_env(env)
    user      = cfg.get("POSTGRES_USER",     alias)
    password  = cfg.get("POSTGRES_PASSWORD", alias)
    db        = cfg.get("POSTGRES_DATABASE", alias if env == "prod" else f"{alias}_dev")
    container = f"{alias}-postgres{'-dev' if env == 'dev' else ''}"
    label     = env.upper()

    dashes = "─" * 20
    bar    = "─" * (2 * 20 + 2 + len(alias))
    print(f"\n{YELLOW}{dashes} {alias} {dashes}{RESET}")
    print(f"{YELLOW}[restore] → {label}  db={db}  container={container}{RESET}")
    print(f"{YELLOW}{bar}{RESET}\n")

    check_container(container)

    if args.file:
        backup = Path(args.file)
        if not backup.is_absolute():
            backup = PROJECT_ROOT / backup
        if not backup.exists():
            print(f"{RED}❌  Arquivo não encontrado: {backup}{RESET}")
            sys.exit(1)
    else:
        backup = list_and_pick()

    src_env = _env_tag_from_name(backup.stem)
    if src_env and src_env != env:
        print(f"\n{YELLOW}⚠️   Cross-env: backup de {src_env.upper()} → restaurando em {label}{RESET}")

    print(f"\n  {BOLD}Backup:{RESET}  {backup.name}")
    print(f"  {BOLD}Destino:{RESET} {db} ({label})\n")
    print(f"  {RED}⚠️   Todo o conteúdo atual do banco será substituído!{RESET}\n")
    raw = input(f"  Digite '{alias}' para confirmar: ").strip()
    if raw != alias:
        print("  Cancelado.")
        sys.exit(0)

    print(f"\n{DIM}[1/4] Copiando backup para o container...{RESET}")
    subprocess.run(["docker", "cp", str(backup), f"{container}:/tmp/gus_restore.backup"], check=True)

    print(f"{DIM}[2/4] Encerrando conexões ativas em {db}...{RESET}")
    subprocess.run([
        "docker", "exec", "-e", f"PGPASSWORD={password}", container,
        "psql", "-U", user, "-d", "postgres", "-c",
        f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='{db}' AND pid<>pg_backend_pid();",
    ], capture_output=True)

    print(f"{DIM}[3/4] Recriando banco {db}...{RESET}")
    for stmt in (f'DROP DATABASE IF EXISTS "{db}";', f'CREATE DATABASE "{db}";'):
        subprocess.run([
            "docker", "exec", "-e", f"PGPASSWORD={password}", container,
            "psql", "-U", user, "-d", "postgres", "-c", stmt,
        ], check=True, capture_output=True)

    print(f"{DIM}[4/4] Restaurando (--no-owner --no-acl)...{RESET}")
    r = subprocess.run([
        "docker", "exec", "-e", f"PGPASSWORD={password}", container,
        "pg_restore", "-U", user, "-d", db, "--no-owner", "--no-acl",
        "/tmp/gus_restore.backup",
    ])
    subprocess.run(["docker", "exec", container, "rm", "/tmp/gus_restore.backup"], capture_output=True)

    if r.returncode not in (0, 1):   # pg_restore retorna 1 para warnings
        print(f"{RED}❌  pg_restore falhou (código {r.returncode}).{RESET}")
        sys.exit(1)

    print(f"\n{GREEN}✅  Restore concluído!{RESET}")
    print(f"   {DIM}{backup.name} → {db} ({label}){RESET}\n")


if __name__ == "__main__":
    main()
