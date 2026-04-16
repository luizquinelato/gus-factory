# Backend and Database Rules

These rules are NON-NEGOTIABLE and must be applied in all backend interactions and code generation.

## 1. Soft Delete
- NEVER physically delete records from the database (e.g., `DELETE FROM table`).
- ALWAYS use logical deletion by updating the `active` column to `false` (e.g., `UPDATE table SET active = false`).
- All queries must filter by `active = true` by default.

## 2. Structured Logging
- NEVER use `print()` in production code.
- ALWAYS use the Python `logging` module configured per module (e.g., `logger = logging.getLogger(__name__)`).
- Use the correct levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).

## 3. Database Language
- The SQL schema, table names, and column names MUST ALWAYS be in English.
- The `DB_LANGUAGE` variable (e.g., `pt_BR.UTF-8`) only defines the charset, collation, and the language of the inserted data, not the structure.

## 3.1. Database Naming Convention
- The database name, user, and password MUST follow the project key pattern (`PROJECT_KEY`).
- **PROD**: `DB_NAME={PROJECT_KEY}`, `DB_USER={PROJECT_KEY}`, `DB_PASS={PROJECT_KEY}`
- **DEV**: `DB_NAME={PROJECT_KEY}_dev`, `DB_USER={PROJECT_KEY}`, `DB_PASS={PROJECT_KEY}`
- Example for project `acme`: PROD DB=`acme`, DEV DB=`acme_dev`, user=`acme`, password=`acme`.
- NEVER use suffixes like `_db`, `_database`, or `_prod` in the database name.

## 4. Data Validation
- Use Pydantic for input and output validation in all FastAPI routes.
- Define clear and typed schemas for request and response.

## 5. Pagination and Performance
- Routes that return lists MUST implement pagination (e.g., `limit`, `offset`).
- Use database indexes for frequently queried columns (e.g., `tenant_id`, `active`).

## 6. Integrations and AI
- AI model configurations and external integrations must reside in the `integrations` table, not in `.env`.
- The system must support automatic fallback for integrations (e.g., if OpenAI fails, try Anthropic).
- Connections to AI models must be direct, without using intermediate AI Gateways (like WEX).
