"""Dependency injections for FastAPI routes."""
from typing import Generator
from sqlalchemy.orm import Session
from backend.app.db.database import SessionLocal, get_db
from backend.app.core.logging import logger
from backend.app.services.audit import AuditService


def get_audit_service() -> AuditService:
    return AuditService()


def get_request_id() -> str:
    import uuid
    request_id = str(uuid.uuid4())
    logger.info("Request started", request_id=request_id)
    return request_id


__all__ = ["get_db", "get_audit_service", "get_request_id"]