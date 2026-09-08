# SyncGuard Release/Product Audit

> Audit-only. No production code modified. Evidence: full backend suite run (360/360), source inspection (routes, resolution, connectors, models, config, deps), test-log review, live docs inventory, README/frontend text review. Every prior PASS was re-inspected, not trusted. Uses PROVEN / PARTIALLY PROVEN / UNVERIFIED / FALSE.

## Executive Verdict

The safety-layer product is real and honestly evidenced within stated limits: matching holds recall 1.0→0.99 on real voter data, zero incorrect auto-merges across every validated dataset, and the PG write path proves stale-rejection, idempotent replay, and verify-before-retry on a live database. The reports disclose limitations instead of hiding them (weak labels, synthetic-only email/phone vetoes, scope artifact, 50K untested). What blocks release is not the product hypothesis but operational readiness: no API authentication, placeholder SECRET_KEY, a single-commit repo with a fully uncommitted tree, and a stale README. Verdict: **C — NEEDS ONE MORE ENGINEERING PHASE** (deployment + portfolio hardening, no new features).

## Current Product Definition

Matches the implementation: a safety layer turning uncertain matching into explainable, reviewable, verified changes. It is not MDM/golden-record/observability/reverse-ETL/generic-sync/LLM product — confirmed by absence of those subsystems in code. The README overstates ("integration reliability platform", weighted-scoring methodology, stale thresholds) and must be narrowed to match reality.

## Claim-by-Claim Evidence Matrix

### A. Matching

| Claim | Evidence | Verification | Status | Risk |
|---|---|---|---|---|
| Blocking preserves high recall | 1.000 candidate recall, both real validations (103k and 1.16M candidates) | Reran suite green; code path unchanged since | PROVEN | Low |
| Identifies likely same-person records | MATCH R 1.0 / 0.9947 on voter_reg_num weak labels | Weak labels are near-trivial linkage; difficulty understated | PARTIALLY PROVEN | Medium — real difficulty lower than claimed setting |
| Decisions persisted | MatchModel + evidence JSON, job-scoped | Inspected routes + tests | PROVEN | Low |
| Job isolation works | entity_group_id job scoping + cross-job tests | Phase 5C-W/5D isolation tests pass | PROVEN | Low |
| Match traceability works | Match→conflict→resolution→sync→audit chain | Traced in code + audit tests | PROVEN | Low |

### B. Decision safety

| Claim | Evidence | Verification | Status | Risk |
|---|---|---|---|---|
| Contradiction veto | Veto logic + synthetic tests | Email/phone vetoes synthetic-only (no emails/phones in NC data — honestly disclosed) | PARTIALLY PROVEN | Medium — most safety-critical paths lack real-data proof |
| Trusted-ID veto | Synthetic tests | Same limitation as above | PARTIALLY PROVEN | Medium |
| Low-information no-auto | 0 auto-eligible on thin real data, all routed manual | Reproduced across phases (0/0/0) | PROVEN | Low |
| Auto requires MATCH+LOW+no-contradiction | Decision engine code + tests | Inspected; never fired on real data (vacuous) | PROVEN | Low — untested under fire on real data |
| Zero incorrect autos | 0 across all validated datasets | Consistent; does NOT prove production zero-risk | PROVEN (bounded) | Medium if overclaimed |

### C. Explainability — all PROVEN

Field evidence persisted and sufficient on 30/30 and 60/60 masked samples; conflict evidence traceable; risk/recommendation from decision engine; ResolutionPanel/Presence render backend truth (verified no frontend inference: status derived server-side, UI renders props).

### D. Human review — all PROVEN

Both records visible; conflicts listed; presence surfaced (detail panel); Use A/B/Edit/Reject/Defer all work with persisted state; every action audited (CONFLICT_REVIEWED/RESOLUTION_CREATED).

### E. Presence semantics — all PROVEN

Four states, completeness gate, scope binding verified by 34 unit + 13 wiring + 12 surfacing tests; lifecycle-vocabulary scanner enforced; reviewer-visible with mandatory neutral copy. Correctly kept out of identity/matching paths.

### F. Synchronization safety

| Claim | Evidence | Verification | Status | Risk |
|---|---|---|---|---|
| Dry-run non-mutating | Before/after row-equality on live PG | Re-ran 6B file green | PROVEN | Low |
| Explicit approval required | confirm:true + prior DRY_RUN enforced; REJECT/DEFER rejected | Code-inspected + tested | PROVEN | Low |
| Stale rejection | Version guard in PG txn, live-tested | Re-ran green | PROVEN | Low |
| Transactional, no partial updates | Mid-txn CHECK-violation rollback test on live PG | Re-ran green | PROVEN | Low |
| Target-enforced idempotency + collision rejection | Ops-table PK, live replay/collision tests | Re-ran green | PROVEN | Low |
| Concurrency protection | Claim guard + live thread races (single mutation) | Re-ran green; sqlite parallel-push flake is app-DB test-only | PROVEN | Low |
| Read-back verification; mismatch ≠ success | Verify-compare; tamper test | Re-ran green | PROVEN | Low |
| Unknown-outcome classification; post-commit loss → no duplicate | Confirm path; injected-loss tests on live PG | Re-ran green; transport fault is injected, PG behavior real (honestly labeled) | PROVEN | Low |
| Bounded retry | Budget 3, non-retryable gate, single-attempt pushes | Code-inspected + tested | PROVEN | Low |
| Audit lineage | Full SYNC_* chain + 1:1 presence audit | Inspected + tested | PROVEN | Low |
| UI reflects backend truth | review block from persisted fields; no UI inference | Tested (17) + build green | PROVEN | Low |

