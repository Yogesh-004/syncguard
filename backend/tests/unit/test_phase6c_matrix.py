"""Phase 6C formal matrix — timeout, concurrency, truthfulness, idempotency-C.

Real PostgreSQL beneath every PG test; fault injection only at the transport
boundary and always labeled as such. Skips (never fakes) if target is down.
"""
import os
import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.database import SessionLocal
from backend.app.db.models import ConflictModel, MatchModel, SourceModel, SyncJobModel, AuditLogModel

DSN = "postgresql://postgres@127.0.0.1:55432/syncguard_target"
os.environ["SYNCGUARD_PG_TARGET"] = DSN

from backend.app.connectors.postgres_connector import (
    PostgresConnector, SCHEMA_SQL, TransientTargetError, StaleTargetError,
    IdempotencyCollisionError)
from backend.app.connectors.mock_connector import MockConnector


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
    return f"pg6m-{uuid.uuid4().hex[:8]}"


def _seed(cur, key, email="old@x.com"):
    cur.execute("DELETE FROM applied_operations WHERE record_key = %s", (key,))
    cur.execute("DELETE FROM customer_records WHERE record_key = %s", (key,))
    cur.execute("INSERT INTO customer_records(record_key,name,email,phone) VALUES (%s,'Ann',%s,'111')",
                (key, email))


def _csv(rows):
    return ("rec_id,given_name,surname,email,phone,postcode\n" +
            "".join(f"{r},G{S}ur,Surname{r},{r}@x.com,555{r},800{r}\n" for r, S in rows))


def _resolved_pg(c, tag, action="USE_SOURCE_A", modified=None):
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
        jkey = f"6m-{tag}-{uuid.uuid4().hex[:8]}"
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
    body = {"action": action}
    if modified:
        body["modified_values"] = modified
    assert c.post(f"/conflicts/{cid}/resolve", json=body).status_code == 200
    rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
    return cid, rid, shared


def test_01_real_lock_timeout_no_blind_retry(tgt):
    """Row locked elsewhere + lock_timeout: real server-side statement cancel.
    Transient, proved not applied, zero mutation, then succeeds after release."""
    k = _tag()
    _seed(tgt, k)
    import psycopg2
    holder = psycopg2.connect(DSN)
    holder.cursor().execute("SELECT version FROM customer_records WHERE record_key=%s FOR UPDATE", (k,))
    pc = PostgresConnector(options="-c lock_timeout=400ms")
    with pytest.raises(TransientTargetError):
        pc.apply(k, "email", "w@x.com", 1, f"{k}-op")
    conf = pc.confirm(k, "email", "w@x.com", 2, f"{k}-op")
    assert conf["applied"] is False
    rec = PostgresConnector().get_record(k)
    assert rec["email"] == "old@x.com" and rec["version"] == 1
    tgt.execute("SELECT COUNT(*) FROM applied_operations WHERE idempotency_key=%s", (f"{k}-op",))
    assert tgt.fetchone()[0] == 0
    holder.commit()
    holder.close()
    out = PostgresConnector().apply(k, "email", "w@x.com", 1, f"{k}-op")
    assert out["applied"] is True


def test_02_race_same_operation_single_mutation(tgt):
    """Two identical operations racing: exactly one applied, no duplication."""
    import psycopg2
    k = _tag()
    _seed(tgt, k)
    barrier = threading.Barrier(3)
    results = []

    def run():
        barrier.wait()
        pc = PostgresConnector()
        try:
            results.append(("applied", pc.apply(k, "email", "race@x.com", 1, f"{k}-op")))
        except StaleTargetError as e:
            results.append(("stale", e))
        except IdempotencyCollisionError as e:
            results.append(("collision", e))

    ts = [threading.Thread(target=run) for _ in range(2)]
    for t in ts:
        t.start()
    barrier.wait()
    for t in ts:
        t.join(timeout=60)
    applied = [r for r in results if r[0] == "applied" and r[1].get("applied")]
    dupes = [r for r in results if r[0] == "applied" and r[1].get("duplicate")]
    assert len(applied) == 1, results
    assert len(applied) + len(dupes) + len([r for r in results if r[0] in ("stale", "collision")]) == 2
    rec = PostgresConnector().get_record(k)
    assert rec["version"] == 2 and rec["email"] == "race@x.com"
    c2 = psycopg2.connect(DSN)
    c2.autocommit = True
    cur = c2.cursor()
    cur.execute("SELECT COUNT(*) FROM applied_operations WHERE record_key=%s", (k,))
    assert cur.fetchone()[0] == 1
    c2.close()


def test_03_race_different_payload_single_mutation(tgt):
    """Same key, different mutations racing: one wins, single mutation kept."""
    k = _tag()
    _seed(tgt, k)
    barrier = threading.Barrier(3)
    results = []

    def run(val):
        barrier.wait()
        pc = PostgresConnector()
        try:
            results.append(pc.apply(k, "email", val, 1, f"{k}-op"))
        except (StaleTargetError, IdempotencyCollisionError) as e:
            results.append(type(e).__name__)

    ts = [threading.Thread(target=run, args=(v,)) for v in ("win1@x.com", "win2@x.com")]
    for t in ts:
        t.start()
    barrier.wait()
    for t in ts:
        t.join(timeout=60)
    rec = PostgresConnector().get_record(k)
    assert rec["version"] == 2 and rec["email"] in ("win1@x.com", "win2@x.com")


