<!-- blueprint: db_changes=false seed_data=false -->
# 05. Security, Authentication and RBAC

This document defines the security architecture, the isolated Auth Service and role-based access control (RBAC).

## 🔑 1. Password Hashing (bcrypt)

Use `bcrypt` **directly** — do not use `passlib` or any other abstraction layer.

```python
# services/auth-service/app/core/security.py
import bcrypt

def hash_password(password: str) -> str:
    """Generates bcrypt hash. Use on registration and password change."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies password against the stored hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
```

> `passlib[bcrypt]` **must not be used** — it is an unsolicited abstraction that fell behind modern `bcrypt` versions.

## 🔐 2. Auth Service Architecture

The Auth Service is an isolated microservice (port `{{ AUTH_PORT }}`) responsible exclusively for:
1. Validating credentials (login).
2. Generating JWT tokens (Access and Refresh).
3. Managing sessions in the `user_sessions` table.

The Frontend **never** calls the Auth Service directly. The flow is:
`Frontend -> Backend (/api/v1/auth/login) -> Auth Service -> Backend -> Frontend`

## 🧩 3. Provider Pattern (Auth Abstraction)

To allow future switching from local auth to Auth0, Okta or Cognito without changing business code, we use the Provider Pattern.

```python
# services/auth-service/app/providers/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any

class AuthProvider(ABC):
    @abstractmethod
    def authenticate(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Validates credentials and returns user data."""
        pass

    @abstractmethod
    def generate_tokens(self, user_data: Dict[str, Any]) -> Dict[str, str]:
        """Generates access_token and refresh_token."""
        pass

    @abstractmethod
    def validate_token(self, token: str) -> Dict[str, Any]:
        """Validates a token and returns the payload."""
        pass
```

## 🛡️ 4. RBAC (Role-Based Access Control)

Access control is based on a standard permissions matrix, with the possibility of granular overrides per user.

### Default Permissions Matrix

```python
# services/auth-service/app/core/rbac.py  ← RBAC lives in Auth Service (source of truth)
from enum import Enum
from typing import Dict, Set

class Role(str, Enum):
    ADMIN = "admin"
    USER = "user"
    VIEW = "view"
    # Add other roles based on {{ USER_ROLES }}

class Resource(str, Enum):
    USERS = "users"
    SETTINGS = "settings"
    REPORTS = "reports"
    ADMIN_PANEL = "admin_panel"

class Action(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"

# Default matrix — uses Set[Action] for O(1) permission checks
DEFAULT_PERMISSIONS: Dict[Role, Dict[Resource, Set[Action]]] = {
    Role.ADMIN: {
        Resource.USERS: {Action.READ, Action.WRITE, Action.DELETE, Action.ADMIN},
        Resource.SETTINGS: {Action.READ, Action.WRITE, Action.ADMIN},
        Resource.REPORTS: {Action.READ, Action.WRITE, Action.DELETE, Action.ADMIN},
        Resource.ADMIN_PANEL: {Action.READ, Action.WRITE, Action.DELETE, Action.ADMIN},
    },
    Role.USER: {
        Resource.USERS: {Action.READ},
        Resource.SETTINGS: {Action.READ},
        Resource.REPORTS: {Action.READ, Action.WRITE},
        Resource.ADMIN_PANEL: set(),
    },
    Role.VIEW: {
        Resource.USERS: {Action.READ},
        Resource.SETTINGS: set(),
        Resource.REPORTS: {Action.READ},
        Resource.ADMIN_PANEL: set(),
    },
}

def has_permission(is_admin: bool, role: str, resource: str, action: str) -> bool:
    """Checks RBAC using role and admin flag."""
    if is_admin:
        return True
    try:
        role_enum = Role(role)
        resource_enum = Resource(resource)
        action_enum = Action(action)
    except ValueError:
        return False
    return action_enum in DEFAULT_PERMISSIONS.get(role_enum, {}).get(resource_enum, set())
```

### FastAPI Dependencies for RBAC

