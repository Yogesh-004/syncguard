"""Background reconciliation execution contract (surgical production fix).

POST /reconciliation must return 202 promptly with a persisted job; the
pipeline runs after the response via BackgroundTasks with its own session.
"""
import time
import uuid

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.database import SessionLocal
from backend.app.db.models import MatchModel, ReconciliationJobModel


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
    sid = c.post("/uploads", files={"file": (f"{tag}.csv", csv.encode(), "text/csv")},
                 headers=_headers()).json()["source_id"]
    return sid


def _wait_status(c, jid, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = c.get(f"/reconciliation/{jid}", headers=_headers()).json()
        if st["status"] in ("completed", "failed"):
            return st
        time.sleep(1)
    raise AssertionError(f"job {jid} did not finish in {timeout}s")


def test_post_returns_202_promptly_with_persisted_job():
    with TestClient(app) as c:
        sid = _upload(c, f"bg{uuid.uuid4().hex[:6]}")
        key = f"bg-{uuid.uuid4().hex[:8]}"
        t0 = time.time()
        r = c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key},
                   headers=_headers({"Idempotency-Key": key}))
        dt = time.time() - t0
        assert r.status_code == 202, r.text
        jid = r.json()["job_id"]
        assert dt < 30, f"POST blocked {dt:.1f}s instead of returning promptly"
        db = SessionLocal()
        try:
            assert db.query(ReconciliationJobModel).filter(
                ReconciliationJobModel.id == jid).count() == 1
        finally:
            db.close()


def test_background_execution_completes_job():
    with TestClient(app) as c:
        sid = _upload(c, f"bgc{uuid.uuid4().hex[:6]}")
        key = f"bgc-{uuid.uuid4().hex[:8]}"
        jid = c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key},
                     headers=_headers({"Idempotency-Key": key})).json()["job_id"]
        st = _wait_status(c, jid)
        assert st["status"] == "completed", st
        db = SessionLocal()
        try:
            assert db.query(MatchModel).filter(
                MatchModel.entity_group_id == f"job-{jid}").count() >= 1
        finally:
            db.close()


def test_background_exception_persists_failed_status():
    from backend.app.api import routes as routes_mod
    with TestClient(app) as c:
        sid = _upload(c, f"bgf{uuid.uuid4().hex[:6]}")
        key = f"bgf-{uuid.uuid4().hex[:8]}"
        jid = c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key},
                     headers=_headers({"Idempotency-Key": key})).json()["job_id"]
        _wait_status(c, jid)
        db = SessionLocal()
        try:
            job = db.query(ReconciliationJobModel).filter(
                ReconciliationJobModel.id == jid).first()
            orig_evaluate = routes_mod.MatchingEngine.evaluate_pairs

            def boom(self, *a, **k):
                raise RuntimeError("injected background failure")

            routes_mod.MatchingEngine.evaluate_pairs = boom
            try:
                job.status = "queued"
                db.commit()
                routes_mod._run_reconciliation_inline(jid, [sid], "1.0.0")
            finally:
                routes_mod.MatchingEngine.evaluate_pairs = orig_evaluate
            db.refresh(job)
            assert job.status == "failed", job.status
            assert "injected background failure" in (job.error_message or "")
        finally:
            db.close()


def test_duplicate_scheduling_runs_once():
    with TestClient(app) as c:
        sid = _upload(c, f"bgd{uuid.uuid4().hex[:6]}")
        key = f"bgd-{uuid.uuid4().hex[:8]}"
        payload = {"source_ids": [sid], "idempotency_key": key}
        headers = _headers({"Idempotency-Key": key})
        j1 = c.post("/reconciliation", json=payload, headers=headers).json()["job_id"]
        j2 = c.post("/reconciliation", json=payload, headers=headers).json()["job_id"]
        assert j1 == j2
        st = _wait_status(c, j1)
        assert st["status"] == "completed", st


def test_claim_guard_skips_non_queued_job():
    from backend.app.api import routes as routes_mod
    with TestClient(app) as c:
        sid = _upload(c, f"bgg{uuid.uuid4().hex[:6]}")
        key = f"bgg-{uuid.uuid4().hex[:8]}"
        jid = c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key},
                     headers=_headers({"Idempotency-Key": key})).json()["job_id"]
        st = _wait_status(c, jid)
        assert st["status"] == "completed", st
        db = SessionLocal()
        try:
            n_before = db.query(MatchModel).filter(
                MatchModel.entity_group_id == f"job-{jid}").count()
        finally:
            db.close()
        routes_mod._run_reconciliation_inline(jid, [str(sid)], "1.0.0")
        db = SessionLocal()
        try:
            n_after = db.query(MatchModel).filter(
                MatchModel.entity_group_id == f"job-{jid}").count()
            job = db.query(ReconciliationJobModel).filter(
                ReconciliationJobModel.id == jid).first()
            assert job.status == "completed"
        finally:
            db.close()
        assert n_after == n_before
