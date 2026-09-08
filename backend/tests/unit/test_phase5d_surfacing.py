"""Phase 5D — persisted presence surfaced in the existing conflict review detail."""
import uuid

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.database import SessionLocal
from backend.app.db.models import ConflictModel, MatchModel, PresenceObservationModel, SyncJobModel
from backend.app.services import presence as ps

SCOPE = {"source_a": "A", "source_b": "B", "snapshot_a": "sA", "snapshot_b": "sB"}


def _csv(rows):
    head = "rec_id,given_name,surname,email,phone,postcode\n"
    return head + "".join(f"{r},G{S}ur,Surname{r},{r}@x.com,555{r},800{r}\n" for r, S in rows)


def _job(c, tag):
    csv_a = _csv([(f"{tag}-a1", "A"), (f"{tag}-shared", "C")])
    csv_b = _csv([(f"{tag}-b1", "D"), (f"{tag}-shared", "C")])
    sa = c.post("/uploads", files={"file": (f"{tag}a.csv", csv_a.encode(), "text/csv")}).json()
    sb = c.post("/uploads", files={"file": (f"{tag}b.csv", csv_b.encode(), "text/csv")}).json()
    key = f"5d-{tag}-{uuid.uuid4().hex[:8]}"
    r = c.post("/reconciliation",
               json={"source_ids": [sa["source_id"], sb["source_id"]], "idempotency_key": key},
               headers={"Idempotency-Key": key})
    assert r.status_code == 202, r.text
    return r.json()["job_id"]


def _seed_conflict(job_id):
    db = SessionLocal()
    try:
        m = db.query(MatchModel).filter(MatchModel.entity_group_id == f"job-{job_id}").first()
        assert m is not None, "pipeline produced no match to attach a conflict to"
        cm = ConflictModel(record_a_id=m.record_a_id, record_b_id=m.record_b_id, match_id=m.id,
                           confidence=m.confidence, conflicting_fields=[{"field_name": "phone"}],
                           evidence={"job_id": job_id}, risk_level="HIGH",
                           recommendation="REVIEW REQUIRED", resolution_status="pending",
                           auto_resolvable=False)
        db.add(cm)
        db.commit()
        db.refresh(cm)
        return cm.id, m.record_a_id, m.record_b_id, (m.evidence or {}).get("decision"), m.risk
    finally:
        db.close()


def _seed_presence(job_id, ref_a, ref_b, state_a, basis_a, state_b=None, basis_b=None,
                   completeness_a="COMPLETE", completeness_b="COMPLETE"):
    db = SessionLocal()
    try:
        scope = dict(SCOPE)
        rp = {"ka": (state_a, basis_a)}
        refs = {"ka": [str(ref_a)]}
        if state_b is not None:
            rp["kb"] = (state_b, basis_b)
            refs["kb"] = [str(ref_b)]
        ps.derive_and_persist(db, scope, ["ka"] + (["kb"] if state_b else []), ["ka"] + (["kb"] if state_b else []),
                              completeness_a=completeness_a, completeness_b=completeness_b,
                              job_id=job_id, record_presence=rp, key_to_refs=refs)
    finally:
        db.close()


def test_a_both_present_appears():
    with TestClient(app) as c:
        jid = _job(c, "pa")
        cid, ra, rb, _, _ = _seed_conflict(jid)
        _seed_presence(jid, ra, rb, ps.BOTH_PRESENT, ps.BOTH_OBSERVED, ps.BOTH_PRESENT, ps.BOTH_OBSERVED)
        d = c.get(f"/conflicts/{cid}").json()
        assert d["presence"]["record_a"]["record_presence"] == "BOTH_PRESENT"
        assert d["presence"]["record_b"]["record_presence"] == "BOTH_PRESENT"
        assert "both" in d["presence"]["record_a"]["explanation"].lower()


def test_b_only_in_a_appears():
    with TestClient(app) as c:
        jid = _job(c, "pb")
        cid, ra, rb, _, _ = _seed_conflict(jid)
        _seed_presence(jid, ra, rb, ps.ONLY_IN_A, ps.ONLY_A_COMPLETE)
        d = c.get(f"/conflicts/{cid}").json()
        assert d["presence"]["record_a"]["record_presence"] == "ONLY_IN_A"
        assert "does not mean" in d["presence"]["record_a"]["explanation"]
        assert d["presence"]["record_b"]["record_presence"] == "BOTH_PRESENT"


def test_c_only_in_b_appears():
    with TestClient(app) as c:
        jid = _job(c, "pc")
        cid, ra, rb, _, _ = _seed_conflict(jid)
        _seed_presence(jid, ra, rb, ps.ONLY_IN_B, ps.ONLY_B_COMPLETE, ps.ONLY_IN_B, ps.ONLY_B_COMPLETE)
        d = c.get(f"/conflicts/{cid}").json()
        assert d["presence"]["record_b"]["record_presence"] == "ONLY_IN_B"


def test_d_unknown_appears():
    with TestClient(app) as c:
        jid = _job(c, "pd")
        cid, ra, rb, _, _ = _seed_conflict(jid)
        _seed_presence(jid, ra, rb, ps.UNKNOWN, ps.SCOPE_MISMATCH)
        d = c.get(f"/conflicts/{cid}").json()
        assert d["presence"]["record_a"]["record_presence"] == "UNKNOWN"
        assert "No conclusion" in d["presence"]["record_a"]["explanation"]


