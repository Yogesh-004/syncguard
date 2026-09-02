"""Database configuration and session management."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from backend.app.core.config import settings
from backend.app.core.logging import logger

db_url = settings.DATABASE_URL
connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
engine = create_engine(db_url, pool_pre_ping=True, echo=settings.DEBUG, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    import backend.app.db.models
    global engine, SessionLocal, db_url
    try:
        Base.metadata.create_all(bind=engine)
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("Database initialized", db_url=db_url)
        return
    except Exception as e:
        logger.error("Postgres init failed, falling back to sqlite", error=str(e))
        fallback_url = "sqlite:///./test_local.db"
        connect_args2 = {"check_same_thread": False}
        engine = create_engine(fallback_url, pool_pre_ping=True, connect_args=connect_args2)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db_url = fallback_url
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized (fallback sqlite)", db_url=db_url)


def get_engine():
    return engine
