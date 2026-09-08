"""Multi-pass candidate generation (Phase 4.6) — shared by benchmark and live.

Passes are INDEPENDENT; results are UNIONED and deduplicated. A pair qualifying
for ONE pass reaches the matcher. Blocking is not matching: it only means
"this pair deserves evaluation". Guardrails refuse silent truncation.
"""
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.app.core.logging import logger
from backend.app.services import normalization as nz

MAX_BLOCK_SIZE = 500
MAX_CANDIDATES = 500000


def _get(d: Dict[str, Any], *names: str) -> Optional[str]:
    for n in names:
        v = d.get(n)
        if v is None and isinstance(d.get("metadata"), dict):
            v = d["metadata"].get(n)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def postcode_key(d: Dict[str, Any]) -> Optional[str]:
    v = _get(d, "postcode", "zip", "zipcode", "pincode")
    if v is None:
        return None
    digits = "".join(c for c in v if c.isdigit())
    return digits or None


def name_key(d: Dict[str, Any]) -> Optional[str]:
    raw = _get(d, "surname", "last_name") or ""
    if not raw:
        full = _get(d, "name", "given_name") or ""
        toks = nz.normalize_name(full).split()
        raw = toks[-1] if toks else ""
    norm = nz.normalize_identifier(raw)
    return norm[:4] if len(norm) >= 2 else None


def phone_key(d: Dict[str, Any]) -> Optional[str]:
    raw = _get(d, "phone", "soc_sec_id", "external_id")
    if raw is None:
        return None
    digits = "".join(c for c in str(raw) if c.isdigit())
    if len(digits) < 7:
        return None
    return digits[-7:]


def email_key(d: Dict[str, Any]) -> Optional[str]:
    raw = _get(d, "email")
    if raw is None:
        return None
    norm = nz.normalize_email(raw)
    if "@" not in norm:
        return None
    local, _, domain = norm.partition("@")
    if not local or not domain:
        return None
    return f"{local}@{domain}"


def address_key(d: Dict[str, Any]) -> Optional[str]:
    addr = d.get("address")
    city = None
    if isinstance(addr, dict):
        city = addr.get("city") or addr.get("suburb")
    city = city or _get(d, "suburb", "city")
    if city is None:
        return None
    norm = nz.normalize_identifier(str(city))
    return norm[:5] if len(norm) >= 3 else None


PASSES = {
    "postcode": postcode_key,
    "name": name_key,
    "phone": phone_key,
    "email": email_key,
    "address": address_key,
}


def generate_candidates(records: List[Dict[str, Any]], passes: Optional[List[str]] = None,
                        max_block_size: int = MAX_BLOCK_SIZE,
                        max_candidates: int = MAX_CANDIDATES) -> Dict[str, Any]:
    """Returns {candidates: set[(i,j)], provenance: {(i,j): [passes]}, stats: per-pass info}."""
    passes = passes or ["postcode"]
    unknown = [p for p in passes if p not in PASSES]
    if unknown:
        raise ValueError(f"Unknown blocking passes: {unknown}")
    ids = list(range(len(records)))
    union: Set[Tuple[int, int]] = set()
    provenance: Dict[Tuple[int, int], List[str]] = {}
    stats: Dict[str, Any] = {}
    for name in passes:
        buckets: Dict[str, List[int]] = defaultdict(list)
        for i in ids:
            try:
                key = PASSES[name](records[i])
            except Exception:
                key = None
            if key:
                buckets[key].append(i)
        sizes = [len(v) for v in buckets.values()]
        big = [(k, len(v)) for k, v in buckets.items() if len(v) > max_block_size]
        if big:
            raise RuntimeError(f"Blocking pass '{name}' produced oversized block(s) {big[:3]} — refusing silent truncation")
        n_pairs = sum(len(v) * (len(v) - 1) // 2 for v in buckets.values())
        for v in buckets.values():
            s = sorted(v)
            for x in range(len(s)):
                for y in range(x + 1, len(s)):
                    pair = (s[x], s[y])
                    union.add(pair)
                    provenance.setdefault(pair, []).append(name)
        stats[name] = {"blocks": len(buckets),
                       "avg_block_size": round(sum(sizes) / len(sizes), 2) if sizes else 0,
                       "largest_block": max(sizes) if sizes else 0,
                       "pairs": n_pairs}
        if len(union) > max_candidates:
            raise RuntimeError(f"Candidate union {len(union)} exceeds MAX_CANDIDATES={max_candidates} — refusing silent truncation")
    logger.info("Candidates generated", passes=passes, candidates=len(union))
    return {"candidates": union, "provenance": provenance, "stats": stats}
