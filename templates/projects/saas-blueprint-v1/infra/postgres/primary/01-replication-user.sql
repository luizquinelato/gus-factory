-- =============================================================
-- infra/postgres/primary/01-replication-user.sql
-- Executed by docker-entrypoint-initdb.d on first container start.
-- Creates the replication user and replication slot used by the replica.
-- =============================================================

-- Create replication user if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'replicator') THEN
        CREATE ROLE replicator WITH REPLICATION LOGIN ENCRYPTED PASSWORD 'replicator_password';
        RAISE NOTICE 'Replication user "replicator" created.';
    ELSE
        RAISE NOTICE 'Replication user "replicator" already exists.';
    END IF;
END
$$;

-- Create physical replication slot if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = 'replica_slot') THEN
        PERFORM pg_create_physical_replication_slot('replica_slot');
        RAISE NOTICE 'Replication slot "replica_slot" created.';
    ELSE
        RAISE NOTICE 'Replication slot "replica_slot" already exists.';
    END IF;
END
$$;
