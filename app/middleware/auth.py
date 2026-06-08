"""
JWT authentication middleware.
Reads the access token from httpOnly cookie first, then falls back to Bearer header
(for API clients / mobile apps that cannot use cookies).
Populates flask.g with user_id and email on every protected request.
"""
import logging
from functools import wraps
from typing import Callable

from flask import g, jsonify, request

from app.utils.security import verify_access_token

logger = logging.getLogger(__name__)


def _extract_token() -> str | None:
    # Prefer httpOnly cookie (browser clients — more secure, not accessible to JS)
    token = request.cookies.get("access_token")
    if token:
        return token
    # Fallback: Authorization: Bearer header (mobile apps, API clients, Postman)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and len(auth_header) > 7:
        return auth_header[7:].strip()
    return None


def require_auth(f: Callable) -> Callable:
    """Validates the JWT and populates g.user_id / g.user_email. Returns 401 on failure."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token()
        if not token:
            return jsonify({
                "success": False,
                "error": {"code": "AUTHENTICATION_REQUIRED", "message": "Authentication token required"},
            }), 401

        payload = verify_access_token(token)
        if not payload:
            return jsonify({
                "success": False,
                "error": {"code": "INVALID_TOKEN", "message": "Invalid or expired token"},
            }), 401

        g.user_id = str(payload["user_id"])
        g.user_email = str(payload["email"])
        return f(*args, **kwargs)

    return decorated


def optional_auth(f: Callable) -> Callable:
    """Populates g.user_id/email if a valid token is present, but does NOT reject unauthenticated requests."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token()
        if token:
            payload = verify_access_token(token)
            if payload:
                g.user_id = str(payload["user_id"])
                g.user_email = str(payload["email"])
        return f(*args, **kwargs)

    return decorated
