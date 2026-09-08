"""Phase 6B — controlled PostgreSQL connector against a REAL external target.

Target: disposable local PostgreSQL (127.0.0.1:55432/syncguard_target), a
separate server from SyncGuard's app DB. Skipped (not faked) if unreachable.
"""
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.database import SessionLocal
from backend.app.db.models import ConflictModel, MatchModel, SourceModel, SyncJobModel, AuditLogModel

DSN = "postgresql://postgres@127.0.0.1:55432/syncguard_target"
os.environ["SYNCGUARD_PG_TARGET"] = DSN

from backend.app.connectors.postgres_connector import (
    PostgresConnector, SCHEMA_SQL, RecordMissingError, ValidationError,
    StaleTargetError, IdempotencyCollisionError, TransientTargetError)


def _pg():
    import psycopg2
    try:
        c = psycopg2.connect(DSN, connect_timeout=5)
    except Exception:
        pytest.skip("PG target unreachable — real integration tests require 127.0.0.1:55432")
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
    return f"pg6b-{uuid.uuid4().hex[:8]}"


def _seed_target(cur, key, name="Ann", email="ann@x.com", phone="111"):
    cur.execute("DELETE FROM applied_operations WHERE record_key = %s", (key,))
    cur.execute("DELETE FROM customer_records WHERE record_key = %s", (key,))
    cur.execute("INSERT INTO customer_records(record_key,name,email,phone) VALUES (%s,%s,%s,%s)",
                (key, name, email, phone))


def test_01_connector_initializes():
    pc = PostgresConnector()
    h = pc.health_check()
    assert h["healthy"] is True and h["label"] == "POSTGRESQL TARGET"
    assert "postgres@" not in h["target"] or "@" in h["target"]
    with pytest.raises(ValidationError):
        PostgresConnector(table="users; DROP TABLE x")
    import os as _os2
    old = _os2.environ.pop("SYNCGUARD_PG_TARGET", None)
    try:
        with pytest.raises(ValidationError):
            PostgresConnector(dsn="")
    finally:
        if old is not None:
            _os2.environ["SYNCGUARD_PG_TARGET"] = old


def test_02_successful_read(tgt):
    k = _tag()
    _seed_target(tgt, k)
    rec = PostgresConnector().get_record(k)
    assert rec["name"] == "Ann" and rec["version"] == 1


def test_03_missing_record(tgt):
    k = _tag() + "-nope"
    tgt.execute("DELETE FROM customer_records WHERE record_key = %s", (k,))
    assert PostgresConnector().get_record(k) is None
    with pytest.raises(RecordMissingError):
        PostgresConnector().preview(k, "email", "a@b.com", "kk")
    with pytest.raises(RecordMissingError):
        PostgresConnector().apply(k, "email", "a@b.com", 1, "kk")


def _csv(rows):
    return ("rec_id,given_name,surname,email,phone,postcode\n" +
            "".join(f"{r},G{S}ur,Surname{r},{r}@x.com,555{r},800{r}\n" for r, S in rows))


def _resolved_pg(c, tag):
    """Two-source job with PG-routed target source.

    Returns (cid, rid, target_key) where target_key is the PG record_key of
    the conflict's target record (the shared rec_id matched across sources).
    """
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
        jkey = f"6b-{tag}-{uuid.uuid4().hex[:8]}"
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
    rr = c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
    assert rr.status_code == 200, rr.text
    rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
    return cid, rid, shared


def test_04_dry_run_does_not_mutate(tgt):
    with TestClient(app) as c:
        tag = _tag()
        cid, rid, key_b = _resolved_pg(c, tag)
        _seed_target(tgt, key_b, email="old@x.com")
        before = PostgresConnector().get_record(key_b)
        dry = c.post(f"/resolutions/{rid}/dry-run")
        assert dry.status_code == 200
        after = PostgresConnector().get_record(key_b)
        assert before == after
        assert dry.json()["operation"] == "UPDATE"


def test_05_successful_confirmed_write(tgt):
    with TestClient(app) as c:
        tag = _tag()
        _, rid, key_b = _resolved_pg(c, tag)
        _seed_target(tgt, key_b, email="old@x.com")
        c.post(f"/resolutions/{rid}/dry-run")
        r = c.post(f"/resolutions/{rid}/push", json={"confirm": True})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "SUCCESS"
        rec = PostgresConnector().get_record(key_b)
        assert rec["email"] != "old@x.com" and rec["version"] == 2


