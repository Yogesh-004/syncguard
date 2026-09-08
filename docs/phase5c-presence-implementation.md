# Phase 5C — Presence Semantics Implementation

> Implements ONLY the minimum read-only scope of `docs/phase5c-presence-semantics-design.md` §25. No matching, blocking, normalization, model, threshold, decision, conflict, synchronization, connector, rollback, source-priority, golden-record, lifecycle, frontend, or deployment artifact was created or modified. One judgment call was settled directly from design §15 text (per-side gating; see §5) — no ambiguity required a STOP.

## 1. Approved Design

Authoritative: `docs/phase5c-presence-semantics-design.md` (four states, orthogonal identity/review dimensions, scope-mandatory observations, completeness-gated derivation, comparison-bound persistence, ACKNOWLEDGE/DEFER/ESCALATE-only handling, lifecycle vocabulary banned from system output). Implemented without reinterpretation; deviations: none.

## 2. Implementation Scope

Built: pure derivation service + completeness gate, `presence_observations` persistence + migration, two read-only GET endpoints, minimum audit via existing `AuditService`, 34 tests, this document. Deliberately NOT built: write endpoints for presence (design: read-only API; creation seam is the tested service function, unwired from the matching pipeline to avoid coupling), frontend changes (labels/warnings served as API explanation copy; no redesign), entity-link wiring beyond the interpreted function (link sources are caller-asserted; no clustering invented).

## 3. Domain Model

Exactly the four design states (`BOTH_PRESENT`, `ONLY_IN_A`, `ONLY_IN_B`, `UNKNOWN`) with basis codes (`BOTH_OBSERVED`, `ONLY_A/B_COMPLETE_SCOPE`, `SOURCE_FAILED`, `PARTIAL_INGESTION`, `SCOPE_MISMATCH`, `RECORD_EXCLUDED`, `NO_LINK`). Record presence (observed membership) and entity presence (link-cited interpretation) are separate fields that never share a column; entity `BOTH_PRESENT` requires a cited cross-side link, otherwise `UNKNOWN`/`NO_LINK`. No `DELETED`/`REMOVED`/`NEW_*`/`CREATED`/`TERMINATED` token is emittable: states are module constants, explanations are fixed copy, and `scan_for_lifecycle_language` tripwires the ban in tests.

## 4. Completeness Gate

`derive_record_presence` enforces the design §15 gate per side: observed membership is positive evidence (never gated); an `ONLY_*` absence claim requires the opposite side COMPLETE; FAILED → `UNKNOWN`/`SOURCE_FAILED`; PARTIAL → `UNKNOWN`/`PARTIAL_INGESTION`; out-of-scope keys → `UNKNOWN`/`SCOPE_MISMATCH`; excluded records → `UNKNOWN`/`RECORD_EXCLUDED`. Invalid completeness values raise `ValueError` (fail loud, never silent). Failure is never converted into absence.

## 5. Presence Derivation

Pure set-membership logic over caller-supplied key sets in `backend/app/services/presence.py` (stdlib only — structural import test bans matching/blocking/decision/evidence/conflict/resolution/sync/connector imports). Identity matching is neither consulted nor affected; presence outputs contain no decision field. One settled reading (design §15: gate applies "for every non-observed record on that side"): the gate is evaluated on the side where absence is claimed, so an observed record on a PARTIAL side still grounds a valid `ONLY_*` against a COMPLETE opposite side — pinned by tests `test_06`–`test_09`.

## 6. Persistence

`PresenceObservationModel` (`presence_observations`, migration `004_phase5c_presence` following the `003` try/except convention): job_id (comparison, nullable FK), snapshot refs, scope JSON (with per-side completeness embedded), record_ref (internal id only), record_presence, entity_presence (nullable), basis, entity_links (nullable), observed_at, pipeline_version. No directive or lifecycle columns exist, so an observation cannot express DELETE/INSERT/DELETED/NEW. Bound to comparison + scope, never stored on the record row.

## 7. API

Read-only only: `GET /presence/observations` (job_id/state filters, pagination, items carry state, basis, fixed neutral explanation, scope, record_ref, observed_at) and `GET /presence/summary` (per-state and per-basis counts). Invalid state → 422. Route test asserts no POST/PUT/DELETE `/presence` path exists. No existing endpoint modified; no presence endpoint touches synchronization. Frontend build not run: no existing contract changed, no frontend code touched.

## 8. Review Visibility

Minimum: API items serve the design §10 fixed neutral copy (including mandatory "does not mean…" warnings) with scope attached — a state without scope is unrepresentable (scope validation raises). No dashboard changes, no new UI actions, no `CONFIRM DELETED`/`CONFIRM NEW` affordances anywhere.

