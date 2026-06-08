"""
Pytest fixtures for integration tests.
Uses a real test PostgreSQL database and mocked Redis/Cloudinary/SendGrid.
"""
import os
import re
import pytest
from unittest.mock import MagicMock, patch

# Set test env vars before importing app
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("DB_HOST", os.getenv("DB_HOST", "localhost"))
os.environ.setdefault("DB_NAME", os.getenv("DB_NAME", "pixmatch_test"))
os.environ.setdefault("DB_USER", os.getenv("DB_USER", "postgres"))
os.environ.setdefault("DB_PASSWORD", os.getenv("DB_PASSWORD", "testpass"))
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_PASSWORD", "")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-long-enough-for-testing-purposes-only")
os.environ.setdefault("JWT_REFRESH_SECRET", "test-refresh-secret-long-enough-for-testing-only")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "test")
os.environ.setdefault("CLOUDINARY_API_KEY", "123456")
os.environ.setdefault("CLOUDINARY_API_SECRET", "test_secret")
os.environ.setdefault("SENDGRID_API_KEY", "SG.test")
os.environ.setdefault("FROM_EMAIL", "test@test.com")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")


def extract_access_token(resp) -> str:
    """
    Extract the access_token value from Set-Cookie response headers.
    Auth tokens are now httpOnly cookies, not returned in the JSON body.
    The auth middleware accepts both cookies AND Bearer headers, so tests
    can pass the extracted cookie value as a Bearer token.
    """
    for cookie in resp.headers.getlist("Set-Cookie"):
        m = re.match(r"^access_token=([^;]+)", cookie)
        if m:
            return m.group(1)
    return ""


def _check_test_db_available() -> bool:
    """Return True only if the local test PostgreSQL is reachable."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            dbname=os.getenv("DB_NAME", "pixmatch_test"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "testpass"),
            connect_timeout=3,
            sslmode="disable",
        )
        conn.close()
        return True
    except Exception:
        return False


_TEST_DB_AVAILABLE = _check_test_db_available()


@pytest.fixture(scope="session")
def app():
    """Create application for testing with mocked external services."""
    if not _TEST_DB_AVAILABLE:
        pytest.skip(
            "Integration tests require a local PostgreSQL at localhost:5432 "
            "(DB_NAME=pixmatch_test). Run: createdb pixmatch_test"
        )

    with patch("app.shared.cloudinary_client.init_cloudinary"), \
         patch("app.shared.email_service.SendGridAPIClient"):
        from app import create_app
        flask_app = create_app()
        flask_app.config["TESTING"] = True
        flask_app.config["WTF_CSRF_ENABLED"] = False
        yield flask_app


@pytest.fixture(scope="session")
def client(app):
    return app.test_client()


@pytest.fixture
def mock_redis(mocker):
    """Mock Redis operations for unit tests."""
    mock = MagicMock()
    mocker.patch("app.extensions.redis_ext._client", mock)
    return mock


@pytest.fixture
def mock_email(mocker):
    """Mock email sending."""
    return mocker.patch("app.shared.email_service.send_email", return_value=True)


@pytest.fixture
def mock_cloudinary_upload(mocker):
    """Mock Cloudinary upload."""
    return mocker.patch(
        "app.shared.cloudinary_client.upload_event_photo",
        return_value={
            "public_id": "events/test-event/test-photo",
            "secure_url": "https://res.cloudinary.com/test/image/upload/events/test/photo.jpg",
            "bytes": 1024,
        }
    )


@pytest.fixture
def auth_headers(client):
    """Register + verify + login to get a valid Bearer token."""
    # Register
    client.post("/api/v1/auth/signup", json={
        "email": "testuser@example.com",
        "mobile_no": "9876543210",
        "password": "Test@12345",
        "confirmpassword": "Test@12345",
    })
    # Force verify (bypass OTP in test)
    from app.extensions.database import get_db
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET is_email_verified = TRUE WHERE email = %s",
                ("testuser@example.com",)
            )

    resp = client.post("/api/v1/auth/login", json={
        "email": "testuser@example.com",
        "password": "Test@12345",
    })
    # Tokens are set as httpOnly cookies; extract from Set-Cookie header for Bearer fallback
    token = extract_access_token(resp)
    return {"Authorization": f"Bearer {token}"}
