"""Phase 8B Supabase deltas — managed-Postgres compatibility guards.

No product behavior touched. Supabase PostgreSQL is standard PostgreSQL over
a DSN; these tests pin the properties that keep it that way.
"""
import os

import pytest


def test_01_database_url_honored_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u@host:5432/db?sslmode=require")
    from backend.app.core.config import Settings
    assert Settings().DATABASE_URL == "postgresql://u@host:5432/db?sslmode=require"


def test_02_driver_and_pool_standard():
    import psycopg2  # noqa: F401 - the only PG driver the app needs
    src = open("backend/app/db/database.py").read()
    assert "pool_pre_ping=True" in src
    assert "NullPool" not in src


def test_03_no_supabase_incompatible_sql():
    import pathlib
    banned = ("CREATE EXTENSION", "pg_advisory", "LISTEN ", "NOTIFY ",
              "prepare_threshold", "server_side_cursors")
    hits = []
    for p in pathlib.Path("backend/app").rglob("*.py"):
        text = p.read_text(errors="ignore")
        for b in banned:
            if b in text:
                hits.append((str(p), b))
    assert hits == [], hits


def test_04_no_session_level_db_options_in_production_path():
    src = open("backend/app/connectors/postgres_connector.py").read()
    assert "self.options" in src
    prod = open("backend/app/services/resolution.py").read()
    assert "options=" not in prod


def test_05_clean_room_model_load():
    import subprocess
    r = subprocess.run(
        ["python", "-c",
         "import sys; sys.path.insert(0, 'D:/01_Projects/Syncguard');"
         "import logging; logging.disable(logging.CRITICAL);"
         "from backend.app.services import model_service as ms;"
         "ms.load_model(); assert ms.get_model_version() == '1.0.0'; print('ok')"],
        cwd="C:/Windows/Temp", capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-1500:]
    assert "ok" in r.stdout


def test_06_redis_not_required_by_config():
    from backend.app.core.config import Settings
    s = Settings()
    assert s.REDIS_URL is not None
    routes = open("backend/app/api/routes.py").read()
    assert 'os.getenv("CELERY_BROKER_URL")' in routes
