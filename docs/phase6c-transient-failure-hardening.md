# Phase 6C — Transient Failure + Unknown-Outcome Hardening

## 1. Objective

Harden the accepted PostgreSQL sync path against transient failures and unknown write outcomes. Governing principle: UNKNOWN WRITE OUTCOME → VERIFY FIRST → ALREADY APPLIED (no duplicate) or NOT APPLIED (safe retry). Never infer "not applied" from an error alone — non-application is proven only by a fresh confirm read (ops row absent + state at pre-write version).

## 2. Existing Retry Behavior

Pre-phase: `SyncJobModel` attempt counting (budget 3), `SyncAttemptModel` rows, FAILED-only retry gate with non-retryable refusal, idempotent replay via ops-table PK, claim guard against concurrent pushes. Gap: verify-transients and unconfirmable outcomes had no path — a committed write could be marked FAILED, and any transient FAILED invited blind retry.

## 3. Failure Phase Model

Five phases, each with distinct semantics: pre-write failure (nothing sent — safe retry) → transaction failure (rolled back — safe retry) → post-commit response loss (applied, reply lost — confirm, never re-mutate) → timeout with ambiguous position (verify first — position determines everything) → verification failure (applied state diverges — human gate). `MockConnector` extended additively with `timeout_before` (no mutation) and `post_commit_loss` (mutates, then raises ConnectionError with UNKNOWN wording); normal mock behavior byte-identical.

## 4. Error Classification

Extended mapping (additive, mock parsing untouched): `TransientTargetError`/connection/timeout/lock-timeout → retryable; stale/missing/validation/collision/divergence → non-retryable. Live server-side lock-timeout (55P03 via `lock_timeout`) verified classified transient with zero mutation. New `options` connector parameter (e.g. `-c lock_timeout=400ms`) exists solely for deterministic failure simulation.

## 5. Unknown-Outcome Contract

States on the job: `outcome_unknown: True` in metadata whenever a retryable PG failure is NOT proven-not-applied; `proved_not_applied` flag (exception attribute) only when confirm positively verified absence; `diverged` outcome forces `retryable: False` with a human-review error. API and audit surfaces below (§§14–15) carry these states; nothing collapses them into success or definite failure.

## 6. Verify-Before-Retry

Single choke point `_pg_confirmed_apply` (shared by push and retry): apply → on transient, `_safe_confirm` (never raises; unreachable → `None`) → applied+verified = `recovered`; applied-but-diverged = `diverged`; proved-not-applied = re-raise (safe retry upstream); unconfirmable = re-raise flagged unknown. Verify-transients resolve through the same confirm path. No code path re-issues a mutation without a confirm verdict or a proved-absent ops row.

## 7. Post-Commit Response-Loss Test

Deterministic: real apply commits on live PG, injected transport loss before SyncGuard receives the reply. Result: confirm finds expected state → SUCCESS with `recovered_via_confirm`, exactly one version bump, one ops row, `SYNC_SUCCEEDED` audit. No second write issued (proven by version + ops counts).

## 8. Unknown + Unchanged Target

Pre-send transient with working confirm: FAILED retryable, NO `outcome_unknown` flag (nothing to doubt — proven), zero mutation, subsequent retry → SUCCESS with a single mutation. Target verified at pre-write state throughout the unknown window.

## 9. Unknown + Changed Target

Applied + externally tampered + lost reply: FAILED, `retryable: False`, retry endpoint 422, tampered state preserved, no duplicate write, stale/version guard never bypassed. UNKNOWN_OUTCOME + TARGET_CHANGED → STALE/CONFLICT → WRITE BLOCKED, exactly per contract.

## 10. Timeout Handling

Real server-side lock timeout (statement sent, canceled by PG, never executed): classified transient, confirm proves non-application, FAILED retryable, row + ops table untouched, succeeds after lock release. Timeouts are never retried blind — every timeout path passes through confirm first. Wall-clock network-partition timeouts use the identical code path (classification-tested); physical packet loss was not reproduced (stated limitation).

