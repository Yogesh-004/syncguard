# SyncGuard Current Functionality Audit
**Date:** 2026-08-31 | **Commit:** pre-benchmark | **Auditor:** automated inspection | **Location:** `D:/01_Projects/Syncguard`

> Audit before any benchmark integration. Classifies every module as *implemented / partially / mock-demo / broken / missing* and records call-graph connectivity.

## 1. Backend Architecture (current)

- **Stack:** FastAPI (lifespan), Pydantic, SQLAlchemy 2.0, Postgres 16 (fallback `sqlite:///./test_local.db`), Alembic `001_initial`, Redis (optional), Celery 5.3, Pandas, RapidFuzz, HTTPX, struct logging, CORS *, healthcheck.
- **Layers:** `api/routes.py` (thin but ~400 LOC, mixed concerns) → `services/` → `connectors/` → `db/models.py` (11 tables) → `workers/celery_app.py`.
- **Startup:** `main.py` lifespan `init_db()` with Postgres→sqlite fallback on auth failure; request-id middleware; unhandled exception handler.
- **Config:** `core/config.py` via `pydantic-settings`, `.env` → `DATABASE_URL`, `REDIS_URL`, `CORS_ORIGINS=*`.

## 2. Implemented (works, tested)

| Area | Evidence | Tests |
|------|----------|-------|
| **Normalization** deterministic, testable, documented | `services/normalization.py`: `normalize_name` (upper+ws), `normalize_phone` (+1/+91/00 handling), `normalize_email` (lower+trim only, safe), `normalize_date` (multi-format), `normalize_address` (conservative), `normalize_numeric` (currency stripping), `normalize_record`, `deterministic_hash` | `tests/unit/test_normalization.py` 8 passed |
| **Matching** 4-stage | `services/matching.py`: exact/prefix/suffix/contains + `fuzzy_match` RapidFuzz, `compute_score` weighted `Σ(score*weight)/Σweights`, `find_matches` O(n²), `find_entity_groups` union-find, `evidence` per field | `test_matching.py` 6 passed (exact, fuzzy, compute, empty) |
| **Reconciliation** in-memory | `services/reconciliation.py`: `detect_conflicts` (missing/mismatch/type_error), `assess_risk` (critical/high/medium/low), `auto_resolve` (≤1 conflict, no type_error), `resolve_conflict`, `run_reconciliation` (groups→conflicts) | `test_reconciliation.py` 5 passed |
| **Schema drift** in-memory | `services/schema_analyzer.py`: `register_schema`, `detect_drift` (added/removed/type_changed), `analyze_schema`, `validate_record` | `test_schema_analyzer.py` 3 passed |
| **Audit** | `services/audit.py`: buffered `AuditService.log` → `audit_logs` table, `flush`, `get_logs`; used in conflict resolve | — |
| **DB models + migrations** | `db/models.py`: sources/records/schemas/matches/conflicts/resolution_logs/reconciliation_jobs/sync_jobs/attempts/sync_attempts/audit_logs with FKs, UNIQUE idempotency_key, indexes; `database.py` fallback; `alembic/versions/001_initial.py` (`Base.metadata.create_all`) | — |
| **Connectors** extensible | `connectors/base.py` implicit via CSV/JSON/REST each `read/read_all/write/validate`; CSV `DictReader`, JSON/REST handle dict/list variants | — |
| **Workers** | `workers/celery_app.py` (broker Redis, late ack), `workers/tasks.py`: `reconcile_task`, `match_task`, `sync_task`, `schema_check_task` with `_backoff` jitter, max_retries 5, progress states | — |
| **API** health + CRUD | `GET /health` 200, `GET /`, `/docs` 200; `POST/GET/DELETE /sources`, `POST /uploads` (sanitize, ext, size 5 MB, magic), `POST /reconciliation` 202 with Idempotency-Key dedup, `GET /reconciliation/{id}`, `POST/GET /jobs`, `GET /schemas`, `GET /audit-logs`; TestClient `client` fixture with `with TestClient(app)` | `tests/integration/test_api.py` 3 passed (health/root/docs) |
| **Seed live data** | `scripts/seed_live.py` creates CRM/ERP/Accounting overlapping Ravi Kumar spec + 20 random, matches 3, conflicts 3, jobs completed | verified `GET /records` 29, `/conflicts` 3 |
| **Frontend** dev | Vite 6.4 + React 19 + Recharts + axios; `App.tsx` routes `/`, `/dashboard`, `/live`, `/records`, `/matching`, `/conflicts`, `/sources`, `/jobs`; `Dashboard` fetches live `/records|conflicts|jobs` with fallback `demo.json`; `Landing` static hero; `LiveAnalysis` FormData upload → 202 polling; build succeeds 692 kB | — |

## 3. Partially Implemented (exists but incomplete or not wired)

