"""
Unit tests for security utilities.
These tests run with no external services (no DB, Redis, Cloudinary).
"""
import hashlib
import time

import pytest

# Set required env vars before any app import
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-unit")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-long-enough")
os.environ.setdefault("JWT_REFRESH_SECRET", "unit-test-refresh-secret-long-enough")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "test")
os.environ.setdefault("CLOUDINARY_API_KEY", "123")
os.environ.setdefault("CLOUDINARY_API_SECRET", "secret")
os.environ.setdefault("SENDGRID_API_KEY", "SG.test")
os.environ.setdefault("FROM_EMAIL", "test@test.com")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")

from app.utils.security import (
    check_password,
    generate_access_token,
    generate_otp,
    generate_refresh_token,
    generate_reset_token,
    hash_otp,
    hash_password,
    is_safe_cloudinary_url,
    validate_email,
    validate_mobile,
    validate_password,
    verify_access_token,
    verify_otp_hash,
    verify_refresh_token_jwt,
)


# ── Password ──────────────────────────────────────────────────────────────────

class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        pw = "MySecret@123"
        assert hash_password(pw) != pw

    def test_hash_roundtrip(self):
        pw = "MySecret@123"
        assert check_password(pw, hash_password(pw)) is True

    def test_wrong_password_fails(self):
        assert check_password("WrongPassword@1", hash_password("Correct@Pass1")) is False

    def test_empty_password_does_not_crash(self):
        result = check_password("anything", "notahash")
        assert result is False

    def test_two_hashes_of_same_password_differ(self):
        pw = "SamePass@1"
        assert hash_password(pw) != hash_password(pw)  # bcrypt salts differ


# ── JWT ───────────────────────────────────────────────────────────────────────

class TestJWT:
    def test_access_token_roundtrip(self):
        token = generate_access_token("user-123", "test@example.com")
        payload = verify_access_token(token)
        assert payload is not None
        assert payload["user_id"] == "user-123"
        assert payload["email"] == "test@example.com"
        assert payload["type"] == "access"

    def test_refresh_token_roundtrip(self):
        # generate_refresh_token returns (token, jti) tuple since session refactor
        token, jti = generate_refresh_token("user-123", "test@example.com")
        assert len(jti) == 32  # 16-byte hex
        payload = verify_refresh_token_jwt(token)
        assert payload is not None
        assert payload["type"] == "refresh"
        assert payload["jti"] == jti

    def test_access_token_rejected_for_refresh(self):
        token = generate_access_token("user-123", "test@example.com")
        # verify_refresh_token_jwt checks type == "refresh"
        assert verify_refresh_token_jwt(token) is None

    def test_refresh_token_rejected_for_access(self):
        token, _jti = generate_refresh_token("user-123", "test@example.com")
        assert verify_access_token(token) is None

    def test_invalid_token_returns_none(self):
        assert verify_access_token("not.a.token") is None

    def test_tampered_token_returns_none(self):
        token = generate_access_token("user-123", "test@example.com")
        tampered = token[:-4] + "XXXX"
        assert verify_access_token(tampered) is None


# ── OTP ───────────────────────────────────────────────────────────────────────

class TestOTP:
    def test_otp_is_6_digits(self):
        otp = generate_otp()
        assert len(otp) == 6
        assert otp.isdigit()

    def test_otps_are_unique(self):
        otps = {generate_otp() for _ in range(200)}
        # With 10^6 possible values and 200 samples, collision probability is ~2%
        # We accept at least 190 unique values
        assert len(otps) >= 190

    def test_otp_hash_verify_roundtrip(self):
        otp = generate_otp()
        stored_hash = hash_otp(otp)
        assert verify_otp_hash(otp, stored_hash) is True

    def test_wrong_otp_hash_fails(self):
        otp = generate_otp()
        stored_hash = hash_otp(otp)
        assert verify_otp_hash("000000", stored_hash) is False

    def test_hash_otp_is_deterministic(self):
        otp = "123456"
        assert hash_otp(otp) == hash_otp(otp)

    def test_hash_otp_uses_sha256(self):
        otp = "123456"
        expected = hashlib.sha256(otp.encode()).hexdigest()
        assert hash_otp(otp) == expected


# ── Reset Token ───────────────────────────────────────────────────────────────

class TestResetToken:
    def test_reset_token_is_url_safe(self):
        token = generate_reset_token()
        safe_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=")
        assert all(c in safe_chars for c in token)

    def test_reset_token_is_long_enough(self):
        token = generate_reset_token()
        # 48 bytes → 64 base64url chars minimum
        assert len(token) >= 60

    def test_two_reset_tokens_differ(self):
        assert generate_reset_token() != generate_reset_token()


# ── SSRF Protection ───────────────────────────────────────────────────────────

class TestSSRFProtection:
    def test_valid_cloudinary_https_url_accepted(self):
        # Cloud name in test env is "test" (set by os.environ.setdefault above)
        url = "https://res.cloudinary.com/test/image/upload/v1/events/photo.jpg"
        assert is_safe_cloudinary_url(url) is True

    def test_http_cloudinary_rejected(self):
        url = "http://res.cloudinary.com/mycloud/image/upload/photo.jpg"
        assert is_safe_cloudinary_url(url) is False

    def test_aws_metadata_url_rejected(self):
        assert is_safe_cloudinary_url("http://169.254.169.254/latest/meta-data/") is False

    def test_localhost_rejected(self):
        assert is_safe_cloudinary_url("https://localhost/secret") is False

    def test_internal_ip_rejected(self):
        assert is_safe_cloudinary_url("https://192.168.1.1/data") is False

    def test_random_https_url_rejected(self):
        assert is_safe_cloudinary_url("https://evil.com/malware.zip") is False

    def test_empty_string_rejected(self):
        assert is_safe_cloudinary_url("") is False


# ── Input Validation ──────────────────────────────────────────────────────────

class TestValidation:
    def test_valid_email(self):
        assert validate_email("user@example.com") is True

    def test_invalid_email_no_at(self):
        assert validate_email("notanemail") is False

    def test_invalid_email_no_domain(self):
        assert validate_email("user@") is False

    def test_valid_mobile(self):
        assert validate_mobile("9876543210") is True

    def test_mobile_wrong_prefix(self):
        assert validate_mobile("5876543210") is False

    def test_mobile_too_short(self):
        assert validate_mobile("98765432") is False

    def test_strong_password(self):
        assert validate_password("MyPass@1234") is True

    def test_password_too_short(self):
        assert validate_password("Abc@1") is False

    def test_password_no_uppercase(self):
        assert validate_password("mypass@123") is False

    def test_password_no_special_char(self):
        assert validate_password("MyPass1234") is False
