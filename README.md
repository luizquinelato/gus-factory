# gus-factory — Fábrica de Projetos

Plataforma de scaffolding para criar e gerenciar múltiplos projetos de qualquer tipo — com controle centralizado de portas, geração automática de scripts PowerShell e prompts de execução para IA.

Cada template define um tipo de projeto. O primeiro é **`saas-blueprint-v1`** (SaaS multi-tenant com FastAPI + React). Outros templates — ERPs, APIs públicas, ferramentas internas — podem ser adicionados à medida que a factory cresce.

## 📁 Estrutura

```
gus-factory/
├── README.md
├── helms/                             ← Configuração central compartilhada
│   ├── ports.yml                      ← Registro de portas + projetos (Source of Truth)
│   └── gus.ps1                        ← CLI global (dot-source no seu $PROFILE)
├── projects/                          ← Docs de módulos custom por projeto (lidos por generate_prompt.py)
│   └── <chave>/
│       └── NN-<modulo>.md             ← Um .md por módulo custom do projeto
├── scripts/                           ← Scripts globais da factory
│   ├── create_project.py              ← Cria / atualiza um projeto
│   ├── delete_helm.py                 ← Remove projeto da configuração central
│   ├── generate_prompt.py             ← Gera prompt de execução para IA
│   ├── setup_venvs.py                 ← Configura venvs Python de todos os serviços
│   └── clean_project.py              ← Remove caches (pycache, node_modules) por projeto
└── templates/                         ← Templates por tipo de projeto
    ├── docs/                          ← Docs base com {{ VAR }} placeholders
    ├── docker/                        ← Templates docker-compose (.j2)
    ├── scripts/                       ← Scripts base copiados ao criar projetos
    └── projects/
        └── saas-blueprint-v1/         ← Template SaaS multi-tenant (FastAPI + React)
```

> O código real de cada projeto vive em `PROJECT_ROOT` (ex: `C:\Workspace\gus-meu-erp`), **não** neste repositório.

---

## 🔑 Conceitos Fundamentais

**Um template = um tipo de projeto.**
Cada template em `templates/projects/` define a stack, a estrutura de serviços e os docs de arquitetura para um tipo específico de projeto. A factory pode ter quantos templates forem necessários.

**Docker = infraestrutura apenas.**
Cada projeto roda seus próprios containers para banco de dados, cache e mensageria. As aplicações **rodam diretamente no host**.

**`helms/ports.yml` é o único registro de portas.**
Ao criar um projeto, as portas são calculadas automaticamente para evitar colisões com tudo que já existe no host. Ao deletar, as portas são liberadas para reutilização.

**Um projeto ativo = entrada em `helms/ports.yml` + `PROJECT_ROOT` (código real) + opcionalmente `projects/<chave>/` (docs de módulos custom).**
A factory mantém apenas a configuração central (`ports.yml`) e, quando aplicável, os `.md` de módulos custom em `projects/<chave>/` (lidos pelo `generate_prompt.py`). Todo o código, docs, migrations, docker-compose e prompts é gerado diretamente no `PROJECT_ROOT` a partir do template.

---

## 🚀 Criar / Atualizar um Projeto

```powershell
python scripts/create_project.py                       # menu interativo
python scripts/create_project.py --template <key|alias> # pula o menu
```

O script é **manifest-driven** — cada template declara suas features e regras em `template.yml`. O fluxo interativo coleta:

| # | Seção | O que define |
|---|---|---|
| 1 | Template | Escolhe o blueprint a clonar (ex: `saas-blueprint-v1`) |
| 2 | Identidade | Chave, alias, nome, descrição, caminho raiz, cor PS, timezone |
| 3 | Features | Toggles declarados em `template.yml` (ex: redis, replica, etl_frontend, qdrant, rabbit) |
| 4 | Portas | Backend/Auth/Frontend/DB prod+dev + extras — calculadas sem colisão |

Ao confirmar, o script executa:

| # | O que faz | Onde |
|---|---|---|
| 1 | Verifica se `PROJECT_ROOT` já existe — exige confirmação (`APAGAR`) para limpar | host |
| 2 | Clona a árvore do template com substituição de identidade (canônica → nova) | `PROJECT_ROOT/` |
| 3 | Processa marcadores `@IF feat / @ENDIF feat` (remove blocos de features desativadas) | `PROJECT_ROOT/` |
| 4 | Remove paths listados em `features[f].removes_when_disabled` para features off | `PROJECT_ROOT/` |
| 5 | Registra portas, cor, identidade e extras | `helms/ports.yml` |

