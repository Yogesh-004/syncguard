# Phase 1 Audit — Model Persistence + Real Live Inference

Date: 2026-09-06. Repository: D:\01_Projects\Syncguard. No code modified for this audit.

## Current architecture
FastAPI (`backend/app/main.py` lifespan + `api/routes.py` ~517 lines) → services (`matching.py`, `normalization.py`, `reconciliation.py`, `schema_analyzer.py`, `audit.py`) → connectors (csv/json/rest) → SQLAlchemy (11 tables, sqlite fallback `test_local.db`) → Celery tasks (fallback to inline when no broker) → React Vite (Landing, Dashboard, LiveAnalysis, Records, Matching, Conflicts, Sources, Jobs, Audit, Benchmarks).

Flow traced: `LiveAnalysis.tsx submit()` → `POST /uploads` (creates `Source(live:true)`, parses CSV/JSON, stores `RecordModel` with `normalized_data`) → `POST /reconciliation {source_ids}` (creates `ReconciliationJobModel queued`, tries Celery, else inline ML pipeline, persists `MatchModel` + `ConflictModel`, sets `completed`) → frontend polls `GET /reconciliation/{id}` → displays job JSON.

## Current model
`LogisticRegression(max_iter=300)` via scikit-learn. Features (7): name_sim (RapidFuzz ratio), pc_exact, ext_exact, suburb_sim, dob_exact, token_overlap, len_diff. Same `_featurize` duplicated in `benchmarks/run.py:featurize` and `backend/app/services/matching.py:_featurize` (compatible but duplicated — risk of drift). Default `MatchingEngine(use_ml=True)` loads pickle at import.

## Current training flow
`scripts/train_production_models.py`: FEBRL3 5K (6538 links) + Walmart-Amazon 10K + Amazon-Google 11K → `normalize_record` → blocking postcode → positives=all truth + sampled negatives → `LogisticRegression.fit` → pickle to `backend/app/models/{febrl3,walmart_amazon,amazon_google}_ml.pkl` + `*_meta.json` + `production_meta.json` with measured P/R/F1 (FEBRL3 P1.0/R0.76/F1 0.86 full-blocked; WA P0.87/R0.52/F1 0.65; AG P0.62/R0.25/F1 0.35). No feature scaler object (raw floats) — good (no scaler persistence needed). No preprocessing version pin.

## Current inference flow
`MatchingEngine.compute_score`: if `use_ml` and pickle loaded → `predict_proba` → confidence=prob + rule evidence for ticks. `find_matches(dicts, threshold=0.6)` O(n²) within source filter. Called from `GET /match`, `POST /matching/run`, and inline reconciliation. Model loaded once at import (`_ML_MODEL`), reused — good.

## Current live-data flow
`POST /uploads` parses CSV (`utf-8-sig` BOM fix present) → creates isolated `Source` → stores records. `POST /reconciliation` filters `RecordModel.source_id.in_(sids)` → `find_matches` → persists matches/conflicts with `entity_group_id=job-{id}`. Frontend sets `localStorage.activeLiveSourceId` and appends `?source_id=` to Records/Matching/Conflicts/Dashboard/Jobs. Training data stays in DB but hidden when live active. Correct in principle.

## Current benchmark flow
`benchmarks/run.py --dataset {febrl3,walmart_amazon,amazon_google} --model {exact,syncguard,ml}` → adapters (`febrl.py`, `walmart_amazon.py` → `CanonicalRecord`) → metrics P/R/F1 + threshold curve → `benchmarks/results/*.json` → copied to `frontend/public/benchmark-results/`. Official DeepMatcher zips present. `scripts/download_benchmarks.py` reproducible.

## Current database flow
`reconciliation_jobs(id, job_type, source_id str, status, progress, total/processed, idempotency_key UNIQUE)`; `records(source_id FK, source_record_id, data, normalized_data)`; `matches(record_a/b FK, confidence, match_method='ml', evidence JSON, entity_group_id)`; `conflicts(...resolution_status, evidence)`; `resolution_logs`, `audit_logs`. Live results traceable via `entity_group_id=job-{id}` and record `source_id`. No `mode` or `model_version` columns — gap.

