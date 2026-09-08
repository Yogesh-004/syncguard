"""Read-only presence semantics (Phase 5C implementation of
`docs/phase5c-presence-semantics-design.md`).

Presence (BOTH_PRESENT / ONLY_IN_A / ONLY_IN_B / UNKNOWN) is derived from
snapshot membership plus a completeness gate. It is INDEPENDENT of identity
matching: this module never imports matching, blocking, normalization,
decision/evidence/conflict engines, resolution, or synchronization, and its
outputs carry no directive field, so no consumer can mistake an observation
for a sync instruction. Absence is scope-relative non-observation, never a
lifecycle claim: lifecycle vocabulary (DELETED/NEW/...) cannot be produced
by any function in this module.
"""
from datetime import datetime
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

BOTH_PRESENT = "BOTH_PRESENT"
ONLY_IN_A = "ONLY_IN_A"
ONLY_IN_B = "ONLY_IN_B"
UNKNOWN = "UNKNOWN"

PRESENCE_STATES = (BOTH_PRESENT, ONLY_IN_A, ONLY_IN_B, UNKNOWN)

COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
FAILED = "FAILED"

COMPLETENESS_VALUES = (COMPLETE, PARTIAL, FAILED)

BOTH_OBSERVED = "BOTH_OBSERVED"
ONLY_A_COMPLETE = "ONLY_A_COMPLETE_SCOPE"
ONLY_B_COMPLETE = "ONLY_B_COMPLETE_SCOPE"
SOURCE_FAILED = "SOURCE_FAILED"
PARTIAL_INGESTION = "PARTIAL_INGESTION"
SCOPE_MISMATCH = "SCOPE_MISMATCH"
RECORD_EXCLUDED = "RECORD_EXCLUDED"
NO_LINK = "NO_LINK"

EXPLANATIONS = {
    BOTH_PRESENT: "Observed in both Snapshot A and Snapshot B within the declared scope.",
    ONLY_IN_A: "Present in Snapshot A; no corresponding record was observed within "
               "Snapshot B's declared scope. This does not mean the entity was deleted.",
    ONLY_IN_B: "Present in Snapshot B; no corresponding record was observed within "
               "Snapshot A's declared scope. This does not mean this is a new customer or new entity.",
    UNKNOWN: "Presence could not be determined. No conclusion should be drawn.",
}

REQUIRED_SCOPE_KEYS = ("source_a", "source_b", "snapshot_a", "snapshot_b")

FORBIDDEN_LIFECYCLE_TOKENS = (
    "DELETED", "REMOVED", "NEW_CUSTOMER", "NEW CUSTOMER", "NEW_ENTITY", "NEW ENTITY",
    "CREATED", "TERMINATED", "CUSTOMER LEFT", "WAS DELETED",
)


def explanation_for(state: str, basis: Optional[str] = None) -> str:
    if state not in PRESENCE_STATES:
        raise ValueError(f"unknown presence state: {state!r}")
    text = EXPLANATIONS[state]
    if state == UNKNOWN and basis:
        text = f"Presence could not be determined: {basis}. No conclusion should be drawn."
    return text


def scan_for_lifecycle_language(text: str) -> List[str]:
    upper = str(text or "").upper()
    return [tok for tok in FORBIDDEN_LIFECYCLE_TOKENS if tok in upper]


def _check_scope(scope: Dict[str, Any]) -> None:
    missing = [k for k in REQUIRED_SCOPE_KEYS if k not in (scope or {})]
    if missing:
        raise ValueError(f"presence observation requires scope keys {missing} (invariant: no scopeless states)")


def _check_completeness(value: str) -> None:
    if value not in COMPLETENESS_VALUES:
        raise ValueError(f"completeness must be one of {COMPLETENESS_VALUES}, got {value!r}")


def derive_record_presence(
    keys_a: Iterable[str],
    keys_b: Iterable[str],
    completeness_a: str = COMPLETE,
    completeness_b: str = COMPLETE,
    out_of_scope_a: FrozenSet[str] = frozenset(),
    out_of_scope_b: FrozenSet[str] = frozenset(),
    excluded: FrozenSet[str] = frozenset(),
) -> Dict[str, Tuple[str, str]]:
    """Derive record-level presence from snapshot membership.

    Returns {record_key: (state, basis)}. Observed membership is positive
    evidence and never gated; ONLY_* absence claims require the opposite
    side to report COMPLETE ingestion, otherwise UNKNOWN. Identity matching
    is neither consulted nor affected.
    """
    _check_completeness(completeness_a)
    _check_completeness(completeness_b)
    set_a, set_b = set(keys_a), set(keys_b)
    result: Dict[str, Tuple[str, str]] = {}
    for key in set_a | set_b:
        if key in excluded:
            result[key] = (UNKNOWN, RECORD_EXCLUDED)
            continue
        in_a, in_b = key in set_a, key in set_b
        if in_a and in_b:
            result[key] = (BOTH_PRESENT, BOTH_OBSERVED)
        elif in_a:
            if completeness_b != COMPLETE:
                result[key] = (UNKNOWN, SOURCE_FAILED if completeness_b == FAILED else PARTIAL_INGESTION)
            elif key in out_of_scope_b:
                result[key] = (UNKNOWN, SCOPE_MISMATCH)
            else:
                result[key] = (ONLY_IN_A, ONLY_A_COMPLETE)
        else:
            if completeness_a != COMPLETE:
                result[key] = (UNKNOWN, SOURCE_FAILED if completeness_a == FAILED else PARTIAL_INGESTION)
            elif key in out_of_scope_a:
                result[key] = (UNKNOWN, SCOPE_MISMATCH)
            else:
                result[key] = (ONLY_IN_B, ONLY_B_COMPLETE)
    return result


