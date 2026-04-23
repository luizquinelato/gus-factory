-- =============================================================
-- infra/postgres/primary/04-variant-init.sql
-- Variant: pgvector
-- Executed by docker-entrypoint-initdb.d on first container start,
-- automatically connected to POSTGRES_DB.
-- Copied to primary/ by scripts/switch_postgres_variant.py when
-- the active variant is "pgvector"; removed when switching away.
-- =============================================================

CREATE EXTENSION IF NOT EXISTS vector;
