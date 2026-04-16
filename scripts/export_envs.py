#!/usr/bin/env python3
"""
scripts/export_envs.py — GLOBAL (workspace-level)
==================================================
Empacota todos os arquivos .env de todos os projetos registrados em
helms/ports.yml em um único .zip, mantendo a estrutura de pastas relativa
ao pai comum (C:\\Workspace). Basta descompactar lá para restaurar todos
os envs nos lugares corretos.

Arquivos incluídos:  .env  .env.dev  .env.prod  .env.local
                     .env.development  .env.production  .env.staging
Arquivos excluídos:  .env.example  .env.sample  .env.template

Uso:
    python scripts/export_envs.py                          # todos os projetos
    python scripts/export_envs.py --project blueprint      # só um (chave ou alias)
    python scripts/export_envs.py -o C:\\envs.zip          # caminho de saída
    python scripts/export_envs.py --dry-run                # lista sem zipar
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌  PyYAML não encontrado. Execute: pip install pyyaml")
    sys.exit(1)

WORKSPACE = Path(__file__).resolve().parent.parent          # gus-factory/
BASE      = WORKSPACE.parent                                # C:\Workspace
PORTS_YML = WORKSPACE / "helms" / "ports.yml"

# Padrões .env incluídos / excluídos
INCLUDE_NAMES = {".env", ".env.dev", ".env.prod", ".env.local",
                 ".env.development", ".env.production", ".env.staging"}
EXCLUDE_NAMES = {".env.example", ".env.sample", ".env.template"}
EXCLUDE_DIRS  = {"node_modules", ".venv", "venv", ".git", "__pycache__"}

# ── Cores ANSI ────────────────────────────────────────────────────────────────
RED, GREEN, YELLOW, CYAN, RESET = "\033[31m", "\033[32m", "\033[33m", "\033[36m", "\033[0m"
DIM = "\033[2m"


# ── ports.yml ─────────────────────────────────────────────────────────────────

def load_projects() -> dict[str, dict]:
    data = yaml.safe_load(PORTS_YML.read_text(encoding="utf-8"))
    return {k: v for k, v in data.get("projects", {}).items()}


def resolve_project(token: str, projects: dict[str, dict]) -> tuple[str, dict]:
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


# ── Coleta de .env ────────────────────────────────────────────────────────────

def _is_excluded_dir(path: Path) -> bool:
    return any(part in EXCLUDE_DIRS for part in path.parts)


def collect_envs(root: Path) -> list[Path]:
    """Retorna todos os .env válidos dentro de root, excluindo dirs ignorados."""
    found = []
    for p in root.rglob(".*"):
        if not p.is_file():
            continue
        if _is_excluded_dir(p.relative_to(root)):
            continue
        if p.name in INCLUDE_NAMES:
            found.append(p)
        # padrão .env.* não listado explicitamente — inclui se não excluído
        elif p.name.startswith(".env.") and p.name not in EXCLUDE_NAMES:
            found.append(p)
    return sorted(found)


# ── Banner ────────────────────────────────────────────────────────────────────

def _banner(key: str, root: Path) -> None:
    dashes = "─" * 18
    bar = "─" * (2 * 18 + 2 + len(key))
    print(f"\n{YELLOW}{dashes} {key} {dashes}{RESET}")
    print(f"{YELLOW}  root → {root}{RESET}")
    print(f"{YELLOW}{bar}{RESET}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    projects = load_projects()

    default_out = BASE / f"gus-envs-{date.today()}.zip"

    parser = argparse.ArgumentParser(
        description="Exporta todos os .env dos projetos para um .zip restaurável.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--project", "-p", metavar="PROJETO", nargs="+",
                        help="Chave(s) ou alias(es) do projeto — aceita múltiplos")
    parser.add_argument("--all", "-a", action="store_true",
                        help="Exporta todos os projetos")
    parser.add_argument("--output", "-o", metavar="CAMINHO", default=str(default_out),
                        help=f"Arquivo .zip de saída (padrão: {default_out.name})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Lista os arquivos sem gerar o .zip")
    args = parser.parse_args()

    if not args.project and not args.all:
        parser.print_help()
        sys.exit(0)

    if args.all:
        targets = projects
    else:
        targets = {}
        for token in args.project:
            key, data = resolve_project(token, projects)
            targets[key] = data

    out_path = Path(args.output)
    all_envs: list[tuple[Path, Path]] = []   # (abs_path, arcname)

    for key, data in targets.items():
        root = Path(data["root"])
        _banner(key, root)

        if not root.exists():
            print(f"  {YELLOW}⚠ pasta não encontrada — pulando{RESET}")
            continue

        envs = collect_envs(root)
        if not envs:
            print(f"  {DIM}nenhum .env encontrado{RESET}")
            continue

        for p in envs:
            try:
                arcname = p.relative_to(BASE)
            except ValueError:
                arcname = Path(key) / p.relative_to(root)
            print(f"  {GREEN}+{RESET} {DIM}{arcname}{RESET}")
            all_envs.append((p, arcname))

    print(f"\n  {CYAN}Total: {len(all_envs)} arquivo(s){RESET}")

    if not all_envs:
        print(f"{YELLOW}⚠ Nenhum .env encontrado. Zip não gerado.{RESET}\n")
        sys.exit(0)

    if args.dry_run:
        print(f"\n{YELLOW}⚠ --dry-run: zip não gerado.{RESET}\n")
        sys.exit(0)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for abs_path, arcname in all_envs:
            zf.write(abs_path, arcname)

    print(f"\n{GREEN}✅ Zip gerado:{RESET} {out_path}")
    print(f"   {DIM}Descompacte em {BASE} para restaurar todos os envs.{RESET}\n")


if __name__ == "__main__":
    main()
