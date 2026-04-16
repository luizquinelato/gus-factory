#!/bin/bash
# =============================================================
# infra/postgres/replica/entrypoint.sh
# Custom entrypoint for the replica container.
#
# On first start (empty PGDATA):
#   1. Waits for the primary to be ready
#   2. Runs pg_basebackup from the primary (streaming WAL)
#   3. Creates standby.signal (Postgres 12+)
#   4. Writes primary_conninfo + slot to postgresql.auto.conf
#
# On subsequent starts: resumes as a hot standby.
# Env vars (align with pulse conventions):
#   POSTGRES_PRIMARY_HOST      — primary container name (default: postgres)
#   POSTGRES_PRIMARY_PORT      — primary port           (default: 5432)
#   POSTGRES_REPLICATION_USER  — replication role       (default: replicator)
#   POSTGRES_REPLICATION_PASSWORD — replication password (default: replicator_password)
# =============================================================

set -e

PRIMARY_HOST="${POSTGRES_PRIMARY_HOST:-postgres}"
PRIMARY_PORT="${POSTGRES_PRIMARY_PORT:-5432}"
REPL_USER="${POSTGRES_REPLICATION_USER:-replicator}"
REPL_PASS="${POSTGRES_REPLICATION_PASSWORD:-replicator_password}"

# ── Wait for primary ──────────────────────────────────────────
echo "[replica] Waiting for primary at ${PRIMARY_HOST}:${PRIMARY_PORT}..."
until pg_isready -h "$PRIMARY_HOST" -p "$PRIMARY_PORT" -U "$REPL_USER" 2>/dev/null; do
    sleep 2
done
echo "[replica] Primary is ready."

# ── Bootstrap if PGDATA is empty ─────────────────────────────
if [ ! -f "$PGDATA/PG_VERSION" ]; then
    echo "[replica] PGDATA is empty — running pg_basebackup..."

    # .pgpass for password-less pg_basebackup
    echo "${PRIMARY_HOST}:${PRIMARY_PORT}:*:${REPL_USER}:${REPL_PASS}" > ~/.pgpass
    chmod 600 ~/.pgpass

    pg_basebackup \
        -h "$PRIMARY_HOST" \
        -p "$PRIMARY_PORT" \
        -U "$REPL_USER" \
        -D "$PGDATA" \
        -Fp \
        -Xs \
        -P \
        -R

    # Ensure standby.signal exists (-R creates it, but be safe)
    touch "$PGDATA/standby.signal"

    # Write replication config (overrides anything -R wrote)
    TZ_NAME="${TZ:-America/Sao_Paulo}"
    cat >> "$PGDATA/postgresql.auto.conf" <<EOF

# Streaming replication — written by replica entrypoint
primary_conninfo = 'host=${PRIMARY_HOST} port=${PRIMARY_PORT} user=${REPL_USER} password=${REPL_PASS} application_name=replica'
primary_slot_name = 'replica_slot'
hot_standby = on
hot_standby_feedback = on
timezone = '${TZ_NAME}'
log_timezone = '${TZ_NAME}'
EOF

    echo "[replica] Base backup complete — starting as hot standby."
else
    echo "[replica] PGDATA exists — resuming as hot standby."
fi

# ── Start postgres ────────────────────────────────────────────
exec docker-entrypoint.sh postgres -c hot_standby=on