def test_04_api_response_truthful_on_unknown(tgt, monkeypatch):
    """UNKNOWN outcome is FAILED + unverified + flagged — never SUCCESS."""
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
        body = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        assert body["status"] == "FAILED"
        assert body.get("verified") is not True
        assert "SUCCESS" not in body.get("result", "")
        assert body.get("already_applied") is not True
        db = SessionLocal()
        try:
            job = db.query(SyncJobModel).filter(SyncJobModel.id == body["sync_job_id"]).first()
            assert job.response_metadata.get("outcome_unknown") is True
        finally:
            db.close()


def test_05_audit_truthful_on_unknown(tgt, monkeypatch):
    """Unknown path records attempt + failure with retryable flag; never
    records success or verification events."""
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
        body = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        db = SessionLocal()
        try:
            acts = [l.action for l in db.query(AuditLogModel).filter(
                AuditLogModel.entity_type == "sync_job",
                AuditLogModel.entity_id == str(body["sync_job_id"])).all()]
            assert "SYNC_STARTED" in acts and "SYNC_FAILED" in acts
            assert "SYNC_SUCCEEDED" not in acts and "SYNC_VERIFIED" not in acts
            job = db.query(SyncJobModel).filter(SyncJobModel.id == body["sync_job_id"]).first()
            assert job.attempt_count == 1
        finally:
            db.close()


def test_06_different_key_same_record_after_unknown(tgt, monkeypatch):
    """Unknown (applied) + new approval with a different value: second mutation
    proceeds on the true current version; stable key identity, no duplication."""
    orig = PostgresConnector.apply

    def lost_reply(self, key, field, value, expected, ikey):
        out = orig(self, key, field, value, expected, ikey)
        raise TransientTargetError("injected: reply lost")

    monkeypatch.setattr(PostgresConnector, "apply", lost_reply)
    with TestClient(app) as c:
        tag = _tag()
        cid, rid, key = _resolved_pg(c, tag)
        _seed(tgt, key)
        c.post(f"/resolutions/{rid}/dry-run")
        c.post(f"/resolutions/{rid}/push", json={"confirm": True})
    monkeypatch.undo()
    with TestClient(app) as c:
        db = SessionLocal()
        try:
            cm = db.query(ConflictModel).filter(ConflictModel.id == cid).first()
            cm.resolution_status = "pending"
            db.commit()
        finally:
            db.close()
        c.post(f"/conflicts/{cid}/resolve",
               json={"action": "MANUAL_EDIT", "modified_values": {"email": "second@x.com"}})
        rids = c.get(f"/conflicts/{cid}/resolutions").json()
        rid2 = max(r["id"] for r in rids)
        c.post(f"/resolutions/{rid2}/dry-run")
        r2 = c.post(f"/resolutions/{rid2}/push", json={"confirm": True}).json()
        assert r2["status"] == "SUCCESS", r2
        rec = PostgresConnector().get_record(key)
        assert rec["email"] == "second@x.com" and rec["version"] == 3, rec


def test_07_retry_is_not_new_authorization(tgt, monkeypatch):
    """FAILED job + external version bump + retry: stale guard blocks the
    retry. A retry reuses the stored approval — it must not bulldoze a
    changed destination."""
    from backend.app.connectors.postgres_connector import TransientTargetError

    def no_send(self, key, field, value, expected, ikey):
        raise TransientTargetError("injected: dropped before send")

    monkeypatch.setattr(PostgresConnector, "apply", no_send)
    with TestClient(app) as c:
        tag = _tag()
        _, rid, key = _resolved_pg(c, tag)
        _seed(tgt, key)
        c.post(f"/resolutions/{rid}/dry-run")
        failed = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        assert failed["status"] == "FAILED"
        jid = failed["sync_job_id"]
    monkeypatch.undo()
    tgt.execute("UPDATE customer_records SET email='ext@x.com', version=99 WHERE record_key=%s", (key,))
    with TestClient(app) as c:
        rr = c.post(f"/sync-jobs/{jid}/retry", json={}).json()
        assert rr["status"] == "FAILED", rr
        rec = PostgresConnector().get_record(key)
        assert rec["email"] == "ext@x.com" and rec["version"] == 99, rec
        tgt.execute("SELECT COUNT(*) FROM applied_operations WHERE record_key=%s", (key,))
        assert tgt.fetchone()[0] == 0


def test_08_mock_phase_modes():
    """MockConnector phase-accurate failures; normal behavior unchanged."""
    mc = MockConnector("MOCK T8")
    MockConnector.clear()
    assert mc.get_record("r1", "email")["value"] is None
    out = mc.update_record("r1", "email", "a@b.com")
    assert out["mock"] is True
    import time as _t
    try:
        mc.update_record("r2", "email", "x", simulate_error="timeout_before")
        assert False
    except TimeoutError:
        pass
    assert mc.get_record("r2", "email")["value"] is None
    try:
        mc.update_record("r3", "email", "y", simulate_error="post_commit_loss")
        assert False
    except ConnectionError as e:
        assert "UNKNOWN" in str(e)
    assert mc.get_record("r3", "email")["value"] == "y"
