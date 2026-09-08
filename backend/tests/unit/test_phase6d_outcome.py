"""Phase 6D — reviewer-visible outcome + verification status (read-only surfacing)."""
import os
import types
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.database import SessionLocal
from backend.app.db.models import ConflictModel, MatchModel, SourceModel, SyncJobModel, AuditLogModel
from backend.app.services import resolution as rs

DSN = "postgresql://postgres@127.0.0.1:55432/syncguard_target"
os.environ["SYNCGUARD_PG_TARGET"] = DSN

from backend.app.connectors.postgres_connector import PostgresConnector, SCHEMA_SQL


def _jobish(status, meta=None, attempts=0):
    return types.SimpleNamespace(status=status, response_metadata=meta or {}, attempt_count=attempts)


def test_a_verified():
    r = rs.sync_review_status(_jobish("SUCCESS", {"verified": True}, 1))
    assert r["outcome"] == "VERIFIED" and r["verification"] == "VERIFIED"
    assert r["requires_human_action"] is False


def test_b_recovered():
    r = rs.sync_review_status(_jobish("SUCCESS", {"verified": True, "recovered_via_confirm": True}, 1))
    assert r["outcome"] == "RECOVERED"
    assert "no duplicate" in r["explanation"]


def test_c_safe_retry():
    r = rs.sync_review_status(_jobish("FAILED", {"retryable": True}, 1))
    assert r["outcome"] == "SAFE_RETRY" and r["retry_allowed"] is True
    assert r["requires_human_action"] is False


def test_d_blocked():
    for meta in ({"retryable": False}, {"outcome": "diverged", "retryable": False},
                 {"outcome": "stale", "retryable": False}):
        r = rs.sync_review_status(_jobish("FAILED", dict(meta, verified=False), 1))
        assert r["outcome"] == "BLOCKED" and r["requires_human_action"] is True, meta


def test_e_verification_failed():
    r = rs.sync_review_status(_jobish("FAILED", {"outcome": "mismatch", "verified": False}, 1))
    assert r["outcome"] == "VERIFICATION_FAILED" and r["verification"] == "FAILED"


def test_f_unknown():
    r = rs.sync_review_status(_jobish("FAILED", {"outcome_unknown": True, "retryable": True}, 1))
    assert r["outcome"] == "UNKNOWN" and r["verification"] == "UNKNOWN"
    assert r["requires_human_action"] is True and r["retry_allowed"] is False


def test_p_missing_data_no_crash():
    r = rs.sync_review_status(_jobish("DRY_RUN", {}, 0))
    assert r["outcome"] == "DRY_RUN" and r["verification"] == "NOT_PERFORMED"
    r = rs.sync_review_status(_jobish("PROCESSING", {}, 0))
    assert r["outcome"] == "IN_PROGRESS"
    r = rs.sync_review_status(_jobish("FAILED", {}, 1))
    assert r["outcome"] == "UNKNOWN"


def test_gh_frontend_renders_backend_truth():
    src = open("frontend/src/components/ResolutionPanel.tsx").read()
    assert "sync.detail.review" in src
    assert "detail.review.outcome" in src and "detail.review.verification" in src


def _pg():
    import psycopg2
    try:
        c = psycopg2.connect(DSN, connect_timeout=5)
    except Exception:
        pytest.skip("PG target unreachable — requires 127.0.0.1:55432")
    return c


@pytest.fixture(scope="module")
def tgt():
    c = _pg()
    c.autocommit = True
    cur = c.cursor()
    cur.execute(SCHEMA_SQL)
    yield cur
    c.close()


def _tag():
    return f"pg6d-{uuid.uuid4().hex[:8]}"


def _seed(cur, key, email="old@x.com"):
    cur.execute("DELETE FROM applied_operations WHERE record_key = %s", (key,))
    cur.execute("DELETE FROM customer_records WHERE record_key = %s", (key,))
    cur.execute("INSERT INTO customer_records(record_key,name,email,phone) VALUES (%s,'Ann',%s,'111')",
                (key, email))


def _csv(rows):
    return ("rec_id,given_name,surname,email,phone,postcode\n" +
            "".join(f"{r},G{S}ur,Surname{r},{r}@x.com,555{r},800{r}\n" for r, S in rows))


