#!/usr/bin/env python3
"""
scripts/switch_postgres_variant.py
==================================
Alterna a variante Postgres ativa de um blueprint ou projeto gerado.

Cada variante vive em `infra/postgres/variants/<nome>/` com os arquivos:
  - docker-compose.db.yml
  - docker-compose.db.dev.yml
  - 04-variant-init.sql   (opcional — extensions, shared_preload_libraries)

O script copia esses arquivos para a raiz do projeto e para
`infra/postgres/primary/` respectivamente, sobrescrevendo a variante anterior.

Variantes suportadas hoje:
  - regular   → postgres:18 (padrão, sem extension extra)
  - pgvector  → pgvector/pgvector:pg18-trixie (+ CREATE EXTENSION vector)

Uso:
    python scripts/switch_postgres_variant.py <regular|pgvector>
    python scripts/switch_postgres_variant.py pgvector --path C:\\Workspace\\gus-toba
"""
from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# ── Cores ANSI ────────────────────────────────────────────────────────────────
RED, GREEN, YELLOW, CYAN, RESET = "\033[31m", "\033[32m", "\033[33m", "\033[36m", "\033[0m"
DIM, BOLD = "\033[2m", "\033[1m"

ROOT = Path(__file__).parent.parent
DEFAULT_PATH = ROOT / "templates" / "projects" / "saas-blueprint-v1"

COMPOSE_FILES = ("docker-compose.db.yml", "docker-compose.db.dev.yml")
VARIANT_INIT = "04-variant-init.sql"
PRIMARY_SUBDIR = Path("infra") / "postgres" / "primary"
VARIANTS_SUBDIR = Path("infra") / "postgres" / "variants"


def die(msg: str) -> None:
    print(f"{RED}❌  {msg}{RESET}")
    sys.exit(1)


def list_variants(project_path: Path) -> list[str]:
    root = project_path / VARIANTS_SUBDIR
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir())


def detect_running_containers(project_path: Path) -> list[str]:
    """Retorna containers rodando cujo nome contém o nome do projeto."""
    project_name = project_path.name.replace("_", "-")
    try:
        res = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}", "--filter", f"name={project_name}"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if res.returncode != 0:
            return []
        return [n for n in res.stdout.strip().splitlines() if n]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def apply_variant_files(variant: str, project_path: Path, verbose: bool = True) -> None:
    """Copia os arquivos da variante para as posições "ativas" do projeto.

    IO puro — sem prompts, sem inspeção de containers. Reutilizada por
    `create_project.py` imediatamente após o clone do template.

    Raises ValueError se a variante não existir ou estiver incompleta.
    """
    variants_root = project_path / VARIANTS_SUBDIR
    variant_dir   = variants_root / variant

    if not variant_dir.is_dir():
        available = list_variants(project_path)
        raise ValueError(
            f"variante '{variant}' não encontrada em {variants_root} "
            f"(disponíveis: {', '.join(available) if available else '(nenhuma)'})"
        )

    missing = [f for f in COMPOSE_FILES if not (variant_dir / f).is_file()]
    if missing:
        raise ValueError(f"variante '{variant}' está incompleta — faltam: {', '.join(missing)}")

    # 1) Composes → raiz do projeto
    for name in COMPOSE_FILES:
        shutil.copy2(variant_dir / name, project_path / name)
        if verbose:
            print(f"  {GREEN}✓{RESET} {name}  {DIM}← {variant}/{RESET}")

    # 2) 04-variant-init.sql → primary/ (ou removido se a variante não tiver)
    primary_dir  = project_path / PRIMARY_SUBDIR
    active_init  = primary_dir / VARIANT_INIT
    variant_init = variant_dir / VARIANT_INIT
    if variant_init.is_file():
        shutil.copy2(variant_init, active_init)
        if verbose:
            print(f"  {GREEN}✓{RESET} {PRIMARY_SUBDIR / VARIANT_INIT}  {DIM}← {variant}/{RESET}")
    elif active_init.is_file():
        active_init.unlink()
        if verbose:
            print(f"  {YELLOW}✗{RESET} {PRIMARY_SUBDIR / VARIANT_INIT}  {DIM}(removido — variante sem extensions){RESET}")


def apply_variant(variant: str, project_path: Path, force: bool) -> None:
    # Aviso se há containers do projeto rodando (interativo)
    running = detect_running_containers(project_path)
    if running and not force:
        print(f"{YELLOW}⚠️  Containers em execução detectados para este projeto:{RESET}")
        for n in running:
            print(f"   {DIM}• {n}{RESET}")
        print(f"\n{YELLOW}Trocar de variante com volumes antigos pode quebrar o startup{RESET}")
        print(f"{YELLOW}(extensions incompatíveis, binários diferentes).{RESET}")
        print(f"{DIM}Recomendado: `docker compose -f docker-compose.db.yml down -v` antes.{RESET}")
        ans = input(f"\n  Continuar mesmo assim? [s/N]: ").strip().lower()
        if ans not in ("s", "y", "sim", "yes"):
            print(f"{DIM}Cancelado.{RESET}")
            sys.exit(0)

    try:
        apply_variant_files(variant, project_path, verbose=True)
    except ValueError as e:
        die(str(e))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Alterna a variante Postgres ativa de um projeto.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("variant", nargs="?", help="regular | pgvector")
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH,
                        help=f"pasta raiz do projeto (default: {DEFAULT_PATH.relative_to(ROOT)})")
    parser.add_argument("--force", action="store_true",
                        help="não pede confirmação se há containers rodando")
    parser.add_argument("--list", action="store_true",
                        help="lista variantes disponíveis e sai")
    args = parser.parse_args()

    project_path = args.path.resolve()
    if not project_path.is_dir():
        die(f"pasta não existe: {project_path}")

    available = list_variants(project_path)
    if not available:
        die(f"nenhuma variante encontrada em {project_path / VARIANTS_SUBDIR}")

    if args.list or not args.variant:
        print(f"{BOLD}Variantes disponíveis em{RESET} {DIM}{project_path}{RESET}:")
        for v in available:
            print(f"  {CYAN}•{RESET} {v}")
        sys.exit(0)

    if args.variant not in available:
        die(f"variante desconhecida: {args.variant}\n    disponíveis: {', '.join(available)}")

    print(f"{BOLD}Aplicando variante{RESET} {CYAN}{args.variant}{RESET} {DIM}em {project_path}{RESET}\n")
    apply_variant(args.variant, project_path, force=args.force)
    print(f"\n{GREEN}✓ Variante ativa:{RESET} {BOLD}{args.variant}{RESET}")


if __name__ == "__main__":
    main()
