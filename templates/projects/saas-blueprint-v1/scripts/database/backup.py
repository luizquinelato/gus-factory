#!/usr/bin/env python3
"""
scripts/database/backup.py — Database Backup
=============================================
Cria um dump pg_dump do banco PROD ou DEV.

Uso (da raiz do projeto):
    python scripts/database/backup.py --prod [--sql]
    python scripts/database/backup.py --dev  [--sql]

Saída: backups/{alias}_{prod|dev}_{timestamp}.backup
       backups/{alias}_{prod|dev}_{timestamp}.sql   (somente com --sql)
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# scripts/database/backup.py → scripts/database/ → scripts/ → project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKUPS_DIR  = PROJECT_ROOT / "backups"

RED    = "\033[31m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
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


def run_dump(container: str, user: str, password: str, db: str,
             out: Path, fmt: str) -> None:
    tmp   = f"/tmp/gus_bkp.{'dump' if fmt == 'c' else 'sql'}"
    r = subprocess.run([
        "docker", "exec", "-e", f"PGPASSWORD={password}", container,
        "pg_dump", "-U", user, "-d", db, f"-F{fmt}", "-f", tmp,
    ])
    if r.returncode != 0:
        print(f"{RED}❌  pg_dump falhou (código {r.returncode}).{RESET}")
        sys.exit(1)
    subprocess.run(["docker", "cp", f"{container}:{tmp}", str(out)], check=True)
    subprocess.run(["docker", "exec", container, "rm", tmp], capture_output=True)
    size_kb = out.stat().st_size // 1024
    print(f"  {GREEN}✔{RESET}  {out.name}  {DIM}({size_kb} KB){RESET}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Backup do banco de dados (PROD ou DEV)")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--prod", action="store_true", help="Backup do banco PROD")
    grp.add_argument("--dev",  action="store_true", help="Backup do banco DEV")
    ap.add_argument("--sql",   action="store_true", help="Também gera .sql (texto plano)")
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
    print(f"{YELLOW}[backup] {label}  db={db}  container={container}{RESET}")
    print(f"{YELLOW}{bar}{RESET}\n")

    check_container(container)
    BACKUPS_DIR.mkdir(exist_ok=True)

    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    stem = f"{alias}_{env}_{ts}"

    print(f"📦  Custom format (.backup) ...")
    run_dump(container, user, password, db, BACKUPS_DIR / f"{stem}.backup", "c")

    if args.sql:
        print(f"📄  SQL format (.sql) ...")
        run_dump(container, user, password, db, BACKUPS_DIR / f"{stem}.sql", "p")

    print(f"\n{GREEN}✅  Backup concluído!{RESET}")
    print(f"   {DIM}{BACKUPS_DIR / stem}.backup{RESET}\n")


if __name__ == "__main__":
    main()
