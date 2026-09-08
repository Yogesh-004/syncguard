"""Phase 6C — transient failure + unknown-outcome hardening on the PG path.

Fault injection at the connector boundary (real PostgreSQL beneath):
SyncGuard's perspective of the outcome is genuinely unknown in these tests.
"""
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.database import SessionLocal
from backend.app.db.models import ConflictModel, MatchModel, SourceModel, SyncJobModel

DSN = "postgresql://postgres@127.0.0.1:55432/syncguard_target"
os.environ["SYNCGUARD_PG_TARGET"] = DSN

from backend.app.connectors.postgres_connector import (
    PostgresConnector, SCHEMA_SQL, TransientTargetError)


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
    return f"pg6c-{uuid.uuid4().hex[:8]}"


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
        jkey = f"6c-{tag}-{uuid.uuid4().hex[:8]}"
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
    return rid, shared


def _orig_apply():
    return PostgresConnector.apply


def test_01_unknown_outcome_recovered_no_duplicate(tgt, monkeypatch):
    """Real apply commits, reply 'lost' (injected transient): push must confirm
    and succeed WITHOUT a second mutation."""
    orig = _orig_apply()

    def faulty(self, key, field, value, expected, ikey):
        out = orig(self, key, field, value, expected, ikey)
        raise TransientTargetError("injected: reply lost after commit")

    monkeypatch.setattr(PostgresConnector, "apply", faulty)
    with TestClient(app) as c:
        tag = _tag()
        rid, key = _resolved_pg(c, tag)
        _seed(tgt, key)
        c.post(f"/resolutions/{rid}/dry-run")
        r = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        assert r["status"] == "SUCCESS", r
        rec = PostgresConnector().get_record(key)
        assert rec["version"] == 2, rec
        db = SessionLocal()
        try:
            job = db.query(SyncJobModel).filter(SyncJobModel.id == r["sync_job_id"]).first()
            assert job.response_metadata.get("recovered_via_confirm") is True
        finally:
            db.close()


def test_02_unknown_outcome_diverged_no_retry(tgt, monkeypatch):
    """Applied, then externally tampered, reply lost: FAILED, non-retryable,
    no duplicate write, tampered state preserved."""
    orig = _orig_apply()

    def faulty(self, key, field, value, expected, ikey):
        out = orig(self, key, field, value, expected, ikey)
        import psycopg2
        cc = psycopg2.connect(DSN)
        cc.autocommit = True
        cc.cursor().execute("UPDATE customer_records SET email='tampered@x.com' WHERE record_key=%s", (key,))
        cc.close()
        raise TransientTargetError("injected: reply lost after commit+tamper")

    monkeypatch.setattr(PostgresConnector, "apply", faulty)
    with TestClient(app) as c:
        tag = _tag()
        rid, key = _resolved_pg(c, tag)
        _seed(tgt, key)
        c.post(f"/resolutions/{rid}/dry-run")
        r = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        assert r["status"] == "FAILED", r
        rec = PostgresConnector().get_record(key)
        assert rec["email"] == "tampered@x.com" and rec["version"] == 2, rec
        db = SessionLocal()
        try:
            job = db.query(SyncJobModel).filter(SyncJobModel.id == r["sync_job_id"]).first()
            assert job.response_metadata.get("retryable") is False
            assert c.post(f"/sync-jobs/{job.id}/retry", json={}).status_code == 422
        finally:
            db.close()


def test_03_unconfirmable_then_retry_succeeds(tgt, monkeypatch):
    """Transient before any send + confirm also down: FAILED retryable with
    outcome_unknown; later retry succeeds with exactly one mutation."""
    def no_send(self, key, field, value, expected, ikey):
        raise TransientTargetError("injected: connection dropped before send")

    def confirm_down(self, *a, **k):
        raise ConnectionError("injected: target unreachable for confirm")

    monkeypatch.setattr(PostgresConnector, "apply", no_send)
    monkeypatch.setattr(PostgresConnector, "confirm", confirm_down)
    with TestClient(app) as c:
        tag = _tag()
        rid, key = _resolved_pg(c, tag)
        _seed(tgt, key)
        c.post(f"/resolutions/{rid}/dry-run")
        r = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        assert r["status"] == "FAILED", r
        db = SessionLocal()
        try:
            job = db.query(SyncJobModel).filter(SyncJobModel.id == r["sync_job_id"]).first()
            assert job.response_metadata.get("retryable") is not False
            assert job.response_metadata.get("outcome_unknown") is True
            assert PostgresConnector().get_record(key)["version"] == 1
        finally:
            db.close()
    monkeypatch.undo()
    with TestClient(app) as c:
        rr = c.post(f"/sync-jobs/{r['sync_job_id']}/retry", json={}).json()
        assert rr["status"] == "SUCCESS", rr
        assert PostgresConnector().get_record(key)["version"] == 2


def test_04_verify_transient_recovered(tgt, monkeypatch):
    """Apply + verify both fine, but the verify reply is lost: confirm path
    must still recover to SUCCESS without re-mutating."""
    orig_verify = PostgresConnector.verify
    state = {"n": 0}

    def flaky_verify(self, key, field, value, version):
        state["n"] += 1
        if state["n"] == 1:
            raise TransientTargetError("injected: verify reply lost")
        return orig_verify(self, key, field, value, version)

    monkeypatch.setattr(PostgresConnector, "verify", flaky_verify)
    with TestClient(app) as c:
        tag = _tag()
        rid, key = _resolved_pg(c, tag)
        _seed(tgt, key)
        c.post(f"/resolutions/{rid}/dry-run")
        r = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        assert r["status"] == "SUCCESS", r
        assert PostgresConnector().get_record(key)["version"] == 2


def test_05_proved_not_applied_has_no_unknown_flag(tgt, monkeypatch):
    """Pre-send transient with working confirm proving non-application:
    FAILED retryable WITHOUT outcome_unknown (nothing to be unsure about)."""
    def no_send(self, key, field, value, expected, ikey):
        raise TransientTargetError("injected: dropped before send")

    monkeypatch.setattr(PostgresConnector, "apply", no_send)
    with TestClient(app) as c:
        tag = _tag()
        rid, key = _resolved_pg(c, tag)
        _seed(tgt, key)
        c.post(f"/resolutions/{rid}/dry-run")
        r = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        assert r["status"] == "FAILED", r
        db = SessionLocal()
        try:
            job = db.query(SyncJobModel).filter(SyncJobModel.id == r["sync_job_id"]).first()
            assert "outcome_unknown" not in (job.response_metadata or {})
            assert PostgresConnector().get_record(key)["version"] == 1
        finally:
            db.close()


def test_06_mock_path_has_no_unknown_flag():
    """Hardening is PG-scoped: mock transient failures carry no outcome flags."""
    with TestClient(app) as c:
        csv = ("rec_id,given_name,surname,email,phone,postcode\n"
               "m1,Ann,Lee,a@x.com,111,1000\nm2,Ann,Lee,b@x.com,111,1000\n")
        sa = c.post("/uploads", files={"file": ("m.csv", csv.encode(), "text/csv")}).json()
        key = f"6c-m-{uuid.uuid4().hex[:8]}"
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
        r = c.post(f"/resolutions/{rid}/push", json={"confirm": True, "simulate_error": 500}).json()
        assert r["status"] == "FAILED"
        db = SessionLocal()
        try:
            job = db.query(SyncJobModel).filter(SyncJobModel.id == r["sync_job_id"]).first()
            assert "outcome_unknown" not in (job.response_metadata or {})
        finally:
            db.close()
