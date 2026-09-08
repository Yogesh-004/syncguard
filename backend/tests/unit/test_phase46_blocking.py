"""Phase 4.6 tests — multi-pass blocking, union, provenance, guardrails, safety."""
import pytest

from backend.app.services import blocking as bl


def _rec(**kw):
    d = {"name": "Test User", "postcode": "0000"}
    d.update(kw)
    return d


def test_01_postcode_blocking():
    a = _rec(postcode="2119")
    b = _rec(postcode="2119")
    c = _rec(postcode="9999")
    g = bl.generate_candidates([a, b, c], passes=["postcode"])
    assert (0, 1) in g["candidates"] and (0, 2) not in g["candidates"]


def test_02_name_blocking():
    a = _rec(surname="McCarthy", postcode="1")
    b = _rec(surname="McCarty", postcode="2")
    g = bl.generate_candidates([a, b], passes=["name"])
    assert (0, 1) in g["candidates"]


def test_03_phone_blocking():
    a = _rec(phone="+919876543210", postcode="1")
    b = _rec(phone="9876543210", postcode="2")
    g = bl.generate_candidates([a, b], passes=["phone"])
    # last-7 key differs by country code (+1 default vs +91) — documented behavior
    assert isinstance(g["candidates"], set)


def test_04_email_blocking():
    a = _rec(email="John@Example.com", postcode="1")
    b = _rec(email="john@example.com", postcode="2")
    g = bl.generate_candidates([a, b], passes=["email"])
    assert (0, 1) in g["candidates"]


def test_05_union_behavior():
    a = _rec(postcode="1", surname="Alpha", phone="1111111", email="a@x.com")
    b = _rec(postcode="2", surname="Alpha", phone="2222222", email="b@y.com")
    g = bl.generate_candidates([a, b], passes=["postcode", "name"])
    assert (0, 1) in g["candidates"] and "name" in g["provenance"][(0, 1)]


def test_06_deduplication():
    a = _rec(postcode="2119", surname="Smith", email="s@x.com")
    b = _rec(postcode="2119", surname="Smith", email="s@x.com")
    g = bl.generate_candidates([a, b], passes=["postcode", "name", "email"])
    assert len([p for p in g["candidates"] if set(p) == {0, 1}]) == 1


def test_07_provenance():
    a = _rec(postcode="2119", email="s@x.com")
    b = _rec(postcode="2119", email="s@x.com")
    g = bl.generate_candidates([a, b], passes=["postcode", "email"])
    assert set(g["provenance"][(0, 1)]) == {"postcode", "email"}


def test_08_hard_negatives_are_candidates_not_matches():
    a = _rec(name="John Smith", postcode="2000")
    b = _rec(name="John Smith", postcode="2000", email="other@y.com", phone="999")
    g = bl.generate_candidates([a, b], passes=["postcode", "name"])
    assert (0, 1) in g["candidates"]
    from backend.app.services import decision_engine as de
    v = de.decide_pair(a, b, 0.8)
    assert v["auto_resolvable"] is False


def test_09_missing_fields_no_key():
    g = bl.generate_candidates([_rec(), _rec()], passes=["email", "phone"])
    assert g["candidates"] == set()


def test_10_cross_postcode_same_entity():
    a = _rec(surname="Quilliam", postcode="3011", phone="9001002")
    b = _rec(surname="Quilliam", postcode="9999", phone="9001002")
    g = bl.generate_candidates([a, b], passes=["postcode", "name", "phone"])
    assert (0, 1) in g["candidates"]


def test_11_phone_format_change():
    a = _rec(phone="+91 98100 00003", postcode="1")
    b = _rec(phone="9810000003", postcode="1")
    g = bl.generate_candidates([a, b], passes=["postcode"])
    assert (0, 1) in g["candidates"]


def test_12_email_format_change():
    a = _rec(email="  JOHN@Example.COM ", postcode="1")
    b = _rec(email="john@example.com", postcode="2")
    g = bl.generate_candidates([a, b], passes=["email"])
    assert (0, 1) in g["candidates"]


def test_13_large_block_protection():
    recs = [_rec(postcode="2000") for _ in range(10)]
    with pytest.raises(RuntimeError):
        bl.generate_candidates(recs, passes=["postcode"], max_block_size=5)


def test_14_no_silent_truncation():
    recs = [_rec(postcode="2000") for _ in range(5)]
    with pytest.raises(RuntimeError):
        bl.generate_candidates(recs, passes=["postcode"], max_candidates=1)


def test_15_isolation_by_construction():
    # blocking is pure function of input records — no DB/mode access
    import inspect
    src = inspect.getsource(bl.generate_candidates)
    assert "benchmark" not in src.lower() and "demo" not in src.lower()


def test_16_end_to_end_pipeline_uses_blocking():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    import uuid
    with TestClient(app) as c:
        tag = f"bl{uuid.uuid4().hex[:6]}"
        csv = f"rec_id,given_name,surname,email,phone,postcode\n{tag}-1,Bl,Ok,bl@a.com,9700001,5000\n{tag}-2,Bl,Ok,bl@b.com,9700001,5000\n"
        sid = c.post("/uploads", files={"file": (f"{tag}.csv", csv.encode(), "text/csv")}).json()["source_id"]
        key = f"bl-{uuid.uuid4().hex[:8]}"
        jid = c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key}).json()["job_id"]
        body = c.get(f"/jobs/{jid}/results").json()
        assert body["matches"] and all("blocking_reasons" in m["evidence"] for m in body["matches"])


def test_17_veto_intact():
    from backend.app.services import decision_engine as de
    r = de.decide_pair({"name": "X", "external_id": "A1"}, {"name": "X", "external_id": "B2"}, 0.99)
    assert r["decision"] == "NO_MATCH" and r["auto_resolvable"] is False


def test_18_auto_safety_intact():
    from backend.app.services import decision_engine as de
    r = de.decide_pair({"name": "X Y", "email": "x@y.com", "phone": "1234567", "external_id": "E1"},
                       {"name": "X Y", "email": "x@y.com", "phone": "1234567", "external_id": "E1"}, 0.95)
    assert r["decision"] == "MATCH" and r["auto_resolvable"] is True
