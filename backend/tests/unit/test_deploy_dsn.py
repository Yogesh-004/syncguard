"""Render-compat DSN normalization (deployment correctness, no behavior change)."""


def test_11_database_url_scheme_normalized(monkeypatch):
    from backend.app.core.config import normalize_database_url, Settings
    assert normalize_database_url("postgres://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"
    assert normalize_database_url("postgresql://u@h/db?sslmode=require").endswith("?sslmode=require")
    assert normalize_database_url("sqlite:///./test.db").startswith("sqlite")
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h:5432/db")
    assert Settings().DATABASE_URL == "postgresql://u:p@h:5432/db"
