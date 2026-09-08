"""Field-level evidence engine (Phase 4.5) — deterministic, independent of ML score.

Every candidate pair gets per-field evidence with normalized values, similarity,
comparison type and status. Missing values are NEVER positive evidence.
"""
from typing import Any, Dict, List, Optional, Tuple

from rapidfuzz import fuzz as _fuzz

from backend.app.services import normalization as nz

TRUSTED_ID_FIELDS = ("customer_id", "external_id", "soc_sec_id")
# NOTE: rec_id/id/entity_id are row labels and DB surrogate keys, NOT identity
# evidence. Comparing them once vetoed every pair (rec_ids always differ).
# They are excluded from evidence entirely (also in conflict IGNORE_FIELDS).


def _is_empty(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _norm_id(v: Any) -> str:
    return nz.normalize_identifier(str(v))


def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return round(_fuzz.ratio(a, b) / 100, 4)


def _status(similarity: float, exact: bool) -> str:
    if exact:
        return "EXACT_MATCH"
    if similarity >= 0.9:
        return "STRONG_MATCH"
    if similarity >= 0.7:
        return "PARTIAL_MATCH"
    return "MISMATCH"


def _field(name: str, va: Any, vb: Any, na: Any, nb: Any, similarity: float,
           ctype: str, trusted: bool = False) -> Dict[str, Any]:
    if _is_empty(va) and _is_empty(vb):
        status = "BOTH_MISSING"
    elif _is_empty(va):
        status = "MISSING_A"
    elif _is_empty(vb):
        status = "MISSING_B"
    else:
        status = _status(similarity, bool(na == nb and na not in ("", None)))
    return {"field": name, "source_a_value": va, "source_b_value": vb,
            "normalized_a": na, "normalized_b": nb, "similarity": similarity,
            "comparison_type": ctype, "status": status, "trusted_identifier": trusted}


def build_evidence(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic per-field evidence for a candidate pair."""
    fields: List[Dict[str, Any]] = []

    trusted_a = {f: _norm_id(a.get(f)) for f in TRUSTED_ID_FIELDS if not _is_empty(a.get(f))}
    trusted_b = {f: _norm_id(b.get(f)) for f in TRUSTED_ID_FIELDS if not _is_empty(b.get(f))}
    common_trusted = [f for f in trusted_a if f in trusted_b]
    if common_trusted:
        # Trusted identifiers are binary: exact agree or MISMATCH. Fuzzy
        # near-misses (e.g. CUST-9051 vs CUST-9151, sim 0.875) must NEVER read
        # as PARTIAL_MATCH — that once veto-bypassed into MATCH+LOW+auto.
        agree = all(trusted_a[f] == trusted_b[f] for f in common_trusted)
        sim = 1.0 if agree else 0.0
        fields.append(_field("trusted_id",
                             {f: a.get(f) for f in common_trusted}, {f: b.get(f) for f in common_trusted},
                             trusted_a, trusted_b, sim, "exact_identifier", trusted=True))
        if not agree:
            fields[-1]["status"] = "MISMATCH"
    elif trusted_a or trusted_b:
        fields.append(_field("trusted_id", trusted_a or None, trusted_b or None, trusted_a or None, trusted_b or None,
                             0.0, "exact_identifier", trusted=True))

    na = nz.normalize_name(str(a.get("name") or a.get("given_name") or ""))
    nb = nz.normalize_name(str(b.get("name") or b.get("given_name") or ""))
    toks_a, toks_b = sorted(na.split()), sorted(nb.split())
    name_sim = max(_sim(na, nb), _sim(" ".join(toks_a), " ".join(toks_b))) if na and nb else 0.0
    fields.append(_field("name", a.get("name") or a.get("given_name"), b.get("name") or b.get("given_name"),
                         na or None, nb or None, name_sim, "token_order_insensitive_fuzzy"))

    ea, eb = nz.normalize_email(str(a.get("email") or "")), nz.normalize_email(str(b.get("email") or ""))
    eva, evb = a.get("email"), b.get("email")
    fields.append(_field("email", eva, evb, ea or None, eb or None,
                         1.0 if (ea and ea == eb) else 0.0, "normalized_exact"))

    pa, pb = nz.normalize_phone(str(a.get("phone") or "")), nz.normalize_phone(str(b.get("phone") or ""))
    pva, pvb = a.get("phone"), b.get("phone")
    fields.append(_field("phone", pva, pvb, pa or None, pb or None,
                         1.0 if (pa and pa == pb) else _sim(pa, pb), "normalized_e164"))

    addr_a, addr_b = a.get("address"), b.get("address")
    if isinstance(addr_a, dict) or isinstance(addr_b, dict):
        da = addr_a if isinstance(addr_a, dict) else {}
        db = addr_b if isinstance(addr_b, dict) else {}
        for comp in ("street", "city", "state", "postcode"):
            va, vb = da.get(comp), db.get(comp)
            na_c = nz.normalize_name(str(va)) if va else None
            nb_c = nz.normalize_name(str(vb)) if vb else None
            sim = 1.0 if (na_c and na_c == nb_c) else _sim(na_c or "", nb_c or "")
            fields.append(_field(f"address.{comp}", va, vb, na_c, nb_c, sim, "normalized_component"))
    else:
        sa, sb = nz.normalize_name(str(addr_a or "")), nz.normalize_name(str(addr_b or ""))
        fields.append(_field("address", addr_a, addr_b, sa or None, sb or None,
                             1.0 if (sa and sa == sb) else _sim(sa, sb), "normalized_full"))

    if a.get("date_of_birth") is not None or b.get("date_of_birth") is not None:
        va, vb = a.get("date_of_birth"), b.get("date_of_birth")
        na_d, nb_d = nz.normalize_date(va), nz.normalize_date(vb)
        fields.append(_field("date_of_birth", va, vb, na_d, nb_d,
                             1.0 if (na_d and na_d == nb_d) else 0.0, "canonical_date"))

    for num in ("amount", "transaction_amount", "price", "total"):
        if a.get(num) is not None or b.get(num) is not None:
            va, vb = a.get(num), b.get(num)
            na_n, nb_n = nz.normalize_numeric(va), nz.normalize_numeric(vb)
            sim = 1.0 if (na_n is not None and na_n == nb_n) else 0.0
            fields.append(_field(num, va, vb, na_n, nb_n, sim, "numeric_tolerance"))
            break

    return {"fields": fields}


def summarize(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate positive/negative signals (no averaging away contradictions)."""
    pos, neg, missing = [], [], []
    critical_conflict = False
    for f in evidence.get("fields", []):
        st = f["status"]
        if st in ("EXACT_MATCH", "STRONG_MATCH"):
            pos.append(f["field"])
        elif st == "MISMATCH":
            neg.append(f["field"])
            if f.get("trusted_identifier") or f["field"] in ("email", "phone"):
                critical_conflict = True
        elif st in ("MISSING_A", "MISSING_B"):
            missing.append(f["field"])
    return {"positive": pos, "negative": neg, "missing": missing, "critical_conflict": critical_conflict}
