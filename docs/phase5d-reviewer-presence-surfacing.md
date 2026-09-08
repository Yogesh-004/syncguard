# Phase 5D — Reviewer-Facing Presence Surfacing

> Presentation/integration only. No matching, blocking, normalization, evidence, thresholds, auto-resolution, synchronization, lifecycle, connector, rollback, source-priority, Celery, model, or deployment changes. Persisted presence flows: database → existing conflict detail API → existing conflict detail panel, in neutral scope-relative wording.

## 1. Scope

Surface persisted `presence_observations` in the existing reviewer experience with zero decision impact: backend adds a read-only `presence` block to the existing conflict detail endpoint; frontend renders a compact informational block in the existing conflict detail panel. No new pages, dashboards, queues, or actions.

## 2. Existing review surfaces inspected

- Queue: `GET /conflicts` → `frontend/src/pages/Conflicts.tsx` list (ID • Entity • Field • Source↔Target • Risk • Conf • Status).
- Detail: `GET /conflicts/{id}` → same page's detail panel + `ResolutionPanel.tsx` (existing resolve/dry-run/push actions, untouched) + `Timeline.tsx` (reads `GET /conflicts/{id}/audit`, untouched).
- Match detail: `GET /matches/{id}` (inspected; left unchanged — conflict detail is where reviewers decide).
- Audit: `GET /conflicts/{id}/audit` filters entity types conflict/resolution/sync_job; presence audit rows are intentionally NOT merged in (no fake audit events; observation ≠ reviewer decision).

## 3. Files/components/endpoints changed

- `backend/app/api/routes.py`: new `_presence_for_records` helper (job-scoped read-only lookup, latest-row-wins ordering for determinism) + `presence: {record_a, record_b}` block on `GET /conflicts/{conflict_id}`. List endpoint, resolve/reject/dry-run/push endpoints untouched.
- `frontend/src/pages/Conflicts.tsx`: new `Presence` component (compact block, existing style) rendered in the detail panel between `ResolutionPanel` and `Timeline`; renders nothing when both slots are null (no frontend inference, ever).

## 4. How persisted presence is retrieved

`_presence_for_records(db, job_id, [record_a_id, record_b_id])` queries `presence_observations` filtered by the conflict's own job_id AND the record ref, ordered by id desc. Backend/database remains the sole source of truth; the frontend never computes presence.

## 5. How presence is displayed

Per record: state token + basis + approved neutral explanation + scope line (sources, snapshots, per-side completeness). Example (ONLY_IN_A): "Present in Snapshot A; no corresponding record was observed within Snapshot B's declared scope. This does not mean the entity was deleted." Header labels the block "informational only".

## 6. Neutral terminology used

Exact approved copy from `explanation_for` (Phase 5C implementation). Banned tokens (`deleted/created/removed/new/inactive/churn/should delete/should insert`) verified absent from all surfaced state/basis strings and directive-free explanations; the word "deleted" appears only inside the mandatory "does not mean…" negation.

## 7. Scope/completeness enforcement

Every surfaced observation carries its scope and per-side completeness; the scope line is rendered with the state (a state without scope is unrepresentable by construction). Completeness-gated `UNKNOWN` rows surface with their basis (e.g. `PARTIAL_INGESTION`) and stored completeness values.

## 8. Cross-job isolation

Lookup filters strictly on the conflict's own job_id; observations from other jobs are never surfaced (tested: foreign-job rows exist yet detail shows only own-job rows). Missing rows surface as `null` per slot — displayed as nothing, never manufactured.

## 9. Tests added

`backend/tests/unit/test_phase5d_surfacing.py`: 12 tests covering brief items A–N (BOTH/ONLY_A/ONLY_B/UNKNOWN display, completeness gating, cross-job isolation, missing-observation nulls, decision/risk invariance, no auto-resolution, existing resolve action works, no sync side effects, neutral wording scan, queue endpoint unchanged). 12/12 pass.

## 10. Full test count

309/309 backend tests pass (297 pre-existing + 12 new), zero regressions.

## 11. Frontend build result

`npm run build` (tsc -b + vite build): PASS in 13.28s, 719 modules transformed. Only pre-existing chunk-size warning.

## 12. Real-data regression result

Same Phase 5B sample keys (760 overlap + 1,000 + 1,000 singletons, same seeds): 2,760 observations persisted and retrievable — BOTH_PRESENT 760, ONLY_IN_A 1,000, ONLY_IN_B 1,000, UNKNOWN 0 (expected: complete-scope sample; UNKNOWN paths covered by gated tests), audit rows 2,760 (1:1), zero lifecycle-token hits. Pipeline-produced states flow through the new lookup shape unchanged.

## 13. Matching regression result

None. Matching/blocking/decision/conflict code untouched; conflict decisions and risk verified byte-identical before/after presence seeding; full suite green; incorrect automatic merges remain 0.

## 14. Synchronization side-effect result

Zero: no sync jobs reference surfaced comparisons; no new write paths; presence block is read-only; resolve/push flows operate exactly as before.

## 15. Limitations

Entity presence stays null at wire time (record-level display only); Celery comparisons carry no observations (nothing to surface); queue list rows show no presence badges (detail-only by design, avoiding per-row joins at list scale); UNKNOWN appears only via gated paths, not in complete-scope samples.

## 16. Decision

ACCEPTED — persisted presence is now reviewer-visible in the existing conflict detail experience as neutral, scope-bound, informational-only observations with no decision, risk, resolution, or synchronization impact, verified by 12 new tests, a 309/309 suite, a passing frontend build, and a clean real-data regression.
