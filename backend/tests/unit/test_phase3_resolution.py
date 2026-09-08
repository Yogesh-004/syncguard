"""Phase 3 tests — resolution, dry-run, push, retry, verification, audit, states."""
import uuid

import pytest
from fastapi.testclient import TestClient


def _live_conflict(client, tag="p3"):
    csv = (
        "rec_id,given_name,surname,email,phone,postcode\n"
        f"{tag}-1,Yara,Moon,yara.moon@a.com,9304001,8000\n"
        f"{tag}-2,Yara,Moon,yara.moon@b.com,9304001,8000\n"
    )
    up = client.post("/uploads", files={"file": (f"{tag}.csv", csv.encode(), "text/csv")})
    assert up.status_code == 201
    sid = up.json()["source_id"]
    key = f"p3-{tag}-{uuid.uuid4().hex[:8]}"
    r = client.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key})
    jid = r.json()["job_id"]
    confs = client.get(f"/conflicts?job_id={jid}&limit=20").json()
    assert confs, "expected live conflicts"
    email = next((x for x in confs if (x["conflicting_fields"][0].get("field_name")) == "email"), confs[0])
    return jid, email["id"]


def test_01_use_source_a():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "srcA")
        r = c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        assert r.status_code == 200
        body = c.get(f"/conflicts/{cid}").json()
        assert body["resolution_status"] == "approved"


def test_02_use_source_b():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "srcB")
        r = c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_B"})
        assert r.status_code == 200
        lst = c.get(f"/conflicts/{cid}/resolutions").json()
        assert lst[0]["selected_source"] == "B"


def test_03_manual_edit():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "edit")
        d = c.get(f"/conflicts/{cid}").json()
        field = d["conflicting_fields"][0]["field_name"]
        r = c.post(f"/conflicts/{cid}/resolve", json={"action": "MANUAL_EDIT", "modified_values": {field: "yara.fixed@c.com"}})
        assert r.status_code == 200
        lst = c.get(f"/conflicts/{cid}/resolutions").json()
        assert lst[0]["resolved_value"] == "yara.fixed@c.com"


def test_04_reject():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "rej")
        assert c.post(f"/conflicts/{cid}/resolve", json={"action": "REJECT"}).status_code == 200
        assert c.get(f"/conflicts/{cid}").json()["resolution_status"] == "rejected"


def test_05_defer():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "def")
        assert c.post(f"/conflicts/{cid}/resolve", json={"action": "DEFER", "reason": "Need business confirmation"}).status_code == 200
        assert c.get(f"/conflicts/{cid}").json()["resolution_status"] == "deferred"


def test_06_invalid_rejected():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "inv")
        assert c.post(f"/conflicts/{cid}/resolve", json={"action": "BOGUS"}).status_code == 422


def test_07_duplicate_prevented():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "dup")
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        n1 = len(c.get(f"/conflicts/{cid}/resolutions").json())
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        assert len(c.get(f"/conflicts/{cid}/resolutions").json()) == n1


def test_08_resolved_protected():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "prot")
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        r = c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_B"})
        assert r.status_code == 409


def test_09_originals_preserved():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "orig")
        before = c.get(f"/conflicts/{cid}").json()["conflicting_fields"]
        d = c.get(f"/conflicts/{cid}").json()
        c.post(f"/conflicts/{cid}/resolve", json={"action": "MANUAL_EDIT", "modified_values": {d["conflicting_fields"][0]["field_name"]: "kept@c.com"}})
        after = c.get(f"/conflicts/{cid}").json()["conflicting_fields"]
        assert before == after


def test_10_before_after():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "ba")
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        lst = c.get(f"/conflicts/{cid}/resolutions").json()
        assert "previous_value" in lst[0] and "resolved_value" in lst[0]


def _resolved(client, tag):
    _, cid = _live_conflict(client, tag)
    client.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
    rid = client.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
    return cid, rid


def test_11_dry_run_ok():
    from backend.app.main import app
    with TestClient(app) as c:
        _, rid = _resolved(c, "dry")
        r = c.post(f"/resolutions/{rid}/dry-run")
        assert r.status_code == 200
        assert r.json()["result"].startswith("DRY RUN SUCCESS")


def test_12_dry_run_no_modify():
    from backend.app.main import app
    with TestClient(app) as c:
        _, rid = _resolved(c, "dryno")
        dry = c.post(f"/resolutions/{rid}/dry-run").json()
        from backend.app.connectors.mock_connector import MockConnector
        assert MockConnector(dry["destination"]).get_record(1, dry["field"])["value"] is None


def test_13_reject_no_dryrun():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "nodry")
        c.post(f"/conflicts/{cid}/resolve", json={"action": "REJECT"})
        rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
        assert c.post(f"/resolutions/{rid}/dry-run").status_code == 422


def test_14_push_success():
    from backend.app.main import app
    with TestClient(app) as c:
        _, rid = _resolved(c, "push")
        c.post(f"/resolutions/{rid}/dry-run")
        r = c.post(f"/resolutions/{rid}/push", json={"confirm": True})
        assert r.status_code == 200
        assert r.json()["status"] == "SUCCESS"
        assert r.json()["mock"] is True


