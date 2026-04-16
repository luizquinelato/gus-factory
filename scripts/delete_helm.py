#!/usr/bin/env python3
"""
scripts/delete_helm.py
======================
Remove um projeto dos arquivos de configuração centralizados:
  - helms/ports.yml          (entrada do projeto)
  - helms/powershell_profile.ps1  (seção, summary e linha de header)

NÃO toca em nenhum arquivo dentro de projects/<key>/.

Uso:
    python scripts/delete_helm.py <chave>
    python scripts/delete_helm.py plurus
"""
from __future__ import annotations
import argparse
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


ROOT         = Path(__file__).parent.parent
PORTS_FILE   = ROOT / "helms" / "ports.yml"
PROFILE_FILE = ROOT / "helms" / "powershell_profile.ps1"


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


# ── PS Profile removal ────────────────────────────────────────────────────────

def remove_from_profile(profile: str, k: str) -> tuple[str, list[str]]:
    """Remove seção, summary e header do projeto k. Retorna (profile_atualizado, itens_removidos)."""
    K    = k.upper()
    done = []

    # Seção principal — usa marcadores # START/END {key} para remoção cirúrgica
    start_marker = f"\n# START {k}\n"
    end_marker   = f"\n# END {k}\n"
    idx_s = profile.find(start_marker)
    if idx_s >= 0:
        idx_e = profile.find(end_marker, idx_s)
        if idx_e >= 0:
            profile = profile[:idx_s] + profile[idx_e + len(end_marker):]
            done.append("seção principal")

    # Bloco no SUMMARY
    sum_start = f'Write-Host "  [{K}]'
    idx_sum   = profile.find(sum_start)
    if idx_sum >= 0:
        close     = '\nWrite-Host ""\n'
        idx_close = profile.find(close, idx_sum)
        if idx_close >= 0:
            profile = profile[:idx_sum] + profile[idx_close + len(close):]
        # Decrement project count
        for n in range(50, 1, -1):
            if f"carregado — {n} projeto" in profile:
                profile = profile.replace(
                    f"carregado — {n} projeto", f"carregado — {n - 1} projeto", 1
                )
                break
        done.append("bloco do SUMMARY")

    # Linha de aliases no cabeçalho
    header_line = f"#   rat-{k} / rat-{k}-dev    dbm-{k} / dbm-{k}-dev    kill-{k}\n"
    if header_line in profile:
        profile = profile.replace(header_line, "")
        done.append("linha do cabeçalho")

    return profile, done


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove um projeto da configuração central (ports.yml + gus.ps1)."
    )
    parser.add_argument("project", metavar="PROJETO",
                        help="Chave ou alias do projeto (ver helms/ports.yml)")
    args = parser.parse_args()

    data     = load_ports()
    projects = data.get("projects", {})
    key, proj = resolve_project(args.project, projects)

    prod     = proj.get("prod") or {}
    prod_svc = prod.get("svc") or {}
    prod_db  = prod.get("db")  or {}

    dashes = "─" * 18
    bar    = "─" * (2 * 18 + 2 + len(key))
    print(f"\n{YELLOW}{dashes} {key} {dashes}{RESET}")
    print(f"{YELLOW}  root → {proj.get('root', '')}{RESET}")
    print(f"{YELLOW}{bar}{RESET}")
    print(f"\n  Projeto : {key}  {DIM}({proj.get('label', '')}){RESET}")
    print(f"  PROD    : backend={prod_svc.get('backend','-')}  auth={prod_svc.get('auth','-')}  "
          f"frontend={prod_svc.get('frontend','-')}  db={prod_db.get('port','-')}")
    print(f"\n  {YELLOW}Será removido de:{RESET}")
    print(f"    • helms/ports.yml")
    print(f"    • helms/gus.ps1")
    print(f"\n  {YELLOW}NÃO será removido:{RESET}")
    print(f"    • projects/{key}/  (arquivos intactos)")

    if not yesno(f"\nConfirmar remoção de '{key}'?"):
        print("Cancelado.")
        sys.exit(0)

    print()

    # 1. ports.yml — remove projeto e limpa shared_services
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

    save_ports(data)
    freed_msg = f" {DIM}(liberou: {', '.join(freed)}){RESET}" if freed else ""
    print(f"  {GREEN}✔{RESET} helms/ports.yml — '{key}' removido{freed_msg}")

    # 2. gus.ps1
    with open(PROFILE_FILE, encoding="utf-8") as f:
        content = f.read()
    content, removed = remove_from_profile(content, key)
    with open(PROFILE_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    if removed:
        print(f"  {GREEN}✔{RESET} helms/gus.ps1 — removido: {', '.join(removed)}")
    else:
        print(f"  {YELLOW}⚠{RESET} helms/gus.ps1 — nenhuma seção encontrada para '{key}'")

    print(f"\n{GREEN}✅ '{key}' removido da configuração central.{RESET}")
    print(f"   Arquivos em projects/{key}/ permanecem intactos.")
    print(f"   Para deletar também os arquivos:")
    print(f"     {DIM}Remove-Item -Recurse -Force projects\\{key}{RESET}")


if __name__ == "__main__":
    main()