### G. Real-data validation

Public real data (NCSBE, licensed public record, masked) PROVEN. Temporal validation PROVEN (R 0.9947, movers matched). Appearance/disappearance PARTIALLY PROVEN — 93.7% singleton rates are prefix-scope artifact, so business appearance/disappearance is unmeasured; reports disclose this honestly. False merges reported, never hidden (130/157 FPs held, 0 escaped). Weak labels disclosed as weak everywhere. Email/phone vetoes correctly labeled synthetic-only — NOT overclaimed. PROVEN as a honesty record.

### H. Performance

Blocking/matching latencies measured and reported (2.7ms/pair small; ~1.1ms/pair at 1.16M; PG op medians 22–53ms) PROVEN. 50K-scale explicitly NOT TESTED, O(n²) guarded by MAX_JOB_RECORDS=2000 — honestly disclosed, NOT falsely implied. PROVEN.

## Real-World Workflow

Small-team data/ops steward reconciling two customer extracts (e.g., billing CSV vs CRM export): upload both → review queue shows POSSIBLE matches with field evidence → steward approves per-field values → dry-run shows exact mutation → confirm writes to the controlled target → verification + audit prove it. SyncGuard saves them at three points: refusing to auto-merge households/lookalikes (HIGH-risk hold), blocking stale overwrites, and proving idempotent recovery instead of double-writing. Vs SQL/manual review: evidence + safety gates come built-in. Vs MDM/AWS-ER/Splink: no enterprise deployment, but with review/verify/write-back those tools omit. Smallest convincing case: two CSVs, one shared-customer correction pushed to Postgres with dry-run + verification + audit.

## Product Boundary

- CORE: blocking → ML match → evidence/decision → conflicts → review/resolve → dry-run → guarded push → verify → audit; presence observations; sync outcome surfacing.
- SUPPORTING: schema drift detection, CSV/JSON/REST ingest, presence-aware review copy.
- INFRASTRUCTURE: Celery/Redis wiring, Alembic, demo fallbacks, benchmark harnesses, Febrl fixtures.
- DEMO/VALIDATION-ONLY: static demo.json, /tmp range-stream validation scripts, disposable PG target recipe.
- NOT PRODUCTIZED: REST writes (primitives exist, unwired — latent hazard), Celery presence, lifecycle semantics, golden records. Ruthless note: `POST /matching/run`, `/match`, `/reconcile` legacy endpoints duplicate `/matches`+`/reconciliation` and should not be presented as product surface.

## Safety Audit

Write path traced end-to-end (approval → claim → dry-run → confirm → version-guarded txn → ops-row idempotency → read-back → audit → UI truth): no bypass found. `RESTConnector.post/put/delete` have zero callers (latent, not live — route or remove). `DELETE /sources/{id}` is unapproved app-DB CRUD (LOW; standard, but note). Retries cannot duplicate (ops PK + claim guard + version check). Stale races blocked in-transaction. Verification cannot false-report (compare-gated SUCCESS). All exception paths write FAILED + attempt + audit. Secrets: PG DSN env-sourced and redacted in logs (tested); **finding (MEDIUM): `SourceModel.connection_string` is stored plaintext and echoed by the source API with no redaction discipline**. **Findings (HIGH, deployment-blocking): no API authentication on any endpoint including push/confirm/delete; `SECRET_KEY` is the placeholder default.**

## UX / Reviewer Audit

Strong: conflict queue answers what/why/risk/action within seconds; evidence ticks, presence block, and sync outcome block are compact and neutral. Stale/confusing: Conflicts header "review only (Phase 2)"; README badge "26 passed" vs 360 actual; README matching methodology describes weighted scoring, not the shipped LogReg model; README threshold text (>95 auto) contradicts the decision engine; tech-stack versions drifted (py3.12/PG16 claims vs 3.9/18 reality); single-source jobs silently skip presence (correct, unexplained in UI). Landing/Dashboard/Audit pages not deep-inspected — UNVERIFIED beyond Conflicts/ResolutionPanel/Timeline/LiveAnalysis/Matching surfaces reviewed.

## Demo Readiness

60-second explanation: fully supportable as documented. 3–5 minute live demo (11 steps): steps 1–6, 8–10 work live today (mock or PG); step 7 (real PG mutation) needs ~5 min manual setup (provision disposable PG per 6B recipe, seed target rows, two CSVs with shared rec_ids); presence (10) needs a two-source job. Nothing must be faked; nothing extra must be built. Manual-prep checklist is the only gap.