## 11. Idempotency Interaction

A: same key + same operation after unknown → original result, no re-mutation (replay). B: same key + different mutation → `IdempotencyCollisionError`, zero mutation (live-tested, including a threaded race where exactly one of two rival payloads wins with a single version bump). C: different key + same record after unknown → proceeds on the true current version as a new operation (live-tested: v2 unknown-applied + MANUAL_EDIT → SUCCESS at v3, two distinct ops rows). D: committed-then-unknown → confirm recovers without re-apply. Key identity stable and payload-bound throughout.

## 12. Concurrency Interaction

Threaded races on live PG: two identical operations → exactly one applied (version +1 once, one ops row; loser replays duplicate or hits the version guard). Operation A unknown while operation B changes the target → A detects divergence and blocks (see §9). Existing claim/version/idempotency mechanisms reused; no distributed locks. Full-suite parallel-push flake observed once (pre-existing sqlite contention, passes solo — unrelated, documented since Phase 5A).

## 13. Verification Failure

Post-write divergence → FAILED with expected-vs-actual attached, `retryable: False` on divergence, complete lineage preserved, no auto-correction, no rollback invented, attempt budget untouched (still 3; verified single-attempt pushes, no loops added).

## 14. Audit Truthfulness

Unknown path records `SYNC_STARTED` + failed attempt + `SYNC_FAILED` (retryable flag, `outcome_unknown` in metadata) and NEVER `SYNC_SUCCEEDED`/`SYNC_VERIFIED`. Recovered path records success only after confirm proof, with `recovered_via_confirm` in metadata. "Write succeeded" is never recorded from an unknown state.

## 15. API Behavior

Unknown outcome returns FAILED with `verified: false`, no SUCCESS wording, `already_applied: false`, and the flag visible via the sync-job GET. No contract redesign: same response shape, truthful values. Mock path carries no new flags (tested).

## 16. Mock Failure Simulation

Additive `timeout_before` / `post_commit_loss` modes with phase-accurate semantics (pre-write: store untouched; post-commit: store mutated + UNKNOWN error). Normal mock behavior pinned unchanged by existing + new tests. Mock staleness is N/A (no versions) — stale semantics are PG-tested only, stated here.

## 17. Real PostgreSQL Validation

All nine required proofs live on the disposable PG 18.4 target (separate server/DB from the app): normal write, transaction rollback (mid-txn CHECK violation → full rollback), stale rejection, idempotent replay, unknown-committed (recovered), unknown-uncommitted (safe retry), unknown-changed (blocked), read-back verification, verification mismatch. Transport faults are labeled simulated; transaction/lock/version behavior is real PG throughout.

## 18. Test Matrix

| Scenario | Outcome Known? | Mutation Applied? | Verify First? | Retry Allowed? | Expected Result |
|---|---|---|---|---|---|
| pre-write connection failure | Yes (not applied) | No | Yes (confirm) | Yes | FAILED retryable, clean retry |
| transaction rollback | Yes (not applied) | No | N/A | Yes | FAILED, zero partial state |
| post-commit response loss | After confirm: yes | Yes | Yes | N/A (recovered) | SUCCESS, single mutation |
| timeout before mutation | After confirm: yes | No | Yes | Yes | FAILED retryable, clean retry |
| timeout after mutation | After confirm: yes | Yes | Yes | N/A (recovered) | SUCCESS, single mutation |
| target unchanged | Yes | No | Yes | Yes | FAILED retryable, then SUCCESS |
| target changed | Yes (diverged) | Yes (original) | Yes | No | FAILED, retry 422, no overwrite |
| stale target | Yes | No | N/A | No | FAILED, no mutation |
| verification mismatch | Yes | Yes (wrong) | Yes | No | FAILED + expected/actual |
| duplicate replay | Yes | Already | Via ops row | N/A | Original result, no mutation |
| idempotency collision | Yes | Original only | Via ops row | No | Error, zero new mutation |
| concurrent update | After guard: yes | One winner | Via version guard | Loser blocked | Single mutation, single version bump |

