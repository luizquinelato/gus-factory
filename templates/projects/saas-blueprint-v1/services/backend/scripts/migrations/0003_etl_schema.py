#!/usr/bin/env python3
"""
Migration 0003: ETL Schema
===========================
Project : SaaS Blueprint V1
Creates : etl_job_errors table
Alters  : system_settings — adds setting_type column
Seeds   : ETL worker settings (extraction/transform/processor counts, ai_enabled)
          ETL settings page (page_key='etl_settings', min_role='admin')
"""
import logging

logger = logging.getLogger(__name__)

ETL_SETTINGS = [
    # (setting_key, setting_value, setting_type, description)
    ("extraction_workers", "2",    "integer", "Number of ExtractionWorker threads"),
    ("transform_workers",  "2",    "integer", "Number of TransformWorker threads"),
    ("processor_workers",  "3",    "integer", "Number of ProcessorWorker threads"),
    ("ai_enabled",         "true", "boolean", "Enable AI embedding in processor step"),
]


def apply(conn):
    logger.info("Applying 0003_etl_schema...")
    with conn.cursor() as cur:

        # 1. Add setting_type to system_settings (idempotent)
        cur.execute("""
            ALTER TABLE system_settings
            ADD COLUMN IF NOT EXISTS setting_type VARCHAR(20) DEFAULT 'string';
        """)
        logger.info("  system_settings.setting_type column added (if not existed)")

        # 2. etl_job_errors
        cur.execute("""
            CREATE TABLE IF NOT EXISTS etl_job_errors (
                id           SERIAL PRIMARY KEY,
                tenant_id    INTEGER      NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                job_id       INTEGER,
                worker_type  VARCHAR(50)  NOT NULL,
                error_code   VARCHAR(100) NOT NULL,
                error_detail TEXT,
                entity_id    VARCHAR(255),
                table_name   VARCHAR(100),
                item_index   INTEGER      DEFAULT 0,
                ai_enabled   BOOLEAN      DEFAULT FALSE,
                is_transient BOOLEAN      DEFAULT FALSE,
                active       BOOLEAN      DEFAULT TRUE,
                created_at   TIMESTAMPTZ  DEFAULT NOW()
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_etl_errors_tenant_id  ON etl_job_errors(tenant_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_etl_errors_job_id     ON etl_job_errors(job_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_etl_errors_error_code ON etl_job_errors(error_code);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_etl_errors_created_at ON etl_job_errors(created_at DESC);")
        logger.info("  etl_job_errors table created")

        # 3. Seed ETL settings for tenant 1 (default tenant)
        cur.execute("SELECT id FROM tenants WHERE active = true ORDER BY id LIMIT 1;")
        row = cur.fetchone()
        if not row:
            logger.warning("  No active tenant found — skipping ETL settings seed")
            return
        tenant_id = row["id"]

        for key, value, stype, desc in ETL_SETTINGS:
            cur.execute(
                """
                INSERT INTO system_settings (tenant_id, setting_key, setting_value, setting_type, description)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, setting_key)
                DO UPDATE SET
                    setting_value = EXCLUDED.setting_value,
                    setting_type  = EXCLUDED.setting_type,
                    description   = EXCLUDED.description,
                    last_updated_at = NOW();
                """,
                (tenant_id, key, value, stype, desc),
            )
        logger.info("  ETL settings seeded: %s", [s[0] for s in ETL_SETTINGS])

        # 4. ETL Settings page (min_role='admin' — ETL access is admin-only by default)
        cur.execute(
            """
            INSERT INTO pages (page_key, label, route, group_label, min_role, tenant_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, page_key) DO NOTHING;
            """,
            ("etl_settings", "ETL Settings", "/etl/queue-management", "ETL", "admin", tenant_id),
        )
        logger.info("  Page 'etl_settings' seeded")

    logger.info("0003_etl_schema applied.")


def rollback(conn):
    logger.info("Rolling back 0003_etl_schema...")
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS etl_job_errors CASCADE;")
        cur.execute("""
            ALTER TABLE system_settings
            DROP COLUMN IF EXISTS setting_type;
        """)
        cur.execute("DELETE FROM system_settings WHERE setting_key IN (%s, %s, %s, %s);",
                    tuple(s[0] for s in ETL_SETTINGS))
        cur.execute("DELETE FROM pages WHERE page_key = 'etl_settings';")
    logger.info("0003_etl_schema rolled back.")
