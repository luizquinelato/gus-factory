#!/usr/bin/env python3
"""
scripts/setup_venvs.py — GLOBAL (workspace-level)
==================================================
Orchestrates venv setup across ALL projects in helms/ports.yml.
Delegates entirely to each project's own scripts/setup_envs.py,
which knows how to handle its specific structure (service dirs or
requirements files).

Usage:
    python scripts/setup_venvs.py                                         # all projects, all services
    python scripts/setup_venvs.py --project saas-blueprint-v1            # one project, all services
    python scripts/setup_venvs.py --project pulse --backend              # backend only
    python scripts/setup_venvs.py --project pulse --auth                 # auth only
    python scripts/setup_venvs.py --project pulse --frontend             # frontend only
    python scripts/setup_venvs.py --project pulse --frontend-etl         # frontend-etl only
    python scripts/setup_venvs.py --project pulse --backend --frontend   # backend + frontend
    python scripts/setup_venvs.py --force                                # recreate all venvs
    python scripts/setup_venvs.py --project pulse --backend -f           # backend venv recreated
"""
import argparse
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌  PyYAML não encontrado. Execute: pip install pyyaml")
    sys.exit(1)

WORKSPACE = Path(__file__).resolve().parent.parent
PORTS_YML = WORKSPACE / "helms" / "ports.yml"

# ── Cores ANSI ────────────────────────────────────────────────────────────────
RED, GREEN, YELLOW, RESET = "\033[31m", "\033[32m", "\033[33m", "\033[0m"
DIM = "\033[2m"


# ── Carregar ports.yml ────────────────────────────────────────────────────────

def load_projects() -> dict[str, dict]:
    """Read helms/ports.yml → {project_key: data_dict}."""
    data = yaml.safe_load(PORTS_YML.read_text(encoding="utf-8"))
    return {k: v for k, v in data.get("projects", {}).items()}


def resolve_project(token: str, projects: dict[str, dict]) -> tuple[str, dict]:
    """Resolve chave ou alias → (key, data). Levanta SystemExit se não encontrar."""
    token = token.strip().lower()
    if token in projects:
        return token, projects[token]
    for key, data in projects.items():
        if str(data.get("alias", "")).lower() == token:
            return key, data
    valid = ", ".join(
        f"{k}" + (f" ({d['alias']})" if d.get("alias") else "")
        for k, d in projects.items()
    )
    print(f"{RED}❌  Projeto '{token}' não encontrado.{RESET}")
    print(f"   Projetos disponíveis: {valid}")
    sys.exit(1)


# ── Banner ────────────────────────────────────────────────────────────────────

def _proj_banner(proj_key: str, proj_root: Path) -> str:
    """Imprime header amarelo. Retorna a barra de fechamento para imprimir após o bloco."""
    dashes = "─" * 18
    bar    = "─" * (2 * 18 + 2 + len(proj_key))
    print(f"\n{YELLOW}{dashes} {proj_key} {dashes}{RESET}")
    print(f"{YELLOW}  root → {proj_root}{RESET}")
    print(f"{YELLOW}{bar}{RESET}")
    return f"{YELLOW}{bar}{RESET}"


# ── Setup ─────────────────────────────────────────────────────────────────────

def run_project_setup(proj_key: str, proj_data: dict, args: argparse.Namespace) -> bool:
    """Delegate to the project's scripts/setup_envs.py."""
    proj_root   = Path(proj_data["root"])
    setup_script = proj_root / "scripts" / "setup_envs.py"
    close = _proj_banner(proj_key, proj_root)

    if not proj_root.exists():
        print(f"  {YELLOW}⚠ pasta não encontrada — pulando ({proj_root}){RESET}")
        print(close)
        return False

    if not setup_script.exists():
        print(f"  {YELLOW}⚠ scripts/setup_envs.py não encontrado — pulando.{RESET}")
        print(close)
        return False

    cmd = [sys.executable, str(setup_script)]
    if args.backend:      cmd.append("--backend")
    if args.auth:         cmd.append("--auth")
    if args.frontend:     cmd.append("--frontend")
    if args.frontend_etl: cmd.append("--frontend-etl")
    if args.force:        cmd.append("--force")

    result = subprocess.run(cmd).returncode == 0
    print(close)
    return result


def main() -> None:
    projects = load_projects()

    parser = argparse.ArgumentParser(description="Global venv setup for all GUS projects.")
    parser.add_argument("--project",      metavar="PROJETO", help="Chave ou alias do projeto (ver helms/ports.yml)")
    parser.add_argument("--backend",      action="store_true", help="Setup backend only")
    parser.add_argument("--auth",         action="store_true", help="Setup auth only")
    parser.add_argument("--frontend",     action="store_true", help="Setup frontend only")
    parser.add_argument("--frontend-etl", action="store_true", dest="frontend_etl", help="Setup frontend-etl only")
    parser.add_argument("--force", "-f",  action="store_true", help="Recreate venvs")
    args = parser.parse_args()

    if args.project:
        key, data = resolve_project(args.project, projects)
        targets = {key: data}
    else:
        targets = projects

    print(f"🚀 Global venv setup — {len(targets)} project(s)")

    ok = sum(run_project_setup(k, v, args) for k, v in targets.items())

    print(f"\n{GREEN}✅ Done — {ok}/{len(targets)} projects ready.{RESET}")


if __name__ == "__main__":
    main()
