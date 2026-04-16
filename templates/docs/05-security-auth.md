<!-- blueprint: db_changes=false seed_data=false -->
# 05. Segurança, Autenticação e RBAC

Este documento define a arquitetura de segurança, o Auth Service isolado e o controle de acesso baseado em roles (RBAC).

## 🔑 1. Hashing de Senha (bcrypt)

Use `bcrypt` **diretamente** — não use `passlib` ou qualquer outra camada de abstração.

```python
# services/auth-service/app/core/security.py
import bcrypt

def hash_password(password: str) -> str:
    """Gera hash bcrypt. Use no cadastro e na troca de senha."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica senha contra o hash armazenado no banco."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
```

> `passlib[bcrypt]` **não deve ser usado** — é uma abstração não solicitada que ficou defasada em relação às versões modernas do `bcrypt`.

## 🔐 2. Arquitetura do Auth Service

O Auth Service é um microserviço isolado (porta `{{ AUTH_PORT }}`) responsável exclusivamente por:
1. Validar credenciais (login).
2. Gerar tokens JWT (Access e Refresh).
3. Gerenciar sessões na tabela `user_sessions`.

O Frontend **nunca** chama o Auth Service diretamente. O fluxo é:
`Frontend -> Backend (/api/v1/auth/login) -> Auth Service -> Backend -> Frontend`

## 🧩 3. Provider Pattern (Abstração de Auth)

Para permitir a troca futura de autenticação local para Auth0, Okta ou Cognito sem alterar o código de negócio, utilizamos o Provider Pattern.

```python
# services/auth-service/app/providers/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any

class AuthProvider(ABC):
    @abstractmethod
    def authenticate(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Valida credenciais e retorna dados do usuário."""
        pass

    @abstractmethod
    def generate_tokens(self, user_data: Dict[str, Any]) -> Dict[str, str]:
        """Gera access_token e refresh_token."""
        pass

    @abstractmethod
    def validate_token(self, token: str) -> Dict[str, Any]:
        """Valida um token e retorna o payload."""
        pass
```

## 🛡️ 4. RBAC — Controle de Acesso Baseado em Página

O modelo de RBAC do sistema é **baseado em página** (`page_key`), não em matriz `Resource × Action`.
**Nunca use o padrão Resource × Action — ele foi removido.**

### Hierarquia de Roles

```
view (0)  <  user (1)  <  admin (2)
```

Um usuário acessa uma página se `role_level(user.role) >= role_level(page.min_role)`.
Super admins (`is_admin = true`) têm acesso irrestrito a tudo, independente da hierarquia.

### Dependências FastAPI (arquivo canônico)

```python
# services/backend/app/dependencies/auth.py
from fastapi import Depends, HTTPException, status, Request
from typing import Dict, Any
import httpx

from app.core.config import get_settings

settings = get_settings()

ROLE_LEVELS = {"view": 0, "user": 1, "admin": 2}

async def require_authentication(request: Request) -> Dict[str, Any]:
    """Valida o token JWT chamando o Auth Service via chave interna."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente ou inválido")

    token = auth_header.split(" ")[1]

    # Chama o Auth Service — localhost, nunca nome de container Docker
    # Envia INTERNAL_API_KEY no header para proteger o endpoint de validação
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.AUTH_SERVICE_URL}/api/v1/token/validate",
                json={"token": token},
                headers={"X-Internal-Key": settings.INTERNAL_API_KEY}
            )
            response.raise_for_status()
            return response.json()  # payload: {id, email, role, is_admin, tenant_id, ...}
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado")


def require_admin(current_user: dict = Depends(require_authentication)):
    """Garante que o usuário é super admin (`is_admin = true`)."""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado. Requer privilégios de administrador.")
    return current_user


def require_page_access(page_key: str):
    """
    Fábrica de dependências para checar acesso por page_key.

    Fluxo:
    1. Super admins → acesso total
    2. Busca `min_role` da página na tabela `pages` (por tenant)
    3. Compara role_level(user.role) >= role_level(page.min_role)

    Uso nos routers:
        current_user = Depends(require_page_access("users"))
        current_user = Depends(require_page_access("reports"))
    """
    def checker(
        request: Request,
        current_user: dict = Depends(require_authentication)
    ):
        if current_user.get("is_admin"):
            return current_user

        # O page_min_role é injetado no payload do token pelo Auth Service
        # (lido da tabela `pages` no momento da validação do token)
        # Alternativamente, pode ser consultado via DB aqui se não estiver no payload.
        from app.core.database import get_db_session
        # Consulta sincrona: busca min_role para o page_key e tenant
        # (implementação real veja services/backend/app/dependencies/auth.py)
        user_level = ROLE_LEVELS.get(current_user.get("role", "view"), 0)
        # Se page não encontrada ou sem restrição, bloqueia por segurança
        page_min_role = current_user.get("page_access", {}).get(page_key, "admin")
        page_level = ROLE_LEVELS.get(page_min_role, 2)

        if user_level < page_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso negado à página '{page_key}'."
            )
        return current_user
    return checker
```

