#!/bin/bash
# =============================================================
# infra/postgres/primary/02-pg-hba-replication.sh
# Executed by docker-entrypoint-initdb.d on first container start.
# Appends replication rule to pg_hba.conf so the replica can connect.
# =============================================================

set -e

# trust is safe inside the Docker network; replica authenticates at OS/network level
echo "host  replication  replicator  all  trust" >> "$PGDATA/pg_hba.conf"
echo "[primary] pg_hba.conf updated — replication allowed for user 'replicator' (trust)."
