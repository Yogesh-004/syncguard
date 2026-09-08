"""Field-level conflict detection (Phase 2) — separate from matching.

Matching answers "same entity?". This answers "where do values disagree?".
One row per field. Original values preserved. Normalization-aware.
"""
from typing import Any, Dict, List, Optional, Tuple

from backend.app.services import normalization as nz

IGNORE_FIELDS = {"id", "entity_id", "rec_id", "customer_id", "source_id", "source_record_id", "rec_a", "rec_b", "_id"}

FIELD_KIND = {
    "name": "name", "given_name": "name", "surname": "name", "title": "name",
    "email": "email",
    "phone": "phone", "soc_sec_id": "identifier", "external_id": "identifier",
    "date_of_birth": "date", "date": "date",
    "amount": "numeric", "transaction_amount": "numeric", "price": "numeric", "total": "numeric", "value": "numeric",
    "address": "address", "address_1": "address", "address_2": "address", "suburb": "address", "city": "address",
    "street_number": "address", "postcode": "identifier", "zip": "identifier", "state": "address",
}


def _kind(field: str) -> str:
    return FIELD_KIND.get(field, "text")


def _norm(kind: str, v: Any) -> Any:
    if v is None:
        return None
    try:
        if kind == "name":
            return nz.normalize_name(str(v))
        if kind == "email":
            return nz.normalize_email(str(v))
        if kind == "phone":
            return nz.normalize_phone(str(v))
        if kind == "date":
            return nz.normalize_date(v)
        if kind == "numeric":
            return nz.normalize_numeric(v)
        if kind == "address":
            return nz.normalize_address(v) if isinstance(v, dict) else nz.normalize_name(str(v))
        if kind == "identifier":
            return nz.normalize_identifier(str(v))
        if isinstance(v, str):
            return v.strip()
        return v
    except Exception:
        return v


def compare_field(field: str, va: Any, vb: Any) -> Tuple[str, Any, Any]:
    """Returns (outcome, norm_a, norm_b). Outcome in NO_CONFLICT, VALUE_CONFLICT, MISSING_VALUE, BOTH_EMPTY, NORMALIZED_EQUAL."""
    ea = va is None or (isinstance(va, str) and not va.strip())
    eb = vb is None or (isinstance(vb, str) and not vb.strip())
    if ea and eb:
        return "BOTH_EMPTY", None, None
    if ea or eb:
        return "MISSING_VALUE", _norm(_kind(field), va), _norm(_kind(field), vb)
    na = _norm(_kind(field), va)
    nb = _norm(_kind(field), vb)
    if na == nb:
        # distinguish raw-identical vs normalized-equal for evidence
        if va == vb:
            return "NO_CONFLICT", na, nb
        return "NORMALIZED_EQUAL", na, nb
    return "VALUE_CONFLICT", na, nb


def detect_field_conflicts(data_a: Dict[str, Any], data_b: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One dict per conflicting field with original values preserved."""
    out: List[Dict[str, Any]] = []
    for field in sorted(set(list(data_a.keys()) + list(data_b.keys()))):
        if field in IGNORE_FIELDS or field.startswith("_") or field.startswith("?"):
            continue
        va = data_a.get(field)
        vb = data_b.get(field)
        outcome, na, nb = compare_field(field, va, vb)
        if outcome in ("NO_CONFLICT", "NORMALIZED_EQUAL", "BOTH_EMPTY"):
            continue
        out.append({
            "field_name": field,
            "conflict_type": "missing" if outcome == "MISSING_VALUE" else "mismatch",
            "outcome": outcome,
            "source_value": va,
            "target_value": vb,
            "norm_a": na if not isinstance(na, dict) else na,
            "norm_b": nb if not isinstance(nb, dict) else nb,
            "values": {"a": va, "b": vb},
            "sources": ["a", "b"],
        })
    return out


def recommend(source_value: Any, target_value: Any) -> Tuple[str, str]:
    """Conservative: never invent reliability scores. Prefer complete value, else REVIEW REQUIRED."""
    sa = source_value is not None and str(source_value).strip() != ""
    sb = target_value is not None and str(target_value).strip() != ""
    if sa and not sb:
        return "SOURCE", "source has value, target missing"
    if sb and not sa:
        return "TARGET", "target has value, source missing"
    return "REVIEW REQUIRED", "both sides populated — human review required (no source-reliability scores configured)"


def classify_risk(field_name: str, outcome: str, match_confidence: float, total_conflicts: int) -> Tuple[str, str]:
    """Explainable rules (see docs/conflict-rules.md)."""
    critical = {"email", "phone", "external_id", "soc_sec_id"}
    if field_name in critical and outcome == "VALUE_CONFLICT":
        return "HIGH", f"{field_name} is an identifier and values differ"
    if total_conflicts >= 3:
        return "HIGH", f"{total_conflicts} fields conflict on same entity"
    if outcome == "MISSING_VALUE":
        return "MEDIUM", f"{field_name} missing on one side"
    if match_confidence >= 0.9:
        return "LOW", "high-confidence match with non-critical disagreement"
    return "MEDIUM", "default: non-critical value conflict"
