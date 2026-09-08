"""Human-in-the-loop resolution service (Phase 3).

Lifecycle: OPEN(pending) -> REVIEWED -> RESOLVED(approved/modified)/REJECTED/DEFERRED.
Resolution rows live in `resolution_logs` (no migration); structured payload in
`detail` JSON: {canonical, selected_source, previous_value, resolved_value,
reason, field_name, dry_run, sync_job_id}. Original conflict rows are never
mutated except status/detail metadata — conflicting_fields stay historical.
"""
import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from backend.app.core.logging import logger
from backend.app.services import normalization as nz

CANONICAL = {
    "approve": "USE_SOURCE_A", "approved": "USE_SOURCE_A", "USE_SOURCE_A": "USE_SOURCE_A",
    "reject": "REJECT", "rejected": "REJECT", "REJECT": "REJECT",
    "modify": "MANUAL_EDIT", "modified": "MANUAL_EDIT", "MANUAL_EDIT": "MANUAL_EDIT",
    "defer": "DEFER", "deferred": "DEFER", "DEFER": "DEFER",
    "USE_SOURCE_B": "USE_SOURCE_B",
}
STATUS_FOR = {"USE_SOURCE_A": "approved", "USE_SOURCE_B": "approved", "MANUAL_EDIT": "modified", "REJECT": "rejected", "DEFER": "deferred"}
TERMINAL = {"approved", "rejected", "modified", "deferred"}
RETRYABLE = {408, 429, 500, 502, 503}
NON_RETRYABLE = {400, 401, 403, 404, 409, 422}

LEGACY_STATUS = {"pending": "OPEN", "approved": "RESOLVED", "modified": "RESOLVED", "rejected": "RESOLVED(rejected)", "deferred": "DEFERRED"}


class ResolutionError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def _field_of(conflict) -> Tuple[str, Any, Any]:
    fields = conflict.conflicting_fields or []
    f = fields[0] if fields else {}
    vals = f.get("values", {}) if isinstance(f, dict) else {}
    return (f.get("field_name", "unknown") if isinstance(f, dict) else "unknown",
            vals.get("a"), vals.get("b"))


def validate_value(field: str, value: Any) -> None:
    kind = field.lower()
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ResolutionError(422, f"Empty value not allowed for field '{field}'")
    if "email" in kind:
        v = nz.normalize_email(str(value))
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ResolutionError(422, f"Invalid email for field '{field}'")
    elif "phone" in kind:
        import re
        if len(re.sub(r"\D", "", str(value))) < 7:
            raise ResolutionError(422, f"Invalid phone for field '{field}'")
    elif "date" in kind:
        if nz.normalize_date(value) is None:
            raise ResolutionError(422, f"Invalid date for field '{field}'")
    elif field.lower() in ("amount", "price", "total", "value", "transaction_amount"):
        if nz.normalize_numeric(value) is None:
            raise ResolutionError(422, f"Invalid numeric for field '{field}'")


def _payload(conflict, action: str, modified_values: Optional[Dict[str, Any]], reason: Optional[str]) -> Dict[str, Any]:
    field, va, vb = _field_of(conflict)
    if action == "USE_SOURCE_A":
        return {"field_name": field, "selected_source": "A", "previous_value": vb, "resolved_value": va,
                "original_a": va, "original_b": vb, "reason": reason}
    if action == "USE_SOURCE_B":
        return {"field_name": field, "selected_source": "B", "previous_value": va, "resolved_value": vb,
                "original_a": va, "original_b": vb, "reason": reason}
    if action == "MANUAL_EDIT":
        mv = modified_values or {}
        new_val = mv.get(field, mv.get("value", mv.get("resolved_value")))
        if new_val is None:
            raise ResolutionError(422, f"MANUAL_EDIT requires a value for field '{field}'")
        validate_value(field, new_val)
        return {"field_name": field, "selected_source": "MANUAL", "previous_value": {"a": va, "b": vb},
                "resolved_value": new_val, "original_a": va, "original_b": vb, "reason": reason}
    if action == "REJECT":
        return {"field_name": field, "selected_source": None, "previous_value": {"a": va, "b": vb},
                "resolved_value": None, "original_a": va, "original_b": vb, "reason": reason or "rejected by reviewer"}
    return {"field_name": field, "selected_source": None, "previous_value": {"a": va, "b": vb},
            "resolved_value": None, "original_a": va, "original_b": vb, "reason": reason or "deferred for later review"}


