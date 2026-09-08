"""Decision engine (Phase 4.5) — separates model score, confidence, decision,
risk, auto-resolvability and verification state. Deterministic. Penalties were
sanity-checked on FEBRL validation (see docs/model-validation.md); the engine
is deliberately conservative: contradictions cap or cut confidence, and nothing
can reach 1.0 (hard cap 0.99)."""
from typing import Any, Dict

from backend.app.services import evidence_engine as _ee

CONFIDENCE_CAP = 0.99
CONFIDENCE_FLOOR = 0.01
EMAIL_PENALTY = 0.25
PHONE_PENALTY = 0.15
OTHER_MISMATCH_PENALTY = 0.05
OTHER_MISMATCH_MAX = 0.15
MISSING_PENALTY = 0.05
MISSING_MAX = 0.15
KEY_FIELDS = ("email", "phone", "name")


def decide_pair(a: Dict[str, Any], b: Dict[str, Any], model_score: float,
                match_threshold: float = 0.6, possible_threshold: float = 0.5) -> Dict[str, Any]:
    evidence = _ee.build_evidence(a, b)
    summ = _ee.summarize(evidence)
    by_field = {f["field"]: f for f in evidence["fields"]}

    penalties: Dict[str, float] = {}
    critical = summ["critical_conflict"]
    trusted = by_field.get("trusted_id", {})
    if trusted.get("status") == "MISMATCH":
        veto = True
    else:
        veto = False
    for f in evidence["fields"]:
        if f["status"] != "MISMATCH":
            continue
        if f["field"] == "email":
            penalties["email_conflict"] = EMAIL_PENALTY
        elif f["field"] == "phone":
            penalties["phone_conflict"] = PHONE_PENALTY
    other = sum(OTHER_MISMATCH_PENALTY for f in evidence["fields"]
                if f["status"] == "MISMATCH" and f["field"] not in ("email", "phone", "trusted_id"))
    if other:
        penalties["other_mismatches"] = round(min(other, OTHER_MISMATCH_MAX), 4)
    # Asymmetric absence (one side has it) is a risk signal; both sides lacking a
    # field is neutral (spec: missing == missing is not evidence either way).
    missing_key = [f["field"] for f in evidence["fields"]
                   if f["field"] in KEY_FIELDS and f["status"] in ("MISSING_A", "MISSING_B")]
    if missing_key:
        penalties["missing_key_fields"] = round(min(len(missing_key) * MISSING_PENALTY, MISSING_MAX), 4)

    if veto:
        final = min(model_score, 0.49)
        penalties["trusted_id_veto"] = "capped at 0.49"
    else:
        final = model_score - sum(v for v in penalties.values() if isinstance(v, float))
    final = round(max(CONFIDENCE_FLOOR, min(CONFIDENCE_CAP, final)), 4)

    if final >= match_threshold and not critical and not veto:
        decision = "MATCH"
    elif final >= possible_threshold and not veto:
        decision = "POSSIBLE_MATCH"
    else:
        decision = "NO_MATCH"

    n_neg = len(summ["negative"])
    strong_base = (trusted.get("status") == "EXACT_MATCH"
                   or (by_field.get("email", {}).get("status") == "EXACT_MATCH"
                       and by_field.get("phone", {}).get("status") == "EXACT_MATCH"))
    if trusted.get("status") == "MISMATCH":
        risk, risk_why = "CRITICAL", "trusted identifier conflicts — likely different entities"
    elif decision == "MATCH" and n_neg > 0:
        risk, risk_why = "HIGH", f"match with {n_neg} conflicting field(s)"
    elif any(f["field"] in ("email", "phone") and f["status"] == "MISMATCH" for f in evidence["fields"]):
        risk, risk_why = "HIGH", "email/phone conflict"
    elif decision == "POSSIBLE_MATCH" or missing_key:
        risk, risk_why = "MEDIUM", "ambiguous evidence or missing key fields"
    elif decision == "MATCH" and not strong_base:
        risk, risk_why = "MEDIUM", "thin evidence — no trusted identifier or email+phone agreement"
    elif decision == "MATCH":
        risk, risk_why = "LOW", "strong agreement, no contradictions, nothing material missing"
    else:
        risk, risk_why = "MEDIUM", "insufficient evidence"

    neg_set = set(summ["negative"])
    miss_set = set(summ["missing"])
    auto = (decision == "MATCH" and not neg_set
            and not (miss_set & {"email", "phone", "name"})
            and strong_base)
    if auto:
        recommendation = "SAFE TO RESOLVE"
    elif decision == "POSSIBLE_MATCH" or (decision == "MATCH" and not auto):
        recommendation = "MANUAL REVIEW"
    else:
        recommendation = "DO NOT MERGE"

    field_scores = {f["field"]: f["similarity"] for f in evidence["fields"]
                    if f["status"] not in ("BOTH_MISSING",)}
    return {"model_score": round(model_score, 4), "final_confidence": final, "decision": decision,
            "risk": risk, "risk_reason": risk_why, "auto_resolvable": auto, "recommendation": recommendation,
            "penalties": penalties, "field_evidence": evidence, "field_scores": field_scores,
            "verification_status": "NEEDS_REVIEW"}
