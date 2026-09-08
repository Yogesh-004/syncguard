"""Phase 2.1 correction tests — traceability, field-level, isolation, no-recompute."""
import pathlib
import uuid

import pytest
from fastapi.testclient import TestClient


def _live_job(client, tag, rows=None):
    rows = rows or (
        "rec_id,given_name,surname,email,phone,postcode\n"
        f"{tag}-1,Xaviera,Plumb,xaviera.plumb@a.com,9203001,7000\n"
        f"{tag}-2,Xaviera,Plumb,xaviera.plumb@b.com,9203001,7000\n"
    )
    up = client.post("/uploads", files={"file": (f"{tag}.csv", rows.encode(), "text/csv")})
    assert up.status_code == 201
    sid = up.json()["source_id"]
    key = f"p21-{tag}-{uuid.uuid4().hex[:8]}"
    r = client.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key})
    assert r.status_code == 202
    return r.json()["job_id"], sid


def test_integrity_one_match_multiple_conflicts():
    from backend.app.main import app
    with TestClient(app) as c:
        jid, _ = _live_job(c, "integ")
        matches = c.get(f"/matches?job_id={jid}&limit=50").json()["items"]
        assert matches, "expected persisted matches"
        m = matches[0]
        confs = c.get(f"/conflicts?job_id={jid}&limit=100").json()
        mine = [x for x in confs if x["match_id"] == m["id"]]
        assert mine, "expected conflicts linked to match"
        assert all(x["match_id"] == m["id"] for x in mine)
        assert len({x["conflicting_fields"][0]["field_name"] for x in mine}) == len(mine)


def test_traceability_chain():
    from backend.app.main import app
    with TestClient(app) as c:
        jid, _ = _live_job(c, "trace")
        confs = c.get(f"/conflicts?job_id={jid}&limit=50").json()
        assert confs
        d = c.get(f"/conflicts/{confs[0]['id']}").json()
        assert d["match_id"] is not None
        assert d["job_id"] == jid
        assert d["source_record"] and d["target_record"]
        assert d["model_version"] == "1.0.0"
        m = c.get(f"/matches/{d['match_id']}").json()
        assert m["job_id"] == jid


def test_job_isolation_matches_and_conflicts():
    from backend.app.main import app
    with TestClient(app) as c:
        ja, _ = _live_job(c, "isoA21")
        jb, _ = _live_job(c, "isoB21")
        ma = {x["id"] for x in c.get(f"/matches?job_id={ja}&limit=100").json()["items"]}
        mb = {x["id"] for x in c.get(f"/matches?job_id={jb}&limit=100").json()["items"]}
        assert ma and mb and ma.isdisjoint(mb)
        ca = {x["id"] for x in c.get(f"/conflicts?job_id={ja}&limit=100").json()}
        cb = {x["id"] for x in c.get(f"/conflicts?job_id={jb}&limit=100").json()}
        assert ca.isdisjoint(cb)


def test_no_recompute_frontend():
    root = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "src" / "pages"
    matching = (root / "Matching.tsx").read_text(encoding="utf-8")
    conflicts = (root / "Conflicts.tsx").read_text(encoding="utf-8")
    assert "/match?" not in matching
    assert "matching/run" not in matching
    assert "/match?" not in conflicts
    assert "matching/run" not in conflicts


def test_thresholds_centralized():
    import re
    root = pathlib.Path(__file__).resolve().parents[3] / "backend" / "app"
    offenders = []
    for p in list((root / "api").glob("*.py")) + list((root / "services").glob("*.py")) + list((root / "workers").glob("*.py")):
        text = p.read_text()
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"threshold\s*=\s*0\.[567]", line) and "settings" not in line and "rule.threshold" not in line and "fuzzy" not in line.lower():
                offenders.append(f"{p.name}:{i}:{line.strip()}")
    assert offenders == [], f"hardcoded decision thresholds remain: {offenders}"


def test_new_conflicts_have_match_id():
    from backend.app.main import app
    with TestClient(app) as c:
        jid, _ = _live_job(c, "midcheck")
        confs = c.get(f"/conflicts?job_id={jid}&limit=50").json()
        assert confs
        assert all(x["match_id"] is not None for x in confs)