def resolve_conflict(db, conflict, action_raw: str, modified_values: Optional[Dict[str, Any]] = None,
                     reason: Optional[str] = None, user: Optional[str] = None):
    from backend.app.db.models import ResolutionLogModel, AuditLogModel, ConflictModel
    if action_raw not in CANONICAL:
        raise ResolutionError(422, f"Invalid action '{action_raw}'")
    action = CANONICAL[action_raw]
    status = STATUS_FOR[action]
    # atomic claim: only one writer can move pending -> terminal (concurrency guard);
    # claim + resolution insert commit together so no half-state survives a crash.
    claimed = False
    if conflict.resolution_status == "pending":
        claimed = db.query(ConflictModel).filter(ConflictModel.id == conflict.id, ConflictModel.resolution_status == "pending").update(
            {"resolution_status": status}, synchronize_session=False) == 1
        if not claimed:
            db.rollback()
            conflict = _conflict_of(db, conflict.id)
    if not claimed:
        # idempotency: identical repeat returns existing resolution
        if conflict.resolution_status in TERMINAL:
            existing = db.query(ResolutionLogModel).filter(ResolutionLogModel.conflict_id == conflict.id).order_by(ResolutionLogModel.id.desc()).first()
            if existing:
                try:
                    prev = json.loads(existing.detail or "{}")
                except Exception:
                    prev = {}
                if prev.get("canonical") == action and prev.get("resolved_value") == (_payload(conflict, action, modified_values, reason).get("resolved_value")):
                    logger.info("RESOLUTION_ALREADY_APPLIED", conflict_id=conflict.id, action=action)
                    return existing, False
            raise ResolutionError(409, f"Conflict {conflict.id} already resolved as '{conflict.resolution_status}'")
        # pending but claim lost handled above; unreachable safety:
        raise ResolutionError(409, f"Conflict {conflict.id} is being resolved concurrently")
    payload = _payload(conflict, action, modified_values, reason)
    payload.update({"canonical": action, "status": status, "reviewed_at": datetime.utcnow().isoformat()})
    row = ResolutionLogModel(conflict_id=conflict.id, action=status, detail=json.dumps(payload), resolved_by=user)
    db.add(row)
    db.flush()
    conflict.resolution_status = status
    conflict.resolution_detail = json.dumps({"resolved_value": payload["resolved_value"], "selected_source": payload["selected_source"]})
    conflict.resolved_at = datetime.utcnow()
    if user:
        conflict.resolved_by = user
    db.add(AuditLogModel(action="CONFLICT_REVIEWED", entity_type="conflict", entity_id=str(conflict.id),
                         details={"conflict_id": conflict.id, "match_id": conflict.match_id}))
    db.add(AuditLogModel(action="RESOLUTION_CREATED", entity_type="resolution", entity_id=str(row.id),
                         details={"conflict_id": conflict.id, "match_id": conflict.match_id, "action": action,
                                  "before": {"a": payload["original_a"], "b": payload["original_b"]},
                                  "after": {"resolved_value": payload["resolved_value"], "selected_source": payload["selected_source"]}}))
    if action == "DEFER":
        db.add(AuditLogModel(action="CONFLICT_DEFERRED", entity_type="conflict", entity_id=str(conflict.id), details={"reason": payload["reason"]}))
    if action == "REJECT":
        db.add(AuditLogModel(action="CONFLICT_REJECTED", entity_type="conflict", entity_id=str(conflict.id), details={"reason": payload["reason"]}))
    db.commit()
    db.refresh(row)
    logger.info("RESOLUTION_CREATED", conflict_id=conflict.id, resolution_id=row.id, action=action)
    return row, True


