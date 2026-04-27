#!/usr/bin/env python3
"""
scripts/sync_docs.py
====================
Copia os documentos de  projects/<alias>/docs/
para dentro de          <project_root>/docs/base/

A pasta destino é criada automaticamente se não existir.
Arquivos existentes no destino são sobrescritos; arquivos que
não existem mais na origem NÃO são removidos (sync aditivo).

Uso:
    python scripts/sync_docs.py <chave|alias>
    python scripts/sync_docs.py <chave|alias> --dry-run
    python scripts/sync_docs.py <chave|alias> --en        # rules em inglês
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌  PyYAML não encontrado. Execute: pip install pyyaml")
    sys.exit(1)

# ── Cores ANSI ────────────────────────────────────────────────────────────────
RED, GREEN, YELLOW, CYAN, RESET = "\033[31m", "\033[32m", "\033[33m", "\033[36m", "\033[0m"
DIM, BOLD = "\033[2m", "\033[1m"

ROOT         = Path(__file__).parent.parent
PORTS_FILE   = ROOT / "helms" / "ports.yml"
PROJECTS_DIR = ROOT / "projects"
RULES_DIR    = ROOT / "templates" / "rules"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_ports() -> dict:
    return yaml.safe_load(PORTS_FILE.read_text(encoding="utf-8"))


def resolve_project(token: str, projects: dict) -> tuple[str, dict]:
    """Resolve chave ou alias → (key, data). Sai com erro se não encontrar."""
    token = token.strip().lower()
    if token in projects:
        return token, projects[token]
    for key, data in projects.items():
        if str(data.get("alias", "")).lower() == token:
            return key, data
    valid = ", ".join(
        k + (f" ({d['alias']})" if d.get("alias") else "")
        for k, d in projects.items()
    )
    print(f"{RED}❌  Projeto '{token}' não encontrado.{RESET}")
    print(f"   Disponíveis: {valid}")
    sys.exit(1)


# ── Core ──────────────────────────────────────────────────────────────────────

def _copy_tree(src: Path, dest: Path, dry_run: bool, label: str,
               exclude_dirs: set[str] | None = None) -> int:
    """Copia recursivamente src → dest. Retorna quantidade de arquivos copiados."""
    exclude_dirs = exclude_dirs or set()
    files = [
        f for f in sorted(src.rglob("*"))
        if f.is_file() and not any(p.name in exclude_dirs for p in f.parents)
    ]
    if not files:
        print(f"  {DIM}(nenhum arquivo em {src}){RESET}")
        return 0
    tag = f"{DIM}[dry-run]{RESET} " if dry_run else ""
    copied = 0
    for src_file in files:
        rel      = src_file.relative_to(src)
        dst_file = dest / rel
        if not dry_run:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
        status = f"{GREEN}✔{RESET}" if not dry_run else f"{YELLOW}~{RESET}"
        print(f"  {tag}{status} [{label}] {rel}")
        copied += 1
    return copied


def sync_docs(key: str, proj: dict, dry_run: bool = False, use_en: bool = False) -> None:
    alias      = proj.get("alias", key)
    root_str   = proj.get("root", "")
    if not root_str:
        print(f"{RED}❌  Projeto '{key}' não tem 'root' definido em ports.yml.{RESET}")
        sys.exit(1)

    src  = PROJECTS_DIR / alias / "docs"
    dest = Path(root_str) / "docs" / "base"

    if not src.exists():
        print(f"{YELLOW}⚠️   Pasta de origem não existe:{RESET} {src}")
        print(f"   Crie-a e coloque seus documentos antes de sincronizar.")
        sys.exit(1)

    # rules: pt-br direto em templates/rules/, en em templates/rules/en/
    rules_src  = RULES_DIR / "en" if use_en else RULES_DIR
    rules_dest = Path(root_str) / "docs" / "rules"
    lang_label = "en" if use_en else "pt-br"

    print(f"\n{BOLD}Sync docs{RESET} — {CYAN}{alias}{RESET}")
    print(f"  {DIM}Docs  origem :{RESET} {src}")
    print(f"  {DIM}Docs  destino:{RESET} {dest}")
    print(f"  {DIM}Rules origem :{RESET} {rules_src}  {DIM}({lang_label}){RESET}")
    print(f"  {DIM}Rules destino:{RESET} {rules_dest}")
    print()

    total = 0
    total += _copy_tree(src, dest, dry_run, "docs")
    # pt-br: exclui a subpasta en/ que fica dentro de templates/rules/
    rules_exclude = {"en"} if not use_en else set()
    total += _copy_tree(rules_src, rules_dest, dry_run, f"rules/{lang_label}", rules_exclude)

    noun = "arquivo" if total == 1 else "arquivos"
    if dry_run:
        print(f"\n{YELLOW}[dry-run]{RESET} {total} {noun} seriam copiados.")
    else:
        print(f"\n{GREEN}✅  {total} {noun} copiados.{RESET}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Copia projects/<alias>/docs/ → <project_root>/docs/base/"
    )
    ap.add_argument("project", metavar="PROJETO",
                    help="Chave ou alias do projeto (ver helms/ports.yml)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Simula a cópia sem alterar nada")
    ap.add_argument("--en", action="store_true",
                    help="Copia rules em inglês (templates/rules/en/) em vez de pt-br")
    args = ap.parse_args()

    data     = load_ports()
    projects = data.get("projects", {})
    key, proj = resolve_project(args.project, projects)

    sync_docs(key, proj, dry_run=args.dry_run, use_en=args.en)


if __name__ == "__main__":
    main()
