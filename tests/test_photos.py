"""
Photo upload + face match tests.
"""
import io
import pytest
from unittest.mock import patch, MagicMock


class TestPhotoUpload:

    def test_upload_requires_auth(self, client):
        resp = client.post(
            "/api/v1/events/test-uuid/photos",
            data={"files": (io.BytesIO(b"fake"), "photo.jpg")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 401

    def test_upload_wrong_owner_forbidden(self, client, auth_headers, mock_cloudinary_upload):
        # Create event with user A
        create_resp = client.post("/api/v1/events", json={
            "photographer_name": "Photo Test",
            "event_name": "Photo Event",
            "event_location": "Pune",
            "event_date": "2026-08-08",
        }, headers=auth_headers)
        event_id = create_resp.json["data"]["event"]["id"]

        # Register user B
        client.post("/api/v1/auth/signup", json={
            "email": "photob@example.com",
            "mobile_no": "9600000000",
            "password": "Test@12345",
            "confirmpassword": "Test@12345",
        })
        from app.extensions.database import get_db
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET is_email_verified=TRUE WHERE email='photob@example.com'")
        login_resp = client.post("/api/v1/auth/login", json={
            "email": "photob@example.com", "password": "Test@12345"
        })
        from tests.conftest import extract_access_token
        user_b_headers = {"Authorization": f"Bearer {extract_access_token(login_resp)}"}

        # Try to upload to user A's event
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        resp = client.post(
            f"/api/v1/events/{event_id}/photos",
            data={"files": (io.BytesIO(fake_jpeg), "test.jpg")},
            content_type="multipart/form-data",
            headers=user_b_headers,
        )
        assert resp.status_code == 403

    def test_upload_invalid_file_type_rejected(self, client, auth_headers):
        # Create event
        create_resp = client.post("/api/v1/events", json={
            "photographer_name": "Test",
            "event_name": "Test Event",
            "event_location": "Test City",
            "event_date": "2026-09-09",
        }, headers=auth_headers)
        event_id = create_resp.json["data"]["event"]["id"]

        # Upload a text file disguised as jpg
        resp = client.post(
            f"/api/v1/events/{event_id}/photos",
            data={"files": (io.BytesIO(b"not an image at all"), "evil.jpg")},
            content_type="multipart/form-data",
            headers=auth_headers,
        )
        # File validation catches it — should be 201 with error_count or 400
        assert resp.status_code in (201, 400)
        if resp.status_code == 201:
            assert resp.json["data"]["error_count"] >= 1


class TestFaceMatchJob:

    def test_create_job_missing_event_id(self, client):
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        resp = client.post(
            "/api/v1/face-match/jobs",
            data={"file": (io.BytesIO(fake_jpeg), "selfie.jpg")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400

    def test_get_nonexistent_job(self, client):
        resp = client.get("/api/v1/face-match/jobs/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


class TestSSRFProtection:

    def test_ssrf_aws_metadata_blocked(self, client):
        import urllib.parse
        malicious_url = urllib.parse.quote("http://169.254.169.254/latest/meta-data/iam/")
        resp = client.get(f"/api/v1/face-match/download?urls={malicious_url}")
        assert resp.status_code == 400
        assert resp.json["error"]["code"] == "INVALID_URL"

    def test_ssrf_localhost_blocked(self, client):
        import urllib.parse
        malicious_url = urllib.parse.quote("http://localhost:5432/")
        resp = client.get(f"/api/v1/face-match/download?urls={malicious_url}")
        assert resp.status_code == 400

    def test_ssrf_http_blocked(self, client):
        import urllib.parse
        url = urllib.parse.quote("http://res.cloudinary.com/test/photo.jpg")  # HTTP not HTTPS
        resp = client.get(f"/api/v1/face-match/download?urls={url}")
        assert resp.status_code == 400
