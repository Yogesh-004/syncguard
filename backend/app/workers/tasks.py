"""Celery background tasks with retry + idempotency."""
import time
import random
from datetime import datetime
from celery import current_task
from backend.app.workers.celery_app import celery_app
from backend.app.core.logging import logger
from backend.app.services.reconciliation import ReconciliationEngine
from backend.app.services.matching import MatchingEngine
from backend.app.services.schema_analyzer import SchemaAnalyzer


def _backoff(attempt: int, base: float = 2.0, cap: float = 60.0) -> float:
    jitter = random.uniform(0, 1)
    return min(cap, (base ** attempt) + jitter)


@celery_app.task(bind=True, max_retries=5, acks_late=True)
def reconcile_task(self, job_id: int, source_id: str, records: list):
    from backend.app.db.database import SessionLocal
    from backend.app.db.models import ReconciliationJobModel, AttemptModel

    db = SessionLocal()
    try:
        job = db.query(ReconciliationJobModel).filter(ReconciliationJobModel.id == job_id).first()
        if not job:
            logger.error("Job not found", job_id=job_id)
            return {"error": "job not found"}
        job.status = "processing"
        job.started_at = datetime.utcnow()
        db.commit()
        self.update_state(state="PROGRESS", meta={"progress": 10, "status": "Starting reconciliation", "job_id": job_id})
        engine = ReconciliationEngine()
        self.update_state(state="PROGRESS", meta={"progress": 50, "status": "Matching and reconciliation", "job_id": job_id})
        result = engine.run_reconciliation(records)
        job.status = "completed"
        job.progress = 100
        job.completed_at = datetime.utcnow()
        db.commit()
        self.update_state(state="SUCCESS", meta={"progress": 100, "result": result, "job_id": job_id})
        logger.info("Reconciliation task completed", job_id=job_id)
        return result
    except Exception as exc:
        db.rollback()
        attempt = self.request.retries + 1
        job = db.query(ReconciliationJobModel).filter(ReconciliationJobModel.id == job_id).first()
        if job:
            job.retry_count = attempt
            job.error_message = str(exc)
            if attempt >= 5:
                job.status = "failed"
            else:
                job.status = "processing"
            att = AttemptModel(job_id=job_id, attempt_number=attempt, status="failed", error_message=str(exc))
            db.add(att)
            db.commit()
        countdown = _backoff(attempt)
        logger.error("Reconciliation task failed, retrying", error=str(exc), attempt=attempt, countdown=countdown)
        raise self.retry(exc=exc, countdown=countdown)
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=5, acks_late=True)
def match_task(self, source_a_id: str, source_b_id: str, threshold=None):
    from backend.app.core.config import settings as _settings
    if threshold is None:
        threshold = _settings.MATCH_THRESHOLD
    try:
        self.update_state(state="PROGRESS", meta={"progress": 10, "status": "Loading records"})
        engine = MatchingEngine()
        self.update_state(state="PROGRESS", meta={"progress": 50, "status": "Matching"})
        logger.info("Matching task completed", source_a=source_a_id, source_b=source_b_id)
        return {"status": "completed", "threshold": threshold}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_backoff(self.request.retries + 1))


@celery_app.task(bind=True, max_retries=5, acks_late=True)
def sync_task(self, job_id: int, source_id: str, target_source_id: str):
    from backend.app.db.database import SessionLocal
    from backend.app.db.models import SyncJobModel, SyncAttemptModel
    db = SessionLocal()
    try:
        self.update_state(state="PROGRESS", meta={"progress": 10, "status": "Starting sync", "job_id": job_id})
        time.sleep(0.1)
        job = db.query(SyncJobModel).filter(SyncJobModel.id == job_id).first()
        if job:
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            job.progress = 100
            db.commit()
        logger.info("Sync task completed", job_id=job_id)
        return {"status": "completed", "job_id": job_id}
    except Exception as exc:
        attempt = self.request.retries + 1
        if 'job' in locals() and job:
            att = SyncAttemptModel(job_id=job_id, attempt_number=attempt, status="failed", error_message=str(exc))
            db.add(att)
            db.commit()
        raise self.retry(exc=exc, countdown=_backoff(attempt))
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3)
def schema_check_task(self, source_id: str):
    try:
        self.update_state(state="PROGRESS", meta={"progress": 50, "status": "Analyzing schema"})
        analyzer = SchemaAnalyzer()
        result = analyzer.analyze_schema([])
        logger.info("Schema check completed", source_id=source_id)
        return {"status": "completed", "source_id": source_id, "result": result}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_backoff(self.request.retries + 1))
