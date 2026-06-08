"""
Auth routes — /api/v1/auth/*
All routes validate input with Marshmallow schemas before delegating to service.
Tokens are set/cleared as httpOnly cookies for browser security.
Bearer token fallback is supported for API clients.
"""
import logging

from flask import Blueprint, current_app, g, make_response, request

from app.middleware.auth import require_auth
from app.modules.auth.schemas import (
    ForgotPasswordSchema,
    LoginSchema,
    RefreshTokenSchema,
    ResetPasswordSchema,
    ResendOtpSchema,
    SignupSchema,
    VerifyOtpSchema,
)
from app.modules.auth.service import AuthTokens, auth_service
from app.utils.response import created, error, success

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

_signup_schema = SignupSchema()
_verify_schema = VerifyOtpSchema()
_login_schema = LoginSchema()
_refresh_schema = RefreshTokenSchema()
_forgot_schema = ForgotPasswordSchema()
_reset_schema = ResetPasswordSchema()
_resend_schema = ResendOtpSchema()


def _is_secure() -> bool:
    """True in production (HTTPS). Cookies without Secure flag work on HTTP for dev."""
    return current_app.config.get("FLASK_ENV") == "production"


def _set_auth_cookies(resp, tokens: AuthTokens) -> None:
    """Set httpOnly, SameSite=Lax auth cookies on the response."""
    secure = _is_secure()
    resp.set_cookie(
        "access_token",
        tokens.access_token,
        httponly=True,
        secure=secure,
        samesite="Lax",
        max_age=15 * 60,
        path="/",
    )
    # Refresh token is path-restricted to /api/v1/auth so the browser only sends
    # it to auth endpoints, reducing the attack surface.
    resp.set_cookie(
        "refresh_token",
        tokens.refresh_token,
        httponly=True,
        secure=secure,
        samesite="Lax",
        max_age=7 * 24 * 3600,
        path="/api/v1/auth",
    )


def _clear_auth_cookies(resp) -> None:
    resp.set_cookie("access_token", "", httponly=True, expires=0, path="/")
    resp.set_cookie("refresh_token", "", httponly=True, expires=0, path="/api/v1/auth")


@auth_bp.route("/signup", methods=["POST"])
def signup():
    data = _signup_schema.load(request.get_json(force=True) or {})
    auth_service.signup(
        email=data["email"],
        mobile_no=data["mobile_no"],
        password=data["password"],
        confirm_password=data["confirmpassword"],
    )
    return created({"message": "Registration successful. Please check your email for the OTP."})


@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = _verify_schema.load(request.get_json(force=True) or {})
    auth_service.verify_otp(email=data["email"], otp=data["otp"])
    return success({"message": "Email verified successfully. You can now log in."})


@auth_bp.route("/resend-otp", methods=["POST"])
def resend_otp():
    data = _resend_schema.load(request.get_json(force=True) or {})
    auth_service.resend_otp(email=data["email"])
    return success({"message": "If your account exists and is unverified, a new OTP has been sent."})


@auth_bp.route("/login", methods=["POST"])
def login():
    data = _login_schema.load(request.get_json(force=True) or {})
    tokens = auth_service.login(email=data["email"], password=data["password"])

    resp = make_response(success({
        "user": {"id": tokens.user_id, "email": tokens.email},
        "message": "Login successful.",
    })[0])
    _set_auth_cookies(resp, tokens)
    return resp


@auth_bp.route("/refresh-token", methods=["POST"])
def refresh_token():
    # Cookie first (browser); body fallback (API clients)
    rt = request.cookies.get("refresh_token")
    if not rt:
        body = request.get_json(silent=True) or {}
        rt = body.get("refresh_token", "")
    if not rt:
        return error("No refresh token provided.", code="AUTHENTICATION_REQUIRED", status=401)

    tokens = auth_service.refresh_access_token(rt)

    resp = make_response(success({"message": "Token refreshed."})[0])
    _set_auth_cookies(resp, tokens)
    return resp


@auth_bp.route("/logout", methods=["POST"])
@require_auth
def logout():
    # Read refresh token from cookie (preferred) or request body
    rt = request.cookies.get("refresh_token")
    if not rt:
        body = request.get_json(silent=True) or {}
        rt = body.get("refresh_token") or None

    auth_service.logout(g.user_email, refresh_token=rt)

    resp = make_response(success({"message": "Logged out successfully."})[0])
    _clear_auth_cookies(resp)
    return resp


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = _forgot_schema.load(request.get_json(force=True) or {})
    auth_service.forgot_password(data["email"])
    return success({"message": "If that email is registered, a reset link has been sent."})


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = _reset_schema.load(request.get_json(force=True) or {})
    auth_service.reset_password(
        token=data["token"],
        new_password=data["new_password"],
        confirm_password=data["confirm_password"],
    )
    # Clear cookies since all sessions were invalidated
    resp = make_response(success({"message": "Password reset successfully. Please log in."})[0])
    _clear_auth_cookies(resp)
    return resp
