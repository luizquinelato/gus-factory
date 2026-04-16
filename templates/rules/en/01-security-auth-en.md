# Security and Authentication Rules

These rules are NON-NEGOTIABLE and must be applied in all interactions and code generation.

## 1. Mandatory Authentication
- NO business route can be public.
- All backend routes must be protected by the authentication middleware/dependency (`require_authentication`).
- The frontend must protect all private routes with a `ProtectedRoute` component.

## 2. Auth Service Isolation
- The frontend MUST NEVER communicate directly with the Auth Service.
- The login flow must be: `Frontend -> Backend (/api/v1/auth/login) -> Auth Service -> Backend -> Frontend`.
- The Backend acts as an API Gateway for the Auth Service.

## 3. Native Multi-tenant
- EVERY business data (database tables) MUST have the `tenant_id` column.
- All backend queries MUST filter by the logged-in user's `tenant_id`. NEVER return data from other tenants.
- The SQLAlchemy base class for business tables must be `AccountBaseEntity` (which already includes `tenant_id`).

## 4. Secrets Management
- NO secret, API key, token, or password can be hardcoded in the source code.
- All secrets must be read from environment variables via `pydantic-settings` (in the backend) or `import.meta.env` (in the frontend).

## 5. Access Control (RBAC)
- Use the Role-Based Access Control (RBAC) pattern.
- Validate granular permissions (e.g., `require_permission(Resource.USERS, Action.WRITE)`) on routes that modify data.
