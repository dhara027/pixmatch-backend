"""
Auth service — all business logic for authentication.
Raises domain exceptions; never returns raw DB rows to routes.
"""
import hmac
import logging
from dataclasses import dataclass

from app.config.settings import config
from app.extensions import database as db
from app.extensions import redis_ext as redis
from app.shared.email_service import send_otp_email, send_password_reset_email
from app.shared.exceptions import (
    AuthenticationError,
    ConflictError,
    ValidationError,
)
from app.utils.security import (
    check_password,
    generate_access_token,
    generate_otp,
    generate_refresh_token,
    generate_reset_token,
    hash_otp,
    hash_password,
    verify_otp_hash,
    verify_refresh_token_jwt,
)

logger = logging.getLogger(__name__)


@dataclass
class AuthTokens:
    access_token: str
    refresh_token: str
    user_id: str
    email: str


class AuthService:

    # ── Signup ───────────────────────────────────────────────────────────────

    def signup(self, email: str, mobile_no: str, password: str, confirm_password: str) -> None:
        email = email.strip().lower()
        mobile_no = mobile_no.strip()

        if password != confirm_password:
            raise ValidationError("Passwords do not match.")

        with db.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM users WHERE email = %s OR mobile_no = %s LIMIT 1",
                    (email, mobile_no),
                )
                existing = cur.fetchone()
                if existing:
                    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
                    if cur.fetchone():
                        raise ConflictError("An account with this email already exists.")
                    raise ConflictError("An account with this mobile number already exists.")

                password_hash = hash_password(password)
                cur.execute(
                    """
                    INSERT INTO users (email, mobile_no, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (email, mobile_no, password_hash),
                )

        otp = generate_otp()
        otp_hash = hash_otp(otp)
        redis.set_otp(email, otp_hash, expiry=redis.OTP_TTL)
        send_otp_email(email, otp)
        logger.info("Signup completed for %s — OTP sent.", email)

    # ── OTP Verification ─────────────────────────────────────────────────────

    def verify_otp(self, email: str, otp: str) -> None:
        email = email.strip().lower()
        otp = otp.strip()

        stored_hash = redis.get_otp_hash(email)
        if not stored_hash:
            raise AuthenticationError("OTP has expired or does not exist. Please request a new one.")

        if not verify_otp_hash(otp, stored_hash):
            remaining = redis.decrement_otp_attempts(email)
            if remaining <= 0:
                redis.delete_otp(email)
                raise AuthenticationError("Too many incorrect attempts. Please request a new OTP.")
            raise AuthenticationError(f"Invalid OTP. {remaining} attempt(s) remaining.")

        redis.delete_otp(email)
        with db.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET is_email_verified = TRUE WHERE email = %s",
                    (email,),
                )
        logger.info("OTP verified for %s.", email)

    # ── Resend OTP ────────────────────────────────────────────────────────────

    def resend_otp(self, email: str) -> None:
        email = email.strip().lower()

        with db.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, is_email_verified FROM users WHERE email = %s AND is_active = TRUE",
                    (email,),
                )
                user = cur.fetchone()

        # Always return success to prevent user enumeration
        if not user or user["is_email_verified"]:
            logger.info("Resend OTP requested for %s (not found or already verified)", email)
            return

        otp = generate_otp()
        otp_hash = hash_otp(otp)
        redis.set_otp(email, otp_hash, expiry=redis.OTP_TTL)
        send_otp_email(email, otp)
        logger.info("OTP resent for %s.", email)

    # ── Login ─────────────────────────────────────────────────────────────────

    def login(self, email: str, password: str) -> AuthTokens:
        email = email.strip().lower()

        # Account lockout check (before any DB query to fail fast)
        failures = redis.get_login_failures(email)
        if failures >= redis.LOGIN_LOCKOUT_THRESHOLD:
            raise AuthenticationError(
                "Account temporarily locked due to too many failed attempts. "
                "Please try again in 15 minutes."
            )

        # Single DB transaction: fetch user + update last_login_at atomically
        with db.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, password_hash, is_email_verified
                    FROM users WHERE email = %s AND is_active = TRUE
                    """,
                    (email,),
                )
                user = cur.fetchone()

                # Constant-time path: always run bcrypt even if user not found
                _DUMMY = "$2b$13$aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                hash_to_check = user["password_hash"] if user else _DUMMY
                password_valid = check_password(password, hash_to_check)

                if not user or not password_valid:
                    count = redis.increment_login_failures(email)
                    remaining = max(0, redis.LOGIN_LOCKOUT_THRESHOLD - count)
                    if remaining == 0:
                        raise AuthenticationError(
                            "Account locked due to too many failed attempts. Try again in 15 minutes."
                        )
                    raise AuthenticationError("Invalid credentials.")

                if not user["is_email_verified"]:
                    raise AuthenticationError("Email address not verified. Please check your inbox.")

                # Success — reset failure counter and update login timestamp
                redis.reset_login_failures(email)
                user_id = str(user["id"])
                cur.execute(
                    "UPDATE users SET last_login_at = NOW() WHERE id = %s",
                    (user["id"],),
                )

        access_token = generate_access_token(user_id, email)
        refresh_token, jti = generate_refresh_token(user_id, email)

        redis.set_refresh_token(jti, email)
        redis.add_user_session(email, jti)

        logger.info("Login successful for %s.", email)
        return AuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user_id,
            email=email,
        )

    # ── Refresh Token (with rotation) ─────────────────────────────────────────

    def refresh_access_token(self, refresh_token: str) -> AuthTokens:
        payload = verify_refresh_token_jwt(refresh_token)
        if not payload:
            raise AuthenticationError("Invalid or expired refresh token.")

        old_jti = payload.get("jti", "")
        email_in_token = payload.get("email", "").lower()
        user_id = payload.get("user_id", "")

        stored_email = redis.get_refresh_token_email(old_jti)
        if not stored_email:
            raise AuthenticationError("Session expired. Please log in again.")

        if not hmac.compare_digest(stored_email.lower(), email_in_token):
            raise AuthenticationError("Refresh token mismatch. Session invalidated.")

        # Token rotation: invalidate old session, issue fresh tokens
        redis.delete_refresh_token(old_jti)
        redis.remove_user_session(email_in_token, old_jti)

        new_access_token = generate_access_token(user_id, email_in_token)
        new_refresh_token, new_jti = generate_refresh_token(user_id, email_in_token)

        redis.set_refresh_token(new_jti, email_in_token)
        redis.add_user_session(email_in_token, new_jti)

        return AuthTokens(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            user_id=user_id,
            email=email_in_token,
        )

    # ── Logout ───────────────────────────────────────────────────────────────

    def logout(self, email: str, refresh_token: str | None = None) -> None:
        if refresh_token:
            payload = verify_refresh_token_jwt(refresh_token)
            if payload and payload.get("jti"):
                jti = payload["jti"]
                # Verify the token email matches the authenticated user (prevents
                # one user from invalidating another user's session)
                if payload.get("email", "").lower() == email.lower():
                    redis.delete_refresh_token(jti)
                    redis.remove_user_session(email, jti)
        logger.info("User %s logged out.", email)

    # ── Forgot Password ───────────────────────────────────────────────────────

    def forgot_password(self, email: str) -> None:
        email = email.strip().lower()

        with db.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE email = %s AND is_active = TRUE", (email,))
                user = cur.fetchone()

        if not user:
            logger.info("Forgot-password requested for non-existent email: %s", email)
            return

        token = generate_reset_token()
        redis.set_reset_token(token, email, expiry=redis.RESET_TTL)

        reset_link = f"{config.FRONTEND_URL}/reset-password?token={token}"
        send_password_reset_email(email, reset_link)
        logger.info("Password reset token issued for %s.", email)

    # ── Reset Password ────────────────────────────────────────────────────────

    def reset_password(self, token: str, new_password: str, confirm_password: str) -> None:
        if new_password != confirm_password:
            raise ValidationError("Passwords do not match.")

        email = redis.get_reset_token_email(token)
        if not email:
            raise AuthenticationError("Invalid or expired reset token. Please request a new one.")

        redis.delete_reset_token(token)

        password_hash = hash_password(new_password)
        with db.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET password_hash = %s WHERE email = %s AND is_active = TRUE",
                    (password_hash, email),
                )

        # Invalidate ALL active sessions — a password change must log out every device
        redis.delete_all_user_sessions(email)
        logger.info("Password reset completed for %s — all sessions invalidated.", email)


auth_service = AuthService()