```python
# services/backend/app/dependencies/auth.py
from fastapi import Depends, HTTPException, status, Request
from typing import Dict, Any
import httpx

from app.core.config import get_settings
from app.core.rbac import Role, Resource, Action, DEFAULT_PERMISSIONS

settings = get_settings()

async def require_authentication(request: Request) -> Dict[str, Any]:
    """Validates JWT token by calling the Auth Service."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid token")

    token = auth_header.split(" ")[1]

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.AUTH_SERVICE_URL}/api/v1/token/validate",
                json={"token": token}
            )
            response.raise_for_status()
            return response.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

def require_admin(current_user: dict = Depends(require_authentication)):
    """Ensures the user is a system super admin."""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Requires administrator privileges.")
    return current_user

def require_permission(resource: Resource, action: Action):
    """Dependency factory for checking granular permissions."""
    def permission_checker(current_user: dict = Depends(require_authentication)):
        if current_user.get("is_admin"):
            return current_user

        role = Role(current_user.get("role", "user"))
        allowed_actions = DEFAULT_PERMISSIONS.get(role, {}).get(resource, [])
        if action not in allowed_actions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires {action} permission on {resource}."
            )
        return current_user
    return permission_checker
```

## 🪙 7. SSO for the ETL — One-Time Token (OTT)

The ETL frontend has no login of its own. Access is made via a **One-Time Token (OTT)**, a secure SSO mechanism that eliminates re-authentication and does not expose tokens or URLs in the address bar.

### Full flow (direct ETL access)

```
1. User opens http://localhost:3344/some-route  (no auth)
      │
      ▼
2. ETL: sessionStorage.set('etl_return_path', '/some-route')
   ETL: redirects → http://localhost:5177/login?etl=1
      │  (clean URL — no ETL port or token exposed)
      ▼
3. User logs in on the main frontend
      │
      ▼
4. POST /api/v1/auth/ott  →  { ott, etl_url, ttl: 30 }
   window.location = etl_url + '?ott=' + ott
      │  (OTT removed from URL in ~1 frame by OttBootstrap)
      ▼
5. ETL exchanges OTT → POST /api/v1/auth/exchange-ott
   Reads sessionStorage → navigates to '/some-route'
   Final URL: http://localhost:3344/some-route  ✓
```

### Backend — endpoints

```python
# POST /api/v1/auth/ott
# Requires authentication + is_admin = true
# Generates UUID, stores {access_token, user, tenant_colors, client_ip} in Redis with 30s TTL
# Returns: { "ott": "<uuid>", "etl_url": "http://localhost:3344", "ttl": 30 }

# POST /api/v1/auth/exchange-ott
# Public (ETL entry point) — rate limited 10/min
# Single-use OTT: deleted from Redis on first call
# Returns: same shape as /auth/login (access_token, user, tenant_colors)
```

### Security properties

| Property | Detail |
|---|---|
| **Single use** | OTT is deleted from Redis on first exchange (`get-and-delete`) |
| **Short TTL** | 30 seconds — minimum window for the redirect |
| **IP fingerprint** | `client_ip` is validated: OTT only works for the IP that generated it |
| **Admin only** | `POST /auth/ott` requires `is_admin = true` — regular users cannot access the ETL |
| **Clean URL** | `?etl=1` in login instead of `?redirect=http://localhost:3344/...` |
| **Clean token** | OTT removed from URL by `window.history.replaceState` in ~1 frame |

### sessionStorage as cross-redirect channel

The ETL preserves the deep link in its own `sessionStorage` (origin `localhost:3344`) before redirecting to login. The main frontend **does not need to know the path** — it only generates the OTT and points to the ETL root. After the OTT exchange, the ETL reads the saved path and navigates internally.

```
sessionStorage (ETL origin) ──► 'etl_return_path' = '/pipelines'
                                       ↑ written before redirect
                                       ↓ read after exchange-ott
navigate('/pipelines', { replace: true })  ← inside React Router
```

> **Rule:** never pass the full ETL URL as a query parameter (`?redirect=http://...`). Always use `?etl=1` + `sessionStorage`.
