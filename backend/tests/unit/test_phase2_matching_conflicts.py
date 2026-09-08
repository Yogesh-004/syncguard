"""Phase 2 tests — matching decisions + field-level conflicts + isolation (no Phase 3)."""
import uuid

import pytest
from fastapi.testclient import TestClient


def _decide(prob):
    from backend.app.services import model_service as ms
    from backend.app.core.config import settings
    return ms.decide(prob, settings.MATCH_THRESHOLD, settings.POSSIBLE_MATCH_THRESHOLD)


def test_01_exact_entity_match():
    from backend.app.services import model_service as ms
    p, _ = ms.predict({"name": "Rahul Kumar", "postcode": "2000", "external_id": "1"}, {"name": "Rahul Kumar", "postcode": "2000", "external_id": "1"})
    assert _decide(p) == "MATCH"


def test_02_normalized_entity_match():
    from backend.app.services import model_service as ms
    p, _ = ms.predict({"name": " Rahul Kumar ", "postcode": "2000", "external_id": "1"}, {"name": "rahul kumar", "postcode": "2000", "external_id": "1"})
    assert _decide(p) == "MATCH"


def test_03_fuzzy_entity_match():
    from backend.app.services import model_service as ms
    p, _ = ms.predict({"name": "Rahul Kumar", "postcode": "2000", "external_id": "1"}, {"name": "Rahul Kumaar", "postcode": "2000", "external_id": "1"})
    assert _decide(p) in ("MATCH", "POSSIBLE_MATCH")


def test_04_possible_match():
    assert _decide(0.55) == "POSSIBLE_MATCH"


def test_05_no_match():
    assert _decide(0.1) == "NO_MATCH"


def test_06_score_persisted():
    from backend.app.main import app
    with TestClient(app) as c:
        r = c.get("/matches?limit=1")
        assert r.status_code == 200
        items = r.json().get("items", [])
        if items:
            assert isinstance(items[0]["confidence"], float)


def test_07_model_version_persisted():
    from backend.app.main import app
    with TestClient(app) as c:
        r = c.get("/matches?limit=1")
        items = r.json().get("items", [])
        if items:
            assert items[0].get("model_version") == "1.0.0"


def test_08_one_field_conflict():
    from backend.app.services import conflict_detection as cd
    out = cd.detect_field_conflicts({"name": "Rahul Kumar", "email": "rahul@gmail.com"}, {"name": "Rahul Kumar", "email": "rahulkumar@gmail.com"})
    assert len(out) == 1 and out[0]["field_name"] == "email"


def test_09_multiple_field_conflicts():
    from backend.app.services import conflict_detection as cd
    out = cd.detect_field_conflicts({"email": "a@x.com", "phone": "111", "name": "A"}, {"email": "b@x.com", "phone": "222", "name": "A"})
    assert {f["field_name"] for f in out} == {"email", "phone"}


def test_10_formatting_only_no_conflict():
    from backend.app.services import conflict_detection as cd
    out = cd.detect_field_conflicts({"phone": "+1 5551234567", "name": " Rahul Kumar "}, {"phone": "5551234567", "name": "rahul kumar"})
    assert out == []


def test_11_null_vs_value():
    from backend.app.services import conflict_detection as cd
    o, _, _ = cd.compare_field("email", "john@gmail.com", None)
    assert o == "MISSING_VALUE"


def test_12_both_null():
    from backend.app.services import conflict_detection as cd
    o, _, _ = cd.compare_field("email", None, None)
    assert o == "BOTH_EMPTY"
    assert cd.detect_field_conflicts({"email": None}, {"email": None}) == []


def _live_job(client, tag):
    csv = f"rec_id,given_name,surname,postcode\n{tag}-1,Zaara,Nair,4000\n{tag}-2,Zaara,Nair,4000\n"
    up = client.post("/uploads", files={"file": (f"{tag}.csv", csv.encode(), "text/csv")})
    assert up.status_code == 201
    sid = up.json()["source_id"]
    key = f"p2-{tag}-{uuid.uuid4().hex[:8]}"
    r = client.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key})
    assert r.status_code == 202
    return r.json()["job_id"], sid


def test_13_multiple_conflicts_same_entity():
    from backend.app.services import conflict_detection as cd
    out = cd.detect_field_conflicts({"email": "a@x.com", "phone": "111", "suburb": "X"}, {"email": "b@x.com", "phone": "222", "suburb": "Y"})
    assert len(out) == 3


def test_14_original_values_preserved():
    from backend.app.services import conflict_detection as cd
    out = cd.detect_field_conflicts({"email": "Rahul@Gmail.com "}, {"email": "rahulkumar@gmail.com"})
    assert out[0]["source_value"] == "Rahul@Gmail.com "
    assert out[0]["target_value"] == "rahulkumar@gmail.com"


def test_15_job_a_not_in_job_b():
    from backend.app.main import app
    with TestClient(app) as c:
        ja, _ = _live_job(c, "jobA")
        jb, _ = _live_job(c, "jobB")
        a = c.get(f"/matches?job_id={ja}&limit=100").json()["items"]
        b = c.get(f"/matches?job_id={jb}&limit=100").json()["items"]
        assert all(x["job"] == str(ja) for x in a)
        assert all(x["job"] == str(jb) for x in b)
        assert {x["id"] for x in a}.isdisjoint({x["id"] for x in b})


def test_16_demo_not_in_live():
    from backend.app.main import app
    with TestClient(app) as c:
        ja, _ = _live_job(c, "demoX")
        body = c.get(f"/jobs/{ja}/results").json()
        assert body["mode"] == "live"
        assert body["records_processed"] != 3247


def test_17_conflict_job_isolation():
    from backend.app.main import app
    with TestClient(app) as c:
        ja, _ = _live_job(c, "isoA")
        jb, _ = _live_job(c, "isoB")
        a = c.get(f"/conflicts?job_id={ja}&limit=100").json()
        b = c.get(f"/conflicts?job_id={jb}&limit=100").json()
        assert {x["id"] for x in a}.isdisjoint({x["id"] for x in b})


def test_18_conflicts_list_real():
    from backend.app.main import app
    with TestClient(app) as c:
        r = c.get("/conflicts?limit=2")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


def test_19_conflict_detail_correct():
    from backend.app.main import app
    with TestClient(app) as c:
        lst = c.get("/conflicts?limit=1").json()
        if lst:
            d = c.get(f"/conflicts/{lst[0]['id']}").json()
            assert d["id"] == lst[0]["id"]
            assert "source_record" in d and "target_record" in d


def test_20_invalid_conflict_404():
    from backend.app.main import app
    with TestClient(app) as c:
        assert c.get("/conflicts/99999999").status_code == 404


def test_21_matching_api_contract():
    from backend.app.main import app
    with TestClient(app) as c:
        r = c.get("/matches?limit=2").json()
        for m in r.get("items", []):
            assert "decision" in m and "evidence" in m


def test_22_match_detail_contract():
    from backend.app.main import app
    with TestClient(app) as c:
        lst = c.get("/matches?limit=1").json().get("items", [])
        if lst:
            d = c.get(f"/matches/{lst[0]['id']}").json()
            assert d["record_a"] and d["target_record" if "target_record" in d else "record_b"]


def test_23_no_hardcoded_live_metrics():
    from backend.app.main import app
    with TestClient(app) as c:
        body = c.get("/matches?limit=5").json()
        assert body["total"] != 892


def test_24_conflicts_field_level():
    from backend.app.main import app
    with TestClient(app) as c:
        lst = c.get("/conflicts?limit=20").json()
        assert all(len(x.get("conflicting_fields", [])) == 1 for x in lst)
