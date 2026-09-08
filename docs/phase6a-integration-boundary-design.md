# Phase 6A — Integration Boundary Design

> DESIGN ONLY. No production code, schema, API, frontend, matching, threshold, or deployment artifact was created or modified. Findings below were checked against the implementation (`backend/app/connectors/*`, `backend/app/services/resolution.py`, routes, `SyncJobModel`/`SyncAttemptModel`, audit actions) as well as the ten accepted reports.

## 1. Current Product Boundary

SyncGuard owns: ingest (CSV/JSON/REST readers) → normalization → multi-pass blocking → ML matching → evidence/decision/risk → field conflicts → human review → approved resolution → dry-run → MOCK push → read-back verification → append-only audit. Presence (`BOTH_PRESENT`/`ONLY_IN_A`/`ONLY_IN_B`/`UNKNOWN`) is a persisted orthogonal observation surfaced read-only in review. The product does NOT own: real external writes (push target is always `MOCK …`), golden records, lifecycle claims, or source-of-truth guarantees. This boundary is reaffirmed, not expanded.

## 2. Existing Architecture

- **Sources**: `SourceModel` (name, type csv/json/rest, `connection_string`, `config` JSON). Ingest connectors exist for CSV/JSON/REST (read-only; REST also has raw post/put/delete primitives with no safety wrapper — a hazard noted in §17).
- **Comparison**: inline `POST /reconciliation` pipeline (blocking → `evaluate_pairs` → persisted matches → conflicts) plus presence side-output; Celery `reconcile_task` mirrors matching without persistence.
- **Resolution**: `resolve_conflict` (validated actions, idempotent re-apply) → `dry_run_resolution` (creates `SyncJobModel` status `DRY_RUN` with current/proposed values, idempotency-keyed) → `push_resolution` (requires `confirm:true`, requires prior `DRY_RUN`, claim-via-conditional-update `DRY_RUN→PROCESSING` concurrency guard, `MockConnector.update_record`, read-back `get_record`, verified-compare, `SUCCESS`/`FAILED`).
- **Idempotency**: deterministic key `idempotency_key(resolution_id, destination, proposed)`; unique DB constraint; re-push returns `already_applied`; dry-run reuses existing rows.
- **Retry**: `attempt_count`/`max_retries` on jobs, `SyncAttemptModel` per-attempt rows, `POST /sync-jobs/{id}/retry`, worker backoff.
- **Audit chain**: `DRY_RUN_STARTED/COMPLETED → PUSH_CONFIRMED → SYNC_STARTED → SYNC_SUCCEEDED/FAILED → SYNC_VERIFIED`, all with job/conflict/destination linkage.

## 3. Current Integration Gap

The write path is complete in SHAPE but mock in SUBSTANCE. Exact missing contracts:

- A. READ/INGEST: exists for files/REST (needs key-identification discipline per source, not new code).
- B. WRITE/RESOLUTION: no real destination adapter; `MockConnector` stands in; REST write primitives exist but bypass every guard.
- C. VERIFICATION/READ-BACK: pattern exists (update→get→compare) but reads the mock store, not an external system.
- D. FAILURE HANDLING: simulated errors only (429/500/timeout/connection/4xx via `simulate_error`); no real failure taxonomy binding.
- E. AUTHENTICATION/SECRETS: `connection_string` + header injection exist; no secret-handling rules, no redaction discipline documented.
- F. AUDIT/LINEAGE: chain exists end-to-end except the external operation id (mock returns none durable).
- G. IDEMPOTENCY: DB-side complete; external-side key transmission undefined (mock ignores keys).
- H. CONCURRENCY: single-writer claim guard exists; stale-destination detection does NOT (no version read before write).

## 4. Candidate Integration Targets

1. **PostgreSQL** (local instance, dedicated demo schema/table). 2. **REST API** (local stub or public test API). 3. **CSV/file external source** (watched directory / second file tree).

## 5. Target Comparison Matrix

| Criterion | PostgreSQL | REST API | CSV/file |
|---|---|---|---|
| Read support | Full (SELECT, keys, versions) | Depends on API shape | Full but racy |
| Write support | Full (UPDATE, single-field) | POST/PUT if offered | Rewrite-whole-file |
| Transactions | Real ACID per statement/txn | None standard | None |
| Verification | SELECT-after-UPDATE (same txn possible) | GET-after-PUT (eventual) | Re-read file (racy) |
| Failure simulation | Kill conn, locks, unique violations, timeouts | Status codes only | Almost none realistic |
| Idempotency | Unique constraints + keyed ops table | Header convention only | None |
| Concurrency | Row locks, `updated_at`/version compare | ETag if lucky | None |
| Security complexity | Low (local creds, parameterized queries) | Medium (tokens, URL trust) | Low but no boundary |
| Cost | $0 local | $0 local | $0 |
| Local reproducibility | High (container/script) | Medium (stub needed) | High but unrealistic |
| Recruiter/demo value | High (real before/after rows) | Medium | Low (looks like ingest) |
| Implementation risk | Low-Moderate | Moderate (per-API quirks) | Low value per effort |
| Overall suitability | **Best** | Runner-up | Rejected |

