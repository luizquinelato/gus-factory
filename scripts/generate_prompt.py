"""
generate_prompt.py
==================
Gera PROMPT_CUSTOM_<CHAVE>.md dentro de PROJECT_ROOT/docs/prompts/.

Uso (a partir da raiz do repositório):
  python scripts/generate_prompt.py plurus          # prompt de módulos custom
  python scripts/generate_prompt.py plurus -u       # conteúdo embutido (Claude.ai, ChatGPT)
  python scripts/generate_prompt.py plurus -s       # 1 migration por arquivo de módulo

Flags:
  project        (obrigatório) Chave do projeto em projects/ (ex: plurus)
  -u / --unified Embute o conteúdo dos arquivos no prompt (ideal p/ Claude.ai, ChatGPT)
  -s / --split   Instrui o agente a criar 1 migration por arquivo (default: unificado)

Saída — sempre em PROJECT_ROOT/docs/prompts/ (o projeto real, não o blueprint):
  plurus         → PROMPT_CUSTOM_PLURUS.md          (módulos customizados do projeto)

Variáveis lidas de: projects/<key>/00-variables.md  (blueprint)
Docs de módulos de: projects/<key>/                 (todos os .md exceto 00-variables.md)
Sincronizado em:    PROJECT_ROOT/docs/initial/custom/ (para referência @file no Augment Code)

As migrations base (0001, 0002), docker-compose e docs base foram pré-gerados pelo
create_project.py. Adicione os docs de módulo em projects/<key>/ e rode este script
para gerar o prompt de extensão da plataforma.
"""

import os
import re
import argparse
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

# Raiz do repositório — sempre dois níveis acima deste script (scripts/generate_prompt.py)
REPO_ROOT     = Path(__file__).resolve().parent.parent
PROJECTS_ROOT = REPO_ROOT / 'projects'
PORTS_YML     = REPO_ROOT / 'helms' / 'ports.yml'

# Arquivos excluídos ao escanear pastas customizadas
EXCLUDED_FILES    = {'00-variables.md', '00-variables-template.md'}
EXCLUDED_PREFIXES = ('PROMPT_',)

# Ordem curada dos arquivos base em docs/
BASE_FILES = [
    '01-architecture.md',        # Estrutura de diretórios e serviços
    '02-docker-environments.md', # Docker Compose e variáveis de ambiente
    '03-database.md',            # Schema SQL e tabelas base
    '04-migrations.md',          # Migration runner e seed data
    '05-security-auth.md',       # Auth Service e RBAC
    '06-backend-patterns.md',    # Padrões de código backend
    '07-frontend-patterns.md',   # Padrões de código frontend
    '08-design-system.md',       # Componentes e sistema de design
    '09-color-schema.md',        # Tokens de cor e CSS Variables
    '10-utils.md',               # Makefile e scripts utilitários
]
OPTIONAL_ETL = '11-etl.md'
OPTIONAL_AI  = '12-ai-agents.md'


