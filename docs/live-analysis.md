# Live Analysis (Phase 1)

## Modes
- `demo`: `frontend/public/demo.json` — Landing/Dashboard fallback only, labeled.
- `benchmark`: `benchmarks/run.py` + `benchmarks/results/*.json` — Benchmarks page only.
- `live`: `POST /uploads` + `POST /reconciliation` + `GET /jobs/{id}/results` — Live Analysis page only. Never reads demo/benchmark files; verified by tests 11–12.

## Flow
1. `POST /uploads` (multipart CSV/JSON, ≤5MB/10k, `utf-8-sig`) → validates → creates `Source(live:true)` → parses → `normalize_record` → stores `RecordModel` → returns `source_id, record_count`.
2. `POST /reconciliation {source_ids}` → 503 `Model unavailable` if artifact missing (no demo fallback) → creates `ReconciliationJobModel(queued)` → inline ML pipeline (or Celery if broker): `LIVE_DATA_VALIDATED` → `FEATURE_GENERATION_STARTED` → `ModelService.load_model` → `INFERENCE_STARTED/COMPLETED` → persists `MatchModel(entity_group_id=job-{id}, match_method=ml)` + `ConflictModel` → `RESULTS_PERSISTED` → `completed` (or `failed` with error). Returns `{job_id, mode:live, model_version}` (202).
3. `GET /reconciliation/{id}` → truthful `{status, progress}` (queued/processing/completed/failed).
4. `GET /jobs/{id}/results` → `{mode:live, model_version, records_processed, matches_found, matches[], conflicts}` — all from DB.
5. Frontend polls status then fetches results; displays Model/Mode/Input/Job + counts. No simulated percentages.

## DB traceability
`AnalysisJob(reconciliation_jobs)` → `LiveInput(records by source_id)` → `Prediction(matches by entity_group_id=job-{id})`. Every match/conflict carries `confidence`, `evidence.ml_prob`, `model` string; job carries `source_id`, `total/processed`, `idempotency_key`.

## Run locally
Upload `data/live_test/unseen_customers.csv` via Live Analysis (or `POST /uploads`), note `source_id`, `POST /reconciliation`, poll `GET /reconciliation/{id}`, fetch `GET /jobs/{id}/results`. Delete source in Live Analysis to restore benchmark view.