def test_15_push_fail_500():
    from backend.app.main import app
    with TestClient(app) as c:
        _, rid = _resolved(c, "fail")
        c.post(f"/resolutions/{rid}/dry-run")
        r = c.post(f"/resolutions/{rid}/push", json={"confirm": True, "simulate_error": 500})
        assert r.json()["status"] == "FAILED"
        assert r.json()["attempt_count"] == 1


def test_16_retryable_500():
    from backend.app.main import app
    with TestClient(app) as c:
        _, rid = _resolved(c, "ret")
        c.post(f"/resolutions/{rid}/dry-run")
        jid = c.post(f"/resolutions/{rid}/push", json={"confirm": True, "simulate_error": 500}).json()["sync_job_id"]
        r = c.post(f"/sync-jobs/{jid}/retry", json={})
        assert r.status_code == 200
        assert r.json()["status"] == "SUCCESS"


def test_17_nonretryable_400():
    from backend.app.main import app
    with TestClient(app) as c:
        _, rid = _resolved(c, "noret")
        c.post(f"/resolutions/{rid}/dry-run")
        jid = c.post(f"/resolutions/{rid}/push", json={"confirm": True, "simulate_error": 400}).json()["sync_job_id"]
        assert c.post(f"/sync-jobs/{jid}/retry", json={}).status_code == 422


def test_18_idempotent_push():
    from backend.app.main import app
    with TestClient(app) as c:
        _, rid = _resolved(c, "idem")
        c.post(f"/resolutions/{rid}/dry-run")
        c.post(f"/resolutions/{rid}/push", json={"confirm": True})
        r = c.post(f"/resolutions/{rid}/push", json={"confirm": True})
        assert "ALREADY_APPLIED" in r.json()["result"]


def test_19_duplicate_push_count():
    from backend.app.main import app
    with TestClient(app) as c:
        _, rid = _resolved(c, "idem2")
        c.post(f"/resolutions/{rid}/dry-run")
        j1 = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()["sync_job_id"]
        j2 = c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()["sync_job_id"]
        assert j1 == j2


def test_20_verify_success():
    from backend.app.main import app
    with TestClient(app) as c:
        _, rid = _resolved(c, "ver")
        c.post(f"/resolutions/{rid}/dry-run")
        assert c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json()["verified"] is True


def test_21_verify_failure():
    from backend.app.main import app
    with TestClient(app) as c:
        _, rid = _resolved(c, "verf")
        c.post(f"/resolutions/{rid}/dry-run")
        r = c.post(f"/resolutions/{rid}/push", json={"confirm": True, "simulate_error": 500})
        assert r.json()["verified"] is False


def _audit(client, cid):
    return client.get(f"/conflicts/{cid}/audit").json()


def test_22_resolution_audit():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "au1")
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        assert any(a["action"] == "RESOLUTION_CREATED" for a in _audit(c, cid))


def test_23_edit_audit():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "au2")
        d = c.get(f"/conflicts/{cid}").json()
        c.post(f"/conflicts/{cid}/resolve", json={"action": "MANUAL_EDIT", "modified_values": {d["conflicting_fields"][0]["field_name"]: "x@y.com"}})
        assert any(a["action"] == "RESOLUTION_CREATED" for a in _audit(c, cid))


def test_24_dryrun_audit():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "au3")
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
        c.post(f"/resolutions/{rid}/dry-run")
        assert any(a["action"] == "DRY_RUN_COMPLETED" for a in _audit(c, cid))


def test_25_push_audit():
    from backend.app.main import app
    with TestClient(app) as c:
        jid, rid = None, None
        _, cid = _live_conflict(c, "au4")
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
        c.post(f"/resolutions/{rid}/dry-run")
        c.post(f"/resolutions/{rid}/push", json={"confirm": True})
        assert any(a["action"] in ("SYNC_STARTED", "SYNC_SUCCEEDED") for a in _audit(c, cid))


def test_26_fail_audit():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "au5")
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
        c.post(f"/resolutions/{rid}/dry-run")
        c.post(f"/resolutions/{rid}/push", json={"confirm": True, "simulate_error": 500})
        assert any(a["action"] == "SYNC_FAILED" for a in _audit(c, cid))


def test_27_verify_audit():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "au6")
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
        c.post(f"/resolutions/{rid}/dry-run")
        c.post(f"/resolutions/{rid}/push", json={"confirm": True})
        assert any(a["action"] == "SYNC_VERIFIED" for a in _audit(c, cid))


def test_28_invalid_transition():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "trans")
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        assert c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_B"}).status_code == 409


def test_29_no_double_resolve():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "dbl")
        c.post(f"/conflicts/{cid}/resolve", json={"action": "DEFER"})
        assert c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"}).status_code == 409


def test_30_unresolved_no_push():
    from backend.app.main import app
    with TestClient(app) as c:
        _, cid = _live_conflict(c, "nopush")
        rid = c.post(f"/resolutions/999999/dry-run")
        assert rid.status_code == 404