def idempotency_key(resolution_id: int, destination: str, resolved_value: Any) -> str:
    h = hashlib.sha256(json.dumps(resolved_value, sort_keys=True, default=str).encode()).hexdigest()[:12]
    return f"res-{resolution_id}|{destination}|{h}"


def _resolution_payload(row) -> Dict[str, Any]:
    try:
        return json.loads(row.detail or "{}")
    except Exception:
        return {}


def _destination_for(db, conflict) -> Tuple[str, Any]:
    from backend.app.db.models import RecordModel, SourceModel
    target = db.query(RecordModel).filter(RecordModel.id == conflict.record_b_id).first()
    src = db.query(SourceModel).filter(SourceModel.id == target.source_id).first() if target else None
    name = src.name if src else f"source-{target.source_id if target else '?'}"
    return f"MOCK {name}", (target.id if target else conflict.record_b_id)


def _pg_target_for(db, conflict) -> Optional[Dict[str, Any]]:
    """Return PG target config if the conflict's target source routes to the
    controlled PostgreSQL target (source.config['pg_target']), else None.
    Minimal compatible extension: mock path untouched when absent."""
    from backend.app.db.models import RecordModel, SourceModel
    target = db.query(RecordModel).filter(RecordModel.id == conflict.record_b_id).first()
    if not target:
        return None
    src = db.query(SourceModel).filter(SourceModel.id == target.source_id).first()
    cfg = (src.config or {}) if src else {}
    pg = cfg.get("pg_target")
    if not isinstance(pg, dict) or not pg.get("enabled"):
        return None
    return {"table": pg.get("table", "customer_records"),
            "record_key": str(target.source_record_id or target.id),
            "source_id": target.source_id}


def _select_connector(destination: str, pg_table: Optional[str] = None):
    from backend.app.connectors.mock_connector import MockConnector
    if pg_table:
        from backend.app.connectors.postgres_connector import PostgresConnector
        return PostgresConnector(table=pg_table)
    return MockConnector(destination)


def dry_run_resolution(db, resolution_id: int):
    from backend.app.db.models import ResolutionLogModel, SyncJobModel, AuditLogModel
    row = db.query(ResolutionLogModel).filter(ResolutionLogModel.id == resolution_id).first()
    if not row:
        raise ResolutionError(404, "Resolution not found")
    payload = _resolution_payload(row)
    if payload.get("canonical") in ("REJECT", "DEFER"):
        raise ResolutionError(422, "Rejected/deferred resolutions cannot be dry-run")
    conflict = _conflict_of(db, row.conflict_id)
    destination, record_id = _destination_for(db, conflict)
    field = payload.get("field_name", "unknown")
    current = _current_value(db, conflict, field)
    proposed = payload.get("resolved_value")
    pg_cfg = _pg_target_for(db, conflict)
    pg_preview = None
    if pg_cfg:
        from backend.app.connectors.postgres_connector import PostgresConnector
        _pg = PostgresConnector(table=pg_cfg["table"])
        destination = _pg.destination
        record_id = pg_cfg["record_key"]
        _preview_key = idempotency_key(resolution_id, destination, proposed)
        pg_preview = _pg.preview(pg_cfg["record_key"], field, proposed, _preview_key)
        current = pg_preview["current_value"]
    key = idempotency_key(resolution_id, destination, proposed)
    existing = db.query(SyncJobModel).filter(SyncJobModel.idempotency_key == key).first()
    if existing:
        return existing, False
    job = SyncJobModel(resolution_id=row.id, source_id=str(conflict.record_a_id), target_source_id=str(conflict.record_b_id),
                       destination=destination, operation="UPDATE", field_name=field, resolved_value=proposed,
                       status="DRY_RUN", progress=100.0, attempt_count=0,
                       idempotency_key=key, started_at=datetime.utcnow(), completed_at=datetime.utcnow(),
                       response_metadata={"current_value": current, "proposed_value": proposed, "dry_run": True,
                                          **({"pg_expected_version": pg_preview["expected_version"],
                                              "pg_current_version": pg_preview["current_version"],
                                              "pg_record_key": pg_cfg["record_key"]} if pg_preview else {})})
    db.add(job)
    payload["dry_run"] = {"sync_job_id": None, "status": "DRY_RUN", "current_value": current, "proposed_value": proposed}
    db.flush()
    payload["dry_run"]["sync_job_id"] = job.id
    row.detail = json.dumps(payload)
    db.add(AuditLogModel(action="DRY_RUN_STARTED", entity_type="resolution", entity_id=str(row.id), details={"conflict_id": conflict.id}))
    db.add(AuditLogModel(action="DRY_RUN_COMPLETED", entity_type="sync_job", entity_id=str(job.id),
                         details={"conflict_id": conflict.id, "destination": destination, "field": field,
                                  "current_value": current, "proposed_value": proposed, "operation": "UPDATE", "result": "DRY RUN SUCCESS"}))
    db.commit()
    db.refresh(job)
    logger.info("DRY_RUN_COMPLETED", resolution_id=row.id, sync_job_id=job.id)
    return job, True


