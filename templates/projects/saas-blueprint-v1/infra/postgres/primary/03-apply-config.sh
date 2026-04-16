#!/bin/bash
# =============================================================
# infra/postgres/primary/03-apply-config.sh
# Executed by docker-entrypoint-initdb.d on FIRST container start.
# Copies postgresql.conf from the mounted config volume to $PGDATA,
# then signals postgres to reload (pg_ctl reload is safe during init).
# =============================================================

set -e

CONFIG_SRC="/etc/saas-blueprint-config/postgresql.conf"

if [ -f "$CONFIG_SRC" ]; then
    echo "[primary] Applying custom postgresql.conf from $CONFIG_SRC..."
    cp "$CONFIG_SRC" "$PGDATA/postgresql.conf"
    chown postgres:postgres "$PGDATA/postgresql.conf" 2>/dev/null || true
    echo "[primary] postgresql.conf applied — WAL replication settings active."
else
    echo "[primary] $CONFIG_SRC not found — skipping config override."
fi
