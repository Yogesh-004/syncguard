"""Phase 8B — pre-containerization implementation tests (config, no behavior change)."""
import os

import pytest
from fastapi.testclient import TestClient


def test_01_port_defaults_8000(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    from backend.app.core.config import Settings
    assert Settings().PORT == 8000


def test_02_port_configured(monkeypatch):
    monkeypatch.setenv("PORT", "9123")
    from backend.app.core.config import Settings
    assert Settings().PORT == 9123


def _init_db_globals():
    from backend.app.db import database as dbmod
    return dbmod.engine, dbmod.SessionLocal, dbmod.db_url


def _restore_init_db_globals(saved):
    from backend.app.db import database as dbmod
    dbmod.engine, dbmod.SessionLocal, dbmod.db_url = saved


def _breaking_engine():
    from sqlalchemy import create_engine
    return create_engine("postgresql://postgres@127.0.0.1:55999/syncguard_nowhere",
                         connect_args={"connect_timeout": 2})


def test_03_production_refuses_sqlite_fallback(monkeypatch):
    from backend.app.db import database as dbmod
    from backend.app.core import config as cfgmod
    from sqlalchemy.orm import sessionmaker
    saved = _init_db_globals()
    monkeypatch.setattr(cfgmod.settings, "ENV", "production")
    monkeypatch.setattr(dbmod, "engine", _breaking_engine())
    monkeypatch.setattr(dbmod, "SessionLocal",
                        sessionmaker(autocommit=False, autoflush=False, bind=dbmod.engine))
    try:
        with pytest.raises(RuntimeError, match="refusing to boot|requires PostgreSQL|ephemeral"):
            dbmod.init_db()
    finally:
        _restore_init_db_globals(saved)


def test_04_development_fallback_preserved(monkeypatch):
    from backend.app.db import database as dbmod
    from backend.app.core import config as cfgmod
    saved = _init_db_globals()
    monkeypatch.setattr(cfgmod.settings, "ENV", "development")
    try:
        dbmod.init_db()
        assert dbmod.db_url.startswith("sqlite")
    finally:
        _restore_init_db_globals(saved)


def test_05_frontend_api_contract():
    src = open("frontend/src/services/api-client.ts").read()
    assert "VITE_API_URL" in src and "'/api'" in src
    for banned in ("SECRET_KEY", "API_KEY", "X-API-Key", "DATABASE_URL", "password", "token"):
        assert banned not in src, banned


def test_06_cors_parsing_and_default_allow():
    from backend.app.main import cors_origins, app
    assert cors_origins("*") == ["*"]
    assert cors_origins("https://a.example, https://b.example") == ["https://a.example", "https://b.example"]
    assert cors_origins("") == ["*"]
    with TestClient(app) as c:
        r = c.get("/health", headers={"Origin": "https://anything.example"})
        assert r.status_code == 200


def test_07_model_artifact_bundled():
    from backend.app.services import model_service as ms
    p = ms.artifact_path()
    assert p.exists(), p
    assert p.parent.name == "models"
    assert "backend" in p.parts
    assert ms.get_model_version() == "1.0.0"


def test_08_config_loading(monkeypatch):
    monkeypatch.setenv("API_KEY", "k-test")
    monkeypatch.setenv("ENV", "development")
    from backend.app.core.config import Settings
    s = Settings()
    assert s.API_KEY == "k-test" and s.ENV == "development"
    assert s.MATCH_THRESHOLD == 0.6 and s.POSSIBLE_MATCH_THRESHOLD == 0.5


def _pg_reachable():
    import socket
    s = socket.socket()
    s.settimeout(2)
    try:
        return s.connect_ex(("127.0.0.1", 55432)) == 0
    finally:
        s.close()


def test_09_migration_chain_linear():
    import importlib.util
    mods = {}
    for rev in ("001_initial", "002_phase3_sync", "003_phase45_decision", "004_phase5c_presence"):
        path = f"D:/01_Projects/Syncguard/alembic/versions/{rev}.py"
        spec = importlib.util.spec_from_file_location(f"mig_{rev}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mods[rev] = mod
    assert mods["001_initial"].down_revision is None
    assert mods["002_phase3_sync"].down_revision == "001_initial"
    assert mods["003_phase45_decision"].down_revision == "002_phase3_sync"
    assert mods["004_phase5c_presence"].down_revision == "003_phase45_decision"


def test_10_fresh_pg_migration_matches_metadata():
    if not _pg_reachable():
        pytest.skip("disposable PG target unreachable — requires 127.0.0.1:55432")
    import subprocess
    import psycopg2
    admin = psycopg2.connect(host="127.0.0.1", port=55432, user="postgres", dbname="postgres")
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute("DROP DATABASE IF EXISTS syncguard_8btest")
    cur.execute("CREATE DATABASE syncguard_8btest")
    admin.close()
    try:
        env = dict(os.environ, DATABASE_URL="postgresql://postgres@127.0.0.1:55432/syncguard_8btest")
        r = subprocess.run(["python", "-m", "alembic", "upgrade", "head"], cwd="D:/01_Projects/Syncguard",
                           env=env, capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-2000:]
        from sqlalchemy import inspect, create_engine
        from backend.app.db.database import Base
        import backend.app.db.models  # noqa: F401
        eng = create_engine("postgresql://postgres@127.0.0.1:55432/syncguard_8btest")
        try:
            insp = inspect(eng)
            db_tables = set(insp.get_table_names())
            for t in Base.metadata.tables:
                assert t in db_tables, t
                mcols = {c.name for c in Base.metadata.tables[t].columns}
                dcols = {c["name"] for c in insp.get_columns(t)}
                assert mcols == dcols, (t, mcols ^ dcols)
        finally:
            eng.dispose()
    finally:
        admin = psycopg2.connect(host="127.0.0.1", port=55432, user="postgres", dbname="postgres")
        admin.autocommit = True
        admin.cursor().execute("DROP DATABASE IF EXISTS syncguard_8btest")
        admin.close()

@pytest.fixture
def _clean_settings(monkeypatch):
    monkeypatch.delenv("MAX_UPLOAD_ROWS", raising=False)
    monkeypatch.delenv("MAX_JOB_RECORDS", raising=False)


def test_12_scope_defaults(_clean_settings):
    from backend.app.core.config import Settings
    s = Settings()
    assert s.MAX_UPLOAD_ROWS == 1000, s.MAX_UPLOAD_ROWS
    assert s.MAX_JOB_RECORDS == 1000, s.MAX_JOB_RECORDS


def test_13_scope_env_override(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_ROWS", "5000")
    monkeypatch.setenv("MAX_JOB_RECORDS", "4000")
    from backend.app.core.config import Settings
    s = Settings()
    assert (s.MAX_UPLOAD_ROWS, s.MAX_JOB_RECORDS) == (5000, 4000)


def _csv_rows(n, tag):
    lines = ["rec_id,given_name,surname,email,phone,postcode"]
    for i in range(n):
        lines.append(f"{tag}-{i},A{i},B{i},u{i}@x.com,9{i:07d},{10000 + i}")
    return ("\n".join(lines) + "\n").encode()


def test_14_boundary_1000_accepted_1001_rejected():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.core.config import settings
    headers = {}
    key = (settings.API_KEY or "").strip()
    if key:
        headers["X-API-Key"] = key
    with TestClient(app) as c:
        ok = c.post("/uploads", files={"file": ("b.csv", _csv_rows(1000, "ok"), "text/csv")},
                    headers=headers)
        assert ok.status_code == 201, ok.text[:200]
        big = c.post("/uploads", files={"file": ("b.csv", _csv_rows(1001, "no"), "text/csv")},
                     headers=headers)
        assert big.status_code == 413, big.status_code
        assert "1000" in big.text


def test_15_job_guard_enforced(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.core import config as cfgmod
    from backend.app.db.database import SessionLocal
    from backend.app.db.models import ReconciliationJobModel
    monkeypatch.setattr(cfgmod.settings, "MAX_JOB_RECORDS", 2)
    headers = {}
    key = (cfgmod.settings.API_KEY or "").strip()
    if key:
        headers["X-API-Key"] = key
    with TestClient(app) as c:
        sid = c.post("/uploads", files={"file": ("g.csv", _csv_rows(3, "gd"), "text/csv")},
                     headers=headers).json()["source_id"]
        r = c.post("/reconciliation", json={"source_ids": [sid]},
                   headers=headers).json()
        db = SessionLocal()
        try:
            for _ in range(60):
                job = db.query(ReconciliationJobModel).filter(
                    ReconciliationJobModel.id == r["job_id"]).first()
                db.refresh(job)
                if job.status in ("completed", "failed"):
                    break
                import time
                time.sleep(1)
            assert job.status == "failed", job.status
            assert "MAX_JOB_RECORDS" in (job.error_message or "")
        finally:
            db.close()
