"""Integration tests for the API."""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "message" in response.json()

    def test_docs(self, client):
        response = client.get("/docs")
        assert response.status_code == 200