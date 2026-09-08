# Phase 6B — Controlled PostgreSQL Connector

## 1. Objective

Replace the mock write destination with a REAL external PostgreSQL target behind the existing approval → resolution → dry-run → claim → confirm → verify → audit path, proving the write-safety boundary from Phase 6A with actual database semantics. Nothing else changed.

## 2. Existing Write Path

Mapped before coding and reused verbatim: reviewer approval → `resolve_conflict` (atomic claim, idempotent re-apply) → `dry_run_resolution` (creates `DRY_RUN` `SyncJobModel` with current/proposed values, idempotency-keyed) → `push_resolution` (requires `confirm:true` + prior `DRY_RUN`, `DRY_RUN→PROCESSING` conditional-update claim, connector write, read-back verify, `SUCCESS`/`FAILED` + attempt/audit rows) → `retry_sync` (FAILED-only, budget 3, non-retryable gate). `MockConnector` participated at exactly two call sites (`push_resolution`, `retry_sync`); both now select the connector by destination, mock default preserved.

## 3. Connector Implementation

NEW `backend/app/connectors/postgres_connector.py` (`PostgresConnector`, `connector_type="postgres"`): `health_check`, `get_record`, `preview` (SELECT-only dry-run), `apply` (transactional guarded write), `confirm` (verify-before-retry read), `verify` (fresh read + compare), typed errors (`RecordMissing/Validation/Stale/IdempotencyCollision/Transient/VerificationMismatch` with failure classes). Minimal compatible extensions elsewhere: `_pg_target_for` + `_select_connector` helpers and PG branches in `dry_run/push/retry_sync` in `resolution.py`; `classify_error` PG mapping; push API response gains `already_applied` and a truthful `mock` flag (mock path responses unchanged in shape).

## 4. Target Database

Separate disposable PostgreSQL 18.4 server (`initdb` private instance, port 55432, trust-auth local), database `syncguard_target` — a different server, port, and database from SyncGuard's app DB. Schema: `customer_records(record_key PK, name, email, phone, version, updated_at)` + `applied_operations(idempotency_key PK, record_key, field_name, resolved_value, version_after, applied_at)`. App schema untouched; no migration needed (external system).

## 5. Read Contract

`get_record(key)` returns current row + version or `None`; connection failures raise classified `TransientTargetError` (fixed during testing — reads initially leaked raw driver errors). Missing rows raise `RecordMissingError` in preview/apply paths.

## 6. Dry-Run Contract

`preview` performs SELECTs only and returns target, current/proposed/expected state, `expected_version`, validation, idempotency key, and `mutated: False`. Proven non-mutating by before/after row-equality test. Dry-run persists `pg_expected_version`/`pg_record_key` into the `DRY_RUN` job metadata for the push to enforce.

## 7. Write Authorization

PG writes require the full existing chain (approved non-REJECT/DEFER resolution + completed PG dry-run carrying expected version + explicit confirm + idempotency key + valid source config). `MATCH`/confidence/risk/presence alone authorize nothing — the connector receives only (key, field, value, expected_version, key) and cannot see model output at all.

## 8. Transaction Safety

`apply` runs version-guarded UPDATE + ops-row INSERT in one transaction; any failure rolls back. Proven by a real mid-transaction failure (CHECK-constraint violation injected on the controlled target): row value/version unchanged, zero ops rows. No distributed-transaction claims.

## 9. Stale-State Protection

Compare-before-write on `version` inside the write transaction: external bump between dry-run and push → `StaleTargetError`, `FAILED` job, zero mutation, no retry (non-retryable classification). Tested at API level (external UPDATE between dry-run and push) and connector level.

## 10. Idempotency

Target-enforced via `applied_operations` PK: same key + same mutation replays the original result (`applied: False, duplicate: True`, version untouched); same key + different mutation raises `IdempotencyCollisionError` with zero mutation. API replay returns `already_applied` without re-mutating (version stays +1).

## 11. Concurrency

Same-operation doubles resolve via existing claim guard + idempotency short-circuit (single version bump, both callers converge). Cross-resolution staleness blocked by version guard (no last-write-wins). No distributed locks invented.

## 12. Verification

`verify` fresh-reads and compares field value + version; SQL success is never reported as success. Push marks `SUCCESS` only on match, else `FAILED` with expected/actual attached. Mismatch path live-tested (post-write tamper → `verified: False`).

