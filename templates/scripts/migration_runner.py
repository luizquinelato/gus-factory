#!/usr/bin/env python3
"""
migration_runner.py — Blueprint SaaS Migration Runner
======================================================
Generic, project-agnostic migration runner.
Reads DATABASE_URL from .env at project root (3 levels up from this file).

Usage:
    python migration_runner.py --status
    python migration_runner.py --apply-all
    python migration_runner.py --new "add_products_table"
    python migration_runner.py --rollback-to 0002
    python migration_runner.py --rollback-to 0000 --confirm
    python migration_runner.py --qdrant-cleanup [--confirm]
    python migration_runner.py --rabbit-cleanup [--confirm]

External services cleanup:
    --rollback-to 0000 --confirm   auto-triggers both cleanups after full reset
    QDRANT_URL                     env var (default: http://localhost:6333)
    RABBITMQ_HOST/PORT/USER/PASSWORD/MANAGEMENT_PORT  env vars (defaults: localhost/5672/guest/guest/15672)
"""
import os
import sys
import re
import argparse
import importlib.util
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR    = Path(__file__).resolve().parent
MIGRATIONS_DIR = SCRIPT_DIR / "migrations"
PROJECT_ROOT  = SCRIPT_DIR.parent.parent.parent   # services/backend/scripts → project root


# ── Database connection ────────────────────────────────────────────────────────

def get_connection():
    """Connect using DATABASE_URL from environment / .env file."""
    _load_env()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌  DATABASE_URL not set. Add it to your .env file.")
        sys.exit(1)

    m = re.match(r"postgresql(?:\+psycopg2)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", db_url)
    if not m:
        print(f"❌  Invalid DATABASE_URL format: {db_url}")
        sys.exit(1)

    user, password, host, port, database = m.groups()
    try:
        conn = psycopg2.connect(
            host=host, port=int(port), database=database,
            user=user, password=password,
            cursor_factory=RealDictCursor
        )
        conn.autocommit = False
        return conn
    except Exception as e:
        print(f"❌  Failed to connect: {e}")
        sys.exit(1)


