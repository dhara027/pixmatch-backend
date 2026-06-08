#!/usr/bin/env python3
"""
test_supabase_connection.py — Verify Supabase connectivity before deploying.

Run: python test_supabase_connection.py
All 4 checks must pass before running the app or migrations.
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

PASS = "[PASS]"
FAIL = "[FAIL]"


def check(label: str, fn):
    try:
        fn()
        print(f"  {PASS}  {label}")
        return True
    except Exception as exc:
        print(f"  {FAIL}  {label}")
        print(f"         {exc}")
        return False


def test_pooler():
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "6543")),
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        connect_timeout=10,
        sslmode="require",
    )
    cur = conn.cursor()
    cur.execute("SELECT version()")
    version = cur.fetchone()[0]
    cur.close()
    conn.close()
    print(f"         PostgreSQL: {version[:60]}")


def test_direct():
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("SUPABASE_DIRECT_HOST"),
        port=int(os.getenv("SUPABASE_DIRECT_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("SUPABASE_DIRECT_USER", "postgres"),
        password=os.getenv("SUPABASE_DIRECT_PASSWORD"),
        connect_timeout=15,
        sslmode="require",
    )
    cur = conn.cursor()
    cur.execute("SELECT current_database(), current_user, NOW()")
    db, user, now = cur.fetchone()
    cur.close()
    conn.close()
    print(f"         db={db}  user={user}  time={now}")


def test_tables_exist():
    import psycopg2
    required = {"users", "events", "photos", "face_match_jobs"}
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "6543")),
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        connect_timeout=10,
        sslmode="require",
    )
    cur = conn.cursor()
    cur.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    )
    found = {r[0] for r in cur.fetchall()}
    cur.close()
    conn.close()
    missing = required - found
    if missing:
        raise RuntimeError(
            f"Missing tables: {missing} — run: python migrations/migrate.py"
        )
    print(f"         Tables found: {sorted(found)}")


def test_pool_import():
    from app.config.settings import config
    from app.extensions.database import close_pool, get_db, init_db_pool
    init_db_pool(config)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS result")
            row = cur.fetchone()
            assert row["result"] == 1
    close_pool()


def main():
    print("\nPixMatch — Supabase connection checks\n")

    results = [
        check("Pooler connection  (port 6543 — app queries)", test_pooler),
        check("Direct connection  (port 5432 — migrations)", test_direct),
        check("Required tables exist", test_tables_exist),
        check("App pool (init_db_pool + get_db)", test_pool_import),
    ]

    print()
    if all(results):
        print("All checks passed. Ready to run the app.\n")
    else:
        print("One or more checks failed.")
        print("\nCommon fixes:")
        print("  - DB_USER must be 'postgres.<your-project-ref>' (pooler format, with dot suffix)")
        print("  - DB_HOST must be the POOLER host  (e.g. aws-0-us-east-1.pooler.supabase.com)")
        print("  - SUPABASE_DIRECT_HOST starts with 'db.'  (e.g. db.abcxyz.supabase.co)")
        print("  - Both hosts require sslmode=require")
        print("  - Run 'python migrations/migrate.py' if tables are missing")
        print("  - Enable pgvector extension in Supabase Dashboard → Database → Extensions")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
