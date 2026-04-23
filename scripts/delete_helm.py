#!/usr/bin/env python3
"""
scripts/delete_helm.py
======================
Remove um projeto da configuração central (`helms/ports.yml`):
  - entrada em `projects[<key>]`
  - todas as ocorrências do projeto em `shared_services[*]`
  - referências a `<key>` em `conflicts_with` de outros projetos

O CLI `helms/gus.ps1` lê projetos dinamicamente de ports.yml — removido daqui,
o projeto desaparece do `gus help` automaticamente.

Por padrão NÃO toca nos arquivos do projeto. Com `--force`, também apaga
recursivamente o diretório indicado em `projects[<key>].root`.

Uso:
    python scripts/delete_helm.py <chave|alias>
    python scripts/delete_helm.py <chave|alias> --force
"""
from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌  PyYAML não encontrado. Execute: pip install pyyaml")
    sys.exit(1)

# ── Cores ANSI ────────────────────────────────────────────────────────────────
RED, GREEN, YELLOW, RESET = "\033[31m", "\033[32m", "\033[33m", "\033[0m"
DIM = "\033[2m"


class _InlineDict(dict):
    """Marker: serializado como {port: N, project: k} em uma única linha."""


class _PortsDumper(yaml.Dumper):
    pass


_PortsDumper.add_representer(
    _InlineDict,
    lambda d, v: d.represent_mapping("tag:yaml.org,2002:map", v.items(), flow_style=True),
)


ROOT       = Path(__file__).parent.parent
PORTS_FILE = ROOT / "helms" / "ports.yml"


def fast_rmtree(path: Path) -> None:
    """Remove uma árvore de diretórios usando o método nativo mais rápido do SO.

    No Windows, `shutil.rmtree` é ordens de magnitude mais lento que `rmdir /s /q`
    em projetos com `node_modules` (dezenas de milhares de arquivos), porque
    percorre Python-side file-by-file. O `cmd /c rmdir` despacha a recursão para
    o kernel em batch. Fora do Windows mantém `shutil.rmtree` (igualmente rápido
    em ext4/APFS).
    """
    if os.name == "nt":
        # /s = recursivo, /q = sem prompts. cmd /c para resolver o built-in rmdir.
        subprocess.run(
            ["cmd", "/c", "rmdir", "/s", "/q", str(path)],
            check=True,
        )
    else:
        shutil.rmtree(path)


# ── Helpers ──────────────────────────────────────────────────────────────────

def yesno(label: str, default: bool = True) -> bool:
    enter_hint = "↵=S" if default else "↵=N"
    val = input(f"  {label} [S/N  {enter_hint}]: ").strip().lower()
    if not val:
        return default
    return val in ("s", "sim", "y", "yes")