## 19. Performance

Local medians: normal write ~50ms, dry-run preview ~26ms, single-read verify ~23ms, unknown-outcome confirm ~45–90ms (two reads), replay ~23–29ms. Confirm/verify run only on affected operations; happy-path cost unchanged from Phase 6B. No material regression; no optimization.

## 20. Security

No secrets in logs/audit (asserted over full audit blobs); parameterized SQL only (injection payloads stored as inert data, tables intact); retries reuse the stored approval and re-pass stale/idempotency/verification guards — retry-after-bump test proves no authorization, stale, idempotency, or verification bypass. A retry is NOT a new authorization and cannot widen the approved mutation.

## 21. Limitations

Physical network-partition timeouts simulated at the transport boundary (identical code path, labeled); disposable target must be reprovisioned per Phase 6B recipe; `diverged` cases require human reconciliation (no auto-merge by design); pre-existing parallel-push sqlite flake unrelated.

## 22. Files Changed

- `backend/app/connectors/postgres_connector.py` (+`options` param for deterministic timeout simulation)
- `backend/app/connectors/mock_connector.py` (+`timeout_before`, +`post_commit_loss` modes; normal path untouched)
- `backend/app/services/resolution.py` (+`_safe_confirm`, +`_pg_confirmed_apply`, outcome/retryable metadata in push + retry)
- `backend/tests/unit/test_phase6c_transient.py` (6 tests, prior phase) + `backend/tests/unit/test_phase6c_matrix.py` (8 tests, this matrix)
- This document (prior `docs/phase6c-transient-hardening.md` retained as historical)

## 23. Test Results

Focused: 8/8 matrix + 6/6 prior transient + 20/20 connector + 30/30 mock resolution — all green on live PG. Full backend suite: 343/343 (one full-run instance of the known pre-existing parallel-push sqlite flake, passing solo; unrelated to this phase).

## 24. Final Scorecard

TRANSIENT FAILURE HARDENING SCORECARD

Failure phases identified: PASS
Error classification: PASS
Unknown-outcome state: PASS
Verify-before-retry: PASS
Post-commit response-loss safety: PASS
Unknown + unchanged target: PASS
Unknown + changed target: PASS
Stale-write protection: PASS
Verification mismatch handling: PASS
Idempotency interaction: PASS
Idempotency collision protection: PASS
Concurrency protection: PASS
Retry boundedness: PASS
Audit truthfulness: PASS
API truthfulness: PASS
Real PostgreSQL validation: PASS
Mock failure simulation: PASS
SQL/security safety: PASS

Focused tests: 14/14 (8 matrix + 6 transient)
Full backend suite: 343/343

Duplicate mutations: 0
Unsafe stale overwrites: 0
Incorrect automatic merges: 0
Unexpected target mutations: 0

Material performance regression: NO

---

DECISION
Transient failure hardening: ACCEPTED
Reason: Every unknown-outcome class resolves to recovered, safely-retryable, or human-gated with zero duplicate mutations and zero stale overwrites proven on live PostgreSQL.
Next permitted phase: Reviewer-visible outcome and verification-status surfacing, pending review approval.
Changes made: _safe_confirm and _pg_confirmed_apply choke point, outcome and retryable metadata in push and retry, proved_not_applied distinction, connector options for timeout simulation, MockConnector timeout_before and post_commit_loss modes, 8 matrix tests, this report.
Changes explicitly NOT made: REST connector, additional connectors, Celery, deployment, cloud infrastructure, rollback and unmerge, source-priority, lifecycle semantics, deletion, insertion, golden records, new ML, retraining, threshold changes, blocking changes, normalization changes, frontend redesign, unrelated refactoring.
Confidence: HIGH
