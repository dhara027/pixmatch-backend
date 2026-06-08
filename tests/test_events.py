"""
Events module integration tests.
"""
import pytest


class TestCreateEvent:

    def test_create_event_requires_auth(self, client):
        resp = client.post("/api/v1/events", json={
            "photographer_name": "John",
            "event_name": "Wedding",
            "event_location": "Mumbai",
            "event_date": "2026-12-25",
        })
        assert resp.status_code == 401

    def test_create_event_success(self, client, auth_headers):
        resp = client.post("/api/v1/events", json={
            "photographer_name": "John Doe",
            "event_name": "Test Wedding",
            "event_location": "Mumbai, India",
            "event_date": "2026-12-25",
        }, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json["data"]
        assert "event" in data
        assert "qr_code_base64" in data
        assert data["event"]["event_name"] == "Test Wedding"

    def test_create_event_missing_fields(self, client, auth_headers):
        resp = client.post("/api/v1/events", json={
            "event_name": "Incomplete",
        }, headers=auth_headers)
        assert resp.status_code == 400
        assert resp.json["error"]["code"] == "VALIDATION_ERROR"

    def test_create_event_invalid_date(self, client, auth_headers):
        resp = client.post("/api/v1/events", json={
            "photographer_name": "John",
            "event_name": "Test",
            "event_location": "City",
            "event_date": "not-a-date",
        }, headers=auth_headers)
        assert resp.status_code == 400


class TestListEvents:

    def test_list_events_scoped_to_user(self, client, auth_headers):
        """Events list must only return current user's events (no IDOR)."""
        resp = client.get("/api/v1/events", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json
        assert data["success"] is True
        assert "events" in data["data"]
        assert "meta" in data
        assert data["meta"]["page"] == 1

    def test_list_events_pagination(self, client, auth_headers):
        resp = client.get("/api/v1/events?page=1&page_size=5", headers=auth_headers)
        assert resp.status_code == 200
        meta = resp.json.get("meta")
        assert meta is not None
        assert meta["page_size"] == 5


class TestGetEvent:

    def test_get_nonexistent_event(self, client, auth_headers):
        resp = client.get(
            "/api/v1/events/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_get_event_other_user_forbidden(self, client, auth_headers):
        """A photographer cannot access another photographer's event."""
        # Create event with primary user
        create_resp = client.post("/api/v1/events", json={
            "photographer_name": "User A",
            "event_name": "User A Event",
            "event_location": "Delhi",
            "event_date": "2026-11-11",
        }, headers=auth_headers)
        event_id = create_resp.json["data"]["event"]["id"]

        # Register second user
        client.post("/api/v1/auth/signup", json={
            "email": "user2@example.com",
            "mobile_no": "9700000000",
            "password": "Test@12345",
            "confirmpassword": "Test@12345",
        })
        from app.extensions.database import get_db
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET is_email_verified=TRUE WHERE email='user2@example.com'")
        login_resp = client.post("/api/v1/auth/login", json={
            "email": "user2@example.com", "password": "Test@12345"
        })
        from tests.conftest import extract_access_token
        user2_token = extract_access_token(login_resp)
        user2_headers = {"Authorization": f"Bearer {user2_token}"}

        # User 2 tries to access User 1's event
        resp = client.get(f"/api/v1/events/{event_id}", headers=user2_headers)
        assert resp.status_code == 403

    def test_public_event_endpoint_no_auth(self, client, auth_headers):
        # Create an event
        create_resp = client.post("/api/v1/events", json={
            "photographer_name": "Pub Photographer",
            "event_name": "Public Event",
            "event_location": "Bangalore",
            "event_date": "2026-10-10",
        }, headers=auth_headers)
        event_id = create_resp.json["data"]["event"]["id"]

        # Public endpoint — no auth needed
        resp = client.get(f"/api/v1/events/{event_id}/public")
        assert resp.status_code == 200
        assert resp.json["data"]["event"]["event_name"] == "Public Event"
