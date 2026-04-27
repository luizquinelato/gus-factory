#!/usr/bin/env python3
"""
scripts/create_project.py
==========================
Clona um template de `templates/projects/<template-key>/` para um novo projeto,
aplicando substituição textual (valores canônicos → valores do novo projeto),
processando marcadores `@IF feat / @ENDIF feat` e removendo paths de features
desligadas.

Fluxo:
  1. Lista templates (helms/ports.yml filtrado por `template: true`) e pergunta
     qual usar (ou lê `--template <key|alias>`).
  2. Carrega `template.yml` do blueprint escolhido.
  3. Coleta info do novo projeto (chave, nome, root, portas, features, etc.).
  4. Aloca portas/cor em `helms/ports.yml` sem colisão com projetos existentes.
  5. Clona a árvore do template para o destino:
       - respeita `ignore` globs
       - `no_substitute` globs → cópia binária
       - demais arquivos → substituição textual (identity map canônica→nova)
       - processa `@IF feat / @ENDIF feat`
       - remove paths listados em `features[f].removes_when_disabled`
  6. Atualiza `helms/ports.yml` (o CLI `helms/gus.ps1` lê projetos dinamicamente
     de ports.yml — não há mais injeção de aliases em profile).

Uso:
    python scripts/create_project.py [--template <key|alias>]

Convenção de portas (alocação automática, sem colisão com outros projetos):
  backend_prod  = próximo bloco múltiplo de 1000 (ex: 9000, 10000 …)
  auth_prod     = backend_prod + 100
  backend_dev   = backend_prod + 10
  auth_dev      = backend_prod + 110
  frontend_prod = próximo par livre 5175+
  frontend_dev  = frontend_prod + 1
  db_prod       = próximo bloco de 4 livre 5436+
  db_dev        = db_prod + 2
"""
from __future__ import annotations
import argparse
import fnmatch
import os
import re
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Instale PyYAML: pip install pyyaml")
    sys.exit(1)

# Reusa a lógica de cópia de kits de variante Postgres (IO puro, sem prompts)
from switch_postgres_variant import apply_variant_files  # noqa: E402


# ── Cores ANSI ───────────────────────────────────────────────────────────────
RED, GREEN, YELLOW, CYAN, RESET = "\033[31m", "\033[32m", "\033[33m", "\033[36m", "\033[0m"
DIM, BOLD = "\033[2m", "\033[1m"


# ── YAML helpers — entradas de shared_services em formato inline ─────────────
class _InlineDict(dict):
    """Marker: serializado como {port: N, project: k} em uma única linha."""


class _PortsDumper(yaml.Dumper):
    """Dumper customizado — _InlineDict usa flow_style=True."""


_PortsDumper.add_representer(
    _InlineDict,
    lambda d, v: d.represent_mapping("tag:yaml.org,2002:map", v.items(), flow_style=True),
)


ROOT                   = Path(__file__).parent.parent
PORTS_FILE             = ROOT / "helms" / "ports.yml"
TEMPLATES_PROJECTS_DIR = ROOT / "templates" / "projects"
PROJECTS_DIR           = ROOT / "projects"

# Paleta de cores PS — ordem de prioridade ao auto-atribuir (Cyan/Magenta/Yellow reservadas)
PS_COLORS = ["Green", "Blue", "Red", "DarkCyan", "DarkGreen", "Gray", "White"]

# Padrões de comentário aceitos para marcadores @IF / @ENDIF
# (cobre py/yml/sh com '#', js/ts/css com '//', jsx com '{/* */}', block comments com '/* */')
_IF_RE    = re.compile(r'^\s*(?:#|//|/\*|\{/\*)\s*@IF\s+([\w-]+)\s*(?:\*/\}|\*/)?\s*$')
_ENDIF_RE = re.compile(r'^\s*(?:#|//|/\*|\{/\*)\s*@ENDIF\s+([\w-]+)\s*(?:\*/\}|\*/)?\s*$')


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
        return f"{YELLOW}⚠ yml:{registered[port]}{RESET}"
    return f"{GREEN}livre{RESET}"


def next_clean_port(shared: dict, svc_keys: list[str], base: int, block: int,
                    extra_occupied: set[int] | None = None) -> int:
    """Retorna a menor porta N >= base tal que o bloco [N, N+block-1] não conflita
    com nenhuma porta registrada em qualquer uma das svc_keys informadas nem com
    `extra_occupied` (portas já alocadas nesta invocação mas ainda não persistidas
    em ports.yml).
    - svc_keys: todas as listas relacionadas ao serviço (ex: db_prod, db_dev,
      db_prod_replica…). Para extras que dividem o mesmo espaço de porta do host
      (qdrant http + grpc, redis prod + dev, rabbit amqp + mgmt), passe todos os
      buckets correlatos para evitar dupla alocação.
    - block: quantas portas o serviço reserva de uma vez (db=4, frontend=2, redis=1).
    """
    all_ports: set[int] = set(extra_occupied or ())
    for k in svc_keys:
        for e in shared.get(k, []):
            all_ports.add(e["port"])

    candidate = max(base, (max(all_ports) + 1) if all_ports else base)
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


def auto_pick_color(data: dict) -> str:
    used = {p.get("color") for p in data.get("projects", {}).values()}
    return next((c for c in PS_COLORS if c not in used), PS_COLORS[0])


# ═══════════════════════════════════════════════════════════════════════
# Template manifest — descobre templates disponíveis e carrega template.yml
# ═══════════════════════════════════════════════════════════════════════