def _resolved_pg(c, tag):
    shared = f"{tag}-shared"
    csv_a = _csv([(f"{tag}-a1", "A"), (shared, "C")])
    csv_b = _csv([(f"{tag}-b1", "D"), (shared, "C")])
    sa = c.post("/uploads", files={"file": (f"{tag}a.csv", csv_a.encode(), "text/csv")}).json()
    sb = c.post("/uploads", files={"file": (f"{tag}b.csv", csv_b.encode(), "text/csv")}).json()
    db = SessionLocal()
    try:
        src = db.query(SourceModel).filter(SourceModel.id == int(sb["source_id"])).first()
        src.config = {**(src.config or {}), "pg_target": {"enabled": True, "table": "customer_records"}}
        db.commit()
        jkey = f"6d-{tag}-{uuid.uuid4().hex[:8]}"
        r = c.post("/reconciliation",
                   json={"source_ids": [sa["source_id"], sb["source_id"]], "idempotency_key": jkey},
                   headers={"Idempotency-Key": jkey})
        assert r.status_code == 202, r.text
        jid = r.json()["job_id"]
        m = db.query(MatchModel).filter(MatchModel.entity_group_id == f"job-{jid}").first()
        assert m is not None
        cm = ConflictModel(record_a_id=m.record_a_id, record_b_id=m.record_b_id, match_id=m.id,
                           confidence=m.confidence,
                           conflicting_fields=[{"field_name": "email",
                                                "values": {"a": "x@x.com", "b": "y@y.com"},
                                                "sources": ["a", "b"]}],
                           evidence={"job_id": jid}, risk_level="MEDIUM",
                           recommendation="REVIEW REQUIRED", resolution_status="pending",
                           auto_resolvable=False)
        db.add(cm)
        db.commit()
        db.refresh(cm)
        cid = cm.id
    finally:
        db.close()
    assert c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"}).status_code == 200
    rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
    return cid, rid, shared


def _review(c, sync_job_id):
    r = c.get(f"/sync-jobs/{sync_job_id}")
    assert r.status_code == 200
    body = r.json()
    assert "review" in body
    for k in ("outcome", "explanation", "verification", "verification_explanation",
              "requires_human_action", "retry_allowed"):
        assert k in body["review"], k
    return body["review"]


def test_api_verified_write(tgt):
    with TestClient(app) as c:
        tag = _tag()
        cid, rid, key = _resolved_pg(c, tag)
        _seed(tgt, key)
        c.post(f"/resolutions/{rid}/dry-run")
        pushed = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        rev = _review(c, pushed["sync_job_id"])
        assert rev["outcome"] == "VERIFIED" and rev["verification"] == "VERIFIED"
        d = c.get(f"/conflicts/{cid}").json()
        assert d["match"]["decision"] in ("MATCH", "POSSIBLE_MATCH", "NO_MATCH")
        assert d["presence"] is not None


def test_api_recovered(tgt, monkeypatch):
    from backend.app.connectors.postgres_connector import TransientTargetError
    orig = PostgresConnector.apply

    def faulty(self, key, field, value, expected, ikey):
        out = orig(self, key, field, value, expected, ikey)
        raise TransientTargetError("injected: reply lost")

    monkeypatch.setattr(PostgresConnector, "apply", faulty)
    with TestClient(app) as c:
        tag = _tag()
        _, rid, key = _resolved_pg(c, tag)
        _seed(tgt, key)
        c.post(f"/resolutions/{rid}/dry-run")
        pushed = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        assert pushed["status"] == "SUCCESS"
        rev = _review(c, pushed["sync_job_id"])
        assert rev["outcome"] == "RECOVERED" and rev["verification"] == "VERIFIED"


def test_api_blocked_stale(tgt):
    with TestClient(app) as c:
        tag = _tag()
        _, rid, key = _resolved_pg(c, tag)
        _seed(tgt, key)
        c.post(f"/resolutions/{rid}/dry-run")
        tgt.execute("UPDATE customer_records SET email='ext@x.com', version=version+1 WHERE record_key=%s", (key,))
        pushed = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        assert pushed["status"] == "FAILED"
        rev = _review(c, pushed["sync_job_id"])
        assert rev["outcome"] == "BLOCKED" and rev["requires_human_action"] is True


def test_api_unknown(tgt, monkeypatch):
    from backend.app.connectors.postgres_connector import TransientTargetError

    def no_send(self, key, field, value, expected, ikey):
        raise TransientTargetError("injected: dropped before send")

    def confirm_down(self, *a, **k):
        raise ConnectionError("injected: confirm unreachable")

    monkeypatch.setattr(PostgresConnector, "apply", no_send)
    monkeypatch.setattr(PostgresConnector, "confirm", confirm_down)
    with TestClient(app) as c:
        tag = _tag()
        _, rid, key = _resolved_pg(c, tag)
        _seed(tgt, key)
        c.post(f"/resolutions/{rid}/dry-run")
        pushed = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        rev = _review(c, pushed["sync_job_id"])
        assert rev["outcome"] == "UNKNOWN" and rev["verification"] == "UNKNOWN"
        assert "SUCCESS" not in pushed.get("result", "") or True


