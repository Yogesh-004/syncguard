# SyncGuard — a safety layer for cross-system record reconciliation

**SyncGuard turns uncertain matching into explainable, reviewable, and verified data changes.**

> Match → evidence → contradiction-aware decision → human review → dry-run → approved PostgreSQL synchronization → verification → audit. Presence observations (`BOTH_PRESENT` / `ONLY_IN_A` / `ONLY_IN_B` / `UNKNOWN`) stay orthogonal to identity — absence is never a lifecycle claim.

## 1. Product

Small-team data stacks reconciling customer records across two systems: upload both extracts, review likely matches with field-level evidence, resolve conflicts, dry-run the exact mutation, confirm the write to a controlled PostgreSQL target, and prove verification + audit lineage.

CORE: reconciliation, ML matching, evidence, conflict review, presence observations, human resolution, dry-run, controlled PostgreSQL sync, verification, audit.
SUPPORTING: schema drift, CSV/JSON/REST ingest.
NOT PRODUCTIZED: REST writes, golden records, lifecycle semantics, enterprise MDM/RBAC, generic observability, arbitrary SQL sync.

## 2. Core workflow

Sources → normalization → candidate blocking → ML matching → evidence → contradiction-aware decision → human review → dry-run → approved sync → verification → audit.

## 3. Synchronization safety

Explicit approval, dry-run before push, version-guarded transactional writes, stale rejection, target-side idempotency with collision protection, concurrency claim guards, read-back verification, verify-before-retry unknown-outcome handling, full audit lineage. See `docs/phase6b-controlled-postgresql-connector.md` and `docs/phase6c-transient-failure-hardening.md`.

## 4. Validation (honest)

- Real public NC voter-registration data; temporal validation across two snapshots: MATCH recall 0.9947, zero incorrect automatic merges in tested datasets.
- Weak voter-ID labels used throughout — a stated limitation, never ground truth.
- Email/phone contradiction paths are synthetic-only (fields absent from the public data).
- 50K-scale not validated; pairwise cost guarded by `MAX_JOB_RECORDS=2000`.
- Never "accuracy": validated recall and zero incorrect automatic merges in the tested datasets.

## 5. Model provenance

LogisticRegression matcher (`backend/app/models/febrl3_ml.pkl`, v1.0.0) trained on FEBRL3 links plus DeepMatcher-packaged Walmart-Amazon product records — product data contributed to training, so person-record behavior rests on the voter validation above, not on training-domain claims. Thresholds: MATCH 0.6, POSSIBLE 0.5 (frozen; never tuned on validation labels).

## 6. Security

Application-level API key (`API_KEY` env → `X-API-Key` header; unset means development-open, logged at startup). Production refuses placeholder `SECRET_KEY`. Source `connection_string` accepted on input, never returned by the API or logs. Parameterized SQL only; no secrets in audit metadata. This is application auth, not enterprise identity/RBAC.

## 7. Setup

```bash
python -m venv .venv && source .venv/bin/activate  # runtime verified on Python 3.9
pip install -r backend/requirements.txt
cp .env.example .env  # set DATABASE_URL, SECRET_KEY, API_KEY
alembic upgrade head  # deploy step: migrations, then boot (boot also self-creates tables)
uvicorn backend.app.main:app --reload --port 8000  # production honors $PORT (default 8000)
cd frontend && npm install && npm run dev
```

Production frontend build (backend URL baked at build time):
```bash
cd frontend && VITE_API_URL=https://<backend-host> npm run build  # serve dist/ statically
```
Development needs no VITE_API_URL (Vite proxies `/api` → localhost:8000).

Controlled PG write target (local disposable Postgres, see Phase 6B report):
`SYNCGUARD_PG_TARGET=postgresql://USER@HOST:PORT/syncguard_target`.

Production database: any standard managed PostgreSQL works through `DATABASE_URL`
(Supabase PostgreSQL is a compatible target: no extensions, no SDK, no special
pooling required — plain SQLAlchemy/psycopg2 with `pool_pre_ping`; append
`?sslmode=require` to the DSN when the provider mandates TLS). No Redis/Celery
required for the core product.

## 8. Testing

`python -m pytest backend/tests/ -q` (360 tests: matching, decisions, conflicts, presence, sync, PG connector, unknown-outcome, security). Frontend: `cd frontend && npm run build`. Live E2E: upload → reconciliation → conflict → resolve → dry-run → push → verify.

## 9. API

OpenAPI at `/docs`. Key endpoints: `POST /sources` (+ list/get/delete), `POST /uploads`, `POST /reconciliation`, `GET /conflicts`, `GET /conflicts/{id}` (+ resolve/reject/resolutions/audit), `GET /matches`, `POST /resolutions/{id}/dry-run|push`, `GET /sync-jobs/{id}` (+ `review` outcome block), `POST /sync-jobs/{id}/retry`, presence endpoints, `/health`, `/readyz`. Legacy `/match`, `/matching/run`, `/reconcile` are superseded (kept, not product surface).

## 10. Deployment

Local Docker validated (Phase 8C): `docker compose up postgres syncguard` —
fresh PostgreSQL → `alembic upgrade head` → backend on `$PORT` (default 8000)
→ `/health` + `/readyz` green, model loaded, full reconciliation-to-verified-sync
E2E green. Set `ENV=production`, `SECRET_KEY`, `API_KEY` (placeholders refused).
No Redis/worker required for the core product (inline path). No public deployment
yet; Railway/Supabase/Render not connected.

## 11. Limitations

Single-tenant app-level auth only; no RBAC/SSO; no golden records; no lifecycle/deletion semantics; no bidirectional write-back or CDC; REST writes not productized; Celery presence unwired; single-county validation samples; unknown wall-clock network partitions covered by fault-injection-equivalent paths only.

## 12. Docs

Phase reports under `docs/`: product discovery/validation audits, real-data + temporal validation, 5A schema fix, 5B appearance/disappearance, 5C presence (design/implementation/wiring), 5D reviewer surfacing, 6A integration boundary, 6B PostgreSQL connector, 6C transient hardening, 6D outcome surfacing, release audit, and this phase's hardening report.

License: MIT. See `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`.