## GitHub / Portfolio Readiness

Gaps: (1) README stale as detailed above; (2) single git commit with the entire product as uncommitted working tree — no reviewable history; (3) two near-duplicate docs (`phase6c-transient-hardening.md` vs `phase6c-transient-failure-hardening.md`); briefs reference `phase6d-sync-review-status.md`, which does not exist (actual: `phase6d-reviewer-outcome-verification.md`); (4) `.env.example` lacks `SYNCGUARD_PG_TARGET`; (5) no screenshots/demo evidence; (6) model trained partly on Walmart-Amazon product records — disclosed in metadata, undisclosed in README; (7) docker-compose status UNVERIFIED (not exercised in this audit).

## Deployment Readiness

Application correctness NEEDS HARDENING (parallel-push sqlite flake; uncommitted tree). Data validation READY (within disclosed limits). Synchronization safety READY (controlled-target scope). Frontend usability NEEDS HARDENING (stale text). Reproducibility NEEDS HARDENING (history, env gaps, disposable-PG recipe manual). Observability NEEDS HARDENING (logs only). Security NOT READY (no auth, placeholder secret, plaintext connection strings). Performance NEEDS HARDENING (50K untested). Operational readiness NOT READY. **Should SyncGuard be deployed publicly right now? NO** — CONDITIONAL on the hardening phase below; demo only in private/local settings.

## Recruiter Value

Problem realism 8, technical depth 8, ML relevance 5, backend engineering 8, data engineering 8, systems thinking 8, safety/reliability 9, frontend/product quality 6, novelty/differentiation 7, interview explainability 9. Strongest engineering achievements: (1) verify-before-retry unknown-outcome protocol proven on live PG with zero duplicate mutations; (2) zero-escape review gating holding 38 false-match pairs across real datasets with full evidence; (3) scope-relative presence semantics that refuse lifecycle conclusions by construction. Best interview topics: why absence must never mean deletion (93.7% scope artifact); the confirm-vs-retry decision table; why idempotency lives in the target, not the client. Never claim: production zero-risk auto-merge; email/phone vetoes validated on real data; scale readiness. Openly disclose: weak labels, synthetic-only veto paths, single-county samples, disposable-target demo scope.

## Proven Strengths

Safety architecture that holds under measurement; evidence-sufficient review UX; honest reporting discipline (limitations stated in every phase); additive, regression-free engineering (360 green with matcher behavior byte-identical across phases); real-database proof for the write path, not mocks alone.

## Unresolved Risks

Email/phone contradiction behavior unproven on real data; single-county generalization unknown; review-queue staffing at city scale unmeasured; no-auth API + placeholder secrets block any public exposure; REST write primitives unwired-but-present; uncommitted tree + stale README erode portfolio credibility.

## Must Fix

1. Add API authentication/authorization + replace placeholder SECRET_KEY (blocks any public exposure).
2. Commit the working tree as reviewable incremental history.
3. Refresh README (tests, ML methodology, thresholds, env incl. PG target, limitations, product-data training note).
4. Redact/isolate `SourceModel.connection_string` (no plaintext credential echo).
5. Resolve duplicate 6C docs + stale "(Phase 2)" label + missing-filename references.

## Should Fix

1. Route or remove `RESTConnector` write primitives.
2. Refresh + verify docker-compose end-to-end.
3. Demo script + screenshots.
4. Address parallel-push sqlite flake (WAL/retry-on-locked or documented known issue).
5. Define sampled false-disappearance audit cadence (open since 5C).

## Optional

1. Celery presence wiring. 2. Review-queue presence badges. 3. Staleness-bound policy. 4. ETag REST analogue. 5. Vite chunk-size warning.

## Final Verdict

**C. NEEDS ONE MORE ENGINEERING PHASE** — not because the hypothesis is unproven (it is proven within disclosed limits) but because shipping any public surface without auth/secrets/history/README remediation would be professionally indefensible. No product feature work is justified first.

## Exactly One Recommended Next Phase

Deployment + portfolio hardening: API auth, secret management, connection-string redaction, incremental commit history, README/env/compose refresh, doc-filename cleanup, and demo packaging — then stop and present.

## Evidence / Commands / Tests Inspected

Full backend suite 360/360 witnessed; `resolution.py` push/retry/confirm paths, both connectors, `SyncJobModel`/attempt/audit models, config thresholds, `deps.py` (no auth), routes (write-path + presence + review endpoints), `ResolutionPanel`/`Conflicts`/`Timeline`/`LiveAnalysis`, model metadata + artifacts, `.env.example`, live docs inventory, 6B/6C live-PG test logs from prior phases, NC validation reports with stated weak-label limits.

AUDIT STATUS: COMPLETE
CODE CHANGES: NONE
PRODUCTION BEHAVIOR CHANGED: NO
