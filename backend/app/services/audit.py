"""Audit logging service."""
from datetime import datetime
from typing import Any, Dict, Optional, List
from backend.app.core.logging import logger
from backend.app.db.database import SessionLocal
from backend.app.db.models import AuditLogModel


class AuditService:
    def __init__(self):
        self._buffer: List[Dict[str, Any]] = []
        self._max_buffer = 1000

    def log(self, action: str, entity_type: Optional[str] = None, entity_id: Optional[str] = None,
            request_id: Optional[str] = None, job_id: Optional[int] = None,
            source_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None,
            processing_time_ms: Optional[int] = None, error: Optional[str] = None,
            db: Optional[SessionLocal] = None) -> None:
        entry = {
            "request_id": request_id,
            "job_id": job_id,
            "source_id": source_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "details": details,
            "processing_time_ms": processing_time_ms,
            "error": error,
            "created_at": datetime.utcnow(),
        }
        self._buffer.append(entry)
        logger.info(action, **{k: v for k, v in entry.items() if v is not None})
        if len(self._buffer) >= self._max_buffer:
            self.flush(db=db)

    def flush(self, db: Optional[SessionLocal] = None, close: bool = True) -> int:
        if not self._buffer:
            return 0
        own_session = db is None
        if db is None:
            db = SessionLocal()
        try:
            for entry in self._buffer:
                log_entry = AuditLogModel(**entry)
                db.add(log_entry)
            db.commit()
            count = len(self._buffer)
            self._buffer.clear()
            logger.info("Audit logs flushed", count=count)
            return count
        except Exception as e:
            db.rollback()
            logger.error("Audit flush failed", error=str(e))
            self._buffer.clear()
            return 0
        finally:
            if db and (close or own_session):
                db.close()

    def get_logs(self, request_id: Optional[str] = None, job_id: Optional[int] = None,
                 source_id: Optional[str] = None, limit: int = 100, db: Optional[SessionLocal] = None) -> List[Dict[str, Any]]:
        if db is None:
            db = SessionLocal()
        query = db.query(AuditLogModel)
        if request_id:
            query = query.filter(AuditLogModel.request_id == request_id)
        if job_id:
            query = query.filter(AuditLogModel.job_id == job_id)
        if source_id:
            query = query.filter(AuditLogModel.source_id == source_id)
        logs = query.order_by(AuditLogModel.created_at.desc()).limit(limit).all()
        results = [
            {
                "id": log.id,
                "request_id": log.request_id,
                "job_id": log.job_id,
                "source_id": log.source_id,
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "details": log.details,
                "processing_time_ms": log.processing_time_ms,
                "error": log.error,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
        return results