"""Pytest configuration and fixtures."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Override database URL before any app imports
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["DEMO_MODE"] = "true"

import pytest
from backend.app.core.config import settings

# Force re-creation of engine with SQLite URL
from backend.app.db.database import engine as _engine, SessionLocal as _SessionLocal, Base as _Base


@pytest.fixture(scope="session")
def app_settings():
    return settings


@pytest.fixture(scope="session")
def test_db():
    _Base.metadata.create_all(bind=_engine)
    yield _SessionLocal()
    _Base.metadata.drop_all(bind=_engine)
    _SessionLocal().close()


@pytest.fixture
def db_session(test_db):
    yield test_db
    test_db.close()


@pytest.fixture
def sample_record():
    return {
        "source_id": "test-source",
        "source_record_id": "rec-001",
        "data": {"name": "John Doe", "email": "john@example.com"},
        "raw_data": None,
    }