def list_templates(data: dict) -> list[dict]:
    """Retorna templates disponíveis (entries em ports.yml com template: true)."""
    out = []
    for key, proj in data.get("projects", {}).items():
        if proj.get("template"):
            out.append({
                "key":   key,
                "alias": proj.get("alias", key),
                "label": proj.get("label", key),
                "root":  proj.get("root", str(TEMPLATES_PROJECTS_DIR / key)),
            })
    return out


def load_manifest(template_key: str) -> dict:
    """Carrega templates/projects/<template_key>/template.yml e valida schema."""
    path = TEMPLATES_PROJECTS_DIR / template_key / "template.yml"
    if not path.is_file():
        raise FileNotFoundError(f"template.yml não encontrado em {path}")
    with open(path, encoding="utf-8") as f:
        manifest = yaml.safe_load(f) or {}
    if manifest.get("schema_version") != 1:
        raise ValueError(f"{path}: schema_version incompatível (esperado 1)")
    for req in ("identity", "canonical_ports", "canonical_db"):
        if req not in manifest:
            raise ValueError(f"{path}: campo obrigatório ausente: {req}")
    manifest.setdefault("features", {})
    manifest.setdefault("ignore", [])
    manifest.setdefault("no_substitute", [])
    manifest.setdefault("canonical_timezone", "America/Sao_Paulo")
    return manifest


def pick_template(data: dict, cli_arg: str | None) -> tuple[str, dict]:
    """Seleciona template via flag CLI ou menu numerado. Retorna (key, manifest)."""
    templates = list_templates(data)
    if not templates:
        print(f"{RED}✗ Nenhum template encontrado em helms/ports.yml (template: true).{RESET}")
        sys.exit(1)

    if cli_arg:
        for t in templates:
            if cli_arg in (t["key"], t["alias"]):
                return t["key"], load_manifest(t["key"])
        print(f"{RED}✗ Template '{cli_arg}' não encontrado.{RESET} Disponíveis:")
        for t in templates:
            print(f"  {DIM}- {t['key']}  (alias: {t['alias']}){RESET}")
        sys.exit(1)

    print(f"\n{YELLOW}── Templates disponíveis ───────────────────────────────────{RESET}")
    for i, t in enumerate(templates, 1):
        print(f"  {CYAN}{i}.{RESET} {t['key']}  {DIM}(alias: {t['alias']}){RESET}")
        print(f"     {DIM}{t['label']}{RESET}")
    print()
    while True:
        val = input(f"  Escolha (1-{len(templates)}) ou alias: ").strip()
        if not val:
            continue
        if val.isdigit() and 1 <= int(val) <= len(templates):
            chosen = templates[int(val) - 1]
            return chosen["key"], load_manifest(chosen["key"])
        for t in templates:
            if val in (t["key"], t["alias"]):
                return t["key"], load_manifest(t["key"])
        print(f"  {RED}✗ Opção inválida.{RESET}")


# ═══════════════════════════════════════════════════════════════════════
# Identity map & substituição textual
# ═══════════════════════════════════════════════════════════════════════

def _derive_name_forms(key: str) -> tuple[str, str, str]:
    """Deriva (kebab, snake, label) a partir da chave do novo projeto."""
    kebab = key.replace("_", "-").lower()
    snake = key.replace("-", "_").lower()
    label = " ".join(w.capitalize() for w in re.split(r"[-_]+", key) if w)
    return kebab, snake, label


def build_identity_map(info: dict, manifest: dict) -> list[tuple[str, str, bool]]:
    """Constrói lista ordenada de substituições (old, new, use_word_boundary).
    Ordem importa: strings mais longas primeiro para evitar substring overlap.
    """
    ident   = manifest["identity"]
    cports  = manifest["canonical_ports"]
    cdb     = manifest["canonical_db"]
    ctz     = manifest["canonical_timezone"]
    p       = info["ports"]
    new_key = info["key"]
    kebab, snake, _ = _derive_name_forms(new_key)

    subs: list[tuple[str, str, bool]] = []

    # 1. Strings textuais — ordem: mais longas primeiro (db_dev antes de db)
    text_pairs = [
        (f"{ident['key_snake']}_dev",     f"{snake}_dev"),
        (cdb["name_dev"],                  info["db_name"] + "_dev"),
        (cdb["name_prod"],                 info["db_name"]),
        (ident["key_snake"],               snake),
        (ident["key"],                     kebab),
        (ident["name"],                    info["name"]),
        (cdb["user"],                      info["db_user"]),
        (cdb["password"],                  info["db_pass"]),
        (ctz,                              info["timezone"]),
    ]
    seen_src: set[str] = set()
    for old, new in sorted(text_pairs, key=lambda x: -len(x[0])):
        if old and old != new and old not in seen_src:
            subs.append((old, new, True))
            seen_src.add(old)

    # 2. Portas — ordem: mais dígitos primeiro (15675 antes de 5675)
    port_pairs: list[tuple[int, int | None]] = [
        (cports["backend_prod"],       p.get("backend_prod")),
        (cports["backend_dev"],        p.get("backend_dev")),
        (cports["auth_prod"],          p.get("auth_prod")),
        (cports["auth_dev"],           p.get("auth_dev")),
        (cports["frontend_prod"],      p.get("frontend_prod")),
        (cports["frontend_dev"],       p.get("frontend_dev")),
        (cports["etl_frontend_prod"],  p.get("etl_frontend_prod")),
        (cports["etl_frontend_dev"],   p.get("etl_frontend_dev")),
        (cports["db_prod"],            p.get("db_prod")),
        (cports["db_dev"],             p.get("db_dev")),
        (cports["db_prod_replica"],    p.get("db_prod_replica")),
        (cports["db_dev_replica"],     p.get("db_dev_replica")),
        (cports["redis_prod"],         p.get("redis_prod")),
        (cports["redis_dev"],          p.get("redis_dev")),
        (cports["rabbitmq_amqp_prod"], p.get("rabbitmq_amqp_prod")),
        (cports["rabbitmq_amqp_dev"],  p.get("rabbitmq_amqp_dev")),
        (cports["rabbitmq_mgmt_prod"], p.get("rabbitmq_mgmt_prod")),
        (cports["rabbitmq_mgmt_dev"],  p.get("rabbitmq_mgmt_dev")),
        (cports["qdrant_prod"],        p.get("qdrant_prod")),
        (cports["qdrant_dev"],         p.get("qdrant_dev")),
        (cports["qdrant_grpc_prod"],   p.get("qdrant_grpc_prod")),
        (cports["qdrant_grpc_dev"],    p.get("qdrant_grpc_dev")),
    ]
    seen_ports: set[int] = set()
    for old, new in sorted(port_pairs, key=lambda x: -len(str(x[0]))):
        if new is None or old == new or old in seen_ports:
            continue
        subs.append((str(old), str(new), False))  # port: usa lookaround de dígito
        seen_ports.add(old)

    return subs