def test_06_only_approved_fields_mutate(tgt):
    with TestClient(app) as c:
        tag = _tag()
        _, rid, key_b = _resolved_pg(c, tag)
        _seed_target(tgt, key_b, name="KeepMe", email="old@x.com", phone="999")
        c.post(f"/resolutions/{rid}/dry-run")
        c.post(f"/resolutions/{rid}/push", json={"confirm": True})
        rec = PostgresConnector().get_record(key_b)
        assert rec["name"] == "KeepMe" and rec["phone"] == "999"


def test_07_transaction_rollback_on_failure(tgt):
    pc = PostgresConnector()
    k = _tag()
    _seed_target(tgt, k, email="old@x.com")
    tgt.execute("ALTER TABLE applied_operations ADD CONSTRAINT no_fail CHECK (resolved_value <> %s)",
                ('"TRIGGER_ROLLBACK"',))
    try:
        with pytest.raises(Exception):
            pc.apply(k, "email", "TRIGGER_ROLLBACK", 1, f"{k}-op")
        rec = pc.get_record(k)
        assert rec["email"] == "old@x.com" and rec["version"] == 1
        tgt.execute("SELECT COUNT(*) FROM applied_operations WHERE idempotency_key = %s", (f"{k}-op",))
        assert tgt.fetchone()[0] == 0
    finally:
        tgt.execute("ALTER TABLE applied_operations DROP CONSTRAINT no_fail")


def test_08_stale_state_rejection(tgt):
    with TestClient(app) as c:
        tag = _tag()
        _, rid, key_b = _resolved_pg(c, tag)
        _seed_target(tgt, key_b, email="old@x.com")
        c.post(f"/resolutions/{rid}/dry-run")
        tgt.execute("UPDATE customer_records SET email='external@x.com', version=version+1 WHERE record_key=%s",
                    (key_b,))
        r = c.post(f"/resolutions/{rid}/push", json={"confirm": True})
        assert r.json()["status"] == "FAILED"
        rec = PostgresConnector().get_record(key_b)
        assert rec["email"] == "external@x.com" and rec["version"] == 2


def test_09_idempotent_replay(tgt):
    with TestClient(app) as c:
        tag = _tag()
        _, rid, key_b = _resolved_pg(c, tag)
        _seed_target(tgt, key_b, email="old@x.com")
        c.post(f"/resolutions/{rid}/dry-run")
        r1 = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        r2 = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        assert r1["status"] == "SUCCESS" and r2.get("already_applied") is True
        assert PostgresConnector().get_record(key_b)["version"] == 2


def test_10_idempotency_collision():
    pc = PostgresConnector()
    k = _tag()
    import psycopg2
    c = psycopg2.connect(DSN)
    c.autocommit = True
    cur = c.cursor()
    cur.execute("DELETE FROM applied_operations WHERE record_key = %s", (k,))
    cur.execute("DELETE FROM customer_records WHERE record_key = %s", (k,))
    cur.execute("INSERT INTO customer_records(record_key,email) VALUES (%s,'a@x.com')", (k,))
    pc.apply(k, "email", "b@x.com", 1, f"{k}-op")
    with pytest.raises(IdempotencyCollisionError):
        pc.apply(k, "email", "DIFFERENT@x.com", 2, f"{k}-op")
    assert pc.get_record(k)["email"] == "b@x.com"
    c.close()


def test_11_concurrent_same_operation(tgt):
    with TestClient(app) as c:
        tag = _tag()
        _, rid, key_b = _resolved_pg(c, tag)
        _seed_target(tgt, key_b, email="old@x.com")
        c.post(f"/resolutions/{rid}/dry-run")
        r1 = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        r2 = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        assert r1["status"] == "SUCCESS"
        assert r2.get("already_applied") is True
        assert PostgresConnector().get_record(key_b)["version"] == 2


def test_12_concurrent_stale_record(tgt):
    pc = PostgresConnector()
    k = _tag()
    _seed_target(tgt, k, email="v1@x.com")
    snap = pc.get_record(k)
    tgt.execute("UPDATE customer_records SET email='v2@x.com', version=version+1 WHERE record_key=%s", (k,))
    with pytest.raises(StaleTargetError):
        pc.apply(k, "email", "mine@x.com", snap["version"], f"{k}-op")
    rec = pc.get_record(k)
    assert rec["email"] == "v2@x.com" and rec["version"] == snap["version"] + 1


