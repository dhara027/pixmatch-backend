#!/usr/bin/env python3
"""
migrate.py — Run SQL migrations against Supabase direct connection.

Usage:
    python migrations/migrate.py

Reads all .sql files from the migrations/ directory in alphabetical order.
Skips files that have already been applied (tracked in _migrations table).
Uses the DIRECT connection (port 5432) — never the pooler.
"""
import glob
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def get_direct_conn():
    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 not installed: pip install psycopg2-binary")
        sys.exit(1)

    required = [
        "SUPABASE_DIRECT_HOST",
        "SUPABASE_DIRECT_PASSWORD",
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        logger.error(
            "Missing required env vars for direct connection: %s",
            ", ".join(missing),
        )
        logger.error(
            "Set SUPABASE_DIRECT_HOST and SUPABASE_DIRECT_PASSWORD in your .env"
        )
        sys.exit(1)

    return psycopg2.connect(
        host=os.getenv("SUPABASE_DIRECT_HOST"),
        port=int(os.getenv("SUPABASE_DIRECT_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("SUPABASE_DIRECT_USER", "postgres"),
        password=os.getenv("SUPABASE_DIRECT_PASSWORD"),
        connect_timeout=15,
        sslmode="require",
    )


def run_migrations():
    conn = get_direct_conn()
    conn.autocommit = True
    cur = conn.cursor()

    # Migration tracking table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id          SERIAL PRIMARY KEY,
            filename    VARCHAR(255) NOT NULL UNIQUE,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    # .sql files live in the same directory as this script
    files = sorted(glob.glob(os.path.join(script_dir, "*.sql")))

    if not files:
        logger.warning("No .sql files found in migrations/")
        return

    applied = 0
    skipped = 0

    for filepath in files:
        filename = os.path.basename(filepath)

        cur.execute(
            "SELECT 1 FROM _migrations WHERE filename = %s", (filename,)
        )
        if cur.fetchone():
            logger.info("SKIP (already applied): %s", filename)
            skipped += 1
            continue

        logger.info("Applying: %s", filename)
        with open(filepath, "r", encoding="utf-8") as f:
            sql = f.read()

        try:
            cur.execute(sql)
            cur.execute(
                "INSERT INTO _migrations (filename) VALUES (%s)", (filename,)
            )
            logger.info("Applied:  %s", filename)
            applied += 1
        except Exception as exc:
            logger.error("FAILED on %s: %s", filename, exc)
            conn.close()
            sys.exit(1)

    cur.close()
    conn.close()
    logger.info(
        "Done — %d applied, %d skipped.", applied, skipped
    )


if __name__ == "__main__":
    run_migrations()