def substitute_in_text(content: str, subs: list[tuple[str, str, bool]]) -> str:
    """Aplica substituições em **passada única** (single-pass) para evitar cascata
    quando o `new` de um par é igual ao `old` de outro. Ex.: com subs sequenciais
    `6343→6344` seguido de `6344→6345`, o `6343` acabaria virando `6345`. Com a
    passada única, cada posição só é substituída uma vez pelo alvo correto.

    Duas passadas independentes (uma para identificadores, uma para portas), cada
    uma com uma regex de alternação combinada ordenada por tamanho decrescente
    (preferência ao match mais longo, ex.: `saas_blueprint_v1_dev` antes de
    `saas_blueprint_v1`). O lookaround alfanum trata `_` e `-` como separadores.
    """
    word_map: dict[str, str] = {}
    port_map: dict[str, str] = {}
    for old, new, word in subs:
        (word_map if word else port_map)[old] = new

    if word_map:
        keys = sorted(word_map.keys(), key=len, reverse=True)
        pattern = re.compile(rf'(?<![A-Za-z0-9])({"|".join(re.escape(k) for k in keys)})(?![A-Za-z0-9])')
        content = pattern.sub(lambda m: word_map[m.group(1)], content)

    if port_map:
        keys = sorted(port_map.keys(), key=len, reverse=True)
        pattern = re.compile(rf'(?<!\d)({"|".join(re.escape(k) for k in keys)})(?!\d)')
        content = pattern.sub(lambda m: port_map[m.group(1)], content)

    return content


# ═══════════════════════════════════════════════════════════════════════
# @IF / @ENDIF processor — features ON mantém bloco, OFF remove bloco inteiro
# ═══════════════════════════════════════════════════════════════════════

def process_if_markers(content: str, features_on: set[str], path_hint: str = "") -> str:
    """Processa marcadores `@IF feat` / `@ENDIF feat`. Sempre remove as linhas-marcador.
    Se `feat` está em features_on, mantém o conteúdo; caso contrário, remove o bloco.
    Suporta comentários: '#', '//', '/* */', '{/* */}'.
    """
    lines = content.splitlines(keepends=True)
    out   = []
    stack: list[tuple[str, bool]] = []   # [(feat, keep), ...]

    for lineno, line in enumerate(lines, 1):
        mif  = _IF_RE.match(line)
        mend = _ENDIF_RE.match(line)

        if mif:
            feat = mif.group(1)
            parent_keep = stack[-1][1] if stack else True
            stack.append((feat, parent_keep and (feat in features_on)))
            continue  # descarta linha do marcador

        if mend:
            feat = mend.group(1)
            if not stack:
                raise ValueError(f"{path_hint}:{lineno}: @ENDIF {feat} sem @IF correspondente")
            open_feat, _ = stack.pop()
            if open_feat != feat:
                raise ValueError(f"{path_hint}:{lineno}: @ENDIF {feat} não bate com @IF {open_feat}")
            continue  # descarta linha do marcador

        # Linha normal — inclui somente se todos os blocos abertos estão on
        if not stack or stack[-1][1]:
            out.append(line)

    if stack:
        raise ValueError(f"{path_hint}: @IF não fechado (pilha: {[f for f, _ in stack]})")

    return "".join(out)


# ═══════════════════════════════════════════════════════════════════════
# Clone template — percorre árvore, aplica substituição + @IF + feature-removes
# ═══════════════════════════════════════════════════════════════════════

# Padrões sempre excluídos (não configuráveis)
_ALWAYS_IGNORE = ["**/package-lock.json", "**/package-lock*.json"]


def _match_any_glob(rel_path: str, patterns: list[str]) -> bool:
    """Confere se rel_path (forward-slashed) casa com algum dos globs fnmatch."""
    for pat in patterns:
        if fnmatch.fnmatch(rel_path, pat):
            return True
        # Padrão "**/foo" também casa com "foo" na raiz
        if pat.startswith("**/") and fnmatch.fnmatch(rel_path, pat[3:]):
            return True
    return False