def _conflict_of(db, conflict_id: int):
    from backend.app.db.models import ConflictModel
    c = db.query(ConflictModel).filter(ConflictModel.id == conflict_id).first()
    if not c:
        raise ResolutionError(404, "Conflict not found")
    return c


def _current_value(db, conflict, field: str):
    from backend.app.db.models import RecordModel
    target = db.query(RecordModel).filter(RecordModel.id == conflict.record_b_id).first()
    if target and isinstance(target.data, dict):
        return target.data.get(field)
    return None


def _safe_confirm(connector, record_key: str, field: str, value: Any,
                  version_after: int, key: str) -> Optional[Dict[str, Any]]:
    """confirm() that never raises: returns None when the target itself is
    unreachable, so callers can mark the outcome UNKNOWN instead of guessing."""
    try:
        return connector.confirm(record_key, field, value, version_after, key)
    except Exception as exc:
        logger.error("PG_CONFIRM_FAILED", error=str(exc)[:200])
        return None


def _pg_confirmed_apply(connector, record_key: str, field: str, proposed: Any,
                        expected: int, key: str) -> Tuple[Dict[str, Any], bool, str]:
    """PG apply with verify-before-retry. Never blindly repeats a mutation.

    Returns (resp, verified, outcome) with outcome in:
    applied | recovered | mismatch | diverged | unknown.
    Raises only for definitive refusals (stale/missing/invalid/collision) and
    for proved-not-applied transients (safe to retry upstream).
    """
    from backend.app.connectors.postgres_connector import TransientTargetError
    try:
        resp = connector.apply(record_key, field, proposed, expected, key)
    except TransientTargetError as texc:
        conf = _safe_confirm(connector, record_key, field, proposed, expected + 1, key)
        if conf is None:
            raise texc
        if conf.get("applied") and conf.get("verified"):
            return ({**{k: v for k, v in conf.items() if k != "verified"},
                     "destination": connector.destination, "record_key": record_key,
                     "field": field, "value": proposed, "version_after": expected + 1,
                     "applied": True, "duplicate": False, "operation_id": key,
                     "recovered_via_confirm": True}, True, "recovered")
        if conf.get("applied"):
            return ({"destination": connector.destination, "record_key": record_key,
                     "field": field, "value": proposed, "operation_id": key,
                     "confirm_note": conf.get("note", "applied but diverged")},
                    False, "diverged")
        texc.proved_not_applied = True
        raise texc
    try:
        check = connector.verify(record_key, field, proposed, resp["version_after"])
    except TransientTargetError:
        conf = _safe_confirm(connector, record_key, field, proposed, resp["version_after"], key)
        if conf is not None and conf.get("applied") and conf.get("verified"):
            return ({**resp, "recovered_via_confirm": True}, True, "recovered")
        return ({**resp, "confirm_failed": conf is None}, False, "unknown")
    verified = bool(check.get("verified"))
    if not verified:
        return ({**resp, "verify_actual": check.get("actual"), "verify_reason": check.get("reason")},
                False, "mismatch")
    return (resp, True, "applied")


