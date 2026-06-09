"""
database.py — Supabase-aware PostgreSQL connection pool.

Two connection modes:
  1. POOLER  (port 6543, PgBouncer transaction mode) — used by all app queries
  2. DIRECT  (port 5432, SSL required)               — used only by migrate.py

PgBouncer transaction mode restrictions:
  - NO prepared statements
  - NO SET LOCAL / SET SESSION
  - NO advisory locks
  - NO server-side cursors with names
  - Standard %s placeholders are fine
  - Regular unnamed cursors are fine
"""
import logging
from contextlib import contextmanager
from typing import Generator

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def init_db_pool(settings) -> None:
    """
    Initialise the connection pool using the Supabase pooler URL.
    Call this once inside create_app().
    """
    global _pool
    try:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=settings.DB_MIN_CONN,
            maxconn=settings.DB_MAX_CONN,
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            dbname=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            cursor_factory=RealDictCursor,
            connect_timeout=10,
            options="-c statement_timeout=30000",
            sslmode="require",
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=5,
            keepalives_count=3,
        )
        logger.info(
            "DB pool initialised — host=%s port=%s db=%s (min=%d max=%d)",
            settings.DB_HOST,
            settings.DB_PORT,
            settings.DB_NAME,
            settings.DB_MIN_CONN,
            settings.DB_MAX_CONN,
        )
    except Exception as exc:
        logger.critical(
            "Failed to initialise DB pool: %s — app will start but DB calls will fail. "
            "Check DB_HOST / DB_USER / DB_PASSWORD env vars and ensure Supabase is not paused.",
            exc,
        )
        # Do NOT raise — let the app start so Render's health probe gets a 200.
        # DB errors will surface per-request via get_db() raising RuntimeError.


@contextmanager
def get_db() -> Generator:
    """
    Yield a connection from the pool.
    Commits on success, rolls back on exception, always returns conn to pool.

    Usage:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT ...")
                row = cur.fetchone()   # returns dict-like row (RealDictCursor)
    """
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call init_db_pool() first")
    conn = _pool.getconn()
    _returned = False
    try:
        # Detect stale / broken connections and replace them
        if conn.closed or conn.status != psycopg2.extensions.STATUS_READY:
            _pool.putconn(conn, close=True)
            conn = _pool.getconn()
        conn.autocommit = False
        yield conn
        conn.commit()
    except psycopg2.OperationalError:
        # Connection dropped mid-request — discard it, don't return to pool
        try:
            conn.rollback()
        except Exception:
            pass
        _pool.putconn(conn, close=True)
        _returned = True
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        if not _returned:
            try:
                _pool.putconn(conn)
            except Exception:
                pass


def get_direct_connection(settings):
    """
    Open a direct connection to Supabase (bypasses PgBouncer).
    USE ONLY in migrate.py — never in request handlers.
    SSL is required on port 5432.
    """
    return psycopg2.connect(
        host=settings.SUPABASE_DIRECT_HOST,
        port=settings.SUPABASE_DIRECT_PORT,
        dbname=settings.DB_NAME,
        user=settings.SUPABASE_DIRECT_USER,
        password=settings.SUPABASE_DIRECT_PASSWORD,
        cursor_factory=RealDictCursor,
        connect_timeout=15,
        sslmode="require",
    )


def close_pool() -> None:
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info("DB pool closed")
