"""Phase 5C-W — presence wired into the comparison pipeline as read-only side output."""
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import presence as ps


def _csv(rows):
    head = "rec_id,given_name,surname,email,phone,postcode\n"
    return head + "".join(f"{r},G{S}ur,Surname{r},{r}@x.com,555{r},800{r}\n" for r, S in rows)


def _two_source_job(c, tag):
    shared = f"{tag}-shared"
    csv_a = _csv([(f"{tag}-a1", "A"), (f"{tag}-a2", "B"), (shared, "C")])
    csv_b = _csv([(f"{tag}-b1", "D"), (shared, "C")])
    sa = c.post("/uploads", files={"file": (f"{tag}a.csv", csv_a.encode(), "text/csv")})
    assert sa.status_code == 201, sa.text
    sb = c.post("/uploads", files={"file": (f"{tag}b.csv", csv_b.encode(), "text/csv")})
    assert sb.status_code == 201, sb.text
    key = f"5cw-{tag}-{uuid.uuid4().hex[:8]}"
    r = c.post("/reconciliation",
               json={"source_ids": [sa.json()["source_id"], sb.json()["source_id"]], "idempotency_key": key},
               headers={"Idempotency-Key": key})
    assert r.status_code == 202, r.text
    return r.json()["job_id"], key, sa.json()["source_id"], sb.json()["source_id"]


def test_01_complete_comparison_yields_both_present():
    with TestClient(app) as c:
        jid, _, _, _ = _two_source_job(c, "both")
        items = c.get(f"/presence/observations?job_id={jid}&state=BOTH_PRESENT&limit=100").json()["items"]
        assert len(items) == 2
        assert all(i["record_presence"] == ps.BOTH_PRESENT for i in items)


def test_02_complete_comparison_yields_only_in_a():
    with TestClient(app) as c:
        jid, _, _, _ = _two_source_job(c, "onlya")
        items = c.get(f"/presence/observations?job_id={jid}&state=ONLY_IN_A&limit=100").json()["items"]
        assert len(items) == 2


def test_03_complete_comparison_yields_only_in_b():
    with TestClient(app) as c:
        jid, _, _, _ = _two_source_job(c, "onlyb")
        items = c.get(f"/presence/observations?job_id={jid}&state=ONLY_IN_B&limit=100").json()["items"]
        assert len(items) == 1


def test_04_incomplete_comparison_yields_unknown():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.app.db.database import Base
    import backend.app.db.models
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    scope = {"source_a": "A", "source_b": "B", "snapshot_a": "sA", "snapshot_b": "sB"}
    obs = ps.derive_and_persist(db, scope, ["k1"], ["k2"], completeness_b=ps.PARTIAL)
    by_ref = {o["record_ref"]: o["record_presence"] for o in obs}
    assert by_ref["k1"] == ps.UNKNOWN and by_ref["k2"] == ps.ONLY_IN_B


def test_05_presence_generated_during_actual_comparison():
    with TestClient(app) as c:
        jid, _, _, _ = _two_source_job(c, "gen")
        total = c.get(f"/presence/observations?job_id={jid}&limit=100").json()["total"]
        assert total == 5  # 3 A records + 2 B records, one shared key


def test_06_presence_persisted_and_07_retrievable():
    with TestClient(app) as c:
        jid, _, _, _ = _two_source_job(c, "persist")
        body = c.get(f"/presence/observations?job_id={jid}&limit=100").json()
        assert body["total"] == 5 and len(body["items"]) == 5
        for item in body["items"]:
            assert {"id", "record_presence", "basis", "explanation", "scope"} <= set(item)


def test_08_comparison_association_09_scope_10_completeness():
    with TestClient(app) as c:
        jid, _, sa, sb = _two_source_job(c, "assoc")
        body = c.get(f"/presence/observations?job_id={jid}&limit=100").json()
        assert all(i["job_id"] == jid for i in body["items"])
        for i in body["items"]:
            assert i["scope"]["source_a"] == str(sa) and i["scope"]["source_b"] == str(sb)
            assert i["scope"]["completeness_a"] == "COMPLETE" and i["scope"]["completeness_b"] == "COMPLETE"
        summ = c.get(f"/presence/summary?job_id={jid}").json()
        assert summ["total"] == 5
        assert summ["counts"]["BOTH_PRESENT"] == 2
        assert summ["counts"]["ONLY_IN_A"] == 2
        assert summ["counts"]["ONLY_IN_B"] == 1


def test_11_matching_output_created_alongside_presence():
    with TestClient(app) as c:
        jid, _, _, _ = _two_source_job(c, "matchok")
        matches = c.get(f"/matches?job_id={jid}&limit=100").json()
        assert matches["total"] >= 1
        decisions = {(m.get("decision")) for m in matches["items"]}
        assert decisions <= {"MATCH", "POSSIBLE_MATCH", "NO_MATCH", None}


def test_12_presence_failure_isolated_from_matching(monkeypatch):
    monkeypatch.setattr(ps, "derive_and_persist", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("presence boom")))
    with TestClient(app) as c:
        jid, _, _, _ = _two_source_job(c, "piso")
        job = c.get(f"/reconciliation/{jid}").json()
        assert job["status"] == "completed"
        assert c.get(f"/matches?job_id={jid}&limit=100").json()["total"] >= 1
        assert c.get(f"/presence/observations?job_id={jid}&limit=100").json()["total"] == 0


def test_13_matching_failure_creates_no_false_absence(monkeypatch):
    from backend.app.services.matching import MatchingEngine
    def boom(self, *a, **k):
        raise RuntimeError("matcher boom")
    monkeypatch.setattr(MatchingEngine, "evaluate_pairs", boom)
    with TestClient(app) as c:
        jid, _, _, _ = _two_source_job(c, "mfail")
        job = c.get(f"/reconciliation/{jid}").json()
        assert job["status"] == "failed"
        assert c.get(f"/presence/observations?job_id={jid}&limit=100").json()["total"] == 0


def test_14_repeated_comparison_does_not_corrupt():
    with TestClient(app) as c:
        jid, key, sa, sb = _two_source_job(c, "repeat")
        first = c.get(f"/presence/observations?job_id={jid}&limit=100").json()["total"]
        r = c.post("/reconciliation", json={"source_ids": [sa, sb], "idempotency_key": key},
                   headers={"Idempotency-Key": key})
        assert r.json()["job_id"] == jid
        second = c.get(f"/presence/observations?job_id={jid}&limit=100").json()["total"]
        assert first == second == 5


def test_15_no_lifecycle_terminology_in_pipeline_output():
    with TestClient(app) as c:
        jid, _, _, _ = _two_source_job(c, "lifecyc")
        body = c.get(f"/presence/observations?job_id={jid}&limit=100").json()
        for item in body["items"]:
            assert not ps.scan_for_lifecycle_language(item["record_presence"] + " " + item["basis"])
            assert "does not mean" in item["explanation"] or item["record_presence"] == ps.BOTH_PRESENT


def test_16_no_synchronization_side_effects():
    from backend.app.db.database import SessionLocal
    from backend.app.db.models import SyncJobModel
    with TestClient(app) as c:
        jid, _, _, _ = _two_source_job(c, "nosync")
        db = SessionLocal()
        try:
            mine = db.query(SyncJobModel).filter(SyncJobModel.reconciliation_job_id == jid).all()
            assert mine == []
        finally:
            db.close()