O `helms/gus.ps1` lê projetos **dinamicamente** de `ports.yml` — nenhum arquivo de profile é gerado ou editado. Se a chave já existir, entra em **modo atualização**: valores atuais viram padrão e as portas são recalculadas preservando as alocações existentes onde possível.

---

## 🗂️ Registro de Portas — `helms/ports.yml`

```yaml
shared_services:                       # Todas as portas ocupadas no host
  backend_prod:
  - {port: 9000, project: meu_erp}
  db_prod:
  - {port: 5434, project: meu_erp}

projects:
  meu_erp:
    label: Meu ERP — descrição
    root: C:\Workspace\gus-meu-erp
    color: Green
    prod:
      svc: {backend: 9000, auth: 9100, frontend: 5175}
      db:  {port: 5434, name: meu_erp, user: meu_erp, pass: "***"}
    dev:
      svc: {backend: 9010, auth: 9110, frontend: 5176}
      db:  {port: 5436, name: meu_erp_dev, user: meu_erp, pass: "***"}
    extra_ports:
    - {name: redis, port: 6380, proto: tcp}
```

### Convenção de portas calculadas automaticamente

| Serviço | Lógica | Exemplo |
|---|---|---|
| `backend_prod` | Próximo múltiplo de 1000 acima do maior backend | 9000, 10000… |
| `auth_prod` | `backend_prod + 100` | 9100 |
| `backend_dev` | `backend_prod + 10` | 9010 |
| `auth_dev` | `backend_prod + 110` | 9110 |
| `frontend_prod` | Próximo bloco de 2 portas livres | 5175, 5177… |
| `frontend_dev` | `frontend_prod + 1` | 5176 |
| `db_prod` | Próximo bloco de 4 portas livres | 5434 |
| `db_prod_replica` | `db_prod + 1` | 5435 |
| `db_dev` | `db_prod + 2` | 5436 |
| `db_dev_replica` | `db_prod + 3` | 5437 |
| Redis / RabbitMQ / Qdrant | Próxima porta livre na faixa do serviço | 6380, 5673… |

---

## 🖥️ CLI `gus` — `helms/gus.ps1`

CLI global que lê `helms/ports.yml` em runtime — novos projetos ficam disponíveis **sem recarregar o profile**.

### Configuração inicial (apenas uma vez)

```powershell
# 1. Cria o $PROFILE se ainda não existir
if (!(Test-Path $PROFILE)) { New-Item -Path $PROFILE -ItemType File -Force }

# 2. Adiciona o dot-source ao fim do seu $PROFILE
Add-Content $PROFILE '. "C:\Workspace\gus-factory\helms\gus.ps1"'

# 3. Recarrega o profile na sessão atual
. $PROFILE
```

### Convenção de argumentos

Todo comando aceita um ou mais projetos — `<proj>` para PROD, `<proj>-dev` para DEV:

| Target | Significado |
|---|---|
| `<proj>` | Projeto em PROD (ex: `gus dkup pulse`) |
| `<proj>-dev` | Projeto em DEV (ex: `gus dkup pulse-dev`) |
| `all` | Todos os projetos, PROD **e** DEV |
| `all-prod` / `all-dev` | Todos os projetos em PROD / DEV |

Aliases definidos em `ports.yml` (`alias:`) também são aceitos.

### Comandos principais