## 13. Failure Handling

Live-tested on real PG: connection failure (transient, no mutation), invalid config (fail-fast validation), missing record, validation failure, stale target, mid-transaction failure with rollback, replay, collision, verification mismatch, malicious input as data. Unknown-outcome-after-timeout follows verify-before-retry (`confirm` path, classification-tested; wall-clock timeout not live-fired — see §19).

## 14. SQL / Security Safety

All statements parameterized; table/field identifiers from fixed allow-lists (constructor rejects anything else); no dynamic SQL from API input; DSN redacted in health/log contexts; audit rows carry no secrets (asserted); approval/stale/idempotency/verification gates unbypassable (enforced in `push_resolution`, not the adapter). Malicious keys/values stored as inert data; tables intact.

## 15. Audit / Lineage

Full existing chain preserved plus PG truth: `DRY_RUN_STARTED/COMPLETED → PUSH_CONFIRMED → SYNC_STARTED → SYNC_SUCCEEDED → SYNC_VERIFIED` with destination `PG:customer_records`, operation id (= idempotency key), field/value, version evidence. Failed operations equally traceable. One session-safety note: no audit changes were needed.

## 16. Tests

`backend/tests/unit/test_phase6b_postgres.py`: 20/20 pass against the real target (module skips — never fakes — if the target is unreachable). Covers all 20 brief items. `MockConnector` behavior pinned unchanged (own test + all 30 Phase-3 mock tests green).

## 17. Performance

Local medians (psycopg2, per-operation connections, conservative): read 22ms, preview 26ms, write 53ms, verify 23ms, replay 22ms. No optimization; negligible against pipeline cost.

## 18. Regression Results

Full backend suite 329/329 (309 pre-existing + 20 new), zero failures. Matching/presence/conflict code untouched; incorrect automatic merges 0; no historical metric altered. Controlled write demonstration uses small synthetic target rows only — matching evidence untouched by design.

## 19. Limitations

Wall-clock timeout with genuine unknown outcome not live-fired (confirm path implemented + classification-tested); PG routing is source-config-gated (`pg_target.enabled`) so unconfigured sources stay mock; target server is a disposable local instance (reprovision per §4 recipe); no frontend exposure (API-validated per brief §20 STOP rule).

## 20. Files Changed

- NEW `backend/app/connectors/postgres_connector.py`
- EDIT `backend/app/services/resolution.py` (PG branches + helpers + error mapping; mock flow byte-identical)
- EDIT `backend/app/api/routes.py` (push response: `already_applied`, truthful `mock` flag)
- NEW `backend/tests/unit/test_phase6b_postgres.py` (20 tests)
- NEW this document

## 21. Final Scorecard

CONTROLLED POSTGRESQL CONNECTOR SCORECARD

Existing write path reused: PASS
Separate external target database: PASS
Real PostgreSQL read: PASS
Real PostgreSQL write: PASS
Dry-run non-mutating: PASS
Explicit approval required: PASS
Transactional write: PASS
Partial-write protection: PASS
Stale-state rejection: PASS
Idempotent replay: PASS
Idempotency collision protection: PASS
Concurrency protection: PASS
Verification read-back: PASS
Verification mismatch handling: PASS
Failure taxonomy: PASS
SQL injection safety: PASS
Secret safety: PASS
Audit lineage: PASS
MockConnector regression: PASS
Focused tests: 20/20
Full backend suite: 329/329
Material performance regression: NO
Incorrect automatic merges: 0
Unexpected mutations: 0

---

DECISION
Controlled PostgreSQL connector: ACCEPTED
Reason: Real external reads, guarded transactional writes, stale rejection, idempotent replay, and read-back verification all pass against live PostgreSQL through the unchanged approval path with zero regressions.
Next permitted phase: Wire the REST connector read path or harden retry semantics for transient PG failures, pending review approval.
Changes made: PostgresConnector, PG branches in dry-run/push/retry, PG error classification, push response already_applied/truthful mock flag, 20 focused tests, this report.
Changes explicitly NOT made: matching, model, retraining, thresholds, blocking, normalization, evidence, decision, conflict, presence, lifecycle, deletion, insertion, source-priority, golden records, rollback, frontend, Celery, deployment, cloud infrastructure, connector marketplace, REST connector, arbitrary SQL.
Confidence: HIGH
