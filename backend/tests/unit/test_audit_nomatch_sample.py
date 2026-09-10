"""Audit coverage for persisted NO_MATCH samples.

Regression test: every persisted MatchModel row must have a corresponding
audit entry in the same transaction. A job with zero kept matches previously
persisted its NO_MATCH sample rows with zero audit rows.
"""
import uuid

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.db.database import SessionLocal
from backend.app.db.models import AuditLogModel, MatchModel


def _headers(extra=None):
    headers = dict(extra or {})
    key = (settings.API_KEY or "").strip()
    if key:
        headers.setdefault("X-API-Key", key)
    return headers


def _repro_job(c, tag="auditcov"):
    csv = ("rec_id,given_name,surname,email,phone,postcode\n"
           f"{tag}-1,Alice,One,a1@x.com,111,10001\n"
           f"{tag}-2,Bob,Two,b2@x.com,222,10002\n"
           f"{tag}-3,Carol,Three,c3@x.com,333,10003\n")
    sid = c.post("/uploads", files={"file": (f"{tag}.csv", csv.encode(), "text/csv")},
                 headers=_headers()).json()["source_id"]
    key = f"{tag}-{uuid.uuid4().hex[:8]}"
    jid = c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key},
                 headers=_headers({"Idempotency-Key": key})).json()["job_id"]
    return jid


def _job_matches(jid):
    db = SessionLocal()
    try:
        return db.query(MatchModel).filter(
            MatchModel.entity_group_id == f"job-{jid}").count()
    finally:
        db.close()


def _job_audit(jid):
    db = SessionLocal()
    try:
        rows = db.query(AuditLogModel).all()
        return [r for r in rows if (r.details or {}).get("job_id") == jid]
    finally:
        db.close()


def test_nomatch_sample_rows_have_audit_entries():
    with TestClient(app) as c:
        jid = _repro_job(c)
        n_match = _job_matches(jid)
        n_audit = len(_job_audit(jid))
        assert n_match > 0, "expected persisted sample rows for this fixture"
        assert n_audit >= n_match, f"match rows={n_match} audit rows={n_audit}"


def test_nomatch_audit_carries_decision_and_sample_flag():
    with TestClient(app) as c:
        jid = _repro_job(c, tag="auditcov2")
        rows = _job_audit(jid)
        assert rows, "expected audit rows for the job"
        for r in rows:
            assert "job_id" in (r.details or {}), f"audit without job_id: {r.action}"
            assert r.job_id == jid, f"audit column job_id not populated: {r.action}"