| Grupo | Comando | Ação |
|---|---|---|
| **Docker** | `gus dkup / dkdown / dkstart / dkstop / dkrestart <proj...>` | Ciclo de vida dos containers |
|  | `gus dkdown <proj...> -v` | Down + remove volumes |
|  | `gus dks <proj...>` | `docker ps` filtrado por projeto |
|  | `gus dkl <proj...>` | Logs em nova aba |
| **Migrations** | `gus dbm <proj...>` | Aplica migrations pendentes |
|  | `gus dbmv <proj> <ver>` / `gus dbrv <proj> <ver>` | Apply / rollback até versão N |
|  | `gus dbmc <proj> <nome>` | Cria nova migration |
|  | `gus dbs <proj...>` / `gus dbr <proj...>` | Status / rollback total |
| **Venvs** | `gus venvs <proj...> [--force] [--backend] [--auth] [--frontend] [--frontend-etl]` | (Re)cria venvs Python |
| **App (tabs)** | `gus rat <proj...>` | Back + auth + front + etl em abas (janela atual) |
|  | `gus ratp <proj...>` | Nova janela por projeto |
|  | `gus back / auth / front / etl <proj...>` | Sobe um serviço específico |
| **Navegação** | `gus cd [--back\|--front\|--auth\|--etl\|--scripts] <proj>` | Troca para o diretório do serviço |
|  | `gus cd --factory` / `gus cd --blueprint` | Raiz da factory / do template principal |
| **Cleanup** | `gus qdc <proj>` / `gus rbc <proj>` | Limpa Qdrant / RabbitMQ do projeto |
| **Utilitários** | `gus list` / `gus help` | Lista projetos / exibe ajuda completa |

---

## 🗑️ Deletar um Projeto

```powershell
python scripts/delete_helm.py <chave|alias>           # só ports.yml
python scripts/delete_helm.py <chave|alias> --force   # + apaga diretório do projeto
```

Remove o projeto de `helms/ports.yml` (confirma antes de executar):

- Entrada em `projects[<chave>]`
- Todas as ocorrências em `shared_services[*]` (portas liberadas)
- Referências a `<chave>` em `conflicts_with` de outros projetos

As portas ficam imediatamente disponíveis para o próximo `create_project.py`.
Como o `gus.ps1` lê `ports.yml` em runtime, o projeto desaparece do `gus list` / `gus help` imediatamente.

Sem `--force`, os arquivos em `PROJECT_ROOT` **não são tocados** — o comando atua apenas na configuração central.
Com `--force`, o diretório indicado em `projects[<chave>].root` é apagado recursivamente após confirmação extra (digite a chave do projeto para confirmar).

---

## 📝 Gerar o Prompt de Módulos Custom

Após `create_project.py`, adicione os docs de módulo diretamente em `projects/<chave>/` e rode:

```powershell
# Prompt de módulos custom (lê projects/<chave>/*.md)
python scripts/generate_prompt.py <chave>

# Conteúdo embutido no prompt (Claude.ai, ChatGPT)
python scripts/generate_prompt.py <chave> -u

# 1 migration por arquivo de módulo
python scripts/generate_prompt.py <chave> -s
```

Gera em `PROJECT_ROOT/docs/prompts/`:
- `PROMPT_CUSTOM_<CHAVE>.md` — prompt de extensão de módulos

> Os docs de `projects/<chave>/` são sincronizados automaticamente para
> `PROJECT_ROOT/docs/initial/custom/` a cada geração — ficam disponíveis como
> referência `@docs/initial/custom/` no workspace do Augment Code.

### Iniciando com Augment Code

Abra o Augment no workspace do **projeto real** (`PROJECT_ROOT`) e envie:

> *"Implemente os módulos usando @docs/prompts/PROMPT_CUSTOM_\<CHAVE\>.md como guia. Crie tasks para cada módulo listado e execute em sequência, sem iteração."*

---

## ⚙️ Pré-requisitos

- **Python 3.11+** com PyYAML: `pip install pyyaml`
- **Docker Desktop** (infraestrutura: DB, Redis, RabbitMQ, Qdrant)
- **Windows Terminal** com PowerShell (para os aliases `rat-*`)

---

## 🛡️ Princípios da Factory

1. **Docker = Infraestrutura** — Apps rodam no host; Docker apenas para DB / Cache / Queue.
2. **Portas centralizadas** — Nenhuma porta é escolhida manualmente; tudo passa pelo `ports.yml`.
3. **Sem secrets no repositório** — `00-variables.md` e `.env` nunca são commitados.
4. **Templates isolados** — Cada template em `templates/projects/` é independente e auto-contido.
5. **Scripts globais > scripts locais** — Operações que afetam múltiplos projetos vivem em `scripts/`; o que é específico de um projeto vive dentro do template.

> Princípios específicos de cada tipo de projeto (ex: multi-tenancy, design system, auth isolation) estão documentados dentro do template correspondente em `templates/projects/<template>/docs/`.

---

*by [Luiz Gustavo Quinelato (Gus)](https://www.linkedin.com/in/gustavoquinelato/)*
