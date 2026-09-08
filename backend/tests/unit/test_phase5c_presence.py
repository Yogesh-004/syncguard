"""Phase 5C — read-only presence semantics (implementation scope ONLY).

Covers: four states, completeness gate, scope enforcement, identity
independence, sync safety, persistence, audit, lifecycle-vocabulary ban.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services import presence as ps
from backend.app.db.database import Base
import backend.app.db.models as models

SCOPE = {"source_a": "A", "source_b": "B", "snapshot_a": "2024-01-01",
         "snapshot_b": "2025-01-01", "geography": "Alamance"}


def _memdb():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


# ---------- 1-4: states ----------

def test_01_both_present():
    out = ps.derive_record_presence(["k1", "k2"], ["k1", "k2"])
    assert out["k1"] == (ps.BOTH_PRESENT, ps.BOTH_OBSERVED)


def test_02_only_in_a():
    out = ps.derive_record_presence(["k1", "k2"], ["k2"])
    assert out["k1"][0] == ps.ONLY_IN_A
    assert out["k2"][0] == ps.BOTH_PRESENT


def test_03_only_in_b():
    out = ps.derive_record_presence(["k2"], ["k1", "k2"])
    assert out["k1"][0] == ps.ONLY_IN_B


def test_04_unknown_excluded():
    out = ps.derive_record_presence(["k1"], ["k1"], excluded=frozenset({"k1"}))
    assert out["k1"] == (ps.UNKNOWN, ps.RECORD_EXCLUDED)


# ---------- 5-10: completeness ----------

def test_05_complete_both_sides():
    out = ps.derive_record_presence(["a"], ["b"], ps.COMPLETE, ps.COMPLETE)
    assert out["a"][0] == ps.ONLY_IN_A and out["b"][0] == ps.ONLY_IN_B


def test_06_incomplete_a():
    out = ps.derive_record_presence(["a"], ["b"], ps.PARTIAL, ps.COMPLETE)
    assert out["b"] == (ps.UNKNOWN, ps.PARTIAL_INGESTION)
    assert out["a"][0] == ps.ONLY_IN_A


def test_07_incomplete_b():
    out = ps.derive_record_presence(["a"], ["b"], ps.COMPLETE, ps.PARTIAL)
    assert out["a"] == (ps.UNKNOWN, ps.PARTIAL_INGESTION)


def test_08_source_failure():
    out = ps.derive_record_presence(["a"], ["b"], ps.COMPLETE, ps.FAILED)
    assert out["a"] == (ps.UNKNOWN, ps.SOURCE_FAILED)
    assert out["b"] == (ps.ONLY_IN_B, ps.ONLY_B_COMPLETE)


def test_09_partial_never_becomes_absence():
    out = ps.derive_record_presence(["a"], ["b"], ps.PARTIAL, ps.COMPLETE)
    assert out["a"] == (ps.ONLY_IN_A, ps.ONLY_A_COMPLETE)
    assert out["b"] == (ps.UNKNOWN, ps.PARTIAL_INGESTION)
    out = ps.derive_record_presence(["a"], ["b"], ps.COMPLETE, ps.PARTIAL)
    assert out["b"] == (ps.ONLY_IN_B, ps.ONLY_B_COMPLETE)
    assert out["a"] == (ps.UNKNOWN, ps.PARTIAL_INGESTION)
    out = ps.derive_record_presence(["a"], ["b"], ps.PARTIAL, ps.PARTIAL)
    assert not any(v[0] in (ps.ONLY_IN_A, ps.ONLY_IN_B) for v in out.values())


def test_10_scope_mismatch():
    out = ps.derive_record_presence(["a", "y"], ["a"], out_of_scope_b=frozenset({"y"}))
    assert out["y"] == (ps.UNKNOWN, ps.SCOPE_MISMATCH)
    assert out["a"][0] == ps.BOTH_PRESENT


def test_10b_invalid_completeness_rejected():
    with pytest.raises(ValueError):
        ps.derive_record_presence(["a"], ["b"], "MOSTLY", ps.COMPLETE)


# ---------- 11-14: scope ----------

def test_11_same_scope_ok():
    db = _memdb()
    obs = ps.derive_and_persist(db, SCOPE, ["a"], ["a", "b"], job_id=None)
    assert {o["record_presence"] for o in obs} == {ps.BOTH_PRESENT, ps.ONLY_IN_B}


def test_12_different_geographic_scope():
    out = ps.derive_record_presence(["countyY-1"], [], out_of_scope_b=frozenset({"countyY-1"}))
    assert out["countyY-1"] == (ps.UNKNOWN, ps.SCOPE_MISMATCH)


def test_13_different_filters_excluded():
    out = ps.derive_record_presence(["f1", "ok"], ["ok"], excluded=frozenset({"f1"}))
    assert out["f1"] == (ps.UNKNOWN, ps.RECORD_EXCLUDED)
    assert out["ok"][0] == ps.BOTH_PRESENT


def test_14_scope_metadata_required_and_stored():
    db = _memdb()
    with pytest.raises(ValueError):
        ps.derive_and_persist(db, {"source_a": "A"}, ["a"], ["a"])
    obs = ps.derive_and_persist(db, SCOPE, ["a"], ["a"], snapshot_a_ref="snapA", snapshot_b_ref="snapB")
    row = db.query(models.PresenceObservationModel).first()
    assert row.scope["source_a"] == "A" and row.snapshot_a_ref == "snapA"
    assert obs[0]["scope"]["snapshot_b"] == "2025-01-01"


# ---------- 15-19: independence ----------

def test_15_16_17_both_present_carries_no_identity():
    out = ps.derive_record_presence(["k"], ["k"])
    assert set(out["k"]) == {ps.BOTH_PRESENT, ps.BOTH_OBSERVED}
    assert "MATCH" not in out["k"] and "NO_MATCH" not in out["k"]


def test_18_only_in_a_does_not_become_no_match():
    out = ps.derive_record_presence(["solo"], [])
    assert out["solo"][0] == ps.ONLY_IN_A
    assert "NO_MATCH" not in out["solo"]


def test_19_only_in_b_does_not_become_no_match():
    out = ps.derive_record_presence([], ["solo"])
    assert out["solo"][0] == ps.ONLY_IN_B
    assert "NO_MATCH" not in out["solo"]


def test_independence_imports():
    import ast
    src = open("backend/app/services/presence.py").read()
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    banned = [m for m in imported if any(k in m for k in ("matching", "blocking", "decision", "evidence", "conflict", "resolution", "sync", "connector"))]
    assert not banned, banned


# ---------- record vs entity ----------

def test_entity_both_present_via_link():
    rec = {"a1": (ps.ONLY_IN_A, ps.ONLY_A_COMPLETE), "b2": (ps.ONLY_IN_B, ps.ONLY_B_COMPLETE)}
    state, basis, cited = ps.interpret_entity_presence(["a1"], ["b2"], rec, links=[("a1", "b2")])
    assert (state, basis, cited) == (ps.BOTH_PRESENT, ps.BOTH_OBSERVED, [("a1", "b2")])


def test_entity_unknown_without_link():
    rec = {"a1": (ps.ONLY_IN_A, ps.ONLY_A_COMPLETE)}
    state, basis, cited = ps.interpret_entity_presence(["a1"], [], rec, links=[])
    assert state == ps.UNKNOWN and cited == []


# ---------- 20-22: safety ----------

def test_20_only_in_a_cannot_trigger_delete():
    db = _memdb()
    obs = ps.derive_and_persist(db, SCOPE, ["solo"], [])
    row = db.query(models.PresenceObservationModel).first()
    assert row.record_presence == ps.ONLY_IN_A
    assert not ps.scan_for_lifecycle_language(row.record_presence + " " + row.basis)
    directive_keys = {"operation", "destination", "action", "sync", "delete", "insert"}
    assert not (set(obs[0]) & directive_keys)
    assert not (set(row.__dict__) & directive_keys)


def test_21_only_in_b_cannot_trigger_insert():
    db = _memdb()
    obs = ps.derive_and_persist(db, SCOPE, [], ["solo"])
    row = db.query(models.PresenceObservationModel).first()
    assert row.record_presence == ps.ONLY_IN_B
    assert not ps.scan_for_lifecycle_language(row.record_presence + " " + row.basis)
    directive_keys = {"operation", "destination", "action", "sync", "delete", "insert"}
    assert not (set(obs[0]) & directive_keys)
    assert not (set(row.__dict__) & directive_keys)


def test_22_unknown_cannot_trigger_action():
    db = _memdb()
    obs = ps.derive_and_persist(db, SCOPE, ["a"], [], completeness_b=ps.FAILED)
    assert obs[0]["record_presence"] == ps.UNKNOWN
    assert set(obs[0]) <= {"id", "job_id", "record_ref", "record_presence", "entity_presence",
                           "basis", "explanation", "scope", "snapshot_a_ref", "snapshot_b_ref",
                           "observed_at", "pipeline_version"}


def test_no_presence_write_routes():
    from backend.app.main import app
    write = [r for r in app.routes if getattr(r, "path", "").startswith("/presence")
             and set(getattr(r, "methods", set())) - {"GET"}]
    assert not write, [ (r.path, r.methods) for r in write ]
    get_paths = sorted(r.path for r in app.routes if getattr(r, "path", "").startswith("/presence"))
    assert "/presence/observations" in get_paths and "/presence/summary" in get_paths


# ---------- 23-25: persistence ----------

def test_23_observation_retains_comparison_context():
    db = _memdb()
    ps.derive_and_persist(db, SCOPE, ["a"], ["b"], job_id=7,
                          snapshot_a_ref="A1", snapshot_b_ref="B1")
    rows = db.query(models.PresenceObservationModel).all()
    assert len(rows) == 2 and all(r.job_id == 7 for r in rows)
    assert {r.snapshot_a_ref for r in rows} == {"A1"}


def test_24_observation_retains_scope():
    db = _memdb()
    ps.derive_and_persist(db, SCOPE, ["a"], ["a"])
    row = db.query(models.PresenceObservationModel).first()
    for k in ("source_a", "source_b", "snapshot_a", "snapshot_b"):
        assert k in row.scope


def test_25_observation_retains_completeness():
    db = _memdb()
    ps.derive_and_persist(db, SCOPE, ["a"], [], completeness_b=ps.PARTIAL)
    row = db.query(models.PresenceObservationModel).first()
    assert row.scope["completeness_b"] == ps.PARTIAL and row.basis == ps.PARTIAL_INGESTION


# ---------- 26-27: audit ----------

def test_26_presence_observation_is_traceable():
    db = _memdb()
    obs = ps.derive_and_persist(db, SCOPE, ["a"], ["b"], job_id=9)
    logs = db.query(models.AuditLogModel).filter(models.AuditLogModel.action == "presence.observed").all()
    assert len(logs) == 2
    logged_refs = {l.details["record_ref"] for l in logs}
    assert logged_refs == {o["record_ref"] for o in obs}
    assert all(l.entity_type == "presence_observation" for l in logs)


def test_26b_audit_contains_no_pii():
    db = _memdb()
    ps.derive_and_persist(db, SCOPE, ["rec-1"], ["rec-1"])
    for log in db.query(models.AuditLogModel).all():
        blob = str(log.details)
        assert "DOUGLAS" not in blob and "@" not in blob


def test_27_no_lifecycle_terminology():
    for state in ps.PRESENCE_STATES:
        assert not ps.scan_for_lifecycle_language(state)
        text = ps.explanation_for(state, ps.SCOPE_MISMATCH)
        if state in (ps.ONLY_IN_A, ps.ONLY_IN_B):
            assert "does not mean" in text
    assert ps.scan_for_lifecycle_language("Customer was deleted") != []
    assert ps.scan_for_lifecycle_language("brand new customer") != []


# ---------- API (read-only) ----------

def test_api_observations_shape():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    with TestClient(app) as c:
        r = c.get("/presence/observations?limit=5")
        assert r.status_code == 200
        body = r.json()
        assert {"total", "page", "limit", "items"} <= set(body)


def test_api_invalid_state_rejected():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    with TestClient(app) as c:
        r = c.get("/presence/observations?state=DELETED")
        assert r.status_code == 422


def test_api_summary_shape():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    with TestClient(app) as c:
        r = c.get("/presence/summary")
        assert r.status_code == 200
        body = r.json()
        assert {"total", "counts", "bases"} <= set(body)
        assert set(body["counts"]) == set(ps.PRESENCE_STATES)