| Area | Gap |
|------|-----|
| **Reconciliation persistence** | `ReconciliationEngine.run_reconciliation` returns dict but `routes.py` `POST /reconciliation` creates `ReconciliationJob` then `reconcile_task.delay` → fallback inline `status=processing` without persisting matches/conflicts via that path; seed bypasses engine for demo matches. |
| **Schema drift endpoint** | `GET /schemas/drift` returns static `SchemaDriftReport(source_id, 1,2, drifts=[],0)` — never reads `SchemaModel` versions, no `added/removed/renamed` from real tables, no `transaction_amount` detection live. |
| **Conflict detail** | `GET /conflicts/{id}` now returns fixed `field_name/conflict_type` mapping but seed used legacy keys; evidence shape not uniform with PRD. |
| **Records pagination** | `PaginatedResponse` schema exists but route now returns raw dict `{"total", "page", "items": [...]}` — not validated via `response_model`, loses OpenAPI typing. |
| **Jobs sync** | `SyncJobModel` created in seed with `failed HTTP 500` but `/jobs` lists only `ReconciliationJobModel`; sync jobs not exposed via API. |
| **Rate limiting / auth** | No `slowapi`, no JWT; `core/security.py` not present despite `python-jose` in requirements. |
| **Performance harness** | `benchmarks/matching/benchmark_matching.py` synthetic only (10–200 records, random), not 1K/10K/100K with corruption or P/R/F1. |
| **Dataset adapters** | None — FEBRL3 / Walmart-Amazon schemas not mapped to canonical `entity_id/name/email/phone/address` model. |

## 4. Mock / Demo (fabricated values, not live)

| File | Hard-coded |
|------|------------|
| `frontend/public/demo.json` | `records_processed:3247`, `matches:892`, `conflicts:47`, `auto_resolvable:31`, `schema_changes:2`, `failed_sync_jobs:3`, `health:94.2%`, `match_rate 86.4%` — labeled static but displayed as primary metrics in `Dashboard` before live fetch. |
| `frontend/src/pages/Dashboard.tsx` | fallback `d = demo || {…}` with same fake numbers if API fails; pie/bar charts from demo, not benchmark. |
| `data/demo/records.csv/json` (100 rows) | synthetic `555xxxxxx` phones, not FEBRL3 ground truth; `gen_demo.py` random, no duplication links. |
| `api/routes.py` `validate_csv/json/rest` | file validation returns synthetic `{"valid":True,"record_count":…}` without reading DB. |
| `docs/architecture.md` etc | Describe blocking/indexing not implemented. |

**Action required §22:** after benchmark pipeline, remove unlabeled hard-coded KPIs from live mode; keep demo but label `DEMO DATA`.

## 5. Broken (fails or validation error before fix)

| Bug | Root | Fixed? |
|-----|------|--------|
| `GET /records` 500 `Unable to serialize unknown type: RecordModel` | `response_model=PaginatedResponse` with `list[Any]` cannot serialize SQLAlchemy ORM | **Fixed 2026-08-31** → route now returns manual dict with isoformat dates |
| `GET /conflicts` 500 `ResponseValidationError: missing field_name/conflict_type` | seed `conflicting_fields` used `{"field":…,"type":…}` vs `ConflictField` expects `field_name` + `conflict_type` | **Fixed** → route normalizes legacy keys; seed should be rewritten to canonical |
| `alembic revision --autogenerate` empty | `target_metadata=None` and Postgres auth failure | Fixed with manual `001_initial.py` (`Base.metadata.create_all`) + sqlite fallback |
| `python -m ruff` not installed on runner | `dev` extra not installed | Not required for audit |
| Frontend `Landing.tsx` `Demo` unused import + `LiveAnalysis` `s` unused | tsc error | Fixed |

## 6. Missing (required for §1–33, not present)

- `data/benchmarks/febrl3/`, `walmart_amazon/`, `amazon_google/` (no download script)
- `data/benchmarks/manifest.yaml`, `data/benchmarks/README.md` (provenance)
- `scripts/download_benchmarks.py` (reproducible pipeline)
- `docs/benchmark-data-profile.md`
- Canonical `benchmarks/adapters/` (FEBRL→SyncGuard, product→SyncGuard)
- `benchmarks/config.yaml` (seed, splits, thresholds, weights)
- `benchmarks/run.py` (`--dataset febrl3 --model syncguard`)
- `benchmarks/results/febrl3.json`, `walmart_amazon.json`, `summary.md` + confusion matrices
- `docs/error-analysis.md`, `docs/validation-report.md`
- ML baseline (logistic regression / XGBoost) — `scikit-learn` not in `requirements.txt`
- Threshold curves (0.50–0.95) + precision-recall
- Leakage checks (duplicate pairs across splits)
- Controlled schema-drift tests (rename/remove/add/type)
- Mock external API for sync failure matrix (200/400/401/404/409/429/500/timeout)
- Frontend benchmark mode — currently no `?mode=benchmark` vs demo
- `SECURITY.md`, `CONTRIBUTING.md` stub (exist but minimal)

## 7. Endpoints: real vs mock/static

