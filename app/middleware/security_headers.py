"""
Security headers applied to every response.
API (JSON) responses use a strict CSP.
Frontend (HTML/JS/CSS) responses use a permissive CSP so the React app runs.
"""
from flask import Flask, request

_FRONTEND_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: https://res.cloudinary.com; "
    "connect-src 'self' https://res.cloudinary.com; "
    "font-src 'self' data:; "
    "frame-ancestors 'none'"
)
_API_CSP = "default-src 'none'; frame-ancestors 'none'"


def register_security_headers(app: Flask) -> None:

    @app.after_request
    def add_security_headers(response):
        # Only send HSTS on HTTPS responses (X-Forwarded-Proto set by nginx/load balancer)
        proto = request.headers.get("X-Forwarded-Proto", request.scheme)
        if proto == "https":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # camera=(self) allows our own origin to use the camera — required for GuestMatch selfie
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(self), microphone=()"
        response.headers.pop("Server", None)
        response.headers.pop("X-Powered-By", None)

        if "application/json" in (response.content_type or ""):
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Content-Security-Policy"] = _API_CSP
        else:
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
            response.headers["Content-Security-Policy"] = _FRONTEND_CSP

        return response
