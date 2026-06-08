"""
Redis client singleton with password auth, TLS support, and graceful reconnect.
"""
import logging

import redis

from app.config.settings import config

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def init_redis() -> None:
    global _client
    if config.REDIS_URL:
        # URL-based init for Upstash / cloud Redis (rediss:// for TLS)
        _client = redis.from_url(
            config.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        _client.ping()
        logger.info("Redis connected via REDIS_URL")
        return

    kwargs: dict = dict(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=config.REDIS_DB,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
        health_check_interval=30,
    )
    if config.REDIS_PASSWORD:
        kwargs["password"] = config.REDIS_PASSWORD
    if config.REDIS_TLS:
        kwargs["ssl"] = True
        kwargs["ssl_cert_reqs"] = "required"

    _client = redis.Redis(**kwargs)
    _client.ping()
    logger.info("Redis connected at %s:%d", config.REDIS_HOST, config.REDIS_PORT)


def get_redis() -> redis.Redis:
    if _client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _client


# ─── OTP (hashed) ────────────────────────────────────────────────────────────

OTP_MAX_ATTEMPTS = 3
OTP_TTL = 120  # seconds


def set_otp(email: str, otp_hash: str, expiry: int = OTP_TTL) -> None:
    r = get_redis()
    pipe = r.pipeline()
    pipe.setex(f"otp:{email}", expiry, otp_hash)
    pipe.setex(f"otp_attempts:{email}", expiry, OTP_MAX_ATTEMPTS)
    pipe.execute()


def get_otp_hash(email: str) -> str | None:
    return get_redis().get(f"otp:{email}")


def decrement_otp_attempts(email: str) -> int:
    """Returns remaining attempts after decrement."""
    remaining = get_redis().decr(f"otp_attempts:{email}")
    return int(remaining)


def delete_otp(email: str) -> None:
    r = get_redis()
    r.delete(f"otp:{email}", f"otp_attempts:{email}")


# ─── Password Reset Token ────────────────────────────────────────────────────

RESET_TTL = 900  # 15 minutes


def set_reset_token(token: str, email: str, expiry: int = RESET_TTL) -> None:
    get_redis().setex(f"reset_token:{token}", expiry, email)


def get_reset_token_email(token: str) -> str | None:
    return get_redis().get(f"reset_token:{token}")


def delete_reset_token(token: str) -> None:
    get_redis().delete(f"reset_token:{token}")


# ─── Refresh Tokens (per-session jti keys) ───────────────────────────────────
# Key: refresh:jti:{jti} → email
# One Redis key per device/session — multiple devices can be logged in simultaneously.

REFRESH_TTL = 7 * 24 * 3600  # 7 days


def set_refresh_token(jti: str, email: str, expiry: int = REFRESH_TTL) -> None:
    get_redis().setex(f"refresh:jti:{jti}", expiry, email)


def get_refresh_token_email(jti: str) -> str | None:
    return get_redis().get(f"refresh:jti:{jti}")


def delete_refresh_token(jti: str) -> None:
    get_redis().delete(f"refresh:jti:{jti}")


# ─── User Session Registry (email → set of jtis) ─────────────────────────────
# Used to invalidate ALL sessions for a user on password reset.
# Key: user_sessions:{email} → Redis Set of active jtis

def add_user_session(email: str, jti: str) -> None:
    """Register a new session for this user."""
    r = get_redis()
    key = f"user_sessions:{email}"
    r.sadd(key, jti)
    r.expire(key, REFRESH_TTL)


def remove_user_session(email: str, jti: str) -> None:
    """Remove a specific session from the user's session registry."""
    get_redis().srem(f"user_sessions:{email}", jti)


def delete_all_user_sessions(email: str) -> None:
    """
    Invalidate every active session for this user.
    Called on password reset so stolen refresh tokens stop working immediately.
    """
    r = get_redis()
    key = f"user_sessions:{email}"
    jtis = r.smembers(key)
    if jtis:
        pipe = r.pipeline()
        for jti in jtis:
            pipe.delete(f"refresh:jti:{jti}")
        pipe.delete(key)
        pipe.execute()
    else:
        r.delete(key)


# ─── Account Lockout ──────────────────────────────────────────────────────────
# After LOGIN_LOCKOUT_THRESHOLD consecutive failures, block for LOGIN_LOCKOUT_TTL.

LOGIN_LOCKOUT_THRESHOLD = 10
LOGIN_LOCKOUT_TTL = 15 * 60  # 15 minutes


def increment_login_failures(email: str) -> int:
    """Increment failure counter. Returns current count."""
    r = get_redis()
    key = f"login_failures:{email}"
    count = r.incr(key)
    if count == 1:
        r.expire(key, LOGIN_LOCKOUT_TTL)
    return int(count)


def get_login_failures(email: str) -> int:
    val = get_redis().get(f"login_failures:{email}")
    return int(val) if val else 0


def reset_login_failures(email: str) -> None:
    """Called after a successful login to clear the failure counter."""
    get_redis().delete(f"login_failures:{email}")
