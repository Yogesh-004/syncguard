"""Truth-audit regression — controlled A–F dataset with ground truth (Part 2/15)."""
import pathlib

import pandas as pd

from backend.app.services import model_service as ms
from backend.app.services import decision_engine as de

CSV = pathlib.Path(__file__).resolve().parents[3] / "data" / "live_test" / "truth_audit.csv"


def _rec(row, side):
    s = "a" if side == "a" else "b"
    d = {"name": row[f"name_{s}"] or None, "email": row[f"email_{s}"] or None, "phone": row[f"phone_{s}"] or None,
         "postcode": row[f"postcode_{s}"],
         "address": {"city": row[f"suburb_{s}"] or None, "postcode": row[f"postcode_{s}"]},
         "external_id": row[f"ext_{s}"] or None}
    return {k: v for k, v in d.items() if v is not None}


def _row(pid):
    df = pd.read_csv(CSV, dtype=str).fillna("")
    return df[df["pair_id"] == pid].iloc[0]


def _verdict(pid):
    r = _row(pid)
    a, b = _rec(r, "a"), _rec(r, "b")
    feats = ms.featurize(a, b)
    prob = float(ms.load_model().predict_proba([feats])[0][1])
    return de.decide_pair(a, b, prob)


def test_hard_positive_auto():
    assert _verdict("T01")["auto_resolvable"] is True


def test_noisy_positives_auto():
    for pid in ("T02", "T03", "T04", "T05"):
        v = _verdict(pid)
        assert v["decision"] == "MATCH" and v["auto_resolvable"] is True, pid


def test_hard_positive_manual():
    v = _verdict("T06")
    assert v["decision"] == "POSSIBLE_MATCH" and v["auto_resolvable"] is False


def test_easy_negative():
    assert _verdict("T07")["decision"] == "NO_MATCH"


def test_hard_negatives_never_auto():
    for pid in ("T08", "T09", "T10"):
        assert _verdict(pid)["auto_resolvable"] is False, pid


def test_contradiction_email_manual():
    v = _verdict("T11")
    assert v["decision"] == "POSSIBLE_MATCH" and v["risk"] == "HIGH" and v["auto_resolvable"] is False


def test_contradiction_trusted_id_veto():
    v = _verdict("T12")
    assert v["decision"] == "NO_MATCH" and v["risk"] == "CRITICAL" and v["auto_resolvable"] is False


def test_missing_never_positive():
    v = _verdict("T04")
    for f in v["field_evidence"]["fields"]:
        if f["status"] in ("MISSING_A", "MISSING_B", "BOTH_MISSING"):
            assert f["similarity"] == 0.0


def test_low_info_not_auto():
    v = _verdict("T09")
    assert v["decision"] == "NO_MATCH" and v["auto_resolvable"] is False


def test_score_distribution_persisted_shape():
    v = _verdict("T01")
    assert 0.01 <= v["final_confidence"] <= 0.99
    assert 0.0 <= v["model_score"] <= 1.0