def clone_template(src_root: Path, dst_root: Path,
                   subs: list[tuple[str, str, bool]],
                   features_on: set[str],
                   manifest: dict) -> tuple[int, int]:
    """Copia recursivamente `src_root` → `dst_root`, aplicando regras do manifesto.
    Retorna (arquivos_copiados, arquivos_substituidos).
    """
    ignore_globs       = manifest.get("ignore", []) + _ALWAYS_IGNORE
    no_substitute_globs = manifest.get("no_substitute", [])

    copied = 0
    subst  = 0

    for path in src_root.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(src_root).as_posix()

        if _match_any_glob(rel, ignore_globs):
            continue

        dst_path = dst_root / rel
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if _match_any_glob(rel, no_substitute_globs):
            shutil.copy2(path, dst_path)
            copied += 1
            continue

        # Arquivo textual — lê, substitui, processa @IF, escreve
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Binário não declarado em no_substitute — copia como está
            shutil.copy2(path, dst_path)
            copied += 1
            continue

        text = substitute_in_text(text, subs)
        text = process_if_markers(text, features_on, path_hint=rel)
        dst_path.write_text(text, encoding="utf-8", newline="\n")
        subst += 1

    return copied, subst


def apply_feature_removes(dst_root: Path, features_off: set[str], manifest: dict) -> list[str]:
    """Remove paths listados em features[f].removes_when_disabled para cada f OFF.
    Retorna lista dos paths efetivamente removidos (para log).
    """
    removed: list[str] = []
    for feat in features_off:
        fdef = manifest.get("features", {}).get(feat, {})
        for rel in fdef.get("removes_when_disabled", []):
            target = dst_root / rel.rstrip("/")
            if target.is_dir():
                shutil.rmtree(target)
                removed.append(rel)
            elif target.is_file():
                target.unlink()
                removed.append(rel)
    return removed


def _ask_features(manifest: dict, suppressed: set[str] | None = None) -> set[str]:
    """Pergunta cada feature do manifesto e resolve dependências (requires).

    `suppressed` contém nomes de features que NÃO devem ser oferecidas ao
    usuário — tipicamente features desativadas automaticamente pela variante
    Postgres escolhida (ex.: qdrant quando pgvector). Aparecem só como uma
    linha informativa para dar transparência.
    """
    suppressed = suppressed or set()
    features_def = manifest.get("features", {})
    features_on: set[str] = set()
    for fname, fdef in features_def.items():
        desc = fdef.get("description", fname)
        if fname in suppressed:
            print(f"  {DIM}↷ '{fname}' — {desc}  (desativada pela variante){RESET}")
            continue
        if yesno(f"Habilitar '{fname}' — {desc}?", default=True):
            features_on.add(fname)
    # Resolve requires recursivamente
    added = True
    while added:
        added = False
        for fname in list(features_on):
            for req in features_def.get(fname, {}).get("requires", []):
                if req in features_def and req not in features_on:
                    features_on.add(req)
                    print(f"  {CYAN}→{RESET} feature '{req}' ativada automaticamente {DIM}(requisito de '{fname}'){RESET}")
                    added = True
    return features_on


def _ask_postgres_variant(manifest: dict) -> str:
    """Pergunta qual variante Postgres ativar. Retorna '' se o manifest não
    declarar `postgres_variants` (blueprint mais antigo — nenhum kit aplicado)."""
    pv = manifest.get("postgres_variants") or {}
    available: dict = pv.get("available") or {}
    if not available:
        return ""
    default = pv.get("default") or next(iter(available))

    names = list(available.keys())
    default_idx = names.index(default) + 1 if default in names else 1

    print(f"\n  {BOLD}Variantes disponíveis{RESET} {DIM}(default: {default_idx}){RESET}:")
    for i, (n, spec) in enumerate(available.items(), 1):
        mark = f"{GREEN}↵{RESET}" if n == default else f"{DIM}{i}{RESET}"
        print(f"    {mark}. {CYAN}{n}{RESET}  {DIM}— {spec.get('description', '')}{RESET}")

    while True:
        val = input(f"  Variante (↵ {default_idx}): ").strip().lower()
        if not val:
            return default
        if val.isdigit() and 1 <= int(val) <= len(names):
            return names[int(val) - 1]
        if val in available:
            return val
        print(f"  {RED}✗ Opção inválida.{RESET} Digite um número (1-{len(names)}) ou o nome da variante.")


