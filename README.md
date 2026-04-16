# gus-factory — Fábrica de Projetos

Plataforma de scaffolding para criar e gerenciar múltiplos projetos de qualquer tipo — com controle centralizado de portas, geração automática de scripts PowerShell e prompts de execução para IA.

Cada template define um tipo de projeto. O primeiro é **`saas-blueprint-v1`** (SaaS multi-tenant com FastAPI + React). Outros templates — ERPs, APIs públicas, ferramentas internas — podem ser adicionados à medida que a factory cresce.

## 📁 Estrutura

```
gus-factory/
├── README.md
├── helms/                             ← Configuração central compartilhada
│   ├── ports.yml                      ← Registro de portas (Source of Truth)
│   └── gus.ps1                        ← Profile PowerShell gerado; inclua em $PROFILE
├── projects/                          ← Um subdiretório por projeto ativo (referência)
│   └── <chave>/
│       ├── 00-variables.md            ← Variáveis do projeto (.gitignore)
│       └── custom/                    ← Docs de módulos de negócio do projeto
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

**Um projeto ativo = `projects/<chave>/` (referência) + `PROJECT_ROOT` (código real).**
A factory mantém apenas `00-variables.md` (nunca commitado) e os docs `custom/` de cada projeto. Todo o restante — docs, migrations, docker-compose e prompts — é gerado diretamente no `PROJECT_ROOT`.

---

## 🚀 Criar / Atualizar um Projeto

```powershell
python scripts/create_project.py
```

O script guia interativamente por 5 seções (↵ aceita o valor sugerido):

| # | Seção | O que define |
|---|---|---|
| 1 | Projeto | Chave, nome, descrição, caminho raiz, cor PS |
| 2 | Portas | Backend/Auth/Frontend/DB prod+dev — calculadas sem conflito |
| 3 | Banco de Dados | Nome, usuário e senha do banco |
| 4 | Serviços Docker | Redis, RabbitMQ, Qdrant — porta calculada em tempo real |
| 4b | Camada de IA | LLM, modelo e agentes (default S se Qdrant selecionado) |
| 5 | Usuários e Admin | USER_ROLES, AUTH_PROVIDER, dados do admin inicial |

Ao confirmar, o script executa automaticamente:

| # | O que faz | Onde |
|---|---|---|
| 1 | Verifica se `PROJECT_ROOT` já existe — alerta e pede confirmação para limpar | host |
| 2 | Copia docs base com vars substituídas | `PROJECT_ROOT/docs/initial/` |
| 3 | Copia migration runner + `0001_initial_schema` + `0002_initial_seed_data` com vars substituídas | `PROJECT_ROOT/services/backend/scripts/` |
| 4 | Gera os 3 docker-compose files (ativa serviços selecionados) | `PROJECT_ROOT/` |
| 5 | Cria `projects/<chave>/00-variables.md` | blueprint |
| 6 | Registra todas as portas | `helms/ports.yml` |
| 7 | Adiciona bloco `# START … # END` | `helms/gus.ps1` |

Se a chave já existir, entra em **modo atualização**: valores atuais viram padrão, portas são recalculadas e a seção do profile é substituída cirurgicamente.

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

## 🖥️ PowerShell Profile — `helms/gus.ps1`

Gerado e mantido automaticamente. Para ativar os aliases em qualquer terminal:

### Configuração inicial (apenas uma vez)

```powershell
# 1. Cria o $PROFILE se ainda não existir
if (!(Test-Path $PROFILE)) { New-Item -Path $PROFILE -ItemType File -Force }

# 2. Adiciona o dot-source ao fim do seu $PROFILE
Add-Content $PROFILE '. "C:\Workspace\gus-factory\helms\gus.ps1"'

# 3. Recarrega o profile na sessão atual
. $PROFILE
```

### Recarregar após cada atualização do blueprint

```powershell
. $PROFILE
```

Cada projeto ocupa um bloco delimitado por marcadores:

```powershell
# START meu_erp
# =================================================================
# MEU_ERP — Meu ERP
# Root   : C:\Workspace\gus-meu-erp
# PROD   : Backend :9000 | Auth :9100 | Frontend :5175 | DB :5434
# DEV    : Backend :9010 | Auth :9110 | Frontend :5176 | DB :5436
# =================================================================
function meu_erp-rat     { ... }   # Sobe Docker + abre tabs PROD
function meu_erp-rat-dev { ... }   # Sobe Docker + abre tabs DEV
Set-Alias -Name rat-meu_erp      -Value meu_erp-rat
# END meu_erp
```

**Aliases disponíveis** (`<p>` = chave do projeto):

| Alias | Ação |
|---|---|
| `rat-<p>` / `rat-<p>-dev` | Docker up + abre tabs PROD / DEV |
| `dkup-<p>` / `dkdown-<p>` | Docker PROD up / down |
| `dkup-<p>-dev` / `dkdown-<p>-dev` | Docker DEV up / down |
| `dbm-<p>` / `dbr-<p>` / `dbs-<p>` | Migration apply / rollback / status PROD |
| `dbm-<p>-dev` / `dbr-<p>-dev` / `dbs-<p>-dev` | Migration apply / rollback / status DEV |
| `kill-<p>` | Para todos os processos nas portas do projeto |

---

## 🗑️ Deletar um Projeto

```powershell
python scripts/delete_helm.py <chave>
```

Remove **cirurgicamente** (confirma antes de executar):

- Entrada em `helms/ports.yml` (projeto + todas as portas em `shared_services`)
- Bloco `# START <chave>` … `# END <chave>` em `helms/gus.ps1`
- Linha do SUMMARY no profile

As portas ficam imediatamente disponíveis para o próximo `create_project.py`.
Os arquivos em `projects/<chave>/` **não são tocados**.

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