def interpret_entity_presence(
    a_members: Iterable[str],
    b_members: Iterable[str],
    record_presence: Dict[str, Tuple[str, str]],
    links: Iterable[Tuple[str, str]] = (),
) -> Tuple[str, str, List[Tuple[str, str]]]:
    """Interpret entity-level presence from record presence plus identity links.

    `links` are caller-asserted cross-side identity links (e.g. MATCH pairs);
    POSSIBLE_MATCH links must NOT be passed (link-uncertainty reads UNKNOWN).
    Entity BOTH_PRESENT requires a cited cross-side link; without one the
    entity reads UNKNOWN (never two-entities-by-default, never ONLY by default:
    entity claims need linking evidence). Returns (state, basis, cited_links).
    """
    set_a, set_b = set(a_members), set(b_members)
    cited = [(a, b) for (a, b) in links if a in set_a and b in set_b]
    if cited:
        return (BOTH_PRESENT, BOTH_OBSERVED, cited)
    states = {record_presence[k][0] for k in (set_a | set_b) if k in record_presence}
    if states == {ONLY_IN_A} or states == {ONLY_IN_B}:
        return (UNKNOWN, NO_LINK, [])
    return (UNKNOWN, NO_LINK, [])


def derive_and_persist(
    db,
    scope: Dict[str, Any],
    keys_a: Iterable[str],
    keys_b: Iterable[str],
    completeness_a: str = COMPLETE,
    completeness_b: str = COMPLETE,
    out_of_scope_a: FrozenSet[str] = frozenset(),
    out_of_scope_b: FrozenSet[str] = frozenset(),
    excluded: FrozenSet[str] = frozenset(),
    job_id: Optional[int] = None,
    snapshot_a_ref: str = "",
    snapshot_b_ref: str = "",
    record_presence: Optional[Dict[str, Tuple[str, str]]] = None,
    key_to_refs: Optional[Dict[str, List[str]]] = None,
    pipeline_version: str = "5c",
) -> List[Dict[str, Any]]:
    """Derive record presence and persist comparison-bound observations.

    Membership is evaluated on caller-supplied keys (source-native record
    identity). By default one observation row is stored per key with the key
    as its ref; pass `key_to_refs` to store one row per internal record ref
    (a shared key observed on both sides then yields one BOTH_PRESENT row per
    side's record). Stores record refs (internal ids) only — never raw PII.
    Emits one audit entry per observation via AuditService
    (action `presence.observed`). Creates no sync jobs, no directives,
    no lifecycle claims.
    """
    from backend.app.db.models import PresenceObservationModel
    from backend.app.services.audit import AuditService

    _check_scope(scope)
    states = record_presence if record_presence is not None else derive_record_presence(
        keys_a, keys_b, completeness_a, completeness_b, out_of_scope_a, out_of_scope_b, excluded)
    stored_scope = dict(scope)
    stored_scope["completeness_a"] = completeness_a
    stored_scope["completeness_b"] = completeness_b
    observed_at = datetime.utcnow()
    audit = AuditService()
    observations: List[Dict[str, Any]] = []
    items: List[Tuple[str, str, str]] = []
    if key_to_refs is not None:
        for key in sorted(states):
            state, basis = states[key]
            for ref in key_to_refs.get(key, [key]):
                items.append((str(ref), state, basis))
    else:
        for key in sorted(states):
            state, basis = states[key]
            items.append((str(key), state, basis))
    for ref, state, basis in items:
        row = PresenceObservationModel(
            job_id=job_id,
            snapshot_a_ref=snapshot_a_ref,
            snapshot_b_ref=snapshot_b_ref,
            scope=stored_scope,
            record_ref=ref,
            record_presence=state,
            entity_presence=None,
            basis=basis,
            entity_links=None,
            observed_at=observed_at,
            pipeline_version=pipeline_version,
        )
        db.add(row)
        db.flush()
        observations.append({
            "id": row.id,
            "job_id": job_id,
            "record_ref": ref,
            "record_presence": state,
            "entity_presence": None,
            "basis": basis,
            "explanation": explanation_for(state, basis),
            "scope": stored_scope,
            "snapshot_a_ref": snapshot_a_ref,
            "snapshot_b_ref": snapshot_b_ref,
            "observed_at": observed_at.isoformat(),
            "pipeline_version": pipeline_version,
        })
        audit.log(action="presence.observed", entity_type="presence_observation",
                  entity_id=str(row.id), job_id=job_id,
                  details={"record_ref": ref, "record_presence": state, "basis": basis},
                  db=db)
    db.commit()
    # Flush audit into the same session without closing it: AuditService.flush
    # closes whatever session it is given, which must never be a live caller
    # session (it would detach the comparison job).
    audit.flush(db=db, close=False)
    return observations