def collect_project_info(data: dict, manifest: dict) -> dict:
    projects      = data.get("projects", {})
    template_keys = {k for k, p in projects.items() if p.get("template")}

    # ── 1. Projeto ────────────────────────────────────────────────
    print(f"\n{YELLOW}── 1. Projeto ──────────────────────────────────────────────{RESET}")
    key = prompt("Chave (ex: meu-erp ou meu_erp)").lower().replace(" ", "-")
    if not key:
        print(f"{RED}✗ Chave inválida.{RESET}"); sys.exit(1)
    if key in template_keys:
        print(f"{RED}✗ '{key}' é uma chave reservada de template{RESET} — escolha outro nome.")
        sys.exit(1)

    existing    = projects.get(key)
    is_update   = existing is not None
    shared_excl = {k: [e for e in v if e.get("project") != key]
                   for k, v in data.get("shared_services", {}).items()}

    ex_prod     = (existing.get("prod") if is_update else None) or {}
    ex_dev      = (existing.get("dev")  if is_update else None) or {}
    ex_prod_svc = ex_prod.get("svc", {}) if isinstance(ex_prod, dict) else {}
    ex_prod_db  = ex_prod.get("db",  {}) if isinstance(ex_prod, dict) else {}
    ex_dev_svc  = ex_dev.get("svc",  {}) if isinstance(ex_dev,  dict) else {}
    ex_dev_db   = ex_dev.get("db",   {}) if isinstance(ex_dev,  dict) else {}

    if is_update:
        print(f"\n  {YELLOW}⚠️  Projeto '{key}' já existe{RESET} — modo atualização {DIM}(valores atuais como default){RESET}.")
        ex_name, _, ex_desc = existing.get("label", f"{key} — ").partition(" — ")
        name_def  = ex_name.strip() or " ".join(w.capitalize() for w in re.split(r"[-_]+", key) if w)
        desc_def  = ex_desc.strip() or f"{name_def} — descrição"
        root_def  = existing.get("root", f"C:\\Workspace\\gus-{key}")
        color_def = existing.get("color", auto_pick_color(data))
        alias_def = existing.get("alias", key.replace("_", "-"))
    else:
        name_def  = " ".join(w.capitalize() for w in re.split(r"[-_]+", key) if w)
        desc_def  = f"{name_def} — descrição"
        root_def  = f"C:\\Workspace\\gus-{key}"
        color_def = auto_pick_color(data)
        alias_def = key.replace("_", "-")

    name        = prompt("Nome do projeto", name_def)
    description = prompt("Descrição curta", desc_def)
    root        = prompt("Caminho raiz (Windows)", root_def)
    print(f"\n  {DIM}Cor PS sugerida :{RESET} {CYAN}{color_def}{RESET}  {DIM}(próxima livre na paleta){RESET}")
    color       = prompt("Cor PS", color_def)

    print(f"\n  {DIM}Alias CLI (não pode terminar em '-dev'){RESET}")
    alias = prompt("Alias CLI", alias_def)
    while alias.lower().endswith("-dev"):
        print(f"  {RED}✗ O alias não pode terminar em '-dev'.{RESET}")
        alias = prompt("Alias CLI", alias_def)

    timezone = prompt("Timezone", manifest.get("canonical_timezone", "America/Sao_Paulo"))

    # ── 2. Motor do Banco ────────────────────────────────────────
    # A variante é escolhida antes das features porque algumas features
    # (ex.: qdrant) são mutuamente exclusivas com certas variantes.
    print(f"\n{YELLOW}── 2. Motor do Banco ───────────────────────────────────────{RESET}")
    postgres_variant = _ask_postgres_variant(manifest)

    # Features desativadas automaticamente pela variante escolhida
    pv_disables: set[str] = set()
    if postgres_variant:
        pv_def = (manifest.get("postgres_variants", {})
                          .get("available", {})
                          .get(postgres_variant, {}))
        pv_disables = set(pv_def.get("disables", []))

    # ── 3. Features ──────────────────────────────────────────────
    print(f"\n{YELLOW}── 3. Features ─────────────────────────────────────────────{RESET}")
    features_on = _ask_features(manifest, suppressed=pv_disables)

    # ── 4. Portas ────────────────────────────────────────────────
    registered = build_registered_ports(data, exclude_key=key)
    print(f"\n{YELLOW}── 4. Portas{RESET} {DIM}(↵ aceita o valor sugerido){RESET} {YELLOW}───────────────────{RESET}")

    def pport(label: str, val: int) -> int:
        return int(prompt(f"{label:<32} [{port_tag(val, registered)}]", str(val)))

    # App ports (sempre alocados)
    backend_prod = pport("backend          PROD",
                         ex_prod_svc.get("backend") or next_backend_block(shared_excl))
    backend_dev  = pport("backend          DEV",  ex_dev_svc.get("backend",  backend_prod + 10))
    auth_prod    = pport("auth             PROD", ex_prod_svc.get("auth",    backend_prod + 100))
    auth_dev     = pport("auth             DEV",  ex_dev_svc.get("auth",     backend_prod + 110))
    frontend_prod = pport("frontend         PROD",
                          ex_prod_svc.get("frontend") or next_clean_port(shared_excl, ["frontend_prod", "frontend_dev"], 5175, 2))
    frontend_dev  = pport("frontend         DEV",  ex_dev_svc.get("frontend", frontend_prod + 1))

    # DB (sempre)
    db_prod = pport("db               PROD",
                    ex_prod_db.get("port") or next_clean_port(shared_excl, ["db_prod", "db_prod_replica", "db_dev", "db_replica_dev"], 5436, 4))
    db_dev  = pport("db               DEV",  ex_dev_db.get("port", db_prod + 2))

    # Feature: etl → frontend-etl + RabbitMQ
    etl_frontend_prod = etl_frontend_dev = None
    rabbitmq_amqp_prod = rabbitmq_mgmt_prod = rabbitmq_amqp_dev = rabbitmq_mgmt_dev = None
    # Buckets correlatos: serviços que dividem o mesmo espaço de porta do host
    # precisam ser alocados conjuntamente para evitar colisões cross-bucket
    # (ex.: qdrant http de um projeto batendo com qdrant grpc de outro).
    # Rabbit AMQP e MGMT são separados porque usam faixas distintas (5xxx vs 15xxx).
    QDRANT_BUCKETS    = ["qdrant", "qdrant_grpc", "qdrant_dev", "qdrant_grpc_dev"]
    REDIS_BUCKETS     = ["redis", "redis_dev"]
    RABBIT_AMQP_BUCKETS = ["rabbitmq_amqp", "rabbitmq_amqp_dev"]
    RABBIT_MGMT_BUCKETS = ["rabbitmq_mgmt", "rabbitmq_mgmt_dev"]

    if "etl" in features_on:
        etl_frontend_prod = pport("etl_frontend     PROD",
                                  ex_prod_svc.get("etl_frontend") or next_clean_port(shared_excl, ["etl_frontend_prod", "etl_frontend_dev"], 3333, 2))
        etl_frontend_dev  = pport("etl_frontend     DEV",  ex_dev_svc.get("etl_frontend", etl_frontend_prod + 1))
        amqp_taken: set[int] = set()
        rabbitmq_amqp_prod = pport("rabbitmq_amqp    PROD", next_clean_port(shared_excl, RABBIT_AMQP_BUCKETS, 5673,  1, amqp_taken))
        amqp_taken.add(rabbitmq_amqp_prod)
        rabbitmq_amqp_dev  = pport("rabbitmq_amqp    DEV",  next_clean_port(shared_excl, RABBIT_AMQP_BUCKETS, 5673,  1, amqp_taken))
        mgmt_taken: set[int] = set()
        rabbitmq_mgmt_prod = pport("rabbitmq_mgmt    PROD", next_clean_port(shared_excl, RABBIT_MGMT_BUCKETS, 15673, 1, mgmt_taken))
        mgmt_taken.add(rabbitmq_mgmt_prod)
        rabbitmq_mgmt_dev  = pport("rabbitmq_mgmt    DEV",  next_clean_port(shared_excl, RABBIT_MGMT_BUCKETS, 15673, 1, mgmt_taken))

    # Feature: replica
    db_prod_replica = db_dev_replica = None
    if "replica" in features_on:
        db_prod_replica = pport("db_replica       PROD", ex_prod_db.get("replica", db_prod + 1))
        db_dev_replica  = pport("db_replica       DEV",  ex_dev_db.get("replica",  db_dev  + 1))

    # Feature: redis
    redis_prod = redis_dev = None
    if "redis" in features_on:
        redis_taken: set[int] = set()
        redis_prod = pport("redis            PROD", next_clean_port(shared_excl, REDIS_BUCKETS, 6380, 1, redis_taken))
        redis_taken.add(redis_prod)
        redis_dev  = pport("redis            DEV",  next_clean_port(shared_excl, REDIS_BUCKETS, 6380, 1, redis_taken))

    # Feature: qdrant
    qdrant_prod = qdrant_grpc_prod = qdrant_dev = qdrant_grpc_dev = None
    if "qdrant" in features_on:
        qdrant_taken: set[int] = set()
        qdrant_prod      = pport("qdrant           PROD", next_clean_port(shared_excl, QDRANT_BUCKETS, 6340, 1, qdrant_taken))
        qdrant_taken.add(qdrant_prod)
        qdrant_grpc_prod = pport("qdrant_grpc      PROD", next_clean_port(shared_excl, QDRANT_BUCKETS, 6340, 1, qdrant_taken))
        qdrant_taken.add(qdrant_grpc_prod)
        qdrant_dev       = pport("qdrant           DEV",  next_clean_port(shared_excl, QDRANT_BUCKETS, 6340, 1, qdrant_taken))
        qdrant_taken.add(qdrant_dev)
        qdrant_grpc_dev  = pport("qdrant_grpc      DEV",  next_clean_port(shared_excl, QDRANT_BUCKETS, 6340, 1, qdrant_taken))

    # ── 5. Credenciais do Banco ──────────────────────────────────
    print(f"\n{YELLOW}── 5. Credenciais do Banco ─────────────────────────────────{RESET}")
    db_name = prompt("Nome do banco PROD", ex_prod_db.get("name", alias))
    db_user = prompt("Usuário do banco",   ex_prod_db.get("user", alias))
    db_pass = prompt("Senha do banco",     ex_prod_db.get("pass", alias))

    # ── 6. RabbitMQ (se etl ON) ──────────────────────────────────
    rabbit_user_prod = rabbit_pass_prod = rabbit_vhost_prod = ""
    rabbit_user_dev  = rabbit_pass_dev  = rabbit_vhost_dev  = ""
    if "etl" in features_on:
        print(f"\n{YELLOW}── 6. RabbitMQ (ETL) ───────────────────────────────────────{RESET}")
        rabbit_user_prod  = prompt("RABBITMQ_USER_PROD",  alias)
        rabbit_pass_prod  = prompt("RABBITMQ_PASS_PROD",  alias)
        rabbit_vhost_prod = prompt("RABBITMQ_VHOST_PROD", f"{alias}_etl")
        rabbit_user_dev   = prompt("RABBITMQ_USER_DEV",   alias)
        rabbit_pass_dev   = prompt("RABBITMQ_PASS_DEV",   alias)
        rabbit_vhost_dev  = prompt("RABBITMQ_VHOST_DEV",  f"{alias}_etl_dev")

    # ── 7. Admin inicial ─────────────────────────────────────────
    print(f"\n{YELLOW}── 7. Admin Inicial ────────────────────────────────────────{RESET}")
    admin_name     = prompt("ADMIN_NAME",     "Luiz Gustavo Quinelato")
    admin_username = prompt("ADMIN_USERNAME", "gustavoquinelato")
    admin_email    = prompt("ADMIN_EMAIL",    "gustavoquinelato@gmail.com")
    admin_password = prompt("ADMIN_PASSWORD", "Gus@2026!")

    # Monta extra_ports (formato legado consumido por update_ports_yml + PS profile)
    extra_ports: list[dict]     = []
    extra_ports_dev: list[dict] = []
    if "redis" in features_on:
        extra_ports.append({"name": "redis",     "port": redis_prod, "proto": "tcp"})
        extra_ports_dev.append({"name": "redis_dev", "port": redis_dev,  "proto": "tcp"})
    if "qdrant" in features_on:
        extra_ports += [
            {"name": "qdrant",      "port": qdrant_prod,      "proto": "tcp"},
            {"name": "qdrant_grpc", "port": qdrant_grpc_prod, "proto": "tcp"},
        ]
        extra_ports_dev += [
            {"name": "qdrant_dev",      "port": qdrant_dev,      "proto": "tcp"},
            {"name": "qdrant_grpc_dev", "port": qdrant_grpc_dev, "proto": "tcp"},
        ]
    if "etl" in features_on:
        extra_ports += [
            {"name": "rabbitmq_amqp", "port": rabbitmq_amqp_prod, "proto": "tcp"},
            {"name": "rabbitmq_mgmt", "port": rabbitmq_mgmt_prod, "proto": "tcp"},
        ]
        extra_ports_dev += [
            {"name": "rabbitmq_amqp_dev", "port": rabbitmq_amqp_dev, "proto": "tcp"},
            {"name": "rabbitmq_mgmt_dev", "port": rabbitmq_mgmt_dev, "proto": "tcp"},
        ]

    return {
        "key": key, "alias": alias, "name": name, "description": description,
        "root": root, "color": color, "timezone": timezone,
        "is_update": is_update,
        "features_on":      features_on,
        "postgres_variant": postgres_variant,
        "has_replica":      "replica" in features_on,
        "has_etl_frontend": "etl"     in features_on,
        "enable_ai":        "ai"      in features_on,
        "db_name": db_name, "db_user": db_user, "db_pass": db_pass,
        "extra_ports": extra_ports, "extra_ports_dev": extra_ports_dev,
        "rabbit_user_prod": rabbit_user_prod, "rabbit_pass_prod": rabbit_pass_prod, "rabbit_vhost_prod": rabbit_vhost_prod,
        "rabbit_user_dev":  rabbit_user_dev,  "rabbit_pass_dev":  rabbit_pass_dev,  "rabbit_vhost_dev":  rabbit_vhost_dev,
        "admin_name": admin_name, "admin_username": admin_username,
        "admin_email": admin_email, "admin_password": admin_password,
        "ports": {
            "backend_prod":       backend_prod,       "backend_dev":       backend_dev,
            "auth_prod":          auth_prod,          "auth_dev":          auth_dev,
            "frontend_prod":      frontend_prod,      "frontend_dev":      frontend_dev,
            "etl_frontend_prod":  etl_frontend_prod,  "etl_frontend_dev":  etl_frontend_dev,
            "db_prod":            db_prod,            "db_dev":            db_dev,
            "db_prod_replica":    db_prod_replica,    "db_dev_replica":    db_dev_replica,
            "redis_prod":         redis_prod,         "redis_dev":         redis_dev,
            "qdrant_prod":        qdrant_prod,        "qdrant_dev":        qdrant_dev,
            "qdrant_grpc_prod":   qdrant_grpc_prod,   "qdrant_grpc_dev":   qdrant_grpc_dev,
            "rabbitmq_amqp_prod": rabbitmq_amqp_prod, "rabbitmq_amqp_dev": rabbitmq_amqp_dev,
            "rabbitmq_mgmt_prod": rabbitmq_mgmt_prod, "rabbitmq_mgmt_dev": rabbitmq_mgmt_dev,
        },
    }


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
    reg("db_replica_dev",     p["db_dev_replica"])

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
    print(f"{GREEN}[OK]{RESET} helms/ports.yml {action} com projeto '{CYAN}{info['key']}{RESET}'")