def _pg_error_outcome(exc: Exception) -> Optional[str]:
    """Map a definitive PG refusal to a persisted outcome token (presentation
    support only; classification behavior unchanged)."""
    try:
        from backend.app.connectors.postgres_connector import (
            StaleTargetError, RecordMissingError, ValidationError as PGValidationError,
            IdempotencyCollisionError)
        if isinstance(exc, StaleTargetError):
            return "stale"
        if isinstance(exc, RecordMissingError):
            return "missing"
        if isinstance(exc, PGValidationError):
            return "invalid"
        if isinstance(exc, IdempotencyCollisionError):
            return "collision"
    except Exception:
        pass
    return None


REVIEW_OUTCOME_EXPLANATIONS = {
    "VERIFIED": "The approved changes were applied to the target and the resulting target state was verified.",
    "RECOVERED": "The write result was initially uncertain. Verification found the approved state already present, so no duplicate write was made.",
    "SAFE_RETRY": "The write outcome was uncertain, then verification determined the approved mutation was not present. Retry is allowed under the existing policy.",
    "BLOCKED": "The write was refused or the target changed. SyncGuard did not overwrite the newer target state. Human review required.",
    "VERIFICATION_FAILED": "The target state could not be verified against the approved resolution. No automatic correction was performed.",
    "UNKNOWN": "SyncGuard could not establish whether the mutation was applied. This is shown as unknown — not as success or failure.",
    "IN_PROGRESS": "The synchronization operation is still running.",
    "DRY_RUN": "Preview only — no write was attempted.",
}

REVIEW_VERIFICATION_EXPLANATIONS = {
    "VERIFIED": "A fresh read of the target confirmed the expected state.",
    "FAILED": "A fresh read of the target did not match the expected state.",
    "NOT_PERFORMED": "No verification read has been performed for this operation.",
    "UNKNOWN": "Verification could not establish the target state.",
}


def sync_review_status(job: Any) -> Dict[str, Any]:
    """Derive reviewer-facing outcome + verification from persisted sync-job
    fields only. Pure function: no I/O, no inference, no behavior change.
    Reads status, response_metadata (verified / outcome / outcome_unknown /
    retryable / recovered_via_confirm) and attempt_count."""
    meta = getattr(job, "response_metadata", None) or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    status = getattr(job, "status", None)
    verified = meta.get("verified")
    outcome = meta.get("outcome")
    if meta.get("recovered_via_confirm") and not outcome:
        outcome = "recovered"
    retryable = meta.get("retryable")
    unknown_flag = bool(meta.get("outcome_unknown"))
    attempts = getattr(job, "attempt_count", 0) or 0
    if status == "DRY_RUN":
        reviewer_outcome, verification = "DRY_RUN", "NOT_PERFORMED"
    elif status in ("PROCESSING", "RETRYING"):
        reviewer_outcome, verification = "IN_PROGRESS", "UNKNOWN" if unknown_flag else "NOT_PERFORMED"
    elif status == "SUCCESS":
        if outcome == "recovered":
            reviewer_outcome = "RECOVERED"
        elif verified is True:
            reviewer_outcome = "VERIFIED"
        else:
            reviewer_outcome = "VERIFICATION_FAILED"
        verification = "VERIFIED" if verified is True else ("UNKNOWN" if unknown_flag else "FAILED")
    else:
        if outcome == "unknown" or unknown_flag:
            reviewer_outcome = "UNKNOWN"
        elif outcome == "mismatch" or (verified is False and retryable is None
                                        and outcome is None):
            reviewer_outcome = "VERIFICATION_FAILED"
        elif outcome in ("diverged", "stale", "missing", "invalid", "collision") or retryable is False:
            reviewer_outcome = "BLOCKED"
        elif retryable is True:
            reviewer_outcome = "SAFE_RETRY"
        else:
            reviewer_outcome = "UNKNOWN"
        if verified is True:
            verification = "VERIFIED"
        elif unknown_flag or reviewer_outcome == "UNKNOWN":
            verification = "UNKNOWN"
        elif verified is False and attempts > 0:
            verification = "FAILED"
        else:
            verification = "NOT_PERFORMED"
    return {"outcome": reviewer_outcome,
            "explanation": REVIEW_OUTCOME_EXPLANATIONS[reviewer_outcome],
            "verification": verification,
            "verification_explanation": REVIEW_VERIFICATION_EXPLANATIONS[verification],
            "requires_human_action": reviewer_outcome in ("BLOCKED", "UNKNOWN", "VERIFICATION_FAILED"),
            "retry_allowed": reviewer_outcome == "SAFE_RETRY"}


