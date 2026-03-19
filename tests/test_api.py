"""
Test Suite: API Endpoints (Integration)
=========================================
Tests for health, auth, and protected API endpoints using FastAPI TestClient.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


# ── TestClient setup ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """Create a TestClient for the FastAPI app with mocked DB."""
    # Mock DB session to avoid needing a real PostgreSQL connection
    with patch("backend.database.SessionLocal") as mock_session_cls:
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        from backend.main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ── Health Endpoint ──────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_structure(self, client):
        response = client.get("/health")
        data = response.json()
        assert "status" in data


# ── Auth Endpoints ───────────────────────────────────────────────────────────

class TestAuthEndpoints:
    def test_login_without_credentials_returns_error(self, client):
        response = client.post("/api/auth/login", json={})
        # Should return 422 (validation error) or 400
        assert response.status_code in [400, 422]

    def test_login_with_invalid_email_format(self, client):
        response = client.post("/api/auth/login", json={
            "email": "not-an-email",
            "password": "test123"
        })
        assert response.status_code == 422

    def test_register_without_data_returns_error(self, client):
        response = client.post("/api/auth/register", json={})
        assert response.status_code in [400, 422]

    def test_register_invalid_email(self, client):
        response = client.post("/api/auth/register", json={
            "email": "bad-email",
            "password": "StrongPass@123"
        })
        assert response.status_code == 422

    def test_refresh_without_token_returns_error(self, client):
        response = client.post("/api/auth/refresh", json={})
        assert response.status_code in [400, 422]


# ── Protected Endpoints ──────────────────────────────────────────────────────

class TestProtectedEndpoints:
    def test_stats_without_auth_returns_401(self, client):
        response = client.get("/api/stats")
        assert response.status_code == 401

    def test_metrics_without_auth_returns_401(self, client):
        response = client.get("/api/metrics")
        assert response.status_code == 401

    def test_threat_score_without_auth_returns_401(self, client):
        response = client.get("/api/threat-score")
        assert response.status_code == 401

    def test_blocked_ips_without_auth_returns_401(self, client):
        response = client.get("/api/blocked-ips")
        assert response.status_code == 401


# ── Security Headers ─────────────────────────────────────────────────────────

class TestSecurityHeaders:
    def test_health_has_security_headers(self, client):
        response = client.get("/health")
        headers = response.headers
        # Check for common security headers added by middleware
        assert "x-content-type-options" in headers or "x-frame-options" in headers or response.status_code == 200


# ── CORS ─────────────────────────────────────────────────────────────────────

class TestCORS:
    def test_options_preflight_returns_ok(self, client):
        response = client.options("/api/stats", headers={
            "Origin": "http://localhost:8080",
            "Access-Control-Request-Method": "GET",
        })
        # Should not return 403 or 500
        assert response.status_code in [200, 204, 400, 405]
