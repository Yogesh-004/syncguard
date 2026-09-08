"""Phase 4.1 regression — tiers, filters, actions, audit/timeline isolation."""
import pathlib
import uuid

import pytest
from fastapi.testclient import TestClient

FRONT = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "src"


def _live_job(client, tag, rows=None):
    rows = rows or (
        "rec_id,given_name,surname,email,phone,postcode\n"
        f"{tag}-1,Noa,Frost,noa.frost@a.com,9403001,7100\n"
        f"{tag}-2,Noa,Frost,noa.frost@b.com,9403001,7100\n"
        f"{tag}-3,Zebulon,Quarry,zebulon.quarry@c.com,9403002,7200\n"
    )
    up = client.post("/uploads", files={"file": (f"{tag}.csv", rows.encode(), "text/csv")})
    assert up.status_code == 201
    sid = up.json()["source_id"]
    key = f"p41-{tag}-{uuid.uuid4().hex[:8]}"
    r = client.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key})
    assert r.status_code == 202
    return r.json()["job_id"], sid


def _src(pages, name):
    return (FRONT / "pages" / name).read_text(encoding="utf-8")


def test_01_match_filter_all_and_tiers():
    from backend.app.main import app
    with TestClient(app) as c:
        jid, _ = _live_job(c, "t1")
        for dec in ("", "MATCH", "NO_MATCH"):
            r = c.get("/matches", params={"job_id": jid, **({"decision": dec} if dec else {})})
            assert r.status_code == 200
            assert r.json()["mode"] == "live"


def test_02_thresholds_from_backend():
    from backend.app.main import app
    with TestClient(app) as c:
        r = c.get("/matches?limit=1").json()
        assert r["thresholds"]["MATCH"] == 0.6
        assert r["thresholds"]["POSSIBLE_MATCH"] == 0.5
        assert r["model_version"] == "1.0.0"
        m = c.get("/model/info").json()
        assert m["match_threshold"] == 0.6 and m["possible_match_threshold"] == 0.5


def test_03_nomatch_persisted_with_sample_flag():
    from backend.app.main import app
    with TestClient(app) as c:
        jid, _ = _live_job(c, "t3")
        rows = c.get(f"/matches?job_id={jid}&decision=NO_MATCH&limit=100").json()["items"]
        assert rows, "expected NO_MATCH sample rows"
        assert all(x["evidence"].get("decision") == "NO_MATCH" for x in rows)


def test_04_invalid_decision_422():
    from backend.app.main import app
    with TestClient(app) as c:
        assert c.get("/matches?decision=MAYBE").status_code == 422


def test_05_frontend_no_compute():
    t = _src(None, "Matching.tsx")
    assert "/match?" not in t and "matching/run" not in t
    assert "NO_MATCH" in t and "thresholds" in t


def test_06_actions_visible():
    t = (FRONT / "components" / "ResolutionPanel.tsx").read_text(encoding="utf-8")
    for a in ("USE_SOURCE_A", "USE_SOURCE_B", "MANUAL_EDIT", "REJECT", "DEFER", "dry-run", "push"):
        assert a in t, a


def test_07_invalid_edit_blocked():
    from backend.app.main import app
    with TestClient(app) as c:
        _, sid = _live_job(c, "t7")
        cid = c.get(f"/conflicts?source_id={sid}&limit=5").json()[0]["id"]
        d = c.get(f"/conflicts/{cid}").json()
        field = d["conflicting_fields"][0]["field_name"]
        bad = "not-an-email" if "email" in field else ""
        if bad:
            assert c.post(f"/conflicts/{cid}/resolve", json={"action": "MANUAL_EDIT", "modified_values": {field: bad}}).status_code == 422


def test_08_reject_defer_no_push():
    from backend.app.main import app
    with TestClient(app) as c:
        for action, tag in (("REJECT", "t8a"), ("DEFER", "t8b")):
            _, sid = _live_job(c, tag)
            cid = [x for x in c.get(f"/conflicts?source_id={sid}&limit=20").json() if x["resolution_status"] == "pending"][0]["id"]
            c.post(f"/conflicts/{cid}/resolve", json={"action": action})
            rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
            assert c.post(f"/resolutions/{rid}/dry-run").status_code == 422
            assert c.post(f"/resolutions/{rid}/push", json={"confirm": True}).status_code == 422


def test_09_audit_job_isolation():
    from backend.app.main import app
    with TestClient(app) as c:
        ja, _ = _live_job(c, "t9a")
        jb, _ = _live_job(c, "t9b")
        a = {x["id"] for x in c.get(f"/audit-logs?job_id={ja}&limit=100").json()["items"]}
        b = {x["id"] for x in c.get(f"/audit-logs?job_id={jb}&limit=100").json()["items"]}
        assert a.isdisjoint(b)


def test_10_audit_source_isolation():
    from backend.app.main import app
    with TestClient(app) as c:
        _, sa = _live_job(c, "t10a")
        _, sb = _live_job(c, "t10b")
        a = {x["id"] for x in c.get(f"/audit-logs?source_id={sa}&limit=100").json()["items"]}
        b = {x["id"] for x in c.get(f"/audit-logs?source_id={sb}&limit=100").json()["items"]}
        assert a.isdisjoint(b)


def test_11_timeline_scoped():
    from backend.app.main import app
    with TestClient(app) as c:
        ja, _ = _live_job(c, "t11a")
        jb, _ = _live_job(c, "t11b")
        ca = c.get(f"/conflicts?job_id={ja}&limit=5").json()[0]["id"]
        cb = c.get(f"/conflicts?job_id={jb}&limit=5").json()[0]["id"]
        c.post(f"/conflicts/{ca}/resolve", json={"action": "USE_SOURCE_A"})
        ta = {x["id"] for x in c.get(f"/conflicts/{ca}/audit").json()}
        tb = {x["id"] for x in c.get(f"/conflicts/{cb}/audit").json()}
        assert ta.isdisjoint(tb)
        assert any("RESOLUTION_CREATED" in x["action"] for x in c.get(f"/conflicts/{ca}/audit").json())


def test_12_audit_page_scoping():
    t = _src(None, "Audit.tsx")
    assert "job_id" in t and "source_id" in t and "LIVE" in t


def test_13_refresh_persistence():
    from backend.app.main import app
    with TestClient(app) as c:
        jid, _ = _live_job(c, "t13")
        mid = c.get(f"/matches?job_id={jid}&limit=5").json()["items"][0]["id"]
        assert c.get(f"/matches/{mid}").status_code == 200
        cid = c.get(f"/conflicts?job_id={jid}&limit=5").json()[0]["id"]
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        assert c.get(f"/conflicts/{cid}").json()["resolution_status"] == "approved"
        assert c.get(f"/audit-logs?job_id={jid}&limit=50").json()["total"] > 0