### Roles do Sistema (seed obrigatório)

| Role | `role_level` | Descrição |
|---|---|---|
| `view` | 0 | Somente leitura — dashboards e relatórios |
| `user` | 1 | Operador — criação e edição de registros |
| `admin` | 2 | Administrador — acesso total ao tenant |

Roles adicionais específicas do projeto são criadas a partir de `0003_seed_roles.py` usando esses três como base.

### Uso nos Routers

```python
# ✅ Correto — acesso baseado em page_key
@router.get("/users")
def list_users(current_user = Depends(require_page_access("users"))):
    ...

# ✅ Correto — apenas super admins
@router.delete("/admin/tenants/{id}")
def delete_tenant(current_user = Depends(require_admin)):
    ...

# ❌ Proibido — padrão Resource×Action foi removido
# current_user = Depends(require_permission("users", "write"))
```

## 🔄 5. Estratégia de Sessão — Access Token + Refresh Token

O sistema usa tokens de **duas camadas**:

| Token | Tipo | TTL | Armazenamento | Validação |
|---|---|---|---|---|
| Access Token | JWT assinado | **5 min** | `localStorage` | Assinatura + `exp` + `sid` |
| Refresh Token | Opaque hex (64 chars) | **7 dias** | `localStorage` | Hash SHA-256 na tabela `user_sessions` |

### Ciclo completo

```
Login → [access_token (5min) + refresh_token (7d)]
              │
              ▼ (qualquer request)
       Authorization: Bearer <access_token>
              │
         ┌────┴────┐
         │  401?   │ ← access token expirado ou revogado
         └────┬────┘
              │ SIM
              ▼
       POST /auth/refresh  { refresh_token }
              │
         ┌────┴─────────┐
         │ refresh ok?  │
         └──┬──────┬────┘
            │SIM   │NÃO
            ▼      ▼
     novo token  Logout → /login
     retry req
```

### Rotação do Refresh Token
A cada `POST /auth/refresh` o servidor:
1. Valida o refresh token antigo (ativo + não expirado)
2. Gera um **novo** refresh token (invalida o antigo — token rotation)
3. Retorna novo `access_token` + novo `refresh_token`

> Isso previne **replay attacks**: se um refresh token for interceptado e usado, o token legítimo é invalidado, a próxima requisição com o token original falha e o servidor detecta a anomalia.

### Revogação Imediata (Logout)
- O JWT carrega `"sid": session_id` (PK da `user_sessions`)
- Em `/token/validate`, o auth-service verifica `is_session_active_by_id(session_id)` — O(1) por PK
- Logout invalida o session_id → access tokens emitidos para aquela sessão são rejeitados em ≤5 min (até o exp natural)

### Configurações
```env
ACCESS_TOKEN_EXPIRE_MINUTES=5
REFRESH_TOKEN_EXPIRE_DAYS=7
```

## 🔑 6. INTERNAL_API_KEY — Comunicação Inter-Serviços

Toda comunicação de serviço a serviço (ex: Backend → Auth Service) **deve** incluir o header `X-Internal-Key` para proteger endpoints internos de chamadas externas não autorizadas.

```
X-Internal-Key: <INTERNAL_API_KEY>
```

### Variáveis de ambiente obrigatórias

```env
# .env.dev e .env.prod (raiz do projeto)
INTERNAL_API_KEY=gera-um-uuid-v4-longo-aqui   # nunca commitar o valor real
```

### No Settings (config.py)

```python
class Settings(BaseSettings):
    # ...
    INTERNAL_API_KEY: str  # obrigatório — sem default para forçar configuração explícita
```

### No Auth Service — validação do header

```python
# services/auth-service/app/dependencies/internal.py
from fastapi import Header, HTTPException, status
from app.core.config import get_settings

settings = get_settings()

def require_internal_key(x_internal_key: str = Header(...)):
    """Protege endpoints internos (ex: /token/validate) de chamadas externas."""
    if x_internal_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chave interna inválida.")

# Uso no router:
@router.post("/token/validate", dependencies=[Depends(require_internal_key)])
async def validate_token(payload: TokenPayload):
    ...
```

> **Regra:** endpoints do Auth Service que só devem ser chamados por outros serviços internos **sempre** usam `Depends(require_internal_key)`. Nunca exponha esses endpoints sem proteção.
