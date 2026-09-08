# Phase 4 Audit — Full System

Date: 2026-09-06. Baseline: Phases 1–3 (106 tests passing, live backend :8000 + frontend :3000).

## Component verdicts
- backend/FastAPI: WORKING (thin-ish routes, Pydantic validation, request-id, generic 500 handler). PARTIAL: `/schemas/drift` static; upload silently truncates >10k rows; 500-record job cap silent.
- frontend: WORKING (live API everywhere, DEMO-labeled fallbacks). STATIC (correctly isolated): `demo.json` (Landing/Dashboard fallback), `benchmark-results/*.json` (Benchmarks page only). No secrets found.
- database: WORKING (FKs, UNIQUE idempotency, indexes). PARTIAL: historical NULL `match_id` (documented); sqlite fallback hides postgres outages in logs but keeps running.
- workers: PARTIAL — Celery configured but no broker in dev; inline pipeline is the real path; `sync_task`/`match_task` never invoked with real data (dead-ish, kept for prod wiring).
- model: WORKING (persisted pickle + metadata + ModelService). INFO: pickle of own artifact (documented limitation, not remote input).
- matching: WORKING but SLOW — O(n²) within source, cap 500/job (~11s/500 recs measured earlier). No blocking in live path (benchmark path uses postcode blocking).
- conflict detection: WORKING (field-level, normalization-aware).
- resolution: WORKING (validation, idempotency, 409 concurrency guard).
- connectors: ingestion-only CSV/JSON/REST + MOCK writer. No real external writer (honest).
- sync jobs: WORKING via mock (retry taxonomy, idempotency, verification).
- audit: WORKING (append-only, per-conflict trail).
- configuration: PARTIAL — thresholds centralized (Phase 2.1); no MAX_JOB_RECORDS; SECRET_KEY default value; CORS `*`; DEBUG flag exists.
- tests: 106 passing. MISSING: data-quality suite, schema-drift tests, perf numbers, failure matrix beyond 400/500, concurrency proof, transaction tests.
- Docker: WORKING (non-root, healthcheck on /health). `.env.example` sane.
- env vars: documented; SECRET_KEY placeholder must be overridden in prod.

## Attention items (spec list)
1. O(n²): confirmed, measured in 4H. 2. 500-cap: silent truncation confirmed in `POST /reconciliation` (`q.limit(500)`) and uploads (10k slice) — must error or flag, not truncate. 3. Phone US assumption: confirmed, documented in conflict-rules; needs configurable handling decision (4C). 4. Legacy records: pre-Phase-2 matches lack decision; old conflicts lack match_id — quarantined, not migrated. 5. Thresholds: centralized Phase 2.1; selection evidence exists (validation curve) — needs clean re-report (4L). 6. Schema validation on upload: only ext/size/parse — missing header/row/type checks. 7. Upload validation gaps: listed in 4G. 8. API validation: good (Pydantic + 404/422/409); needs ownership tests (4W). 9. Errors: generic 500 handler good; resolve/push return structured errors; must verify no traceback leaks. 10. Transactions: resolve commits resolution+audit atomically (good); pipeline commits progressively (job row first, then results — crash leaves PROCESSING; needs recovery note/test). 11. Worker failure: inline path has no stuck-PROCESSING (exception→FAILED); Celery path untested without broker (documented). 12. Redis failure: no broker in dev — routes fall back to inline (good); Celery tasks untested live (NOT TESTED honestly). 13. Model failure: 503 + FAILED (good). 14. Connector failure: classified retryable/non-retryable (good; extend matrix). 15. Audit consistency: append-only (good); verify no SUCCESS-on-failure. 16. Idempotency: resolutions + push covered; dry-run idempotent via job lookup; retry bounded. 17. Concurrency: resolve guarded; push guarded; needs explicit parallel test. 18. Sensitive logging: logs carry ids/counts, no record values seen; verify + fix if found.

## Plan
B: data-quality suite. C: normalization tests + phone decision (configurable default-country? minimal: document + add `PHONE_DEFAULT_REGION` config used by normalize_phone instead of hardcoded +1 — safe, backward compatible for existing data? Changes future normalizations only; document). D–F: schema service hardening + versioning + upload integration. G: upload hardening. H–J: perf measure, blocking eval, configurable cap. K–M: eval + thresholds + error analysis docs. N–O: edge tests. P–U: transaction/worker/sync/concurrency/idempotency/audit tests. V–Y: security review + fixes + health. AB–AF: isolation, e2e, lineage. AG–AI: reports. AJ–AK: regression + flows.