## 9. Audit

`derive_and_persist` emits one `presence.observed` audit row per observation via the existing `AuditService` (entity_type `presence_observation`, details limited to record_ref/state/basis — no PII; test asserts traceability and PII-freedom). Audit minimum (comparison, scope, snapshots, state, basis, timestamp) satisfied from observation rows + audit rows joined by id.

## 10. Synchronization Safety

Structurally verified, not just asserted: observation dicts and DB rows contain no directive keys (tested); presence module imports no sync machinery (AST import test); router exposes no presence writes (route test); full real-data rerun shows matcher behavior byte-identical with presence code present. `ONLY_IN_A` cannot cause DELETE, `ONLY_IN_B` cannot cause INSERT, `UNKNOWN` cannot cause action — there is no code path from an observation to any write. No accidental coupling found; no STOP needed.

## 11. Tests

`backend/tests/unit/test_phase5c_presence.py`: 34 tests, 34 pass. Coverage maps to the brief §§1–27: four states (1–4), completeness matrix incl. partial/failed (5–10), scope same/geo/filter/metadata (11–14), identity independence incl. import-structure test (15–19), record/entity split with link citation, sync-safety incl. route-shape test (20–22), persistence context/scope/completeness (23–25), audit traceability + PII-freedom (26), lifecycle-vocabulary ban incl. mandatory negation copy (27), API shape + 422 rejection.

## 12. Real-Data Regression

Same two-snapshot NC validation rerun (same snapshots, sample, seeds, methodology, thresholds, model, blocking): BEFORE vs AFTER identical on every reported number — candidates 1,157,687, recall 1.000, MATCH 910 (TP 753/FP 157, P 0.8275, R 0.9947, F1 0.9034), POSSIBLE 32, missed 4 truth (0 blocked), auto 0/0/0, crit-auto 0, singleton outcomes (974/22/3/1 and 972/25/3), singleton MATCH pairs (15/23, all HIGH/MANUAL), by-case taxonomy identical. Matching results unchanged, as required — presence is genuinely uncoupled.

## 13. Performance

Presence derivation + persist + audit on a 3,520-record real sample: 3,504 observations in 1.9s (~0.5ms/observation), peak 8.7MB — negligible against the ~1,500s matching pipeline (unchanged: infer 1,493s vs 1,271s prior is run-to-run machine variance at identical pair count and identical decisions). No optimization performed; no regression.

## 14. Security

Record refs are internal ids only; scope/basis metadata contains zero PII by construction; audit details carry state/basis/ref only (tested PII-free); logs carry ids and counts. No new PII surface created.

## 15. Files Changed

- NEW `backend/app/services/presence.py` (derivation, gate, entity interpretation, persist+audit, explanations, lifecycle scanner)
- NEW `backend/app/schemas/presence.py` (read-only Pydantic models)
- EDIT `backend/app/db/models.py` (+`PresenceObservationModel` only)
- NEW `alembic/versions/004_phase5c_presence.py` (table + indexes, same convention as `003`)
- EDIT `backend/app/api/routes.py` (+2 GET endpoints only)
- NEW `backend/tests/unit/test_phase5c_presence.py` (34 tests)
- NEW this document

## 16. Limitations

Entity-link sources are caller-asserted (no clustering invented — by design); presence creation is a tested service seam not yet wired into any pipeline (wiring is future work, deliberately deferred to avoid coupling); staleness bound remains an open design question (§27); false disappearance/appearance rates remain sampled-audit-only metrics.

---

PHASE 5C IMPLEMENTATION SCORECARD

BOTH_PRESENT:
PASS

ONLY_IN_A:
PASS

ONLY_IN_B:
PASS

UNKNOWN:
PASS

Completeness gate:
PASS

Scope enforcement:
PASS

Identity independence:
PASS

Auditability:
PASS

Read-only safety:
PASS

Delete prevention:
PASS

Insert prevention:
PASS

Real-data regression:
PASS

False merges:
157 (all HIGH/MANUAL, none auto)

Incorrect automatic merges:
0

Full tests:
284/284

Performance regression:
NO

---

PHASE 5C IMPLEMENTATION DECISION

Implementation:
ACCEPTED

Presence semantics:
PASS

Core invariant preserved:
YES

Real-data regression:
PASS

Safety regression:
PASS

Biggest limitation:
Presence creation is a tested but unwired service seam, so observations are not yet produced inside any live pipeline.

Next permitted phase:
Wire presence derivation into the comparison pipeline as a read-only side output, pending review approval.

Explicitly postponed:
connectors, rollback, source-priority policy, lifecycle states, deletion, insertion, golden records, retraining, threshold changes, unrelated UI, deployment

Confidence:
HIGH
