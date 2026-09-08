# Phase 6D — Reviewer-Visible Outcome + Verification Status

## 1. Objective

Expose the truthful sync outcomes established in Phase 6B/6C (VERIFIED, RECOVERED, SAFE_RETRY, BLOCKED, VERIFICATION_FAILED, UNKNOWN, plus DRY_RUN/IN_PROGRESS) in the existing review experience. Read-only presentation; zero synchronization-behavior change.

## 2. Existing Status Data

Persisted per sync job: status, `response_metadata` (verified, outcome token, outcome_unknown, retryable, recovered_via_confirm, error_code), error_message, attempt_count, idempotency_key, destination, timestamps — plus `SyncAttemptModel` rows and the `SYNC_*`/audit chain. One gap found: the outcome token was computed but never persisted; now stored additively (`outcome` key) in push/retry post-processing and except paths (presentation support only, no behavior change).

## 3. Existing Reviewer Surface

`ResolutionPanel.tsx` (conflict detail): resolutions → dry-run box → push → sync box (already fetched `GET /sync-jobs/{id}` as `detail`, but rendered raw status with hardcoded "(MOCK)" labels). Conflict detail, Timeline, and queue list left structurally unchanged.

## 4. Backend/API Exposure

NEW pure `sync_review_status(job)` in `resolution.py` (no I/O, no inference) deriving `{outcome, explanation, verification, verification_explanation, requires_human_action, retry_allowed}` from persisted fields only; exposed as a `review` block on the existing `GET /sync-jobs/{id}` (additive key; 404 and all other keys unchanged). No new endpoints, no contract redesign.

## 5. Reviewer-Facing States

Outcome and verification kept separate (e.g. RECOVERED outcome + VERIFIED verification stay distinguishable). Fixed neutral explanations per state; human-action and retry-allowed flags are backend-derived, never UI-computed.

## 6. SUCCESS / VERIFIED

Shown only when the backend recorded verified completion: "The approved changes were applied to the target and the resulting target state was verified." Never inferred from HTTP status, connector return, confidence, or approval.

## 7. RECOVERED

Distinct from SUCCESS: "The write result was initially uncertain. Verification found the approved state already present, so no duplicate write was made." Recovery event preserved in metadata and display.

## 8. SAFE RETRY

Shown when verification proved non-application with policy permitting retry: original uncertainty + verified-absent + retry-allowed stated; UI never auto-retries (existing explicit retry action untouched).

## 9. DIVERGED / STALE

BLOCKED with: "The target changed … SyncGuard did not overwrite the newer target state. Human review required." No auto-retry (backend `retryable: False` enforced), no overwrite, no lifecycle terms.

## 10. VERIFICATION FAILED

"The target state could not be verified against the approved resolution. No automatic correction was performed." Never shown as VERIFIED/success; no rollback invented.

## 11. UNKNOWN

"SyncGuard could not establish whether the mutation was applied … not as success or failure." Shown exactly when the backend left the outcome unresolved.

## 12. Status vs Verification Separation

Two independent fields from one derivation; e.g. recovered-vs-verified remain distinct. No invented states — every token traces to a persisted outcome or an explicit defensive fallback.

## 13. Audit Linkage

No audit changes: existing `SYNC_*`/attempt events already distinguish approval, attempt, outcome, verification, and retry. Review block references them without duplicating; Timeline untouched (presence/sync observation rows stay out of the reviewer-decision timeline by design).

## 14. Tests

`backend/tests/unit/test_phase6d_outcome.py`: 17/17 pass — mapping unit tests (A–F, P), frontend-truth test (G/H: component renders only `detail.review`), presence/match/risk invariance via live detail assertions (I–L), retry behavior (M), audit lineage (N), secret scan (O), API scoping/404/isolation (§15), mock parity (Q), plus live-PG API proofs for VERIFIED, RECOVERED, BLOCKED, UNKNOWN, and replay-still-VERIFIED (§16).

## 15. Real PostgreSQL Regression

All five scenarios verified through the real API against live PG: verified write → VERIFIED; injected post-commit loss → RECOVERED (single version bump); external bump → BLOCKED; replay → VERIFIED + `already_applied`; unconfirmable loss → UNKNOWN. Zero synchronization-behavior change to make tests pass.

## 16. Safety Regression

Duplicate mutations 0, unsafe stale overwrites 0, unexpected target mutations 0, incorrect automatic merges 0. UI work is render-only; the one full-suite failure observed was the known pre-existing parallel-push sqlite flake (passes solo, documented since Phase 5A, mock path untouched by this phase).

## 17. Performance

Derivation 0.012ms (pure, zero queries); `GET /sync-jobs/{id}` 12.5ms total. No material regression. Frontend build 10.57s, PASS (719 modules; pre-existing chunk-size warning only).

## 18. Files Changed

- `backend/app/services/resolution.py` (+outcome token persistence, +`sync_review_status` + explanations; behavior untouched)
- `backend/app/api/routes.py` (+`review` block on `GET /sync-jobs/{id}`)
- `frontend/src/components/ResolutionPanel.tsx` (sync box renders backend `review`; destination-driven MOCK label; legacy fallback)
- `backend/tests/unit/test_phase6d_outcome.py` (17 tests)
- This document

## 19. Limitations

Legacy/pre-phase jobs without outcome tokens derive defensively (mismatch detection relies on verified+retryable shape); DRY_RUN jobs show preview-only state (no sync semantics); Celery-path jobs carry no review block content beyond raw status.

## 20. Final Scorecard

REVIEWER OUTCOME SURFACING SCORECARD

Existing status model reused: PASS
Existing review surface reused: PASS
Backend source of truth preserved: PASS
SUCCESS/VERIFIED surfaced correctly: PASS
RECOVERED surfaced correctly: PASS
SAFE_RETRY surfaced correctly: PASS
DIVERGED/STALE surfaced correctly: PASS
VERIFICATION_FAILED surfaced correctly: PASS
UNKNOWN surfaced correctly: PASS
Status/verification separation: PASS
No frontend inference: PASS
Audit linkage preserved: PASS
No secret leakage: PASS
Presence unchanged: PASS
Matching unchanged: PASS
Synchronization behavior unchanged: PASS

Focused tests: 17/17
Full backend suite: 359/360 (1 pre-existing parallel-push sqlite flake, green solo)
Frontend tests: N/A (no runner; covered by build + API tests)
Frontend build: PASS

Real PostgreSQL regression: PASS

Duplicate mutations: 0
Unsafe stale overwrites: 0
Unexpected target mutations: 0
Incorrect automatic merges: 0

Material performance regression: NO

---

DECISION
Reviewer outcome surfacing: ACCEPTED
Reason: Truthful sync outcomes and verification states now render from persisted backend truth with zero behavior change and full test cover.
Next permitted phase: Any reviewer-workflow follow-up defined by review, pending approval.
Changes made: sync_review_status derivation, outcome token persistence, review block on sync-job API, ResolutionPanel outcome rendering, 17 focused tests, this report.
Changes explicitly NOT made: matching, model, weights, retraining, thresholds, blocking, normalization, evidence, decision engine, conflict engine, presence semantics, resolution logic, synchronization behavior, retry policy, idempotency behavior, stale-state protection, connector behavior, PostgreSQL transaction behavior, verification behavior, audit generation, Celery, REST connector, rollback and unmerge, source-priority, lifecycle semantics, deletion, insertion, golden records, deployment, cloud infrastructure.
Confidence: HIGH
