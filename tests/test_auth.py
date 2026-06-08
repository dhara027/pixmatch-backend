"""
Auth module integration tests.
"""
import pytest


class TestSignup:

    def test_signup_success(self, client, mock_email):
        resp = client.post("/api/v1/auth/signup", json={
            "email": "new_user@example.com",
            "mobile_no": "9876543211",
            "password": "Test@12345",
            "confirmpassword": "Test@12345",
        })
        assert resp.status_code == 201
        assert resp.json["success"] is True
        mock_email.assert_called_once()

    def test_signup_missing_fields(self, client):
        resp = client.post("/api/v1/auth/signup", json={"email": "x@x.com"})
        assert resp.status_code == 400
        assert resp.json["success"] is False
        assert resp.json["error"]["code"] == "VALIDATION_ERROR"

    def test_signup_weak_password(self, client):
        resp = client.post("/api/v1/auth/signup", json={
            "email": "weak@example.com",
            "mobile_no": "9876543212",
            "password": "weak",
            "confirmpassword": "weak",
        })
        assert resp.status_code == 400

    def test_signup_password_mismatch(self, client):
        resp = client.post("/api/v1/auth/signup", json={
            "email": "mismatch@example.com",
            "mobile_no": "9876543213",
            "password": "Test@12345",
            "confirmpassword": "Different@123",
        })
        assert resp.status_code in (400, 409)

    def test_signup_duplicate_email(self, client, mock_email):
        data = {
            "email": "dup@example.com",
            "mobile_no": "9111111111",
            "password": "Test@12345",
            "confirmpassword": "Test@12345",
        }
        client.post("/api/v1/auth/signup", json=data)
        resp = client.post("/api/v1/auth/signup", json={**data, "mobile_no": "9222222222"})
        assert resp.status_code == 409
        assert resp.json["error"]["code"] == "CONFLICT"

    def test_signup_invalid_email(self, client):
        resp = client.post("/api/v1/auth/signup", json={
            "email": "not-an-email",
            "mobile_no": "9876543210",
            "password": "Test@12345",
            "confirmpassword": "Test@12345",
        })
        assert resp.status_code == 400

    def test_signup_invalid_mobile(self, client):
        resp = client.post("/api/v1/auth/signup", json={
            "email": "mobile@test.com",
            "mobile_no": "1234567890",  # Doesn't start with 6-9
            "password": "Test@12345",
            "confirmpassword": "Test@12345",
        })
        assert resp.status_code == 400


class TestLogin:

    def test_login_unverified_email_rejected(self, client, mock_email):
        # Register without verifying
        client.post("/api/v1/auth/signup", json={
            "email": "unverified@example.com",
            "mobile_no": "9800000001",
            "password": "Test@12345",
            "confirmpassword": "Test@12345",
        })
        resp = client.post("/api/v1/auth/login", json={
            "email": "unverified@example.com",
            "password": "Test@12345",
        })
        assert resp.status_code == 401
        assert "verified" in resp.json["error"]["message"].lower()

    def test_login_wrong_password(self, client):
        resp = client.post("/api/v1/auth/login", json={
            "email": "testuser@example.com",
            "password": "WrongPass@99",
        })
        assert resp.status_code == 401
        assert resp.json["error"]["code"] == "AUTHENTICATION_FAILED"

    def test_login_nonexistent_user(self, client):
        resp = client.post("/api/v1/auth/login", json={
            "email": "nobody@example.com",
            "password": "Test@12345",
        })
        assert resp.status_code == 401
        # Must not reveal whether email exists
        assert resp.json["error"]["message"] == "Invalid credentials."

    def test_login_success(self, client, auth_headers):
        # auth_headers fixture already logs in successfully
        assert auth_headers is not None
        assert "Authorization" in auth_headers
        assert auth_headers["Authorization"].startswith("Bearer ")

    def test_login_sets_auth_cookies(self, client, auth_headers):
        from tests.conftest import extract_access_token
        resp = client.post("/api/v1/auth/login", json={
            "email": "testuser@example.com",
            "password": "Test@12345",
        })
        assert resp.status_code == 200
        # Tokens are set as httpOnly cookies, not returned in JSON body
        token = extract_access_token(resp)
        assert token != "", "access_token cookie must be present in Set-Cookie"
        # User info IS returned in the body
        assert resp.json["data"]["user"]["email"] == "testuser@example.com"


class TestProtectedRoutes:

    def test_protected_route_without_token(self, client):
        resp = client.get("/api/v1/events")
        assert resp.status_code == 401
        assert resp.json["error"]["code"] == "AUTHENTICATION_REQUIRED"

    def test_protected_route_invalid_token(self, client):
        resp = client.get("/api/v1/events", headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.status_code == 401
        assert resp.json["error"]["code"] == "INVALID_TOKEN"

    def test_protected_route_with_valid_token(self, client, auth_headers):
        resp = client.get("/api/v1/events", headers=auth_headers)
        assert resp.status_code == 200


class TestForgotPassword:

    def test_forgot_password_always_200(self, client):
        # Must not reveal whether email exists
        resp = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@test.com"})
        assert resp.status_code == 200
        assert resp.json["success"] is True


class TestResetPassword:

    def test_reset_with_invalid_token(self, client):
        resp = client.post("/api/v1/auth/reset-password", json={
            "token": "completely-invalid-token-value-here",
            "new_password": "NewPass@123",
            "confirm_password": "NewPass@123",
        })
        assert resp.status_code == 401

    def test_reset_password_mismatch(self, client):
        resp = client.post("/api/v1/auth/reset-password", json={
            "token": "some-token",
            "new_password": "NewPass@123",
            "confirm_password": "Different@456",
        })
        assert resp.status_code in (400, 401)