## Current frontend flow
`LiveAnalysis.tsx`: upload → reconciliation → `setInterval` with `p + Math.random()*18` fake progress + staged labels, 9s timeout forces 100%. Polls only `GET /reconciliation/{id}` (status), never fetches `GET /match?source_id=` or `GET /conflicts?source_id=` results. Shows raw `JSON.stringify(result)` block (backend code as output). No `mode:LIVE` badge, no `model_version` display. `Dashboard.tsx`/`Landing.tsx` fall back to `demo.json` / hardcoded stats when API fails — perception leak (not API leak, but must label).

## Existing model artifact
`backend/app/models/`: `febrl3_ml.pkl` (729B), `walmart_amazon_ml.pkl`, `amazon_google_ml.pkl`, `*_meta.json` (features + measured metrics), `production_meta.json`. Independently loadable via pickle. No `model_version`, `artifact_hash`, `preprocessing_version` manifest. No `ModelService`.

## Existing bugs
1. Fake progress in `LiveAnalysis.tsx` (Math.random) — violates 1J (must show truthful QUEUED/PROCESSING/COMPLETED).
2. No `mode` field anywhere — demo/benchmark/live not machine-distinguishable (1B).
3. No `model_version` in API responses or DB (1E/1M).
4. `MatchingEngine` loads pickle at import with silent fallback to rules if missing — violates 1N (must FAILED, not fallback).
5. `POST /reconciliation` runs inline synchronously (11s for 500 recs) then returns 202 with `completed` — contracts says QUEUED then poll; currently blocks request (1J).
6. Live results never surfaced in LiveAnalysis page (only job JSON) — user can't see matches (1F/1L).
7. `GET /match` without `source_id` returns benchmark data — correct only if caller isolates; LiveAnalysis doesn't auto-link to results view (1H risk).
8. `Dashboard` demo fallback numbers (3247/892/47) shown without DEMO label on first paint (1H).
9. Duplicate `_featurize` (training vs inference) — must unify (1C).
10. No `data/live_test/unseen_customers.csv`, no phase-1 live test (1G/1P).

## Static/mock paths discovered
- `frontend/public/demo.json` (3247/892/47/94.2%) — used by Landing/Dashboard fallback. OK for DEMO only; must never be imported by `LiveAnalysis.tsx` (verified: not imported — good).
- `frontend/public/benchmark-results/*.json` — used by Benchmarks page only (verified not imported by LiveAnalysis — good).
- `frontend/public/test_model_sample.csv` — 20-row sample, overlaps training names (Mitchell Green) — NOT unseen.
- No `demo_results.json` returned by `POST /live-analysis` (no such endpoint; live uses `/uploads`+`/reconciliation` — good). No hardcoded match arrays in routes (verified).
- `GET /schemas/drift` returns static `drifts=[]` — out of Phase 1 scope, leave.

## Files that need modification
- `backend/app/services/model_service.py` (NEW): ModelService load/predict/metadata, single featurize source.
- `backend/app/services/matching.py`: use ModelService, remove silent fallback (raise on missing), keep rule compare for evidence only.
- `backend/app/models/model_metadata.json` (NEW): model_id/version/algorithm/datasets/feature+preprocessing versions/artifact hash/metrics.
- `backend/app/api/routes.py`: add `mode="live"`, `model_version` in reconciliation responses; truthful job states; no demo fallback on model failure (FAILED); add `GET /jobs/{id}/results` (matches+conflicts for job); structured logging markers.
- `frontend/src/pages/LiveAnalysis.tsx`: remove fake progress, poll real status, fetch+display live results (records/matches/conflicts counts + side-by-side sample), show mode/model_version/job_id, no demo/benchmark imports.
- `data/live_test/unseen_customers.csv` (NEW): truly unseen names.
- `backend/tests/unit/test_phase1_live.py` (NEW): 15 tests per 1P.
- `docs/model-inference.md`, `docs/live-analysis.md` (NEW).

## Files that should NOT be modified
- `scripts/train_production_models.py` (training works; only add metadata emission if trivial — else leave).
- `benchmarks/*`, `data/benchmarks/*` (frozen evaluation).
- `backend/app/db/models.py` (no schema change; use existing `entity_group_id` + `config` for traceability — add columns only if migration-safe; prefer not).
- Conflict resolution UI/logic, sync push, schema-drift workflow (Phase 2+).
- Docker, CI, auth (out of scope).

## Proposed Phase 1 implementation
1. ModelService + metadata + unify featurize.
2. Harden routes: mode, model_version, FAILED on model error, results endpoint, logging.
3. Rewrite LiveAnalysis frontend: truthful polling + live results display.
4. Unseen CSV + automated tests (15).
5. Docs + regression + evidence run.
