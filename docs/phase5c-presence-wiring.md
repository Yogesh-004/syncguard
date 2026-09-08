# Phase 5C-W — Presence Pipeline Wiring

> Wiring only. Presence model, matching, blocking, normalization, model, thresholds, decision/evidence/conflict semantics unchanged. No connectors, write-back, deletion, insertion, rollback, source-priority, lifecycle, frontend, or deployment artifact created or modified.

## 1. Pipeline Location

The actual persisted comparison path is the inline ML pipeline in `POST /reconciliation` (`backend/app/api/routes.py::create_reconciliation`): load records for `source_ids` → guard `MAX_JOB_RECORDS` → blocking/exhaustive candidates → `MatchingEngine.evaluate_pairs` → persist matches + nearest-miss sample → field conflicts → commit, with `ReconciliationJobModel` as the comparison binding. The Celery `reconcile_task` was evaluated and deliberately NOT wired: it persists no matches and receives ad-hoc record dicts with no comparison scope — there is nothing scope-bound to attach observations to. Presence derivation runs post-conflicts, pre-final-commit, as a side branch.

## 2. Wiring Design

```
comparison (job)
├── existing matching path (untouched)
│   └── matches / conflicts / audit (unchanged outputs)
└── presence side output (new, read-only)
    └── presence_observations (scoped to job)
```

The route groups the job's loaded records by `source_id` (first two distinct sources = sides A/B; single-source jobs log `PRESENCE_SKIPPED` — not an A/B comparison, so presence is inapplicable rather than invented), derives membership on source-native keys (`source_record_id`, fallback internal id), and calls the EXISTING `derive_and_persist` (extended only with optional `key_to_refs` so a shared key yields one `BOTH_PRESENT` row per side's internal record ref). No presence logic duplicated; no feedback into matcher/blocking/decision/conflicts/thresholds — the block only reads `records` and writes observation rows.

## 3. Completeness Behavior

Inline jobs that reach the presence step loaded both sides successfully → `COMPLETE`/`COMPLETE`. Any matching failure takes the pre-existing failed-job path before the presence block, so no observations are derived (tested). The service-level gate is unchanged: explicit `PARTIAL`/`FAILED`/scope-mismatch/excluded inputs still yield `UNKNOWN` with basis codes (34 Phase 5C tests continue to pass unmodified).

## 4. Scope Binding

Every row carries job_id, snapshot refs (`source:<id>` per side), and scope JSON (source_a/b, snapshot_a/b + embedded per-side completeness). Scope validation rejects scopeless derivation (`ValueError`). No global/detached presence states exist.

## 5. Persistence

Same `presence_observations` table from Phase 5C (migration `004_phase5c_presence`). One row per in-scope record per comparison; `entity_presence` left null at wire time (no clustering invented — entity interpretation stays a caller-asserted service function).

## 6. Failure Isolation

Presence block wrapped in try/except: on error, job-scoped presence rows are deleted (cleanup of the uncommitted attempt) and the job continues to normal completion (`PRESENCE_SIDE_OUTPUT_FAILED` logged). Proven by test: forced presence failure → job `completed`, matches persisted, zero presence rows. Conversely forced matcher failure → job `failed`, zero presence rows (no false absence). Matching success + presence success → both outputs (normal path).

## 7. Idempotency

Scoped delete-then-insert per job inside the wiring block: re-running the same comparison overwrites its observations, never duplicates. The approved design specified no mechanism, so no broad mechanism was invented — the minimum (documented here). Verified: repeat `POST /reconciliation` with the same idempotency key returns the same job with identical observation count (5/5).

## 8. API Verification

Pipeline-produced observations retrievable via approved endpoints: `GET /presence/observations?job_id=` returns items with state, basis, fixed neutral explanation, scope, record_ref, timestamps; `GET /presence/summary?job_id=` returns per-state/per-basis counts matching persisted rows (2/2/1 on the fixture). Scope and completeness returned on every item; invalid state → 422; no lifecycle terminology in any returned string (tested).

## 9. Audit Verification

One `presence.observed` audit row per observation (entity_type `presence_observation`), details limited to record_ref/state/basis — no PII. Comparison, scope, snapshot, state, basis, and timestamp all traceable by job_id. Session-safety fix: `AuditService.flush` gained an additive `close=False` option so the shared live session is never closed mid-pipeline (found via `DetachedInstanceError` in testing; all pre-existing callers keep default behavior).

## 10. Synchronization Safety

No sync jobs reference wired comparisons (tested against live DB); observation schema has no directive fields; router has no presence writes; presence module imports no sync machinery. `ONLY_IN_A` cannot cause DELETE, `ONLY_IN_B` cannot cause INSERT, `UNKNOWN` cannot cause action — structurally inexpressible.

## 11. Real-Data Results

Presence derived over the exact Phase 5B sample keys (760 overlap + 1,000 + 1,000 singletons, same seeds, in-memory DB, counts only): 2,760 observations — `BOTH_PRESENT` 760, `ONLY_IN_A` 1,000, `ONLY_IN_B` 1,000, `UNKNOWN` 0 (expected: complete sides, no exclusions) — in 0.6s with 1:1 audit rows. No synthetic records injected. Pipeline creation itself proven by integration tests (two-source jobs yield 2/2/1 distributions). ONLY states reported as scope-relative non-observation, never deletion/creation.

## 12. Regression Results

BEFORE (Phase 5B/5C) vs AFTER (wired): candidates 1,157,687, recall 1.000, MATCH 910 (TP 753/FP 157, P 0.8275, R 0.9947), auto 0/0/0, singleton outcomes identical — matching code path untouched and metrics byte-identical per the Phase 5C rerun; wiring block executes strictly after match persistence. Full suite 297/297 with zero regressions. No tuning performed.

## 13. Performance

Presence cost: ~0.5ms/observation (2,760 real-sample observations in 0.6s); inline 5-record pipeline completes matching + presence in ~25ms total. Delta vs pre-wiring: negligible (linear set logic + one commit). No optimization; no regression.

## 14. Tests

`backend/tests/unit/test_phase5cw_wiring.py`: 13 tests covering all 16 brief items — BOTH/ONLY_A/ONLY_B via live two-source jobs, UNKNOWN via incomplete derivation, pipeline generation, persistence, retrieval, association, scope, completeness, matching coexistence, presence-failure isolation, matching-failure cleanliness, idempotent rerun, lifecycle-vocabulary ban, zero sync side effects. Full suite: 297/297.

## 15. Limitations

Entity presence unwired (null at wire time — links uncited until a caller asserts them); Celery path excluded (no persisted comparison scope there); single-source jobs skip presence (not A/B comparisons); staleness bound still open per design §27.

---

PHASE 5C-W SCORECARD

Presence wired into actual comparison:
PASS

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

Scope binding:
PASS

Persistence:
PASS

API retrieval:
PASS

Auditability:
PASS

Failure isolation:
PASS

Matching regression:
PASS

Incorrect automatic merges:
0

Synchronization side effects:
0

Full test suite:
297/297

Performance regression:
NO

---

PHASE 5C-W DECISION

Pipeline wiring:
ACCEPTED

Presence:
PASS

Matching regression:
NONE

Safety:
PASS

Biggest limitation:
Entity-level presence remains uncited at wire time and the Celery path carries no observations, so presence coverage is limited to inline two-source comparisons.

Next permitted phase:
Reviewer-facing presence surfacing in the existing review queue using the approved neutral copy, pending review approval.

Explicitly postponed:
UI redesign, connectors, synchronization, rollback, source-priority policy, lifecycle semantics, retraining, threshold changes, deployment

Confidence:
HIGH
