"""Phase 7 — security hardening regression tests (auth, secrets, redaction)."""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core import config as cfg
from backend.app.core.config import require_production_secrets


def test_production_refuses_placeholder_secret():
    with pytest.raises(RuntimeError):
        require_production_secrets("production", "change-me-in-production")
    with pytest.raises(RuntimeError):
        require_production_secrets("PRODUCTION", "")
    require_production_secrets("development", "change-me-in-production")
    require_production_secrets("production", "s3cr3t-strong-random-value-9f8c")


def test_unauthenticated_protected_routes_rejected(monkeypatch):
    monkeypatch.setattr(cfg.settings, "API_KEY", "test-key-123")
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/conflicts?limit=1").status_code == 401
        assert c.post("/reconciliation", json={}).status_code == 401
        assert c.get("/sources").status_code == 401
        assert c.post("/sources", json={"name": "x", "source_type": "csv"}).status_code == 401
        assert c.get("/matches?limit=1").status_code == 401


def test_wrong_key_rejected_no_secret_leak(monkeypatch):
    monkeypatch.setattr(cfg.settings, "API_KEY", "test-key-123")
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/conflicts?limit=1", headers={"X-API-Key": "wrong"})
        assert r.status_code == 401
        assert "test-key-123" not in r.text


def test_correct_key_allowed_and_public_paths_open(monkeypatch):
    monkeypatch.setattr(cfg.settings, "API_KEY", "test-key-123")
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/readyz").status_code == 200
        r = c.get("/conflicts?limit=1", headers={"X-API-Key": "test-key-123"})
        assert r.status_code == 200


def test_open_mode_without_key_documents_dev_behavior(monkeypatch):
    monkeypatch.setattr(cfg.settings, "API_KEY", None)
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/conflicts?limit=1").status_code == 200


def test_connection_string_never_in_api():
    with TestClient(app) as c:
        r = c.post("/sources", json={"name": "sec-src", "source_type": "csv",
                                     "connection_string": "postgresql://boss:s3cr3t@db/x"})
        assert r.status_code == 201, r.text
        assert "connection_string" not in r.json()
        assert "s3cr3t" not in r.text
        lst = c.get("/sources").json()
        assert isinstance(lst, list)
        for item in lst:
            assert "connection_string" not in item
        body = c.get("/sources").text
        assert "s3cr3t" not in body
        from backend.app.db.database import SessionLocal
        from backend.app.db.models import SourceModel
        db = SessionLocal()
        try:
            row = db.query(SourceModel).filter(SourceModel.name == "sec-src").first()
            assert row is not None and row.connection_string == "postgresql://boss:s3cr3t@db/x"
        finally:
            db.close()


def test_rest_write_primitives_removed():
    from backend.app.connectors.rest_connector import RESTConnector
    import inspect
    assert not hasattr(RESTConnector, "post")
    assert not hasattr(RESTConnector, "put")
    assert not hasattr(RESTConnector, "delete")
    assert "method" not in inspect.signature(RESTConnector._request).parameters
    assert "body" not in inspect.signature(RESTConnector._request).parameters