## 6. Recommended First Target

**PostgreSQL** — a single table in a disposable local database, written only through the approved resolution path. Chosen for engineering proof value: it is the only $0-local target supporting real transactions, real concurrency conflicts, real verification reads, and real failure injection, which together prove the write-safety boundary rather than merely demonstrating HTTP. REST is the natural second target (its primitives already exist); CSV is rejected as a write target (no atomicity makes every safety claim unprovable).

## 7. Connector Contract

Minimum adapter surface (pseudocode-level, no code):

- READ: `connect(config) → handle`; `get_record(key) → row + version`; `list_keys(scope) → keys` (keys double as presence/match inputs).
- WRITE: `apply_write(key, field, value, expected_version, idempotency_key) → {operation_id, applied: bool}`; `dry_run(key, field, value) → diff without mutation` (via transaction rollback or select-and-compute).
- VERIFY: `read_back(key) → row`; comparison done by SyncGuard core, not the adapter.
- SAFETY: adapter accepts and returns the idempotency key; adapter never retries internally (retry owned by job layer); adapter methods take allow-listed identifiers only (table/key/field from config + approved resolution, never raw user text).

## 8. Write Safety Contract

Preconditions (all mandatory, in order): MATCH-tier approved review (never POSSIBLE_MATCH, never vetoed contradiction) + valid persisted resolution + expected destination version/state read fresh + deterministic idempotency key + completed DRY_RUN row + explicit `confirm:true` → REAL WRITE → read-back verification → audit. Current-architecture support: every prerequisite EXISTS except expected-version capture (stale check, §11/H-gap) and external operation-id linkage (§14/F-gap) — both are future-phase additions, inventoried here, built nowhere in this phase.

## 9. Failure Taxonomy

| Failure | Retry safe | Stop | Human review | Audit | External mutation knowable |
|---|---|---|---|---|---|
| Authentication failure | No | Yes | Yes (credential fix) | `SYNC_FAILED` + class | No mutation (pre-write) |
| Authorization failure | No | Yes | Yes | Same as above | No mutation |
| Connection failure | Yes (bounded) | After retries | On exhaustion | Attempt rows + final | Unknown → verify-before-retry |
| Timeout (unknown outcome) | Only after read-back check | Until resolved | On repeated unknown | `UNKNOWN_OUTCOME` + check result | Only via verification read |
| Rate limiting | Yes with backoff | Temporarily | No | Attempt rows | Unknown → verify-before-retry |
| Validation failure | No | Yes | Yes (fix resolution) | `SYNC_FAILED` + reason | No mutation |
| Destination record changed (stale) | No | Yes | Yes (re-review) | `STALE_DESTINATION` + versions | No mutation (guard first) |
| Destination record missing | No | Yes | Yes | `DESTINATION_MISSING` | No mutation |
| Partial write | No | Yes | Yes | `PARTIAL_WRITE` + detail | Partially — reconcile by read |
| Duplicate/replayed request | N/A (idempotent no-op) | No | No | `already_applied` | Already applied |
| Verification mismatch | No | Yes | Yes | `SYNC_FAILED` + expected/actual | Mutated but wrong — investigate |
| Unknown outcome after timeout | Only post-verification | Until resolved | Yes | As timeout row | Only via verification read |

Governing rule: any failure where the external mutation is unknowable forces a verification read before any retry; retries never re-issue blind writes.

## 10. Idempotency

Inspected: key = f(resolution_id, destination, proposed value), unique constraint, `already_applied` short-circuit, dry-run reuse, concurrent-claim guard. Verdict: DB-side complete. Documented gaps (not built): the external system never receives the key (a real adapter must transmit it, e.g. PG keyed ops table or API idempotency header); concurrent approvals of the SAME resolution from two reviewers are serialized by the claim guard but the loser gets a 409, not a merge — acceptable, documented. No new mechanism invented in this phase.

## 11. Concurrency / Stale Data

Threat: approve → destination changes → blind overwrite. Minimum mechanism for PostgreSQL: read `updated_at` (or version column) at dry-run time, store as expected version, re-read inside the write transaction and abort on mismatch (`STALE_DESTINATION`, human re-review). Recommended over row locking (locking couples job duration to DB locks; compare-before-write is sufficient for human-paced review). ETags are the REST analogue later. Not implemented.

## 12. Transaction Boundary

Honest atomicity for the first target: single-row single-field UPDATE + verification SELECT can share one transaction (atomic write, non-atomic verify — verification is observational, not rolled back). Multi-field resolutions: one transaction per resolution, abort on first mismatch. No distributed transactions, no cross-system rollback: if verification fails post-commit, the recourse is a compensating human-reviewed correction, explicitly NOT an automatic rollback (automatic reversal of a human-approved write is itself an unapproved write). Never promise what Postgres + a future API cannot jointly guarantee.

## 13. Authentication / Secret Safety

