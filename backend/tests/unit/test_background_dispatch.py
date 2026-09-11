"""Background dispatch wiring + setup-phase failure persistence.

Covers: POST schedules (not inline), missing job returns cleanly,
setup-phase failure persists failed status instead of stuck processing.
"""
import uuid

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.database import SessionLocal
from backend.app.db.models import ReconciliationJobModel


def _headers(extra=None):
    from backend.app.core.config import settings
    headers = dict(extra or {})
    key = (settings.API_KEY or "").strip()
    if key:
        headers.setdefault("X-API-Key", key)
    return headers


def _upload(c, tag):
    csv = ("rec_id,given_name,surname,email,phone,postcode\n"
           f"{tag}-1,Alice,One,a1@x.com,111,10001\n"
           f"{tag}-2,Bob,Two,b2@x.com,222,10002\n")
    return c.post("/uploads", files={"file": (f"{tag}.csv", csv.encode(), "text/csv")},
                  headers=_headers()).json()["source_id"]


def test_dispatch_schedules_not_inline():
    """POST returns 202 while the job is still queued: the pipeline runs
    after the response, not inside the request."""
    import time
    from backend.app.api import routes as routes_mod
    with TestClient(app) as c:
        sid = _upload(c, f"bgw{uuid.uuid4().hex[:6]}")
        key = f"bgw-{uuid.uuid4().hex[:8]}"
        calls = []
        orig = routes_mod._run_reconciliation_inline

        def stub(job_id, source_ids, version):
            calls.append((job_id, list(source_ids), version))

        routes_mod._run_reconciliation_inline = stub
        try:
            t0 = time.time()
            r = c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key},
                       headers=_headers({"Idempotency-Key": key}))
            dt = time.time() - t0
            assert r.status_code == 202, r.text
            jid = r.json()["job_id"]
        finally:
            routes_mod._run_reconciliation_inline = orig
        assert dt < 30, f"POST blocked {dt:.1f}s"
        assert calls == [(jid, [sid], "1.0.0")], calls
        db = SessionLocal()
        try:
            job = db.query(ReconciliationJobModel).filter(
                ReconciliationJobModel.id == jid).first()
            assert job.status == "queued", job.status
        finally:
            db.close()


def test_setup_failure_persists_failed_status():
    """A setup-phase failure (claim commit) still persists failed status
    via a fresh session instead of leaving the job stuck."""
    import backend.app.db.database as dbmod
    real_session_local = dbmod.SessionLocal

    class FlakySession:
        def __init__(self, real):
            self.__dict__["_real"] = real
            self.__dict__["commits"] = 0

        def __getattr__(self, name):
            if name == "commit":
                def _commit():
                    self.__dict__["commits"] += 1
                    if self.__dict__["commits"] == 1:
                        raise RuntimeError("injected setup commit failure")
                    return self._real.commit()
                return _commit
            return getattr(self._real, name)

        def close(self):
            return self._real.close()

    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        if calls["n"] == 1:
            return FlakySession(real_session_local())
        return real_session_local()

    with TestClient(app) as c:
        sid = _upload(c, f"bgs{uuid.uuid4().hex[:6]}")
        key = f"bgs-{uuid.uuid4().hex[:8]}"
        jid = c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key},
                     headers=_headers({"Idempotency-Key": key})).json()["job_id"]
        db = SessionLocal()
        try:
            job = db.query(ReconciliationJobModel).filter(
                ReconciliationJobModel.id == jid).first()
            assert job.status == "completed", job.status
            job.status = "queued"
            db.commit()
        finally:
            db.close()
        dbmod.SessionLocal = factory
        try:
            from backend.app.api import routes as routes_mod
            assert routes_mod._run_reconciliation_inline(jid, [sid], "1.0.0") is None
        finally:
            dbmod.SessionLocal = real_session_local
        db = SessionLocal()
        try:
            job = db.query(ReconciliationJobModel).filter(
                ReconciliationJobModel.id == jid).first()
            assert job.status == "failed", job.status
            assert "injected setup commit failure" in (job.error_message or "")
        finally:
            db.close()


def test_missing_job_returns_cleanly():
    from backend.app.api import routes as routes_mod
    assert routes_mod._run_reconciliation_inline(99999999, [], "1.0.0") is None


def test_no_broker_path_schedules_background_with_persisted_job(monkeypatch):
    """Exact production path (no broker env): POST persists the job, then
    invokes _run_reconciliation_inline once with (job_id, source_ids,
    version) while the row is still queued. No broker, no Celery."""
    import os
    from backend.app.api import routes as routes_mod
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with TestClient(app) as c:
        sid = _upload(c, f"nbw{uuid.uuid4().hex[:6]}")
        key = f"nbw-{uuid.uuid4().hex[:8]}"
        calls = []
        orig = routes_mod._run_reconciliation_inline

        def stub(job_id, source_ids, version):
            calls.append((job_id, list(source_ids), version))
            db = SessionLocal()
            try:
                job = db.query(ReconciliationJobModel).filter(
                    ReconciliationJobModel.id == job_id).first()
                assert job is not None and job.status == "queued", \
                    f"job must be persisted as queued before execution, got {job}"
            finally:
                db.close()

        routes_mod._run_reconciliation_inline = stub
        try:
            r = c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key},
                       headers=_headers({"Idempotency-Key": key}))
            assert r.status_code == 202, r.text
            jid = r.json()["job_id"]
        finally:
            routes_mod._run_reconciliation_inline = orig
        assert calls == [(jid, [sid], "1.0.0")], calls