def _print_summary(info: dict, manifest: dict) -> None:
    p = info["ports"]
    print(f"\n{YELLOW}── Resumo ──────────────────────────────────────────────────{RESET}")
    print(f"  {DIM}Projeto  :{RESET} {CYAN}{info['key']}{RESET}  {DIM}({info['name']}){RESET}")
    print(f"  {DIM}Desc     :{RESET} {info['description']}")
    print(f"  {DIM}Root     :{RESET} {info['root']}")
    print(f"  {DIM}Timezone :{RESET} {info['timezone']}")
    print(f"  {DIM}Cor PS   :{RESET} {info['color']}")
    print(f"  {DIM}Features :{RESET} {', '.join(sorted(info['features_on'])) or '(nenhuma)'}")
    if info.get("postgres_variant"):
        print(f"  {DIM}PG kit   :{RESET} {CYAN}{info['postgres_variant']}{RESET}")
    print(f"  {DIM}PROD     :{RESET} backend={p['backend_prod']}  auth={p['auth_prod']}  frontend={p['frontend_prod']}  db={p['db_prod']}")
    if info["has_replica"]:
        print(f"             db_replica={p['db_prod_replica']}")
    if info["has_etl_frontend"]:
        print(f"             etl_frontend={p['etl_frontend_prod']}")
    print(f"  {DIM}DEV      :{RESET} backend={p['backend_dev']}  auth={p['auth_dev']}  frontend={p['frontend_dev']}  db={p['db_dev']}")
    if info["has_replica"]:
        print(f"             db_replica={p['db_dev_replica']}")
    if info["has_etl_frontend"]:
        print(f"             etl_frontend={p['etl_frontend_dev']}")
    if info["extra_ports"]:
        extras = ", ".join(f"{e['name']}:{e['port']}" for e in info["extra_ports"])
        print(f"  {DIM}Extras   :{RESET} {extras}")
    print(f"{YELLOW}────────────────────────────────────────────────────────────{RESET}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Clona um template para um novo projeto")
    ap.add_argument("--template", help="Chave ou alias do template (pula o menu)")
    args = ap.parse_args()

    os.system("cls" if os.name == "nt" else "clear")
    print(f"{BOLD}{'=' * 65}{RESET}")
    print(f"{BOLD}  create_project.py{RESET} {DIM}— Clonar template para novo projeto{RESET}")
    print(f"{BOLD}{'=' * 65}{RESET}")

    data = load_ports()

    # 1. Seleciona template
    tpl_key, manifest = pick_template(data, args.template)
    tpl_root = TEMPLATES_PROJECTS_DIR / tpl_key
    if not tpl_root.is_dir():
        print(f"{RED}✗ Pasta do template não encontrada:{RESET} {tpl_root}")
        sys.exit(1)
    print(f"\n📦  {BOLD}Template:{RESET} {CYAN}{tpl_key}{RESET}  {DIM}(alias: {manifest['identity'].get('alias', tpl_key)}){RESET}")

    # 2. Coleta dados do novo projeto
    info = collect_project_info(data, manifest)

    # 3. Resumo + confirmação
    _print_summary(info, manifest)
    if not yesno("\nConfirmar e criar projeto?", default=True):
        print(f"{DIM}Cancelado.{RESET}")
        sys.exit(0)

    # 4. Prepara destino (limpa se já existir)
    project_root = Path(info["root"])
    if project_root.exists():
        print()
        print(f"  {YELLOW}⚠️  🔴  ATENÇÃO!{RESET}")
        print(f"  A pasta já existe:  {CYAN}{project_root}{RESET}")
        print(f"  {YELLOW}Todo o conteúdo será APAGADO e reconstruído a partir do template.{RESET}")
        confirm = input(f"\n  Digite '{BOLD}APAGAR{RESET}' para confirmar a limpeza total: ").strip()
        if confirm != "APAGAR":
            print(f"  {DIM}Operação cancelada.{RESET}")
            sys.exit(0)
        shutil.rmtree(project_root)
        print(f"  🗑️  {DIM}{project_root} removida.{RESET}")
    project_root.mkdir(parents=True, exist_ok=True)

    # 5. Clona árvore do template com substituição + @IF
    print()
    features_on  = info["features_on"]
    features_off = set(manifest.get("features", {}).keys()) - features_on
    subs         = build_identity_map(info, manifest)
    copied, subst = clone_template(tpl_root, project_root, subs, features_on, manifest)
    removed      = apply_feature_removes(project_root, features_off, manifest)
    print(f"{GREEN}[OK]{RESET} Clonado: {CYAN}{subst}{RESET} substituído(s), {CYAN}{copied}{RESET} cópia(s) binária(s) → {DIM}{project_root}{RESET}")
    if removed:
        print(f"{GREEN}[OK]{RESET} Removido(s) por features off: {DIM}{', '.join(removed)}{RESET}")

    # 5.5 Aplica o kit da variante Postgres escolhida (copia sobre os composes da raiz)
    pg_variant = info.get("postgres_variant")
    if pg_variant:
        try:
            apply_variant_files(pg_variant, project_root, verbose=False)
            print(f"{GREEN}[OK]{RESET} Variante Postgres aplicada: {CYAN}{pg_variant}{RESET}")
        except ValueError as e:
            print(f"{YELLOW}[WARN]{RESET} Variante Postgres não aplicada: {e}")

    # 6. Atualiza ports.yml
    update_ports_yml(data, info)

    key    = info["key"]
    alias  = info.get("alias", key)
    action = "atualizado" if info["is_update"] else "criado"

    # 7. Cria pasta de documentação na factory (projects/{alias}/docs/)
    #    Preservada mesmo se o projeto for deletado do helms.
    factory_docs = PROJECTS_DIR / alias / "docs"
    if not factory_docs.exists():
        factory_docs.mkdir(parents=True, exist_ok=True)
        print(f"{GREEN}[OK]{RESET} Pasta de docs criada: {CYAN}{factory_docs}{RESET}")
    else:
        print(f"{DIM}[--]{RESET} Pasta de docs já existe: {DIM}{factory_docs}{RESET}")

    print(f"\n{GREEN}✅  Projeto{RESET} '{CYAN}{key}{RESET}' {GREEN}{action}!{RESET}")
    print(f"\n   📁 {DIM}Projeto destino:{RESET} {CYAN}{project_root}{RESET}")
    print(f"   📂 {DIM}Docs factory  :{RESET} {CYAN}{factory_docs}{RESET}")
    print(f"\n   📋 {BOLD}Próximos passos:{RESET}")
    print(f"      1. {DIM}cd {project_root}  &&  npm install (onde houver package.json){RESET}")
    print(f"      2. {DIM}Coloque seus docs em {factory_docs}{RESET}")
    print(f"         {DIM}e rode: python scripts/sync_docs.py {alias}{RESET}")
    print(f"\n   🖥️  {BOLD}GUS CLI:{RESET}")
    print(f"      {CYAN}gus dkup {key}{RESET}              {DIM}← sobe DB PROD{RESET}")
    print(f"      {CYAN}gus dkup-dev {key}{RESET}          {DIM}← sobe DB DEV{RESET}")
    print(f"      {CYAN}gus run rat {key}{RESET}           {DIM}← sobe tudo em PROD (wt){RESET}")
    print(f"      {CYAN}gus help{RESET}                    {DIM}← lista projetos e comandos{RESET}")


if __name__ == "__main__":
    main()