def _load_env():
    """Load .env from project root, silently skip if not found."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        env_file = SCRIPT_DIR.parent.parent.parent / ".env.prod"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
            print(f"   .env loaded: {env_file}")
        except ImportError:
            _parse_env_manually(env_file)


def _parse_env_manually(env_file: Path):
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


# ── migration_history table ────────────────────────────────────────────────────

def ensure_history_table(conn):
    """Create migration_history if it doesn't exist yet (idempotent)."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS migration_history (
                id          SERIAL PRIMARY KEY,
                version     VARCHAR(50)  NOT NULL UNIQUE,
                name        VARCHAR(255) NOT NULL,
                status      VARCHAR(20)  NOT NULL DEFAULT 'applied',
                applied_at  TIMESTAMPTZ  DEFAULT NOW(),
                rollback_at TIMESTAMPTZ
            );
        """)
    conn.commit()


def get_applied(conn) -> dict[str, dict]:
    """Return {version: row} for all applied migrations."""
    ensure_history_table(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM migration_history WHERE status = 'applied' ORDER BY version;")
        return {row["version"]: dict(row) for row in cur.fetchall()}


def register(conn, version: str, name: str, status: str):
    """Upsert a migration record in migration_history."""
    with conn.cursor() as cur:
        if status == "applied":
            cur.execute(
                """
                INSERT INTO migration_history (version, name, status, applied_at, rollback_at)
                VALUES (%s, %s, 'applied', NOW(), NULL)
                ON CONFLICT (version) DO UPDATE
                    SET status = 'applied', applied_at = NOW(), rollback_at = NULL;
                """,
                (version, name)
            )
        else:
            cur.execute(
                "UPDATE migration_history SET status = 'rolled_back', rollback_at = NOW() WHERE version = %s;",
                (version,)
            )
    conn.commit()


# ── Migration file discovery ───────────────────────────────────────────────────

def list_migration_files() -> list[dict]:
    """Return sorted list of {version, name, path} dicts from migrations/."""
    if not MIGRATIONS_DIR.exists():
        return []
    files = []
    for f in sorted(MIGRATIONS_DIR.iterdir()):
        m = re.match(r"^(\d{4})_(.+)\.py$", f.name)
        if m:
            files.append({"version": m.group(1), "name": m.group(2), "path": f})
    return files


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("migration", path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── CLI commands ───────────────────────────────────────────────────────────────

def cmd_status(conn):
    print("\n📋  Migration Status")
    print("=" * 55)
    files   = list_migration_files()
    applied = get_applied(conn)
    if not files:
        print("   No migration files found in", MIGRATIONS_DIR)
        return
    for f in files:
        v = f["version"]
        if v in applied:
            ts = applied[v]["applied_at"].strftime("%Y-%m-%d %H:%M") if applied[v]["applied_at"] else "?"
            print(f"   ✅  {v}  {f['name']:<40}  applied {ts}")
        else:
            print(f"   ⏸   {v}  {f['name']}")
    print("=" * 55)
    print(f"   {len(applied)} applied  |  {len(files) - len(applied)} pending  |  {len(files)} total\n")


def cmd_apply_all(conn):
    files   = list_migration_files()
    applied = get_applied(conn)
    pending = [f for f in files if f["version"] not in applied]
    if not pending:
        print("✅  All migrations already applied.")
        return
    print(f"🚀  Applying {len(pending)} pending migration(s)...")
    for f in pending:
        print(f"   → {f['version']} {f['name']}")
        mod = load_module(f["path"])
        try:
            mod.apply(conn)
            conn.commit()
            register(conn, f["version"], f["name"], "applied")
            print(f"   ✅  {f['version']} done")
        except Exception as e:
            conn.rollback()
            print(f"   ❌  {f['version']} failed: {e}")
            sys.exit(1)
    print(f"\n✅  {len(pending)} migration(s) applied successfully.")


def _history_table_exists(conn) -> bool:
    """Return True if migration_history still exists in the database."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                AND   table_name   = 'migration_history'
            );
        """)
        return cur.fetchone()["exists"]


def cmd_rollback_to(conn, target: str, confirm: bool):
    files   = list_migration_files()
    applied = get_applied(conn)
    is_full_reset = target.strip("0") == ""
    if is_full_reset and not confirm:
        print("❌  Full reset requires --confirm flag.")
        sys.exit(1)
    to_revert = []
    for f in reversed(files):
        if f["version"] not in applied:
            continue
        if is_full_reset or f["version"] > target:
            to_revert.append(f)
        else:
            break
    if not to_revert:
        print(f"✅  Already at or before version {target}. Nothing to revert.")
        return
    print(f"🔄  Reverting {len(to_revert)} migration(s)...")
    for f in to_revert:
        print(f"   ← {f['version']} {f['name']}")
        mod = load_module(f["path"])
        try:
            mod.rollback(conn)
            conn.commit()
            # migration_history pode ter sido dropada pelo próprio rollback
            # (ex: 0001 dropa todo o schema). Só registra se a tabela ainda existir.
            if _history_table_exists(conn):
                register(conn, f["version"], f["name"], "rolled_back")
            else:
                print(f"   ℹ️   migration_history removida pelo rollback — registro ignorado.")
            print(f"   ✅  {f['version']} reverted")
        except Exception as e:
            conn.rollback()
            print(f"   ❌  {f['version']} rollback failed: {e}")
            sys.exit(1)
    print(f"\n✅  {len(to_revert)} migration(s) reverted.")
    if is_full_reset:
        print("\n🧹 Full reset — cleaning up external services...")
        cmd_qdrant_cleanup(confirm=True)
        cmd_rabbit_cleanup(confirm=True)


def cmd_qdrant_cleanup(confirm: bool = False) -> bool:
    """Delete all Qdrant collections. Safe to run on empty Qdrant."""
    try:
        import requests
    except ImportError:
        print("❌  requests is required: pip install requests"); return False

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    print(f"\n🧹 Qdrant cleanup — {qdrant_url}")
    try:
        r = requests.get(f"{qdrant_url}/collections", timeout=5)
        r.raise_for_status()
        collections = r.json().get("result", {}).get("collections", [])
    except Exception as e:
        print(f"⚠️   Cannot reach Qdrant ({e}) — skipping."); return True

    if not collections:
        print("ℹ️   No collections found."); return True

    names = [c["name"] for c in collections]
    print(f"📋  Collections: {', '.join(names)}")
    if not confirm:
        answer = input(f"\n⚠️  Delete ALL {len(names)} collection(s)? Type 'DELETE ALL': ")
        if answer != "DELETE ALL":
            print("❌  Cancelled."); return False

    ok = True
    for name in names:
        try:
            requests.delete(f"{qdrant_url}/collections/{name}", timeout=10).raise_for_status()
            print(f"   ✅  Deleted: {name}")
        except Exception as e:
            print(f"   ❌  Failed:   {name} — {e}"); ok = False
    print(f"\n✅  Qdrant cleanup done ({len(names)} collection(s)).")
    return ok


def cmd_rabbit_cleanup(confirm: bool = False) -> bool:
    """Delete all RabbitMQ queues. Queues are recreated on service start.
    Primary:  RabbitMQ Management API (discovers queues dynamically).
    Fallback: blueprint standard — {queue_type}_queue_{tier}
              tiers=[free,basic,premium,enterprise] × types=[extraction,transform,embedding]
    """
    try:
        import requests
        from requests.auth import HTTPBasicAuth
        import pika
    except ImportError as e:
        print(f"❌  Missing dependency: {e}. pip install pika requests"); return False

    host      = os.getenv("RABBITMQ_HOST",            "localhost")
    amqp_port = int(os.getenv("RABBITMQ_PORT",        "5672"))
    mgmt_port = int(os.getenv("RABBITMQ_MANAGEMENT_PORT", "15672"))
    user      = os.getenv("RABBITMQ_USER",             "guest")
    password  = os.getenv("RABBITMQ_PASSWORD",         "guest")
    vhost     = os.getenv("RABBITMQ_VHOST",            "/")
    vhost_enc = "%2F" if vhost == "/" else vhost

    print(f"\n🧹 RabbitMQ cleanup — {host}:{amqp_port}  mgmt:{mgmt_port}")

    queues: list[str] = []
    try:
        r = requests.get(f"http://{host}:{mgmt_port}/api/queues/{vhost_enc}",
                         auth=HTTPBasicAuth(user, password), timeout=10)
        if r.status_code == 200:
            queues = [q["name"] for q in r.json()]
            print(f"📋  Found {len(queues)} queue(s) via Management API")
        else:
            raise Exception(f"status {r.status_code}")
    except Exception as e:
        print(f"⚠️   Management API unavailable ({e}) — using blueprint fallback")
        tiers       = ["free", "basic", "premium", "enterprise"]
        queue_types = ["extraction", "transform", "embedding"]
        queues = [f"{qt}_queue_{t}" for t in tiers for qt in queue_types]
        print(f"📋  Fallback: {len(queues)} queues ({' × '.join([str(queue_types), str(tiers)])})")

    if not queues:
        print("ℹ️   No queues found."); return True

    if not confirm:
        print(f"📋  Queues: {', '.join(queues)}")
        answer = input("\n⚠️  Delete ALL queues? Type 'DELETE ALL': ")
        if answer != "DELETE ALL":
            print("❌  Cancelled."); return False

    try:
        creds  = pika.PlainCredentials(user, password)
        params = pika.ConnectionParameters(host=host, port=amqp_port, virtual_host=vhost, credentials=creds)
        conn   = pika.BlockingConnection(params)
        ch     = conn.channel()
        deleted = failed = 0
        for q in queues:
            try:
                ch.queue_delete(queue=q); print(f"   ✅  Deleted: {q}"); deleted += 1
            except Exception as e:
                print(f"   ⚠️   {q} — {e}"); failed += 1
        conn.close()
        print(f"\n✅  RabbitMQ cleanup done. Deleted: {deleted}  Failed: {failed}")
        return failed == 0
    except Exception as e:
        print(f"❌  RabbitMQ connection failed: {e}"); return False


def cmd_new(name: str):
    files = list_migration_files()
    next_version = f"{len(files) + 1:04d}"
    slug = re.sub(r"[^a-z0-9_]", "_", name.lower().strip())
    filename = f"{next_version}_{slug}.py"
    dest = MIGRATIONS_DIR / filename
    dest.write_text(
        f'#!/usr/bin/env python3\n"""Migration {next_version}: {name}"""\nimport logging\n\n'
        f'logger = logging.getLogger(__name__)\n\n\ndef apply(conn):\n'
        f'    """Apply migration {next_version}."""\n'
        f'    logger.info("Applying {filename}...")\n'
        f'    with conn.cursor() as cur:\n        pass  # TODO\n'
        f'    logger.info("{filename} applied.")\n\n\ndef rollback(conn):\n'
        f'    """Rollback migration {next_version}."""\n'
        f'    logger.info("Rolling back {filename}...")\n'
        f'    with conn.cursor() as cur:\n        pass  # TODO\n'
        f'    logger.info("{filename} rolled back.")\n',
        encoding="utf-8"
    )
    print(f"✅  Created: {dest}")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Blueprint SaaS Migration Runner")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--status",         action="store_true", help="Show migration status")
    grp.add_argument("--apply-all",      action="store_true", help="Apply all pending migrations")
    grp.add_argument("--new",            metavar="NAME",      help="Create a new migration template")
    grp.add_argument("--rollback-to",    metavar="VERSION",   help="Rollback to VERSION (0000 = full reset)")
    grp.add_argument("--qdrant-cleanup", action="store_true", help="Delete all Qdrant collections")
    grp.add_argument("--rabbit-cleanup", action="store_true", help="Delete all RabbitMQ queues")
    parser.add_argument("--confirm",     action="store_true", help="Skip confirmation prompts")
    args = parser.parse_args()

    if args.new:
        cmd_new(args.new)
        sys.exit(0)

    if args.qdrant_cleanup:
        sys.exit(0 if cmd_qdrant_cleanup(args.confirm) else 1)

    if args.rabbit_cleanup:
        sys.exit(0 if cmd_rabbit_cleanup(args.confirm) else 1)

    conn = get_connection()
    try:
        if args.status:
            cmd_status(conn)
        elif args.apply_all:
            cmd_apply_all(conn)
        elif args.rollback_to:
            cmd_rollback_to(conn, args.rollback_to, args.confirm)
    finally:
        conn.close()