def push_resolution(db, resolution_id: int, confirm: bool, simulate_error: Optional[int] = None):
    from backend.app.db.models import ResolutionLogModel, SyncJobModel, SyncAttemptModel, AuditLogModel
    from backend.app.connectors.mock_connector import MockConnector
    if not confirm:
        raise ResolutionError(422, "Push requires explicit confirmation {confirm:true} after dry run")
    row = db.query(ResolutionLogModel).filter(ResolutionLogModel.id == resolution_id).first()
    if not row:
        raise ResolutionError(404, "Resolution not found")
    payload = _resolution_payload(row)
    if payload.get("canonical") in ("REJECT", "DEFER"):
        raise ResolutionError(422, "Rejected/deferred resolutions cannot be pushed")
    conflict = _conflict_of(db, row.conflict_id)
    destination, record_id = _destination_for(db, conflict)
    field = payload.get("field_name", "unknown")
    proposed = payload.get("resolved_value")
    key = idempotency_key(resolution_id, destination, proposed)
    pg_cfg = _pg_target_for(db, conflict)
    if pg_cfg:
        from backend.app.connectors.postgres_connector import PostgresConnector
        destination = PostgresConnector(table=pg_cfg["table"]).destination
        record_id = pg_cfg["record_key"]
        key = idempotency_key(resolution_id, destination, proposed)
    done = db.query(SyncJobModel).filter(SyncJobModel.idempotency_key == key, SyncJobModel.status == "SUCCESS").first()
    if done:
        logger.info("PUSH_ALREADY_APPLIED", resolution_id=resolution_id)
        done.response_metadata = {**(done.response_metadata or {}), "already_applied": True}
        return done, False
    dry = db.query(SyncJobModel).filter(SyncJobModel.idempotency_key == key, SyncJobModel.status == "DRY_RUN").first()
    if not dry:
        import time as _time2
        for _ in range(150):
            db.expire_all()
            done0 = db.query(SyncJobModel).filter(SyncJobModel.idempotency_key == key, SyncJobModel.status == "SUCCESS").first()
            if done0:
                done0.response_metadata = {**(done0.response_metadata or {}), "already_applied": True}
                return done0, False
            _time2.sleep(0.1)
        raise ResolutionError(422, "Dry run must complete before push")
    claimed = db.query(SyncJobModel).filter(SyncJobModel.id == dry.id, SyncJobModel.status == "DRY_RUN").update(
        {"status": "PROCESSING"}, synchronize_session=False) == 1
    if not claimed:
        import time as _time
        for _ in range(150):
            db.expire_all()
            done2 = db.query(SyncJobModel).filter(SyncJobModel.idempotency_key == key, SyncJobModel.status == "SUCCESS").first()
            if done2:
                done2.response_metadata = {**(done2.response_metadata or {}), "already_applied": True}
                return done2, False
            _time.sleep(0.1)
        raise ResolutionError(409, "Push already in progress concurrently")
    job = db.query(SyncJobModel).filter(SyncJobModel.id == dry.id).first()
    job.started_at = datetime.utcnow()
    db.add(AuditLogModel(action="PUSH_CONFIRMED", entity_type="resolution", entity_id=str(row.id), details={"sync_job_id": job.id}))
    db.add(AuditLogModel(action="SYNC_STARTED", entity_type="sync_job", entity_id=str(job.id), details={"destination": destination, "field": field}))
    db.commit()
    connector = _select_connector(destination, pg_cfg["table"] if pg_cfg else None)
    is_pg = pg_cfg is not None
    pg_outcome: Optional[str] = None
    try:
        if not is_pg:
            resp = connector.update_record(record_id, field, proposed, simulate_error=simulate_error)
            check = connector.get_record(record_id, field)
            verified = check.get("value") == proposed
        else:
            dry_meta = (dry.response_metadata or {})
            expected = dry_meta.get("pg_expected_version")
            if expected is None:
                raise ResolutionError(422, "PG push requires a PG dry-run carrying expected version")
            resp, verified, pg_outcome = _pg_confirmed_apply(
                connector, pg_cfg["record_key"], field, proposed, int(expected), key)
        job.status = "SUCCESS" if verified else "FAILED"
        job.completed_at = datetime.utcnow()
        job.progress = 100.0
        job.response_metadata = {**(job.response_metadata or {}), **resp, "verified": verified, "dry_run": False}
        if is_pg:
            job.response_metadata["outcome"] = pg_outcome or ("applied" if verified else "mismatch")
        if is_pg and pg_outcome == "diverged":
            job.response_metadata["retryable"] = False
            job.error_message = "Write applied but state diverged — human review required, automatic retry disabled"
        if is_pg and pg_outcome == "unknown":
            job.response_metadata["outcome_unknown"] = True
        if not verified:
            job.error_message = job.error_message or "Verification read-back mismatch"
        db.add(SyncAttemptModel(job_id=job.id, attempt_number=job.attempt_count + 1, status="success" if verified else "failed",
                               error_message=job.error_message, started_at=job.started_at, completed_at=job.completed_at))
        job.attempt_count += 1
        db.add(AuditLogModel(action="SYNC_SUCCEEDED" if verified else "SYNC_FAILED", entity_type="sync_job", entity_id=str(job.id),
                             details={"destination": destination, "verified": verified}))
        if verified:
            db.add(AuditLogModel(action="SYNC_VERIFIED", entity_type="sync_job", entity_id=str(job.id),
                                 details={"destination": destination, "field": field, "value": proposed, **({} if is_pg else {"mock": True})}))
        db.commit()
        db.refresh(job)
        logger.info("SYNC_SUCCEEDED" if verified else "SYNC_FAILED", sync_job_id=job.id)
        return job, True
    except Exception as exc:
        kind, code = classify_error(exc)
        job.status = "FAILED"
        job.completed_at = datetime.utcnow()
        job.error_message = str(exc)
        job.response_metadata = {**(job.response_metadata or {}), "error_code": code, "retryable": kind == "retryable", "dry_run": False}
        if is_pg:
            job.response_metadata["outcome"] = _pg_error_outcome(exc)
        if is_pg and kind == "retryable" and not getattr(exc, "proved_not_applied", False):
            job.response_metadata["outcome_unknown"] = True
            job.error_message = f"{exc} — outcome UNKNOWN, verify before retry"
        db.add(SyncAttemptModel(job_id=job.id, attempt_number=job.attempt_count + 1, status="failed",
                               error_message=str(exc), started_at=job.started_at, completed_at=job.completed_at))
        job.attempt_count += 1
        db.add(AuditLogModel(action="SYNC_FAILED", entity_type="sync_job", entity_id=str(job.id),
                             details={"destination": destination, "error": str(exc), "retryable": kind == "retryable"}))
        db.commit()
        db.refresh(job)
        logger.error("SYNC_FAILED", sync_job_id=job.id, error=str(exc))
        return job, True