def test_e_completeness_gated_observation_surfaced():
    with TestClient(app) as c:
        jid = _job(c, "pe")
        cid, ra, rb, _, _ = _seed_conflict(jid)
        _seed_presence(jid, ra, rb, ps.UNKNOWN, ps.PARTIAL_INGESTION,
                       completeness_b=ps.PARTIAL)
        d = c.get(f"/conflicts/{cid}").json()
        p = d["presence"]["record_a"]
        assert p["basis"] == "PARTIAL_INGESTION"
        assert p["scope"]["completeness_b"] == "PARTIAL"


def test_f_other_job_observation_not_surfaced():
    with TestClient(app) as c:
        j1 = _job(c, "pf1")
        j2 = _job(c, "pf2")
        cid, ra, rb, _, _ = _seed_conflict(j1)
        _seed_presence(j2, ra, rb, ps.ONLY_IN_A, ps.ONLY_A_COMPLETE)
        db = SessionLocal()
        try:
            foreign = db.query(PresenceObservationModel).filter(
                PresenceObservationModel.job_id == j2,
                PresenceObservationModel.record_ref.in_([str(ra), str(rb)])).count()
            assert foreign >= 1, "foreign-job rows must exist for the isolation test to mean anything"
        finally:
            db.close()
        d = c.get(f"/conflicts/{cid}").json()
        for slot in ("record_a", "record_b"):
            p = d["presence"][slot]
            assert p["scope"].get("source_a") != "A", p
        assert d["presence"]["record_a"]["record_presence"] == "BOTH_PRESENT"


def test_g_missing_observation_no_inference():
    with TestClient(app) as c:
        jid = _job(c, "pg")
        cid, _, _, _, _ = _seed_conflict(jid)
        db = SessionLocal()
        try:
            db.query(PresenceObservationModel).filter(
                PresenceObservationModel.job_id == jid).delete()
            db.commit()
        finally:
            db.close()
        d = c.get(f"/conflicts/{cid}").json()
        assert d["presence"] == {"record_a": None, "record_b": None}


def test_h_presence_does_not_modify_decision_and_i_risk():
    with TestClient(app) as c:
        jid = _job(c, "ph")
        cid, ra, rb, dec0, risk0 = _seed_conflict(jid)
        before = c.get(f"/conflicts/{cid}").json()
        _seed_presence(jid, ra, rb, ps.ONLY_IN_A, ps.ONLY_A_COMPLETE, ps.ONLY_IN_B, ps.ONLY_B_COMPLETE)
        after = c.get(f"/conflicts/{cid}").json()
        assert after["match"]["decision"] == before["match"]["decision"] == dec0
        assert after["risk"] == before["risk"] and after["risk_level"] == before["risk_level"]


def test_j_presence_does_not_resolve_and_m_actions_work():
    with TestClient(app) as c:
        jid = _job(c, "pj")
        cid, ra, rb, _, _ = _seed_conflict(jid)
        _seed_presence(jid, ra, rb, ps.ONLY_IN_A, ps.ONLY_A_COMPLETE)
        assert c.get(f"/conflicts/{cid}").json()["status"] == "pending"
        r = c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        assert r.status_code == 200
        d = c.get(f"/conflicts/{cid}").json()
        assert d["status"] in ("approved", "modified", "pending")
        assert d["presence"]["record_a"]["record_presence"] == "ONLY_IN_A"


def test_k_no_synchronization_triggered():
    with TestClient(app) as c:
        jid = _job(c, "pk")
        cid, ra, rb, _, _ = _seed_conflict(jid)
        _seed_presence(jid, ra, rb, ps.ONLY_IN_A, ps.ONLY_A_COMPLETE, ps.ONLY_IN_B, ps.ONLY_B_COMPLETE)
        c.get(f"/conflicts/{cid}")
        db = SessionLocal()
        try:
            assert db.query(SyncJobModel).filter(SyncJobModel.reconciliation_job_id == jid).all() == []
        finally:
            db.close()


def test_l_neutral_wording_no_lifecycle_claims():
    with TestClient(app) as c:
        jid = _job(c, "pl")
        cid, ra, rb, _, _ = _seed_conflict(jid)
        _seed_presence(jid, ra, rb, ps.ONLY_IN_A, ps.ONLY_A_COMPLETE, ps.UNKNOWN, ps.SCOPE_MISMATCH)
        d = c.get(f"/conflicts/{cid}").json()
        for slot in ("record_a", "record_b"):
            p = d["presence"][slot]
            assert not ps.scan_for_lifecycle_language(p["record_presence"] + " " + p["basis"])
            for token in ("should delete", "should insert", "should create"):
                assert token not in p["explanation"].lower()
        assert "does not mean" in d["presence"]["record_a"]["explanation"]


def test_n_conflict_queue_unchanged():
    with TestClient(app) as c:
        jid = _job(c, "pn")
        rows = c.get(f"/conflicts?job_id={jid}&limit=20").json()
        assert isinstance(rows, list)
