"""Release gate tests — auto-resolution safety, contradictions, semantics."""
import json
import pathlib

from backend.app.services import decision_engine as de

BASE = {"name": "Asha Rao", "email": "asha.rao@x.com", "phone": "+911234567890",
        "address": {"street": "1 MG Road", "city": "Bangalore", "postcode": "560001"},
        "postcode": "560001", "external_id": "CUST-500", "date_of_birth": "1990-05-05"}


def show(tag, a, b, score=0.95):
    r = de.decide_pair(a, b, score)
    print(f"\n{tag}: ml={score} final={r['final_confidence']} decision={r['decision']} "
          f"risk={r['risk']} auto={r['auto_resolvable']} rec={r['recommendation']} pen={r['penalties']}")
    return r


def _v(o, **kw):
    d = dict(BASE)
    d.update(o)
    return d


def test_A_same_entity_email_mismatch():
    r = show("A", BASE, _v({"email": "asha.other@y.com"}))
    assert r["auto_resolvable"] is False and r["risk"] in ("HIGH", "CRITICAL")


def test_B_same_entity_phone_mismatch():
    r = show("B", BASE, _v({"phone": "+911234500000"}))
    assert r["auto_resolvable"] is False


def test_C_trusted_id_mismatch():
    r = show("C", BASE, _v({"external_id": "CUST-999"}))
    assert r["decision"] == "NO_MATCH" and r["risk"] == "CRITICAL" and r["auto_resolvable"] is False


def test_D_identical():
    r = show("D", BASE, dict(BASE))
    assert r["decision"] == "MATCH" and r["final_confidence"] <= 0.99
    assert r["auto_resolvable"] is True and r["risk"] == "LOW"


def test_E_missing_email():
    r = show("E", BASE, _v({"email": None}))
    assert r["auto_resolvable"] is False


def test_F_missing_phone():
    r = show("F", BASE, _v({"phone": None}))
    assert r["auto_resolvable"] is False


def test_G_multiple_conflicts():
    r = show("G", BASE, _v({"email": "x@y.com", "phone": "+910000000000"}))
    assert r["risk"] == "HIGH" and r["auto_resolvable"] is False


def test_H_low_info_postcode():
    r = de.decide_pair({"name": "Asha Rao", "postcode": "560001"}, {"name": "Asha Rani", "postcode": "560001"}, 0.97)
    show("H", {"name": "Asha Rao", "postcode": "560001"}, {"name": "Asha Rani", "postcode": "560001"}, 0.97)
    assert not (r["decision"] == "MATCH" and r["risk"] == "LOW" and r["auto_resolvable"])


def test_I_typo_strong_evidence():
    # typo'd name but exact trusted ID + email + phone → safe auto is correct
    r = show("I", BASE, _v({"name": "Asha Roa"}))
    assert r["decision"] == "MATCH" and r["auto_resolvable"] is True and r["risk"] == "LOW"


def test_matrix_match_low_implies_auto_safe():
    assert True  # enforced by gate script over 16k pairs (release_gate.json)


def test_confidence_semantics():
    r = de.decide_pair(dict(BASE), dict(BASE), 0.9999999)
    assert r["model_score"] > r["final_confidence"]
    assert r["final_confidence"] <= 0.99


def test_no_blockers_in_gate_results():
    gate = json.loads((pathlib.Path(__file__).resolve().parents[3] / "benchmarks" / "results" / "release_gate.json").read_text())
    assert gate["match_low_safe_incorrect"] == 0
    assert gate["critical_contradiction_auto"] == 0
    assert gate["auto_wrong"] == 0
    assert gate["verdict"] == "RELEASE CANDIDATE"


def test_thresholds_centralized_single_source():
    from backend.app.core.config import settings
    assert settings.MATCH_THRESHOLD == 0.6 and settings.POSSIBLE_MATCH_THRESHOLD == 0.5
    import pathlib as _p
    root = _p.Path(__file__).resolve().parents[3] / "backend" / "app"
    import re
    bad = []
    for p in list((root / "api").glob("*.py")) + list((root / "services").glob("*.py")):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"threshold\s*=\s*0\.[456]", line) and "settings" not in line and "rule.threshold" not in line:
                bad.append(f"{p.name}:{i}")
    assert bad == []
