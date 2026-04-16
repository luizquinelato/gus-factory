#!/usr/bin/env python3
"""
scripts/clean_project.py — GLOBAL (workspace-level)
=====================================================
Remove artefatos gerados (pycache, node_modules) de um ou todos os projetos
registrados em helms/ports.yml. Aceita tanto a chave quanto o alias do projeto.

Uso:
    python scripts/clean_project.py <projeto>              # tudo (pycache + node_modules)
    python scripts/clean_project.py <projeto> --pycache    # só __pycache__
    python scripts/clean_project.py <projeto> --node       # só node_modules
    python scripts/clean_project.py <projeto> --npm-cache  # só npm cache global
    python scripts/clean_project.py --all                  # todos os projetos
    python scripts/clean_project.py --factory              # pycache da raiz (scripts/)
    python scripts/clean_project.py --all --factory        # tudo + raiz

Exemplos:
    python scripts/clean_project.py saas-blueprint-v1
    python scripts/clean_project.py blueprint
    python scripts/clean_project.py --all
    python scripts/clean_project.py blueprint --node
"""
from __future__ import annotations

import argparse
import shutil
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
RED, GREEN, YELLOW, CYAN, RESET = "\033[31m", "\033[32m", "\033[33m", "\033[36m", "\033[0m"
DIM = "\033[2m"


# ── Carregar ports.yml ────────────────────────────────────────────────────────

def _load_raw() -> dict:
    return yaml.safe_load(PORTS_YML.read_text(encoding="utf-8"))


def load_projects() -> dict[str, dict]:
    """Retorna {key: {root, alias, label, ...}} para todos os projetos."""
    raw = _load_raw()
    return {k: v for k, v in raw.get("projects", {}).items()}


def resolve_project(token: str, projects: dict[str, dict]) -> tuple[str, dict]:
    """Resolve chave ou alias → (key, data). Levanta SystemExit se não encontrar."""
    token = token.strip().lower()
    # exact key
    if token in projects:
        return token, projects[token]
    # alias
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

def _banner(key: str, root: Path) -> None:
    dashes = "─" * 18
    bar = "─" * (2 * 18 + 2 + len(key))
    print(f"\n{YELLOW}{dashes} {key} {dashes}{RESET}")
    print(f"{YELLOW}  root → {root}{RESET}")
    print(f"{YELLOW}{bar}{RESET}")


# ── Limpeza ───────────────────────────────────────────────────────────────────

def _rmdir(path: Path) -> bool:
    """Remove diretório e retorna True se removido."""
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
        print(f"  {RED}✗{RESET} {DIM}{path}{RESET}")
        return True
    return False


def clean_pycache(root: Path) -> int:
    """Remove todos os __pycache__ dentro de root. Retorna a contagem."""
    targets = list(root.rglob("__pycache__"))
    count = sum(_rmdir(p) for p in targets)
    if count == 0:
        print(f"  {DIM}nenhum __pycache__ encontrado{RESET}")
    return count


def clean_node_modules(root: Path) -> int:
    """Remove todos os node_modules dentro de root. Retorna a contagem."""
    targets = list(root.rglob("node_modules"))
    # não descer dentro de node_modules ao procurar
    seen: set[Path] = set()
    top_level: list[Path] = []
    for p in sorted(targets):
        if not any(p.is_relative_to(s) for s in seen):
            top_level.append(p)
            seen.add(p)
    count = sum(_rmdir(p) for p in top_level)
    if count == 0:
        print(f"  {DIM}nenhum node_modules encontrado{RESET}")
    return count


def clean_npm_cache() -> None:
    """Executa npm cache clean --force globalmente."""
    print(f"  {CYAN}→ npm cache clean --force{RESET}")
    result = subprocess.run(["npm", "cache", "clean", "--force"],
                            capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  {GREEN}✔ npm cache limpo{RESET}")
    else:
        print(f"  {RED}⚠ npm cache clean falhou:{RESET} {result.stderr.strip()}")


def clean_factory_pycache() -> None:
    """Remove __pycache__ na raiz da factory (scripts/)."""
    print(f"\n{YELLOW}─── factory (raiz) ───{RESET}")
    count = clean_pycache(WORKSPACE / "scripts")
    print(f"  {GREEN}✔ {count} __pycache__ removidos (factory){RESET}")


# ── Main ──────────────────────────────────────────────────────────────────────

def clean_one(key: str, data: dict, args: argparse.Namespace) -> None:
    root = Path(data["root"])
    _banner(key, root)

    if not root.exists():
        print(f"  {YELLOW}⚠ pasta não encontrada — pulando ({root}){RESET}")
        return

    do_all = not args.pycache and not args.node and not args.npm_cache

    if do_all or args.pycache:
        count = clean_pycache(root)
        print(f"  {GREEN}✔ {count} __pycache__ removidos{RESET}")

    if do_all or args.node:
        count = clean_node_modules(root)
        print(f"  {GREEN}✔ {count} node_modules removidos{RESET}")

    if args.npm_cache:
        clean_npm_cache()


def main() -> None:
    projects = load_projects()
    keys_and_aliases = list(projects) + [
        d["alias"] for d in projects.values() if d.get("alias")
    ]

    parser = argparse.ArgumentParser(
        description="Limpa artefatos gerados (pycache, node_modules) por projeto.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("project", nargs="?", metavar="PROJETO",
                        help="Chave ou alias do projeto (ver helms/ports.yml)")
    parser.add_argument("--all",       action="store_true", help="Limpa todos os projetos")
    parser.add_argument("--factory",   action="store_true", help="Limpa __pycache__ da raiz (scripts/)")
    parser.add_argument("--pycache",   action="store_true", help="Remove só __pycache__")
    parser.add_argument("--node",      action="store_true", help="Remove só node_modules")
    parser.add_argument("--npm-cache", action="store_true", dest="npm_cache",
                        help="Executa npm cache clean --force")
    args = parser.parse_args()

    if not args.project and not args.all and not args.factory:
        parser.print_help()
        sys.exit(0)

    targets: dict[str, dict] = {}
    if args.all:
        targets = projects
    elif args.project:
        key, data = resolve_project(args.project, projects)
        targets = {key: data}

    for key, data in targets.items():
        clean_one(key, data, args)

    if args.all or args.factory:
        clean_factory_pycache()

    print(f"\n{GREEN}✅ Limpeza concluída.{RESET}\n")


if __name__ == "__main__":
    main()
