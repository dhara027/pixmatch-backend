"""
Security utilities: JWT generation/verification, bcrypt, OTP, SSRF protection.
"""
import hashlib
import hmac
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

import bcrypt
import jwt

from app.config.settings import config


# ─── Password ────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    # rounds=13: ~500ms on modern hardware — OWASP recommended minimum for 2025
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=13)).decode("utf-8")


def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ─── JWT ──────────────────────────────────────────────────────────────────────

def generate_access_token(user_id: str, email: str) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=config.JWT_ACCESS_EXPIRY_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def generate_refresh_token(user_id: str, email: str) -> tuple[str, str]:
    """
    Generate a refresh token and return (token_string, jti).
    Returning jti directly avoids a redundant JWT decode in the caller.
    """
    jti = secrets.token_hex(16)
    payload = {
        "jti": jti,
        "user_id": user_id,
        "email": email,
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=config.JWT_REFRESH_EXPIRY_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, config.JWT_REFRESH_SECRET, algorithm="HS256")
    return token, jti


def verify_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "access":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def verify_refresh_token_jwt(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, config.JWT_REFRESH_SECRET, algorithms=["HS256"])
        if payload.get("type") != "refresh":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ─── OTP ─────────────────────────────────────────────────────────────────────

def generate_otp(length: int = 6) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


def verify_otp_hash(provided_otp: str, stored_hash: str) -> bool:
    provided_hash = hashlib.sha256(provided_otp.encode("utf-8")).hexdigest()
    return hmac.compare_digest(provided_hash, stored_hash)


# ─── Reset Token ──────────────────────────────────────────────────────────────

def generate_reset_token() -> str:
    return secrets.token_urlsafe(48)


# ─── SSRF Protection ─────────────────────────────────────────────────────────

def is_safe_cloudinary_url(url: str) -> bool:
    """
    Validate that a URL belongs to THIS application's Cloudinary account and uses HTTPS.
    Checks both the domain (res.cloudinary.com) AND the cloud name path segment to
    prevent proxying assets from other Cloudinary accounts.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return False
        host = parsed.netloc.lower()
        if host != "res.cloudinary.com":
            return False
        # Path must start with /{cloud_name}/ to prevent SSRF to other Cloudinary tenants
        cloud_name = config.CLOUDINARY_CLOUD_NAME.lower()
        path = parsed.path.lstrip("/")
        return path.startswith(f"{cloud_name}/") or path.startswith(f"{cloud_name}?")
    except Exception:
        return False


# ─── Input Validators ────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_MOBILE_RE = re.compile(r"^[6-9]\d{9}$")
_PASSWORD_RE = re.compile(r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[@$!%*#?&]).{8,}$")


def validate_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email.strip().lower()))


def validate_mobile(mobile: str) -> bool:
    return bool(_MOBILE_RE.match(mobile.strip()))


def validate_password(password: str) -> bool:
    return bool(_PASSWORD_RE.match(password))
