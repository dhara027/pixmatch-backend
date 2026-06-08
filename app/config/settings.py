"""
Centralized configuration management with validation.
All environment variables are validated on startup — missing critical vars crash immediately.
"""
import os
import sys
from typing import Optional


def _require(key: str) -> str:
    """Fetch a required env var; abort if missing."""
    value = os.getenv(key, "").strip()
    if not value:
        print(f"[FATAL] Missing required environment variable: {key}", file=sys.stderr)
        sys.exit(1)
    return value


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


class Config:
    # ── Flask ────────────────────────────────────────────────────
    FLASK_ENV: str = _optional("FLASK_ENV", "production")
    DEBUG: bool = _optional("FLASK_ENV", "production") == "development"
    SECRET_KEY: str = _require("SECRET_KEY")
    PORT: int = int(_optional("PORT", "5000"))

    # ── Database ─────────────────────────────────────────────────
    DB_HOST: str = _require("DB_HOST")
    DB_NAME: str = _require("DB_NAME")
    DB_USER: str = _require("DB_USER")
    DB_PASSWORD: str = _require("DB_PASSWORD")
    DB_PORT: int = int(_optional("DB_PORT", "6543"))  # 6543 = Supabase PgBouncer pooler
    DB_MIN_CONN: int = int(_optional("DB_MIN_CONN", "2"))
    DB_MAX_CONN: int = int(_optional("DB_MAX_CONN", "10"))

    # Supabase direct connection — bypasses PgBouncer (migrations only)
    SUPABASE_DIRECT_HOST: str = _optional("SUPABASE_DIRECT_HOST", "")
    SUPABASE_DIRECT_PORT: int = int(_optional("SUPABASE_DIRECT_PORT", "5432"))
    SUPABASE_DIRECT_USER: str = _optional("SUPABASE_DIRECT_USER", "postgres")
    SUPABASE_DIRECT_PASSWORD: str = _optional("SUPABASE_DIRECT_PASSWORD", "")

    # Supabase API (optional — only needed if using supabase-py client)
    SUPABASE_URL: str = _optional("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = _optional("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = _optional("SUPABASE_SERVICE_ROLE_KEY", "")

    # ── Redis ────────────────────────────────────────────────────
    # REDIS_URL takes precedence (Upstash / cloud Redis, e.g. rediss://...)
    # If not set, individual host/port/password vars are used (local/Docker).
    REDIS_URL: str = _optional("REDIS_URL", "")
    REDIS_HOST: str = _optional("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(_optional("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = _optional("REDIS_PASSWORD", "")
    REDIS_TLS: bool = _optional("REDIS_TLS", "false").lower() == "true"
    REDIS_DB: int = int(_optional("REDIS_DB", "0"))

    # ── JWT ──────────────────────────────────────────────────────
    JWT_SECRET: str = _require("JWT_SECRET")
    JWT_REFRESH_SECRET: str = _require("JWT_REFRESH_SECRET")
    JWT_ACCESS_EXPIRY_MINUTES: int = int(_optional("JWT_ACCESS_EXPIRY_MINUTES", "15"))
    JWT_REFRESH_EXPIRY_DAYS: int = int(_optional("JWT_REFRESH_EXPIRY_DAYS", "7"))

    # ── Cloudinary ───────────────────────────────────────────────
    CLOUDINARY_CLOUD_NAME: str = _require("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY: str = _require("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET: str = _require("CLOUDINARY_API_SECRET")
    CLOUDINARY_MAX_FILE_BYTES: int = int(_optional("CLOUDINARY_MAX_FILE_BYTES", str(20 * 1024 * 1024)))

    # ── SendGrid ─────────────────────────────────────────────────
    SENDGRID_API_KEY: str = _require("SENDGRID_API_KEY")
    FROM_EMAIL: str = _require("FROM_EMAIL")

    # ── Frontend ─────────────────────────────────────────────────
    FRONTEND_URL: str = _require("FRONTEND_URL")

    # ── CORS ─────────────────────────────────────────────────────
    CORS_ORIGINS: list = _optional("FRONTEND_URL", "").split(",")

    # ── Rate Limiting ────────────────────────────────────────────
    RATELIMIT_DEFAULT: str = "200 per day;50 per hour"
    RATELIMIT_HEADERS_ENABLED: bool = True

    @classmethod
    def redis_url(cls) -> str:
        """Full Redis URL for any client (limiter, Celery, direct). Prefers REDIS_URL."""
        if cls.REDIS_URL:
            return cls.REDIS_URL
        if cls.REDIS_PASSWORD:
            return f"redis://:{cls.REDIS_PASSWORD}@{cls.REDIS_HOST}:{cls.REDIS_PORT}/{cls.REDIS_DB}"
        return f"redis://{cls.REDIS_HOST}:{cls.REDIS_PORT}/{cls.REDIS_DB}"

    # ── InsightFace ──────────────────────────────────────────────
    INSIGHTFACE_CTX_ID: int = int(_optional("INSIGHTFACE_CTX_ID", "-1"))  # -1 = CPU
    INSIGHTFACE_DET_SIZE: tuple = (640, 640)
    MATCH_DISTANCE_THRESHOLD: float = float(_optional("MATCH_DISTANCE_THRESHOLD", "0.50"))

    # ── Celery ───────────────────────────────────────────────────
    @classmethod
    def celery_broker_url(cls) -> str:
        """Celery uses the same Redis URL — Upstash doesn't support DB index selection."""
        return cls.redis_url()

    @classmethod
    def celery_result_backend(cls) -> str:
        return cls.redis_url()

    # ── Allowed MIME Types for Uploads ───────────────────────────
    ALLOWED_IMAGE_MIMES: frozenset = frozenset({
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "image/heif",
    })


config = Config()
