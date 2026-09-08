"""Application configuration via environment variables."""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "SyncGuard"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    ENV: str = "development"
    PORT: int = 8000
    API_KEY: Optional[str] = None
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/syncguard"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    MAX_UPLOAD_SIZE_MB: int = 10
    DEMO_MODE: bool = True
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "*"
    MATCH_THRESHOLD: float = 0.6
    POSSIBLE_MATCH_THRESHOLD: float = 0.5
    PERSIST_NOMATCH_SAMPLE: int = 100
    MAX_JOB_RECORDS: int = 2000
    MAX_UPLOAD_ROWS: int = 10000
    MAX_FIELD_CHARS: int = 10000
    PHONE_DEFAULT_REGION: str = "US"
    BLOCKING_PASSES: str = "postcode,name,phone,email"
    EXHAUSTIVE_PAIR_LIMIT: int = 50000
    MAX_CANDIDATES: int = 500000
    MAX_BLOCK_SIZE: int = 500

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


PLACEHOLDER_SECRETS = {"", "change-me-in-production", "changeme", "secret", "test"}


def require_production_secrets(env: str, secret_key: Optional[str]) -> None:
    """Fail clearly when production would run on an unsafe SECRET_KEY.

    Development keeps the historical warning path in main.lifespan; production
    refuses to start. Pure function so tests can exercise it directly.
    """
    if str(env or "").lower() == "production" and (secret_key or "") in PLACEHOLDER_SECRETS:
        raise RuntimeError(
            "Refusing to start with placeholder SECRET_KEY in production. "
            "Set a strong SECRET_KEY environment value.")


settings = Settings()
