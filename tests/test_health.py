"""Tests for GET /health endpoint."""


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "enterprise-kb-api"
    assert data["version"] == "0.1.0"
