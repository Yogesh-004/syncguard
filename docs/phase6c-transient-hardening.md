# Phase 6C — Transient Failure + Unknown-Outcome Hardening

> Phase 7 addendum: HISTORICAL interim report. The authoritative formal-spec report is `docs/phase6c-transient-failure-hardening.md` (24-section matrix, scorecard, decision). Preserved unchanged below.

## 1. Problem

Push-time transient failures had two unhandled holes: a transient during read-back verification marked a committed write FAILED without checking, and an unconfirmable outcome was indistinguishable from a proved-not-applied one, inviting blind retries. Governing principle implemented: UNKNOWN WRITE OUTCOME → VERIFY FIRST → ALREADY APPLIED (no duplicate) or NOT APPLIED (safe retry).

## 2. Changes

`backend/app/services/resolution.py` only (mock path byte-identical):

- NEW `_safe_confirm` (confirm that never raises; unreachable target → `None`).
- NEW `_pg_confirmed_apply` (single verify-before-retry choke point for push AND retry): apply → on transient, confirm → applied+verified = `recovered` (SUCCESS, no re-mutation) → applied-but-diverged = `diverged` (FAILED, retry disabled) → proved-not-applied = re-raise (FAILED retryable, safe retry) → unconfirmable = re-raise flagged unknown. Verify-transients resolve through the same confirm path (`recovered` or `unknown`, never blind success).
- Push/retry metadata now records `outcome_unknown: True` for unconfirmable transients (retry stays allowed; reviewer sees the uncertainty) and forces `retryable: False` with a human-review error for `diverged`. `proved_not_applied` flag on re-raised transients keeps proved-safe retries free of the unknown flag. Hardening is PG-scoped: mock failures carry no new flags (tested).

## 3. What was NOT changed

Matching, thresholds, blocking, normalization, decision, presence, lifecycle, connectors beyond the PG path, frontend, Celery, deployment. No new tables, no schema change.

## 4. Tests

`backend/tests/unit/test_phase6c_transient.py`: 6/6 pass against live PostgreSQL with boundary fault injection (real apply beneath, injected lost-reply): (1) unknown-outcome recovered to SUCCESS with exactly one version bump; (2) diverged → FAILED, retry endpoint 422, tampered state preserved, no duplicate write; (3) unconfirmable → FAILED retryable with `outcome_unknown`, zero mutation, later retry → SUCCESS; (4) lost verify reply recovered; (5) proved-not-applied carries no unknown flag; (6) mock path flag-free. Full suite: 335/335, zero regressions.

## 5. Limitations

Wall-clock network-partition timeouts are simulated by fault injection at the connector boundary, not by physical packet loss; the disposable target cannot produce a genuine commit-then-drop; `diverged` resolution remains a human task (no auto-reconciliation by design).

## 6. Scorecard

Unknown-outcome recovery: PASS. Diverged handling: PASS. Unconfirmable flagging: PASS. Safe-retry preservation: PASS. Mock-path isolation: PASS. Focused tests: 6/6. Full suite: 335/335. Blind retries remaining: 0.

---

DECISION
Transient hardening: ACCEPTED
Reason: Every transient outcome class now resolves to recovered, safely-retryable, or human-gated with zero blind re-mutations proven on live PostgreSQL.
Next permitted phase: Reviewer-visible outcome/verification status surfacing, or REST read-path work, pending review approval.
Changes made: _safe_confirm, _pg_confirmed_apply, outcome/retryable metadata flags in push and retry (resolution.py only), 6 fault-injection tests, this report.
Changes explicitly NOT made: matching, thresholds, blocking, normalization, decision, presence, lifecycle, deletion, insertion, frontend, Celery, deployment, schema, mock behavior.
Confidence: HIGH
