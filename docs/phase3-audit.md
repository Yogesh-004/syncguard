# Phase 3 Audit — Resolution + Sync + Audit

Date: 2026-09-06. Baseline: Phase 2 (field-level conflicts, match_id linked, job isolation verified job 12/13).

## Trace: Conflict UI → API → Resolution → DB → Sync → Connector → Verification → Audit
- UI (`Conflicts.tsx` queue + detail panel) → `POST /conflicts/{id}/resolve {action}` → sets `conflicts.resolution_status` + inserts `resolution_logs` + `audit_logs` → returns mapped status. No sync step exists. No dry-run. No push. Timeline in UI reads `GET /audit-logs`.
- `GET /conflicts/{id}` returns full chain (match/records/job/model). `GET /conflicts/{id}/audit` MISSING. `GET /conflicts/{id}/resolutions` MISSING.

## Findings
WORKING: status model (`pending/approved/rejected/modified/deferred`); resolve endpoint with 409-free idempotent-ish behavior? NO — re-resolving overwrites silently (no duplicate protection); resolution_logs append-only (good); audit_logs on every resolve (good); original `conflicting_fields` never mutated (good); record `data` never touched by resolve (good); Audit page live with detail pane.
PARTIALLY: resolution stores only `action+detail(text)` — no structured previous/resolved/selected_source/reason; no validation on manual-edit values; no state machine (any action on any status, including re-resolving approved).
BROKEN: duplicate rapid clicks create duplicate resolution_logs rows (no idempotency); concurrency unhandled (last write wins).
MOCK: none yet — no MockConnector, no sync job creation anywhere (SyncJobModel/SyncAttemptModel tables exist but zero rows ever written; `workers/tasks.py::sync_task` only flips state, no connector call).
STATIC: none in resolve path (verified — all values from DB/request).
MISSING: lifecycle doc; USE_SOURCE_A/B + MANUAL_EDIT actions (only approve/reject/modify/defer strings); dry-run; push + confirm; sync jobs; retry; verification; per-conflict audit endpoint; resolutions list endpoint; idempotency keys for push; failure taxonomy.
UNSAFE: `modify` accepts arbitrary `modified_values` without field-type validation; no destination allowlist (nothing to push to yet — must constrain to mock); resolve allows re-resolve of already-resolved (history confusing).

## Plan (no rebuild)
1. Lifecycle: pending=OPEN; first touch→REVIEWED (audit); approved/modified→RESOLVED; deferred=DEFERRED; rejected=RESOLVED(rejected, terminal, non-pushable). Document state machine; enforce in service.
2. Resolution entity: reuse `resolution_logs` (no migration) with JSON `detail` = {previous_value, resolved_value, selected_source, reason, dry_run, sync_job_id}; add `GET /conflicts/{id}/resolutions`.
3. Field validation for manual edit (email/phone/date/numeric reuse normalization utils).
4. Idempotency: same conflict+action+values → return existing (ALREADY_APPLIED note); different action on RESOLVED → 409; concurrency via re-read + status check in same transaction.
5. `MockConnector` (new, labeled MOCK everywhere): health_check/read/get_record/update_record on isolated in-memory store (never touches RecordModel); failure injection only via explicit `simulate_error` on mock destination.
6. Dry-run endpoint (no writes) → SyncJob row DRY_RUN + audit; push endpoint requires `{confirm:true}` + completed dry-run → PROCESSING → mock write → SUCCESS/FAILED + attempt row + verification read-back + audit; idempotency key = resolution+destination+value hash → ALREADY_APPLIED; retry endpoint with retryable/non-retryable taxonomy, max 3.
7. Audit events for every step; `GET /conflicts/{id}/audit` (filtered trail); conflict detail timeline from it.
8. Frontend: extend Conflict detail (Use A/B, Edit+validation, Reject, Defer+reason → resolution panel → dry-run panel → confirm push → sync/verify status → timeline). No bulk, no redesign.
9. Tests (30) + 2 live e2e (success + forced 500) + docs (resolution, synchronization, audit).