def retry_sync(db, sync_job_id: int, simulate_error: Optional[int] = None):
    from backend.app.db.models import SyncJobModel, AuditLogModel
    from backend.app.connectors.mock_connector import MockConnector
    job = db.query(SyncJobModel).filter(SyncJobModel.id == sync_job_id).first()
    if not job:
        raise ResolutionError(404, "Sync job not found")
    if job.status != "FAILED":
        raise ResolutionError(422, f"Only FAILED jobs can be retried (status={job.status})")
    if job.attempt_count >= 3:
        raise ResolutionError(422, "Retry budget exhausted (max 3 attempts)")
    if (job.response_metadata or {}).get("retryable") is False:
        raise ResolutionError(422, "Non-retryable failure — correct the error first")
    job.status = "RETRYING"
    db.add(AuditLogModel(action="SYNC_RETRY", entity_type="sync_job", entity_id=str(job.id), details={"attempt": job.attempt_count + 1}))
    db.commit()
    connector = _select_connector(job.destination or "MOCK", "customer_records" if str(job.destination or "").startswith("PG:") else None)
    is_pg_retry = str(job.destination or "").startswith("PG:")
    pg_retry_outcome: Optional[str] = None
    try:
        if not is_pg_retry:
            target_id = int(job.target_source_id) if job.target_source_id and str(job.target_source_id).isdigit() else job.target_source_id
            resp = connector.update_record(target_id, job.field_name or "field", job.resolved_value, simulate_error=simulate_error)
            check = connector.get_record(target_id, job.field_name or "field")
            verified = check.get("value") == job.resolved_value
        else:
            meta = job.response_metadata or {}
            resp, verified, pg_retry_outcome = _pg_confirmed_apply(
                connector, str(meta.get("pg_record_key")), job.field_name or "field",
                job.resolved_value, int(meta.get("pg_expected_version")), job.idempotency_key)
        job.status = "SUCCESS" if verified else "FAILED"
        job.completed_at = datetime.utcnow()
        job.response_metadata = {**(job.response_metadata or {}), **resp, "verified": verified}
        if is_pg_retry:
            job.response_metadata["outcome"] = pg_retry_outcome or ("applied" if verified else "mismatch")
        if is_pg_retry and pg_retry_outcome == "diverged":
            job.response_metadata["retryable"] = False
        if is_pg_retry and pg_retry_outcome == "unknown":
            job.response_metadata["outcome_unknown"] = True
        db.add(AuditLogModel(action="SYNC_SUCCEEDED" if verified else "SYNC_FAILED", entity_type="sync_job", entity_id=str(job.id), details={"retry": True, "verified": verified}))
        db.commit()
        db.refresh(job)
        return job, True
    except Exception as exc:
        kind, code = classify_error(exc)
        from backend.app.db.models import SyncAttemptModel
        job.status = "FAILED"
        job.completed_at = datetime.utcnow()
        job.error_message = str(exc)
        job.response_metadata = {**(job.response_metadata or {}), "error_code": code, "retryable": kind == "retryable"}
        if is_pg_retry:
            job.response_metadata["outcome"] = _pg_error_outcome(exc)
        if is_pg_retry and kind == "retryable" and not getattr(exc, "proved_not_applied", False):
            job.response_metadata["outcome_unknown"] = True
        db.add(SyncAttemptModel(job_id=job.id, attempt_number=job.attempt_count + 1, status="failed", error_message=str(exc), started_at=job.started_at, completed_at=job.completed_at))
        job.attempt_count += 1
        db.add(AuditLogModel(action="SYNC_FAILED", entity_type="sync_job", entity_id=str(job.id), details={"retry": True, "error": str(exc)}))
        db.commit()
        db.refresh(job)
        return job, True


def classify_error(exc: Exception) -> Tuple[str, Optional[int]]:
    msg = str(exc)
    import re
    m = re.search(r"MOCK (\d+)", msg)
    code = int(m.group(1)) if m else None
    if code in RETRYABLE:
        return "retryable", code
    if code in NON_RETRYABLE:
        return "non-retryable", code
    try:
        from backend.app.connectors.postgres_connector import (
            TransientTargetError, StaleTargetError, RecordMissingError,
            ValidationError as PGValidationError, IdempotencyCollisionError,
            VerificationMismatchError)
        if isinstance(exc, TransientTargetError):
            return "retryable", code
        if isinstance(exc, (StaleTargetError, RecordMissingError, PGValidationError,
                            IdempotencyCollisionError, VerificationMismatchError)):
            return "non-retryable", code
    except Exception:
        pass
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return "retryable", code
    if isinstance(exc, ValueError):
        return "non-retryable", code
    return "retryable", code
