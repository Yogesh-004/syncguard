# Phase 2 Audit — Matching + Conflict Detection

Date: 2026-09-06. Baseline: Phase 1 (ModelService v1.0.0, live inference working, job 9 evidence).

## How Phase 1 predictions are represented
`MatchModel`: id, record_a/b FK, confidence (=ml_prob), match_method='ml', matched_fields[], evidence{name,email,phone,ml_prob,ml_features,model}, entity_group_id='job-{id}'. Decision NOT stored explicitly (derived: confidence>=threshold → match). No model_version column (version only in evidence string + API).

## Matching service
`MatchingEngine(use_ml=True)` → `ModelService.load_model` (cached pickle) + `ModelService.featurize` (7 feats) → `predict_proba`. Rule `compare_field` kept for evidence ticks only. `find_matches(dicts, threshold=0.6)` O(n²) within source filter. No POSSIBLE_MATCH tier; single threshold.

## Matching DB model / record / source
As above + `RecordModel(data, normalized_data, source_id)`, `SourceModel(is_active, config{live,benchmark})`. Source records never mutated by matching (relationship only) — good.

## Frontend Matching page
Live: fetches `GET /match?threshold&source_id` + `GET /records`, side-by-side cards, ticks, threshold slider. Issues: uses compute endpoint (not DB-persisted matches), no search/filter/pagination, no per-match detail route, no decision label, no job badge.

## Conflicts page
Live: fetches `GET /conflicts` + records + audit preview, side-by-side, ticks, approve/reject/modify/defer buttons (Phase 3 workflows already wired — must keep but not extend). Issues: conflicts are grouped (up to 2 fields per row), not field-level; no per-conflict detail view; filters only risk/status.

## Conflict DB model
`ConflictModel`: record_a/b, match_id (NULL — never set!), confidence, conflicting_fields[] (array ≤2), evidence, risk (low if conf>0.8 else medium), recommendation (AUTO-RESOLVE/RECOMMEND), resolution_status pending/approved/..., auto_resolvable. Good base, but: match_id never populated (breaks traceability), grouped not field-level, no per-field original-value columns (uses generic values{a,b}), no job link except via record source.

## Generation status
Conflicts ARE generated (20 live) from inline pipeline, but grouped + match_id NULL + IDs (`rec_id`, `entity_id`) previously leaked (now filtered). Individual-field rows: MISSING.

## Confidence / field similarity
Confidence = ml_prob (real, reproducible). Field evidence = rule compare scores (real). Product-model feats (title_sim etc.) not used for FEBRL-style records — single FEBRL model serves all (documented limitation).

## Static/demo/benchmark mixing
`GET /match` without source_id returns benchmark-spanning pairs — isolated only by frontend `?source_id=`. No mode column. Dashboard demo fallback labeled. Benchmark JSON never imported by live pages (verified). Duplicate logic: `_featurize` now unified in ModelService (matching.py delegates) — old duplicate removed; `benchmarks/run.py:featurize` remains for training only (acceptable, documented).

## Categorization
WORKING: ModelService load/predict, normalization utils, live upload→isolated source, inline job pipeline, match persistence, grouped conflicts, resolve endpoint, audit trail, job isolation via source_id.
PARTIALLY: match decision (implicit only), evidence (rule+ML mixed, no field_scores map), risk (2-tier only), recommendation (2 values, no source-priority doc), conflict filtering (no job/field filter), frontend (no search/pagination/detail).
BROKEN: `match_id` NULL on all conflicts (traceability gap); conflicts grouped not field-level.
MOCK/STATIC: none in live path (verified). Demo/benchmark JSONs isolated to their pages.
DUPLICATED: featurize resolved; threshold 0.6 hardcoded in 3 route spots + frontend default.
MISSING: decision tiers, model_version column (use evidence+API), per-field conflict rows, conflict detail API/UI, job_id filter on /match & /conflicts, docs (matching-engine update, conflict-rules, conflict-data-model).

## Implementation plan
1. Config thresholds; decision fn in ModelService.
2. New `conflict_detection.py` service (field-aware, normalization-aware, null taxonomy, original values preserved).
3. Routes: wire service into pipeline (one row/field, match_id link, duplicate prevention, decision tiers persisted), add job_id filters + `GET /matches`, `GET /matches/{id}`, enrich `GET /conflicts/{id}` traceability, keep resolve untouched.
4. Frontend: Matching DB table + detail; Conflicts queue + detail; LIVE badges; no Phase 3 additions.
5. Tests (24), unseen e2e, perf note, docs.

## Phase 2.1 corrections (applied)
- Root cause of NULL match_id: pipeline persisted matches then generated conflicts without linking (match_id hardcoded None). Fixed: flush matches first, pass `match_id=mm.id`.
- Migration: `conflicts.match_id` FK already exists, nullable. No schema change required → no migration; historical NULL rows (seed data, match_id None) documented and excluded from job-scoped queries (they have no match link); all new rows carry valid match_id (test `test_new_conflicts_have_match_id`).
- Thresholds centralized: `core/config.py` is the single source (`MATCH_THRESHOLD=0.6`, `POSSIBLE_MATCH_THRESHOLD=0.5`, from validation F1 0.606/0.609); `model_service.decide`, `MatchingEngine.find_matches/find_entity_groups`, routes (`/match`, `/matching/run`, `/entity-groups`, worker `match_task`) all default from settings. Frontend no longer sends thresholds (Matching page is read-only DB).
- Matching page no longer calls compute (`/match?`, `matching/run` removed); Landing uses `GET /matches?decision=MATCH`. Verified by `test_no_recompute_frontend`.
- Python 3.9 compat: `X | None` annotations replaced with `Optional` (runtime env is 3.9).