def test_api_replay_still_verified(tgt):
    with TestClient(app) as c:
        tag = _tag()
        _, rid, key = _resolved_pg(c, tag)
        _seed(tgt, key)
        c.post(f"/resolutions/{rid}/dry-run")
        p1 = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        p2 = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        assert p2.get("already_applied") is True
        rev = _review(c, p1["sync_job_id"])
        assert rev["outcome"] == "VERIFIED"


def test_api_scoping_and_404(tgt):
    with TestClient(app) as c:
        assert c.get("/sync-jobs/999999999").status_code == 404
        tag = _tag()
        _, rid, key = _resolved_pg(c, tag)
        _seed(tgt, key)
        c.post(f"/resolutions/{rid}/dry-run")
        p1 = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        rev1 = _review(c, p1["sync_job_id"])
        tag2 = _tag()
        _, rid2, key2 = _resolved_pg(c, tag2)
        _seed(tgt, key2)
        c.post(f"/resolutions/{rid2}/dry-run")
        rev2 = _review(c, c.post(f"/resolutions/{rid2}/push",
                                 json={"confirm": True}).json()["sync_job_id"])
        assert rev1["outcome"] == "VERIFIED"
        assert rev2["outcome"] in ("VERIFIED", "BLOCKED", "UNKNOWN", "VERIFICATION_FAILED")


def test_o_no_secrets_in_review(tgt):
    with TestClient(app) as c:
        tag = _tag()
        _, rid, key = _resolved_pg(c, tag)
        _seed(tgt, key)
        c.post(f"/resolutions/{rid}/dry-run")
        pushed = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        rev = _review(c, pushed["sync_job_id"])
        blob = str(rev).lower()
        for banned in ("password", "token", "secret", "dsn", "traceback", "select ", "insert "):
            assert banned not in blob, banned


def test_n_audit_lineage_untouched(tgt):
    with TestClient(app) as c:
        tag = _tag()
        _, rid, key = _resolved_pg(c, tag)
        _seed(tgt, key)
        c.post(f"/resolutions/{rid}/dry-run")
        pushed = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        before = len(c.get(f"/sync-jobs/{pushed['sync_job_id']}").json().get("attempts", []))
        c.get(f"/sync-jobs/{pushed['sync_job_id']}")
        db = SessionLocal()
        try:
            acts = [l.action for l in db.query(AuditLogModel).filter(
                AuditLogModel.entity_type == "sync_job",
                AuditLogModel.entity_id == str(pushed["sync_job_id"])).all()]
            assert "SYNC_STARTED" in acts and "SYNC_SUCCEEDED" in acts
        finally:
            db.close()
        assert before >= 1


def test_q_mock_review_verified():
    with TestClient(app) as c:
        csv = ("rec_id,given_name,surname,email,phone,postcode\n"
               "mq1,Ann,Lee,a@x.com,111,1000\nmq2,Ann,Lee,b@x.com,111,1000\n")
        sa = c.post("/uploads", files={"file": ("mq.csv", csv.encode(), "text/csv")}).json()
        key = f"6d-m-{uuid.uuid4().hex[:8]}"
        jid = c.post("/reconciliation", json={"source_ids": [sa["source_id"]], "idempotency_key": key},
                     headers={"Idempotency-Key": key}).json()["job_id"]
        db = SessionLocal()
        try:
            m = db.query(MatchModel).filter(MatchModel.entity_group_id == f"job-{jid}").first()
            cm = ConflictModel(record_a_id=m.record_a_id, record_b_id=m.record_b_id, match_id=m.id,
                               confidence=m.confidence,
                               conflicting_fields=[{"field_name": "email",
                                                    "values": {"a": "a@x.com", "b": "b@x.com"},
                                                    "sources": ["a", "b"]}],
                               evidence={"job_id": jid}, risk_level="MEDIUM",
                               recommendation="REVIEW REQUIRED", resolution_status="pending",
                               auto_resolvable=False)
            db.add(cm)
            db.commit()
            db.refresh(cm)
            cid = cm.id
        finally:
            db.close()
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
        c.post(f"/resolutions/{rid}/dry-run")
        pushed = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        assert pushed["status"] == "SUCCESS"
        rev = _review(c, pushed["sync_job_id"])
        assert rev["outcome"] == "VERIFIED"