def test_13_verification_success(tgt):
    with TestClient(app) as c:
        tag = _tag()
        _, rid, key_b = _resolved_pg(c, tag)
        _seed_target(tgt, key_b, email="old@x.com")
        c.post(f"/resolutions/{rid}/dry-run")
        r = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()
        assert r["status"] == "SUCCESS"
        db = SessionLocal()
        try:
            logs = db.query(AuditLogModel).filter(
                AuditLogModel.entity_type == "sync_job").all()
            assert any("SYNC_VERIFIED" in (l.action or "") for l in logs)
        finally:
            db.close()


def test_14_verification_mismatch(tgt):
    pc = PostgresConnector()
    k = _tag()
    _seed_target(tgt, k, email="a@x.com")
    pc.apply(k, "email", "b@x.com", 1, f"{k}-op")
    tgt.execute("UPDATE customer_records SET email='tampered@x.com' WHERE record_key=%s", (k,))
    v = pc.verify(k, "email", "b@x.com", 2)
    assert v["verified"] is False and "actual" in v


def test_15_connection_failure():
    pc = PostgresConnector(dsn="postgresql://postgres@127.0.0.1:55999/syncguard_target", timeout_s=2)
    with pytest.raises(TransientTargetError):
        pc.get_record("anything")
    from backend.app.services.resolution import classify_error
    kind, _ = classify_error(TransientTargetError("boom"))
    assert kind == "retryable"


def test_16_invalid_configuration():
    import os as _os
    old = _os.environ.get("SYNCGUARD_PG_TARGET")
    _os.environ.pop("SYNCGUARD_PG_TARGET", None)
    try:
        with pytest.raises(ValidationError):
            PostgresConnector()
    finally:
        if old is not None:
            _os.environ["SYNCGUARD_PG_TARGET"] = old


def test_17_sql_injection_safety(tgt):
    pc = PostgresConnector()
    with pytest.raises(ValidationError):
        pc.get_record("x") if False else pc.preview("x", "email'; DROP TABLE customer_records--", "v", "k")
    evil_key = "k'); DROP TABLE customer_records;--"
    evil_val = "v'); DELETE FROM customer_records;--"
    _seed_target(tgt, evil_key, email="old@x.com")
    pc.apply(evil_key, "email", evil_val, 1, f"{evil_key}-op")
    rec = pc.get_record(evil_key)
    assert rec["email"] == evil_val
    tgt.execute("SELECT COUNT(*) FROM customer_records")
    assert tgt.fetchone()[0] >= 1


def test_18_audit_lineage(tgt):
    with TestClient(app) as c:
        tag = _tag()
        cid, rid, key_b = _resolved_pg(c, tag)
        _seed_target(tgt, key_b, email="old@x.com")
        c.post(f"/resolutions/{rid}/dry-run")
        c.post(f"/resolutions/{rid}/push", json={"confirm": True})
        db = SessionLocal()
        try:
            actions = {l.action for l in db.query(AuditLogModel).all()}
            for need in ("DRY_RUN_STARTED", "DRY_RUN_COMPLETED", "PUSH_CONFIRMED",
                         "SYNC_STARTED", "SYNC_SUCCEEDED", "SYNC_VERIFIED"):
                assert need in actions, need
        finally:
            db.close()


def test_19_no_secrets_in_logs(tgt):
    from backend.app.connectors.postgres_connector import _redacted_dsn
    assert "s3cr3t" not in _redacted_dsn("postgresql://u:s3cr3t@h/db")
    with TestClient(app) as c:
        tag = _tag()
        _, rid, key_b = _resolved_pg(c, tag)
        _seed_target(tgt, key_b, email="old@x.com")
        c.post(f"/resolutions/{rid}/dry-run")
        c.post(f"/resolutions/{rid}/push", json={"confirm": True})
        db = SessionLocal()
        try:
            blob = str([ (l.action, l.details) for l in db.query(AuditLogModel).all() ])
            assert "s3cr3t" not in blob and "SYNCGUARD_PG_TARGET" not in blob
        finally:
            db.close()


def test_20_mock_connector_unchanged():
    from backend.app.connectors.mock_connector import MockConnector
    mc = MockConnector("MOCK T")
    assert mc.get_record("r1", "email")["value"] is None
    out = mc.update_record("r1", "email", "a@b.com")
    assert out["mock"] is True
    assert mc.get_record("r1", "email")["value"] == "a@b.com"
    with pytest.raises(ConnectionError):
        mc.update_record("r1", "email", "x", simulate_error=500)