| Endpoint | Status |
|----------|--------|
| `GET /health`, `GET /`, `GET /docs` | real |
| `POST /sources`, `GET /sources`, `GET /sources/{id}`, `DELETE` | real (DB) |
| `POST /uploads` (multipart) | real (sanitize, ext, size, json parse) |
| `POST /reconciliation` 202 | real but worker fallback inline, not fully persisted |
| `GET /reconciliation/{id}` | real (DB) |
| `GET /records` | real (after fix) |
| `GET /match`, `GET /entity-groups` (legacy) | mock — returns empty `find_matches([])` unless payload |
| `GET /conflicts`, `GET /conflicts/{id}` | real (DB) after fix |
| `POST /conflicts/{id}/resolve`, `/reject` | real (writes `ResolutionLogModel` + `AuditLogModel`) |
| `GET /schemas`, `GET /schemas/{id}` | real (DB) |
| `GET /schemas/drift` | **mock** static `[]` |
| `GET /jobs`, `GET /jobs/{id}` | real |
| `GET /audit-logs`, `GET /audit` | real |
| `GET /connectors/*/validate` | real but file-system only |

## 8. Frontend components

| Page | Real | Mock |
|------|------|------|
| `Landing` | static hero, architecture text (demo.json) — intended mock, OK | Hard-coded stats not labeled “demo” before fetch |
| `Dashboard` | fetches live `/records|conflicts|jobs|schemas|sources` + fallback demo — now live-aware after patch | Charts use demo `match_rate` etc until benchmark metrics wired |
| `Records` | now live table from `/records` (was `useQuery('/records')` with `No records`) | filter local only |
| `Conflicts` | now live list + resolve buttons POST (was `<pre>` dump) | diff view not side-by-side per PRD |
| `Jobs` | shows `status/progress` polling (was stub) | — |
| `Matching`/`Sources` | stub forms | — |
| `LiveAnalysis` | FormData → `/uploads` → `/reconciliation` → 202 polling (demo staged loader) | progress is simulated `Math.random()*18` not real job progress |

## 9. TODOs / Incomplete Methods

- `backend/app/utils/helpers.py` `parse_connection_string` not used by connectors; `retry_on_failure` not used by `rest_connector`.
- `reconciliation.py` `auto_resolve` heuristic `len(conflicts)<=1` overly permissive; no per-field severity.
- `schema_analyzer.validate_record` only checks missing `nullable=False`, not type/unique.
- `workers/tasks.py` `_backoff` not unit-tested; `reconcile_task` takes `job_id` but `routes.py` previously called `delay(str(source_ids), [])` mismatch (now fixed to `job_id`).
- No `pytest` for jobs/retry, CSV/REST, or idempotency duplicate.

## 10. Risk Matrix for Benchmark Integration

| Risk | Impact | Mitigation |
|------|--------|------------|
| FEBRL3 `load_febrl3` requires `recordlinkage` not in `requirements.txt`; version pin may break | pipeline not reproducible | Pin `recordlinkage==x.y`, add to `backend/requirements.txt`, script with `pip install --quiet` check |
| Walmart-Amazon license redistribution unclear | legal | Do not commit raw CSV; `download_benchmarks.py` with `requests` + checksum, `manifest.yaml` `license: needs_verification` |
| Schema mismatch: FEBRL fields (`given_name`,`surname`,`street_number`,`address_1`,`date_of_birth`…) vs SyncGuard `name/email/phone` | hard-coded adapter breaks | Build `benchmarks/adapters/febrl.py` → canonical `Record{entity_id,name,email,phone,address,dob,source}` extensible, no engine coupling |
| O(n²) `find_matches` on 5K FEBRL3 (12.5M pairs) OOM/slow | benchmark infeasible | Add blocking (e.g., `surname` prefix, `postcode` blocking) + chunking, measure `matching time` vs `blocking time` |
| Leakage via `rec_id` split | inflated F1 | Deterministic split by `entity_id` not pair, check `duplicate pairs` via `true_links` overlap |
| Threshold tuning on test | fake accuracy | Freeze threshold on validation only, report `threshold curves` on validation, `benchmarks/config.yaml` records `random_seed` |
| Frontend hard-coded KPIs mistaken as benchmark | demo/bm mixing | §22: live mode must query `benchmarks/results/*.json`; label demo `DEMO DATA` |

## 11. Files That Will Need Modification (benchmark phase)

`backend/requirements.txt` (+recordlinkage, scikit-learn, deepmatcher optional), `backend/app/services/matching.py` (blocking, threshold param), `backend/app/utils/helpers.py` (canonical model), `benchmarks/` (`run.py`, `config.yaml`, `adapters/`, `results/`), `scripts/download_benchmarks.py`, `data/benchmarks/` (manifest, README), `docs/` (profile, error-analysis, validation-report), `frontend/src/pages/Dashboard.tsx` (benchmark mode), `backend/tests/` (regression for drift/sync failure).

## 12. Proposed Architecture Until Audit

No architecture change yet — audit complete. Next steps per “FIRST STEP” A–I follow.