def _get_project_root_from_ports(project_key: str) -> str | None:
    """Lê PROJECT_ROOT de helms/ports.yml para a chave informada."""
    if yaml is None:
        return None
    if not PORTS_YML.exists():
        return None
    with open(PORTS_YML, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    proj = data.get("projects", {}).get(project_key, {})
    return proj.get("root")


def detect_project_context(project_key: str) -> tuple:
    """Detecta o contexto do projeto a partir da chave informada.

    Retorna (blueprint_project_root, variables_file):
      - blueprint_project_root: projects/<key>/ (docs de módulo)
      - variables_file: caminho para 00-variables.md (projeto ou blueprint como fallback)

    Ordem de busca:
      1. PROJECT_ROOT/docs/initial/00-variables.md  (caminho canônico gerado pelo create_project.py)
      2. projects/<key>/00-variables.md             (cópia no blueprint, fallback automático)
    """
    blueprint_project_root = PROJECTS_ROOT / project_key
    actual_root_str = _get_project_root_from_ports(project_key)

    if actual_root_str:
        canonical = Path(actual_root_str) / "docs" / "initial" / "00-variables.md"
        if canonical.exists():
            return blueprint_project_root, str(canonical)

    # Fallback — cópia no blueprint (gerada pelo create_project.py junto com o projeto)
    return blueprint_project_root, str(blueprint_project_root / "00-variables.md")


def parse_file_meta(filepath):
    """Lê o marcador <!-- blueprint: db_changes=X seed_data=X --> do arquivo.

    Procura apenas nas primeiras 5 linhas do arquivo.
    Retorna dict com 'db_changes' e 'seed_data' como booleans.
    Se o marcador não existir, assume False para ambos.
    """
    meta = {'db_changes': False, 'seed_data': False}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i >= 5:
                    break
                m = re.search(
                    r'<!--\s*blueprint:\s*db_changes=(true|false)\s+seed_data=(true|false)\s*-->',
                    line
                )
                if m:
                    meta['db_changes'] = m.group(1) == 'true'
                    meta['seed_data']  = m.group(2) == 'true'
                    break
    except FileNotFoundError:
        pass
    return meta


def read_variables(filepath):
    """Lê KEY=VALUE do arquivo de variáveis, ignorando linhas de comentário e seções."""
    variables = {}
    if not os.path.exists(filepath):
        print(f"⚠️  Arquivo não encontrado: {filepath}")
        print(f"    Copie templates/docs/00-variables-template.md para docs/00-variables.md e preencha os valores.")
        return variables

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Ignora linhas vazias, comentários e cabeçalhos Markdown
            if not line or line.startswith('#') or line.startswith('|') or line.startswith('>'):
                continue
            if '=' in line:
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip()
                # Aceita apenas chaves em UPPER_SNAKE_CASE
                if re.match(r'^[A-Z][A-Z0-9_]+$', key):
                    variables[key] = value

    return variables


def inject_variables(content, variables):
    """Substitui {{ VAR_NAME }} pelo valor correspondente."""
    for key, value in variables.items():
        content = content.replace(f"{{{{ {key} }}}}", value)
    # Sinaliza variáveis não resolvidas
    content = re.sub(r'\{\{ [A-Z_]+ \}\}', '[NÃO DEFINIDO]', content)
    return content


def build_header(variables, is_module=False):
    """Monta o cabeçalho com papel da IA, variáveis resolvidas e premissas.

    is_module=True: prompt de extensão de módulos (base já implementada).
    is_module=False: prompt base (implementação do zero).
    """
    project_name = variables.get('PROJECT_NAME', '[NÃO DEFINIDO]')

    if is_module:
        lines = [
            f"Você é um Engenheiro Full-Stack Especialista continuando a implementação do projeto **{project_name}**.",
            "A estrutura base (autenticação, migrations, Docker, design system, padrões de código) já está",
            "completamente implementada. Não leia nem altere nenhum arquivo fora da pasta dos módulos abaixo.",
            "Sua missão agora é implementar os **módulos adicionais** listados na seção 3,",
            "integrando-os à base existente sem alterar os arquivos e padrões já estabelecidos.",
            "",
            "# 1. CONTEXTO DO PROJETO",
            "",
        ]
    else:
        lines = [
            "Você é um Arquiteto de Soluções Enterprise Sênior e Engenheiro Full-Stack Especialista.",
            "Sua missão é construir uma plataforma SaaS multi-tenant do zero, com foco em segurança,",
            "performance e escalabilidade. Siga estritamente os padrões de arquitetura e código fornecidos.",
            "",
            "# 1. VARIÁVEIS DO PROJETO",
            "",
        ]

    # Para módulos, só emite as variáveis relevantes para implementação de código.
    # Infra (portas, DB, Docker) já está configurada — não precisa repetir.
    MODULE_VARS = {
        'PROJECT_NAME', 'PROJECT_DESCRIPTION', 'LANGUAGE', 'TIMEZONE',
        'PROJECT_PREFIX', 'PROJECT_ROOT', 'USER_ROLES',
    }
    vars_to_emit = {k: v for k, v in variables.items() if not is_module or k in MODULE_VARS}
    for key, value in vars_to_emit.items():
        lines.append(f"- **{key}**: `{value}`")

    if is_module:
        lines += [
            "",
            "# 2. PREMISSAS",
            "",
            "- A implementação base já está completa e funcional — não a releia nem a altere.",
            "- Todos os serviços (Backend, Auth Service, Frontend) estão configurados e em execução.",
            "- O banco de dados base (tenants, users, migration_history) já existe.",
            "- Os padrões de código, design system e convenções de banco já foram aplicados.",
            "- **Leia apenas** os arquivos listados na seção 3. Não acesse nenhum outro arquivo do projeto.",
            "- **Não altere** arquivos, tabelas ou padrões já existentes — apenas adicione.",
            "",
        ]
    else:
        lines += [
            "",
            "# 2. PRINCÍPIOS INEGOCIÁVEIS",
            "",
            "1. **Segurança Primeiro** — Nenhuma rota de negócio sem autenticação. Nenhum secret hardcoded.",
            "2. **Multi-tenant Nativo** — Todo dado de negócio deve ter `tenant_id`.",
            "3. **Isolamento de Auth** — O frontend NUNCA fala com o Auth Service diretamente; sempre via Backend.",
            "4. **Soft Delete** — Nunca delete registros físicos; use a flag `active = false`.",
            "5. **Roteamento Frontend** — Nunca use `useState` para controlar abas principais; use rotas dedicadas.",
            "6. **Design System** — Nunca use cores hardcoded; use sempre as CSS Custom Properties.",
            "7. **Logging Estruturado** — Nunca use `print()`; use o logger Python configurado por módulo.",
            "8. **Dependências sem pin** — Nos `requirements.txt`, escreva apenas o nome do pacote, nunca a versão (`==x.y.z`). Use exatamente o que o doc especifica — não introduza bibliotecas de abstração não solicitadas (ex: o doc diz `bcrypt` → use `bcrypt`, não `passlib`).",
            "",
        ]

    return "\n".join(lines)


def get_file_pairs(folder: str, variables: dict, is_base: bool = False) -> list:
    """Retorna lista de (folder, filename, meta) na ordem correta.

    is_base=True  → PROJECT_ROOT/docs/initial/: usa ordem curada BASE_FILES.
    is_base=False → projects/<key>/custom/: escaneia .md em ordem alfabética.

    meta = {'db_changes': bool, 'seed_data': bool}
    """
    if is_base:
        files = list(BASE_FILES)
        if variables.get('ENABLE_ETL', '').lower() in ('true', 'yes'):
            files.append(OPTIONAL_ETL)
        if variables.get('ENABLE_AI_LAYER', '').lower() in ('true', 'yes'):
            files.append(OPTIONAL_AI)
    else:
        files = sorted(
            f for f in os.listdir(folder)
            if f.endswith('.md')
            and f not in EXCLUDED_FILES
            and not any(f.startswith(p) for p in EXCLUDED_PREFIXES)
        )

    return [(folder, f, parse_file_meta(os.path.join(folder, f))) for f in files]


def build_body_mode_a(file_pairs, is_module: bool = False, path_prefix: str = "docs/initial") -> str:
    """Modo A: lista de referências a arquivos.

    path_prefix: prefixo relativo ao PROJECT_ROOT para compor o path de cada arquivo.
      base  → "docs/initial"
      custom → "docs/initial/custom"
    """
    if is_module:
        lines = [
            "# 3. MÓDULOS A IMPLEMENTAR (BLUEPRINT)",
            "",
            "Leia cada arquivo de módulo na ordem indicada e implemente-o completamente antes de avançar.",
            "Cada arquivo define rotas, models, migrations e telas do respectivo módulo.",
            "",
        ]
    else:
        lines = [
            "# 3. ARQUIVOS DE REFERÊNCIA (BLUEPRINT)",
            "",
            "Antes de escrever qualquer código, leia os arquivos abaixo na ordem indicada.",
            "Eles contêm os padrões obrigatórios de arquitetura, banco de dados, backend, frontend e infra.",
            "",
        ]
    for i, (_folder, filename, _meta) in enumerate(file_pairs, 1):
        lines.append(f"{i}. `{path_prefix}/{filename}`")
    return "\n".join(lines)


def build_body_mode_b(file_pairs, variables, is_module=False):
    """Modo B: conteúdo embutido e compactado."""
    section_title = "# 3. MÓDULOS A IMPLEMENTAR (BLUEPRINT)" if is_module else "# 3. ARQUIVOS DE REFERÊNCIA (BLUEPRINT)"
    section_intro = "Abaixo estão os módulos a implementar. Integre cada um à base existente." if is_module \
        else "Abaixo estão os padrões de código e arquitetura que você DEVE seguir."
    lines = [section_title, "", section_intro]
    for folder, filename, _meta in file_pairs:
        filepath = os.path.join(folder, filename)
        if not os.path.exists(filepath):
            lines.append(f"\n⚠️ Arquivo não encontrado: {filepath}")
            continue
        with open(filepath, 'r', encoding='utf-8') as f:
            content = inject_variables(f.read(), variables)
        lines.append(f"\n\n{'─'*60}")
        lines.append(f"### {filename}")
        lines.append('─'*60)
        lines.append(content.strip())
    return "\n".join(lines)


def build_migration_instruction(file_pairs, split=False, is_module=False, project_key="project"):
    """Gera a seção de instrução de migration.

    Base (is_module=False):
      Migrations 0001 e 0002 já foram pré-geradas pelo create_project.py.
      IA NÃO deve recriá-las — apenas usa como referência e cria a partir de 0003.

    Custom sem -s: unificado NNNN_custom_initial_{project_key}
    Custom com -s: uma tupla por arquivo com alterações
    """
    common_rules = [
        "Regras para cada arquivo de migration:",
        "- O arquivo de schema cria/altera tabelas respeitando a ordem de FKs",
        "- O arquivo _seed_data insere apenas dados de configuração necessários (não aleatórios)",
        "- O **runner** registra automaticamente na `migration_history` — NÃO inclua esse código dentro da migration",
        "- Seguir o mesmo padrão de migration já estabelecido (consulte 0001/0002 como referência)",
    ]
    no_changes = "## 📦 Migrations\n\n> ℹ️ Nenhum arquivo da pasta declara alterações de banco (`db_changes=false, seed_data=false`)."

    # ── BASE: migrations base já existem — IA não deve recriá-las ────────────
    if not is_module:
        return "\n".join([
            "## 📦 Migrations — Base já pré-gerada",
            "",
            "> ✅ As migrations base foram **pré-geradas automaticamente** pelo `create_project.py`.",
            "> **NÃO as recrie.** Use-as como referência de padrão.",
            "",
            "Arquivos já existentes no projeto:",
            "- `services/backend/scripts/migrations/0001_initial_schema.py`  ← schema base (tenants, users, sessions, permissions, settings, colors, integrations)",
            "- `services/backend/scripts/migrations/0002_initial_seed_data.py` ← seed data (tenant padrão, admin, cores, system_settings)",
            "- `services/backend/scripts/migration_runner.py`                ← CLI: `--apply-all`, `--status`, `--rollback-to NNNN`",
            "",
            "Docker Compose também pré-gerado (não recriar):",
            "- `docker-compose.db.yml`      ← PROD (valores hardcoded de prod)",
            "- `docker-compose.db.dev.yml`  ← DEV  (valores hardcoded de dev)",
            "",
            "> 🚫 **NÃO crie migrations adicionais.** Não assuma a necessidade de tabelas de negócio",
            "> específicas do projeto. Aguarde um prompt customizado separado que definirá",
            "> os módulos, entidades e migrations necessários para este projeto.",
            "",
        ])

    # ── CUSTOM SEM -s: unificado NNNN_custom_initial_{project_key} ───────────
    if not split:
        any_schema = any(meta['db_changes'] for _, _, meta in file_pairs)
        any_seed   = any(meta['seed_data']   for _, _, meta in file_pairs)
        if not any_schema and not any_seed:
            return no_changes

        n    = "NNNN"
        slug = f"custom_initial_{project_key}"
        lines = [
            "## 📦 Migrations — Arquivo(s) unificado(s) para todas as alterações",
            "",
            "Após implementar todos os módulos acima, crie:",
        ]
        if any_schema:
            lines.append(f"- `{n}_{slug}.py`       → CREATE TABLE/ALTER TABLE para todas as tabelas dos módulos, na ordem correta (FKs primeiro)")
        if any_seed:
            lines.append(f"- `{n}_{slug}_seed_data.py`  → dados de configuração inicial dos módulos")
        lines += [
            "",
            "Substitua `NNNN` pelo próximo número sequencial após `0002` (ou o último migration existente).",
            "",
        ] + common_rules
        return "\n".join(lines)

    # ── CUSTOM COM -s: uma tupla por arquivo ──────────────────────────────────
    entries = []
    offset  = 0
    for _folder, filename, meta in file_pairs:
        if not meta['db_changes'] and not meta['seed_data']:
            continue
        raw         = os.path.splitext(filename)[0]
        module_name = re.sub(r'^\d+-', '', raw)
        slug        = f"{project_key}_{module_name}"
        n           = "NNNN" if offset == 0 else f"NNNN+{offset}"
        if meta['db_changes'] and meta['seed_data']:
            entries.append(f"- `{n}_{slug}.py` + `{n}_{slug}_seed_data.py`  ← `{filename}`")
        elif meta['db_changes']:
            entries.append(f"- `{n}_{slug}.py`  ← `{filename}` (schema)")
        else:
            entries.append(f"- `{n}_{slug}_seed_data.py`  ← `{filename}` (seed)")
        offset += 1

    if not entries:
        return no_changes

    lines = [
        "## 📦 Migrations — Uma tupla por módulo com alterações",
        "",
        "Crie migrations apenas para os módulos que declaram alterações de banco.",
        "Numere sequencialmente a partir do próximo número após o último migration existente:",
        "",
    ] + entries + [""] + common_rules
    return "\n".join(lines)


def build_env_section(values: dict) -> str:
    """Gera a seção de criação obrigatória dos arquivos .env com valores reais do projeto.

    Lê as variáveis já resolvidas do projeto (portas, nomes de DB, usuários, etc.)
    e monta os três blocos completos: .env.dev, .env.prod e .env.example.
    Inclui stanzas opcionais de Redis, Qdrant e RabbitMQ se as portas estiverem definidas.
    """
    db_port_prod  = values.get("DB_PORT_PROD", "")
    db_port_dev   = values.get("DB_PORT_DEV", "")
    db_name_prod  = values.get("DB_NAME_PROD", "")
    db_name_dev   = values.get("DB_NAME_DEV", "")
    db_user       = values.get("DB_USER", "")
    db_pass_prod  = values.get("DB_PASSWORD_PROD", "")
    db_pass_dev   = values.get("DB_PASSWORD_DEV", "")
    back_prod     = values.get("BACKEND_PORT", "")
    back_dev      = values.get("BACKEND_PORT_DEV", "")
    auth_prod     = values.get("AUTH_PORT", "")
    auth_dev      = values.get("AUTH_PORT_DEV", "")
    front_prod    = values.get("FRONTEND_PORT", "")
    front_dev     = values.get("FRONTEND_PORT_DEV", "")

    redis_prod    = values.get("REDIS_PORT_PROD", "")
    redis_dev     = values.get("REDIS_PORT_DEV", "")
    qdrant_prod   = values.get("QDRANT_PORT_PROD", "")
    qdrant_dev    = values.get("QDRANT_PORT_DEV", "")
    mq_amqp_prod  = values.get("RABBITMQ_AMQP_PORT_PROD", "")
    mq_amqp_dev   = values.get("RABBITMQ_AMQP_PORT_DEV", "")

    def _optional_stanza_dev() -> list[str]:
        lines = []
        if redis_dev:
            lines += ["", f"REDIS_URL=redis://localhost:{redis_dev}/0"]
        if qdrant_dev:
            lines += [f"QDRANT_URL=http://localhost:{qdrant_dev}"]
        if mq_amqp_dev:
            lines += [f"RABBITMQ_URL=amqp://guest:guest@localhost:{mq_amqp_dev}/"]
        return lines

    def _optional_stanza_prod() -> list[str]:
        lines = []
        if redis_prod:
            lines += ["", f"REDIS_URL=redis://localhost:{redis_prod}/0"]
        if qdrant_prod:
            lines += [f"QDRANT_URL=http://localhost:{qdrant_prod}"]
        if mq_amqp_prod:
            lines += [f"RABBITMQ_URL=amqp://guest:guest@localhost:{mq_amqp_prod}/"]
        return lines

    def _optional_stanza_example() -> list[str]:
        lines = []
        if redis_prod or redis_dev:
            lines += ["", f"REDIS_URL=redis://localhost:<porta>  # DEV:{redis_dev} | PROD:{redis_prod}"]
        if qdrant_prod or qdrant_dev:
            lines += [f"QDRANT_URL=http://localhost:<porta>   # DEV:{qdrant_dev} | PROD:{qdrant_prod}"]
        if mq_amqp_prod or mq_amqp_dev:
            lines += [f"RABBITMQ_URL=amqp://guest:guest@localhost:<porta>/  # DEV:{mq_amqp_dev} | PROD:{mq_amqp_prod}"]
        return lines

    sections = [
        "## 🔐 Arquivos .env — Criar **obrigatoriamente** antes de qualquer serviço",
        "",
        "> Crie os três arquivos abaixo na **raiz do projeto**. Valores já preenchidos com as portas corretas.",
        "> `.env.dev` e `.env.prod` estão no `.gitignore`. `.env.example` vai para o Git.",
        "> O mecanismo de seleção é `APP_ENV`: o PS Profile injeta `$env:APP_ENV = \"dev\"` ou `\"prod\"`",
        "> antes de iniciar cada serviço, e o `Settings` carrega `env_file=[f\"../../.env.{APP_ENV}\", ...]`.",
        "",
        "**`.env.dev`**",
        "```env",
        "ENVIRONMENT=dev",
        "LOG_LEVEL=DEBUG",
        "SQL_ECHO=true",
        "",
        "# Database (DEV)",
        "POSTGRES_HOST=localhost",
        f"POSTGRES_PORT={db_port_dev}",
        f"POSTGRES_USER={db_user}",
        f"POSTGRES_PASSWORD={db_pass_dev}",
        f"POSTGRES_DATABASE={db_name_dev}",
        *_optional_stanza_dev(),
        "",
        "# Security",
        "JWT_SECRET_KEY=dev-secret-inseguro-nao-usar-em-prod",
        "ALGORITHM=HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES=1440",
        "",
        "# Portas dos serviços (DEV)",
        f"BACKEND_PORT={back_dev}",
        f"AUTH_PORT={auth_dev}",
        f"FRONTEND_PORT={front_dev}",
        "",
        "# URLs dos serviços (DEV)",
        f"AUTH_SERVICE_URL=http://localhost:{auth_dev}",
        f"FRONTEND_URL=http://localhost:{front_dev}",
        f'BACKEND_CORS_ORIGINS=["http://localhost:{front_dev}"]',
        "```",
        "",
        "**`.env.prod`**",
        "```env",
        "ENVIRONMENT=prod",
        "LOG_LEVEL=INFO",
        "SQL_ECHO=false",
        "",
        "# Database (PROD)",
        "POSTGRES_HOST=localhost",
        f"POSTGRES_PORT={db_port_prod}",
        f"POSTGRES_USER={db_user}",
        f"POSTGRES_PASSWORD={db_pass_prod}",
        f"POSTGRES_DATABASE={db_name_prod}",
        *_optional_stanza_prod(),
        "",
        "# Security — TROQUE antes de ir a produção real",
        "JWT_SECRET_KEY=TROQUE-PARA-VALOR-SEGURO-python-c-import-secrets-print-secrets.token_hex-32",
        "ALGORITHM=HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES=1440",
        "",
        "# Portas dos serviços (PROD)",
        f"BACKEND_PORT={back_prod}",
        f"AUTH_PORT={auth_prod}",
        f"FRONTEND_PORT={front_prod}",
        "",
        "# URLs dos serviços (PROD)",
        f"AUTH_SERVICE_URL=http://localhost:{auth_prod}",
        f"FRONTEND_URL=http://localhost:{front_prod}",
        f'BACKEND_CORS_ORIGINS=["http://localhost:{front_prod}"]',
        "```",
        "",
        "**`.env.example`** ← commitar no Git, sem valores sensíveis",
        "```env",
        "ENVIRONMENT=dev                      # dev | prod",
        "LOG_LEVEL=DEBUG                      # DEBUG | INFO",
        "SQL_ECHO=true                        # true | false",
        "",
        "POSTGRES_HOST=localhost",
        f"POSTGRES_PORT=                       # DEV:{db_port_dev} | PROD:{db_port_prod}",
        f"POSTGRES_USER={db_user}",
        "POSTGRES_PASSWORD=                   # ver 00-variables.md",
        f"POSTGRES_DATABASE=                   # DEV:{db_name_dev} | PROD:{db_name_prod}",
        *_optional_stanza_example(),
        "",
        "JWT_SECRET_KEY=                      # gere: python -c \"import secrets; print(secrets.token_hex(32))\"",
        "ALGORITHM=HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES=1440",
        "",
        f"BACKEND_PORT=                        # DEV:{back_dev} | PROD:{back_prod}",
        f"AUTH_PORT=                           # DEV:{auth_dev} | PROD:{auth_prod}",
        f"FRONTEND_PORT=                       # DEV:{front_dev} | PROD:{front_prod}",
        "",
        "AUTH_SERVICE_URL=http://localhost:<AUTH_PORT>",
        "FRONTEND_URL=http://localhost:<FRONTEND_PORT>",
        'BACKEND_CORS_ORIGINS=["http://localhost:<FRONTEND_PORT>"]',
        "```",
        "",
    ]
    return "\n".join(sections)


def build_footer(file_pairs, split=False, is_module=False, project_key="project", values=None, **_):
    """Monta a seção de execução. A ordem de implementação é a própria seção 3."""
    migration_section = build_migration_instruction(
        file_pairs, split=split, is_module=is_module, project_key=project_key
    )

    if is_module:
        intro = (
            "Leia cada módulo da seção 3 **na ordem indicada** e implemente-o completamente, "
            "**sem aguardar confirmação entre os módulos**.\n"
            "Não acesse nem modifique nenhum arquivo fora dos listados na seção 3."
        )
    else:
        intro = (
            "Leia todos os arquivos de referência acima **na ordem da seção 3** e implemente o projeto completo, "
            "**sem aguardar confirmação entre as fases**."
        )

    env_section = ""
    if not is_module and values:
        env_section = "\n\n" + build_env_section(values)

    return (
        "\n\n# 4. EXECUÇÃO\n\n"
        f"{intro}\n\n"
        "**Regras de execução:**\n"
        "- Execute cada arquivo até a conclusão antes de avançar para o próximo.\n"
        "- Ao concluir cada arquivo/fase, anuncie brevemente o que foi feito e prossiga imediatamente.\n"
        "- Substitua todos os `{{ VAR_NAME }}` pelos valores definidos na seção 1 antes de gerar qualquer arquivo.\n"
        "- Em caso de dúvida sobre uma decisão de implementação, escolha a opção mais conservadora e documente no código.\n"
        "- O `README.md` do projeto deve incluir no rodapé: "
        "`by [Luiz Gustavo Quinelato (Gus)](https://www.linkedin.com/in/gustavoquinelato/)`\n"
        f"{env_section}\n\n"
        f"{migration_section}\n"
    )


def _sync_custom_to_project(blueprint_project_root: Path, project_initial: Path) -> None:
    """Copia docs de módulo de projects/<key>/ → PROJECT_ROOT/docs/initial/custom/.

    Copia todos os .md da raiz do projeto no blueprint, exceto 00-variables.md.
    """
    import shutil
    dest = project_initial / "custom"
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in blueprint_project_root.glob("*.md"):
        if src.name in EXCLUDED_FILES or any(src.name.startswith(p) for p in EXCLUDED_PREFIXES):
            continue
        shutil.copy2(src, dest / src.name)
        count += 1
    if count:
        print(f"   🔄 {count} doc(s) de módulo sincronizados → docs/initial/custom/")


def generate_base_prompt(project_key: str, values: dict, project_root: "Path") -> None:
    """Gera PROMPT_INICIAL_<KEY>.md em PROJECT_ROOT/docs/prompts/.

    Chamada por create_project.py ao final da criação do projeto.
    Recebe as variáveis já resolvidas (values) e o caminho do projeto destino.
    Lê os docs de docs/initial/ (já gerados pelo create_project.py).
    """
    docs_initial = project_root / "docs" / "initial"
    prompts_dir  = project_root / "docs" / "prompts"
    project_key_u = project_key.upper()

    if not docs_initial.is_dir():
        print(f"⚠️  docs/initial/ não encontrado — prompt base não gerado.")
        return

    prompt_filename = f"PROMPT_INICIAL_{project_key_u}.md"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    output_file = prompts_dir / prompt_filename

    print(f"🚀 Gerando {output_file} (Padrão)...")

    folder_for_pairs = str(docs_initial)
    file_pairs = get_file_pairs(folder_for_pairs, values, is_base=True)
    if not file_pairs:
        print(f"⚠️  Nenhum arquivo base encontrado em: {folder_for_pairs}")
        return

    header = build_header(values, is_module=False)
    body   = build_body_mode_a(file_pairs, is_module=False, path_prefix="docs/initial")
    footer = build_footer(file_pairs, split=False, is_module=False, project_key=project_key, values=values)

    output_file.write_text(header + "\n" + body + footer, encoding="utf-8")
    lines = sum(1 for _ in open(output_file, encoding="utf-8"))
    print(f"✅ {output_file} — {lines} linhas")
    print(f"   → Abra o Augment no workspace do projeto e use @docs/prompts/{prompt_filename}")


def generate_prompt(project=None, unified=False, split=False):
    """Gera PROMPT_CUSTOM_<KEY>.md a partir dos docs de módulo em projects/<key>/."""
    if project is None:
        print("❌ Informe o nome do projeto  ex: python scripts/generate_prompt.py plurus")
        return

    # 1. Detecta contexto no blueprint
    blueprint_project_root, variables_file = detect_project_context(project)

    if not blueprint_project_root.is_dir():
        print(f"❌ Projeto não encontrado no blueprint: {blueprint_project_root}")
        return

    # 2. Lê variáveis de projects/<key>/00-variables.md
    variables = read_variables(variables_file)
    if not variables:
        return

    # 3. Resolve caminhos a partir de PROJECT_ROOT (projeto real)
    project_actual_root_str = variables.get('PROJECT_ROOT', '')
    if not project_actual_root_str:
        print("❌ PROJECT_ROOT não definido em 00-variables.md")
        return
    actual_root   = Path(project_actual_root_str)
    docs_initial  = actual_root / "docs" / "initial"
    prompts_dir   = actual_root / "docs" / "prompts"
    project_key   = blueprint_project_root.name.lower()
    project_key_u = project_key.upper()

    # 4. Lê docs de módulo direto de projects/<key>/ e sincroniza para docs/initial/custom/
    _sync_custom_to_project(blueprint_project_root, docs_initial)
    folder_for_pairs = str(docs_initial / "custom")
    path_prefix      = "docs/initial/custom"

    prompt_filename = f"PROMPT_CUSTOM_{project_key_u}.md"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    output_file = str(prompts_dir / prompt_filename)

    labels = []
    if unified: labels.append('Unificado')
    if split:   labels.append('Split')
    if not labels: labels.append('Padrão')
    print(f"🚀 Gerando {output_file} ({' + '.join(labels)})...")

    file_pairs = get_file_pairs(folder_for_pairs, variables, is_base=False)
    if not file_pairs:
        print(f"⚠️  Nenhum arquivo de módulo encontrado em: {blueprint_project_root}")
        print(f"   Adicione docs de módulo (.md) em projects/{project_key}/ e tente novamente.")
        return

    header = build_header(variables, is_module=True)
    body   = build_body_mode_b(file_pairs, variables, is_module=True) if unified \
        else build_body_mode_a(file_pairs, is_module=True, path_prefix=path_prefix)
    footer = build_footer(file_pairs, split=split, is_module=True, project_key=project_key, values=variables)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(header + "\n" + body + footer)

    lines = sum(1 for _ in open(output_file, encoding='utf-8'))
    print(f"✅ {output_file} — {lines} linhas")
    print(f"   Destino   : {actual_root}")
    print(f"   Módulos   : projects/{project_key}/  ({len(file_pairs)} arquivo(s))")
    print(f"   Sincron.  : docs/initial/custom/")
    print(f"   Modo      : {'Unificado (conteúdo embutido)' if unified else 'Padrão (referências a arquivos)'}")
    print(f"   Migration : {'Um arquivo por módulo (-s)' if split else 'Unificado'}")
    if not unified:
        print("   → Ideal para Augment Code, Cursor, Windsurf (abre no workspace do projeto).")
    else:
        print("   → Ideal para Claude.ai, ChatGPT.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Gera PROMPT_CUSTOM_<CHAVE>.md a partir dos docs de módulo em projects/<chave>/.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        'project',
        metavar='PROJETO',
        help='Nome da pasta do projeto em projects/ (ex: plurus)'
    )
    parser.add_argument(
        '-u', '--unified',
        action='store_true',
        help='Embute o conteúdo dos arquivos no prompt (ideal para Claude.ai, ChatGPT)'
    )
    parser.add_argument(
        '-s', '--split',
        action='store_true',
        help='Instrui o agente a criar 1 migration por arquivo de módulo (default: unificado)'
    )
    args = parser.parse_args()
    generate_prompt(project=args.project, unified=args.unified, split=args.split)