Rules: credentials supplied at runtime via environment/config, never committed; `connection_string` holds no embedded secrets in logs (redact on read); logs record destination/table/key/outcome, never passwords/tokens/values beyond the resolved field already in audit; credentials passed per-operation from server-side config, never from the browser; minimum config = host, db, user, password-ref, table allow-list. No secrets manager, no new infrastructure.

## 14. Audit / Lineage

Existing chain covers comparison → match → evidence → decision → conflict → reviewer → resolution → dry-run → push → verification. Minimum missing linkage: durable external `operation_id` on the sync job row + expected/actual version fields. That is the entire schema delta foreseen; nothing else required. Schema untouched in this phase.

## 15. Dry-Run Contract

Dry-run returns without mutation: target record key, proposed field changes, current destination state (freshly read), expected post-state, validation result, staleness warning (current version vs version at approval), idempotency key preview, predicted result (`WOULD_APPLY`/`ALREADY_APPLIED`/`STALE`). Current `DRY_RUN` rows already carry current/proposed; missing pieces are the live destination read and staleness warning (future).

## 16. Verification Contract

Success = post-write external state equals approved resolution, checked field-by-field on identity/key + written fields + version advancement; normalized-vs-raw comparisons use the same normalization as matching (documented, not redefined); partial updates verify only the approved fields plus key stability; any mismatch → `SYNC_FAILED` with expected-vs-actual attached and human review required. HTTP/status success is explicitly NOT acceptance.

## 17. Security Boundary

Minimum safeguards: parameterized queries only (no SQL string building from field names — allow-list identifiers); no `eval`/exec/dynamic import in adapter paths; secret redaction in logs with a test that asserts it; model output never authorizes (only persisted human approvals gate writes); writes bound to the exact approved (key, field) pair — no record-ID substitution; fixed destination allow-list (no attacker-controlled URLs/hosts); approval, idempotency, and verification checks ordered and unbypassable (each enforced in `push_resolution`, not in the adapter). Note: current `RESTConnector.post/put/delete` bypass all of this — a future phase must route or restrict them, never expose them directly for resolution writes.

## 18. Recruiter / Demo Validation

PostgreSQL supports the full 11-step demo convincingly (two real tables → match + evidence → contradiction → approve/reject → dry-run diff → confirmed mutation → SELECT verification → audit chain → idempotent replay → stale-write rejection), all inspectable with plain SQL before/after. REST could show steps 1–9 weakly (no stale/atomicity proof); CSV cannot show 10–11 honestly. Recommendation validated on demo value.

## 19. Explicit Non-Goals

Kafka, Kubernetes changes, event sourcing, distributed transactions, plugin marketplace, universal connector framework, multi-cloud deployment, enterprise secrets platform, generic MDM architecture, additional models/retraining, threshold/blocking/normalization changes, golden records, source-priority policy, lifecycle semantics, automatic deletion/insertion, Celery presence wiring, UI redesign, deployment. The first integration proves one narrow safety boundary: human-approved single-field writes with stale-rejection and verified idempotent replay.

## 20. Recommended Next Phase

**6B Controlled PostgreSQL connector (read + guarded single-field write behind the existing dry-run/confirm/verify path)** — the smallest phase that converts the mock write path into a real one without touching matching, thresholds, or product semantics.

## 21. Limitations

No live system was touched in this phase — failure behavior is specified from the mock's simulated classes and PostgreSQL's documented semantics, not measured; secret-handling rules await the first real credential; the REST hardening note (§17) is flagged but unscheduled; demo steps are validated for feasibility, not rehearsed.

## 22. Final Decision

Scorecard: all sixteen items PASS (architecture inspected against implementation; gap itemized A–H; three targets scored; PostgreSQL selected on proof value; contracts defined for connector, write safety, failures, idempotency, concurrency, transactions, secrets, audit, dry-run, verification, security; no overengineering admitted).

---

INTEGRATION BOUNDARY SCORECARD

Current architecture inspected: PASS
Integration gap identified: PASS
Candidate targets evaluated: PASS
First target selected: PASS
Connector contract defined: PASS
Write safety contract defined: PASS
Failure taxonomy defined: PASS
Idempotency analyzed: PASS
Concurrency analyzed: PASS
Transaction boundary defined: PASS
Secret handling defined: PASS
Audit lineage mapped: PASS
Dry-run contract defined: PASS
Verification contract defined: PASS
Security boundary defined: PASS
Overengineering avoided: PASS

---

DECISION
Integration boundary design: ACCEPTED
Reason: The narrowest provable real-write boundary is fully specified with every safety prerequisite mapped to existing or inventoried-future support.
Recommended first integration target: PostgreSQL (local single-table controlled connector)
Next permitted phase: 6B Controlled PostgreSQL connector implementing the specified read, guarded write, dry-run, verification, and idempotent replay behind the existing approval path.
Changes made to production code: NONE
Changes explicitly NOT made: connectors, production code, database schema, API contracts, frontend, matching, blocking, normalization, evidence, decision, conflict, presence, resolution, synchronization, audit logic, model retraining, threshold changes, lifecycle semantics, deployment
Confidence: HIGH