def load_ports() -> dict:
    with open(PORTS_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_project(token: str, projects: dict) -> tuple[str, dict]:
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


def save_ports(data: dict) -> None:
    out = dict(data)
    if "shared_services" in out:
        out["shared_services"] = {
            svc: [_InlineDict(e) for e in entries]
            for svc, entries in out["shared_services"].items()
        }
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
                    p[env] = e
            if "extra_ports" in p:
                p["extra_ports"] = [_InlineDict(ep) for ep in p["extra_ports"]]
            compacted[key] = p
        out["projects"] = compacted
    with open(PORTS_FILE, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(out, f, allow_unicode=True, sort_keys=False,
                  default_flow_style=False, Dumper=_PortsDumper)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove um projeto da configuração central (helms/ports.yml)."
    )
    parser.add_argument("project", metavar="PROJETO",
                        help="Chave ou alias do projeto (ver helms/ports.yml)")
    parser.add_argument("--force", action="store_true",
                        help="Também apaga recursivamente o diretório do projeto (root). Requer confirmação extra.")
    args = parser.parse_args()

    data     = load_ports()
    projects = data.get("projects", {})
    key, proj = resolve_project(args.project, projects)

    prod     = proj.get("prod") or {}
    prod_svc = prod.get("svc") or {}
    prod_db  = prod.get("db")  or {}
    root_str = proj.get("root", "") or ""
    root_path = Path(root_str) if root_str else None

    dashes = "─" * 18
    bar    = "─" * (2 * 18 + 2 + len(key))
    print(f"\n{YELLOW}{dashes} {key} {dashes}{RESET}")
    print(f"{YELLOW}  root → {root_str}{RESET}")
    print(f"{YELLOW}{bar}{RESET}")
    print(f"\n  Projeto : {key}  {DIM}({proj.get('label', '')}){RESET}")
    print(f"  PROD    : backend={prod_svc.get('backend','-')}  auth={prod_svc.get('auth','-')}  "
          f"frontend={prod_svc.get('frontend','-')}  db={prod_db.get('port','-')}")
    print(f"\n  {YELLOW}Será removido de:{RESET}")
    print(f"    • helms/ports.yml  (projects + shared_services + conflicts_with)")
    if args.force:
        exists_note = "" if (root_path and root_path.exists()) else f"  {DIM}(não existe){RESET}"
        print(f"    • {RED}{root_str}{RESET}  {RED}(--force: apaga recursivamente){RESET}{exists_note}")
    else:
        print(f"\n  {YELLOW}NÃO será removido:{RESET}")
        print(f"    • {root_str}  (arquivos do projeto intactos)")

    if not yesno(f"\nConfirmar remoção de '{key}'?"):
        print("Cancelado.")
        sys.exit(0)

    if args.force and root_path and root_path.exists():
        print(f"\n  {RED}⚠  --force apagará {root_path} de forma irreversível.{RESET}")
        typed = input(f"  Digite '{key}' para confirmar: ").strip()
        if typed != key:
            print("Cancelado (confirmação não confere).")
            sys.exit(0)

    print()

    # 1. ports.yml — remove projeto, limpa shared_services e conflicts_with
    del data["projects"][key]

    shared = data.get("shared_services", {})
    freed: list[str] = []
    for svc_name, entries in list(shared.items()):
        before = len(entries)
        shared[svc_name] = [e for e in entries if e.get("project") != key]
        released = before - len(shared[svc_name])
        if released:
            freed.extend(
                f"{svc_name}:{e['port']}"
                for e in entries
                if e.get("project") == key
            )
        if not shared[svc_name]:
            del shared[svc_name]

    conflicts_cleaned: list[str] = []
    for other_key, other_proj in data.get("projects", {}).items():
        cw = other_proj.get("conflicts_with") or []
        if key in cw:
            other_proj["conflicts_with"] = [c for c in cw if c != key]
            conflicts_cleaned.append(other_key)

    save_ports(data)
    freed_msg = f" {DIM}(liberou: {', '.join(freed)}){RESET}" if freed else ""
    print(f"  {GREEN}✔{RESET} helms/ports.yml — '{key}' removido{freed_msg}")
    if conflicts_cleaned:
        print(f"  {GREEN}✔{RESET} conflicts_with limpo em: {', '.join(conflicts_cleaned)}")

    # 2. --force: apaga o diretório do projeto (se existir)
    if args.force and root_path:
        if root_path.exists():
            print(f"  {DIM}… apagando {root_path} (pode levar alguns segundos){RESET}")
            try:
                fast_rmtree(root_path)
                print(f"  {GREEN}✔{RESET} {root_path} — diretório apagado")
            except Exception as exc:
                print(f"  {RED}✗{RESET} falha ao apagar {root_path}: {exc}")
                sys.exit(1)
        else:
            print(f"  {DIM}• {root_path} — não existe, nada a apagar{RESET}")

    print(f"\n{GREEN}✅ '{key}' removido da configuração central.{RESET}")
    if not (args.force and root_path and not root_path.exists()):
        if not args.force:
            print(f"   Arquivos do projeto permanecem intactos em: {root_str}")
            print(f"   Para deletar também os arquivos:")
            print(f"     {DIM}python scripts/delete_helm.py {key} --force{RESET}")


if __name__ == "__main__":
    main()
