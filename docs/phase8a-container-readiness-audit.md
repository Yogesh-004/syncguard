# SyncGuard Phase 8A — Pre-Containerization Readiness Audit

> READ-ONLY. Zero code, Dockerfile, compose, config, or dependency changes. Findings verified against the repository, not assumed from reports.

## Executive Summary

The application is containerizable with small, well-bounded pre-work — no architecture rework needed. Proven facts: backend starts via uvicorn on the app module, creates its own tables on boot, runs the full product inline without Redis/Celery, loads its model from a package-relative path, logs to stdout, and exposes truthful health endpoints. The gaps are all at the container boundary: hardcoded port 8000 (Railway requires `$PORT`), no production frontend API-URL strategy (dev-only vite proxy), no `.dockerignore`, no migration execution step, untested Python 3.9→3.12 image jump, and a compose file whose app/redis services were never built here. Decision: **B — NEEDS SMALL PRE-CONTAINER CHANGES**.

## Repository Structure

| PATH | PURPOSE | REQUIRED AT RUNTIME? | CONTAINER IMPLICATION |
|---|---|---|---|
| `backend/app/` | FastAPI app, services, connectors, models | Yes | Copy whole package (models/ artifacts live inside) |
| `backend/app/models/*.pkl` | Shipped ML artifacts (~721B each, git-tracked) | Yes | Tiny; include in image, no download needed |
| `backend/requirements.txt` | Pinned-ish runtime deps | Build-time | Heavy tail (sklearn, recordlinkage, pandas, celery) → slow build |
| `frontend/` + `frontend/dist/` | React+Vite UI; `dist/` prebuilt | `dist/` only | Serve statically; no Node server needed |
| `Dockerfile` | Backend image (py3.12-slim, port 8000) | Build reference | Hardcoded port must become `$PORT` |
| `docker-compose.yml` | backend/postgres/redis/worker | Partially | Config valid; only postgres service verified here |
| `alembic/`, `alembic.ini` | Migrations (env.py reads `settings.DATABASE_URL`) | Deploy-time | Needs an explicit upgrade step; boot does NOT run it |
| `data/live_test/`, `benchmarks/` | Synthetic fixtures, harnesses | No | Exclude from image via `.dockerignore` |
| `scripts/` | Training/seeding/download utilities | No | Exclude; training script is not a runtime path |
| `docs/` | Phase/audit reports | No | Exclude from image |
| `test.db`, `test_local.db`, `*.log*` | Local sqlite + shell-redirect logs | No | Ephemeral; must not be copied or relied upon |
| `backend/tests/` | 367-test suite | No | Exclude from image |
| `.env.example` | Documented placeholders | Reference | No secrets present; verified clean |

## Backend Runtime

- Startup: `uvicorn backend.app.main:app`, workdir repo root, `CMD` bakes `--host 0.0.0.0 --port 8000` (compose + Dockerfile agree; `__main__` block also binds 0.0.0.0 — host binding OK, port hardcoded NOT OK for Railway).
- Port configurability: none — no `$PORT` support anywhere. Documented change required, not implemented.
- Python: `pyproject` demands >=3.12, image builds 3.12-slim, but the entire validated suite runs on local 3.9. The 3.9→3.12 behavior gap (notably sklearn/recordlinkage) is UNVERIFIED in-container.
- Lifespan: secret enforcement (production refuses placeholder key) → `init_db()`; shutdown is a log line (no drain logic — acceptable for the inline product).
- Health: `/health` (always 200), `/readyz` (truthful DB + model checks) — suitable as container healthchecks as-is.

## Frontend Runtime

- React 19 + Vite 6 (Node v22.13.1 present locally; no `engines` pin — minor).
- Scripts: `dev` (vite :3000), `build` (`tsc -b && vite build`, verified green), `preview`.
- API access: `VITE_API_URL || '/api'`; dev serves `/api` via vite proxy rewrite to `localhost:8000`. Production has NO `/api` serving strategy — static `dist/` output cannot reach the backend without either a build-time `VITE_API_URL` or a reverse proxy. This is the largest frontend-side pre-container change.
- Independently containerizable: yes, as static files (no SSR, no Node server required).

## Database & Migrations

- Engine: `DATABASE_URL` (default local postgres DSN; sqlite fallback `test_local.db` when PG unreachable).
- Boot behavior: `init_db()` runs `Base.metadata.create_all` — fresh containers start WITHOUT running alembic; tables self-create. Alembic (`env.py` bound to app metadata, URL from settings) is available but orphaned from startup — production Postgres needs an explicit `alembic upgrade head` step (missing today).
- No seed/demo data required; uploads live in DB rows, not on disk.
- Fresh-container failure modes: sqlite default is ephemeral (data lost on restart — must set `DATABASE_URL`); PG auth failure falls back silently to sqlite (documented behavior, dangerous if unnoticed — log it loudly at deploy).

## Redis / Celery

- `create_reconciliation` uses Celery ONLY if `CELERY_BROKER_URL`/`REDIS_URL` env vars exist; otherwise the proven inline path runs. No other endpoint requires the broker (presence, sync, retry all inline).
- Classification: Redis + worker = OPTIONAL (unused infrastructure for the current product); frontend polling works identically on inline jobs. Compose redis/worker services are VALIDATION/INFRASTRUCTURE ONLY for today's product. Excluded from the recommended architecture — do not pay for what the request path never touches.

## ML Model Artifact

- `backend/app/models/febrl3_ml.pkl` (+2 sibling artifacts, all ~721B, git-tracked), resolved via `Path(__file__).parents[1] / "models"` — fully relative, no absolute paths, no runtime download. Dockerfile `COPY backend/` includes it. Container-ready as-is provided the copy order keeps `backend/app/models/` in the image.

## Filesystem & Storage

- App writes: none to local disk (uploads parsed in memory → DB rows; logs to stdout via `StreamHandler`; no `/tmp`, no report files, no caches in app code). Root `*.log*`/`test*.db` files are shell/sqlite-fallback artifacts.
- Persistence required: only the database. Container-safe with `DATABASE_URL` pointed at managed Postgres; restart-safe except the sqlite fallback (ephemeral by nature).

## Environment Variables

| VARIABLE | USED BY | REQUIRED? | DEFAULT | SECRET? | PRODUCTION SOURCE |
|---|---|---|---|---|---|
| `ENV` | lifespan secret gate | No (defaults development) | `development` | No | Railway env: `production` |
| `API_KEY` | auth middleware (`X-API-Key`) | Yes in prod | Unset (open, logged) | Yes | Railway secret |
| `SECRET_KEY` | config (sessions/JWT-ready) | Yes in prod | Placeholder (refused in prod) | Yes | Railway secret |
| `DATABASE_URL` | SQLAlchemy + alembic | Yes | Local PG DSN w/ sqlite fallback | Credentials | Railway Postgres plugin |
| `REDIS_URL` / `CELERY_*` | Celery routing only | No | Unset → inline | No | Omit (excluded arch) |
| `CORS_ORIGINS` | CORS middleware | No | `*` | No | Restrict to frontend origin |
| `SYNCGUARD_PG_TARGET` | PG write-target connector | For real-write demo | Unset (mock path) | DSN-shaped | Railway secret or omit |
| `VITE_API_URL` | frontend build | For static prod | `/api` (dev proxy) | No | Build arg = backend URL |
| Thresholds/limits | matching/blocking | No | Frozen, must not change | No | Leave at defaults |

`.env.example` matches this table. No secrets are bundled into the frontend (only `VITE_API_URL`).

## Network & Ports

Backend 8000 (hardcoded), frontend dev 3000, PG 5432, Redis 6379 — all localhost assumptions in dev/proxy config. Docker networking requires: backend `$PORT`, frontend→backend via absolute URL or proxy, CORS narrowed from `*`. Inter-container names only matter if compose is used in prod (not recommended — see below).

## Existing Docker / Compose

- `Dockerfile`: valid structure (non-root user, layer-cached deps, HEALTHCHECK on `/health`), but base-image pull currently fails here (registry auth) and port is hardcoded.
- `docker-compose.yml`: config-valid; postgres:16 service verified live (healthy, connect, query); app/redis images unbuildable here → app + worker + redis = UNVERIFIED. Compose also omits any frontend service the README once claimed.
- No `.dockerignore` — image would ingest docs/benchmarks/tests/node artifacts.

## Dependency Audit

Runtime-heavy tail: scikit-learn, recordlinkage, pandas, celery, redis (all required at import by at least one module path; celery/redis imported but unused without broker env). System deps (`gcc`, `libpq-dev`) already in Dockerfile. Likely build risks: 3.12-vs-3.9 wheel behavior for recordlinkage/sklearn (UNVERIFIED), build time from pandas/sklearn compile (mitigated: slim + binary wheels). No version changes made.

## Railway Compatibility

- SUPPORTED NOW: 0.0.0.0 binding, `/health`+`/readyz`, stdout logs, env-driven config, secret refusal gate, relative model paths, DB fallback chain.
- REQUIRES CONFIGURATION: `PORT`, `DATABASE_URL` (plugin), `ENV=production`, `SECRET_KEY`, `API_KEY`, `CORS_ORIGINS`, `VITE_API_URL` build, alembic upgrade step, ephemeral-disk acceptance.
- REQUIRES CODE CHANGE: `$PORT` startup binding (small); frontend production API strategy (build-arg or proxy).
- UNVERIFIED: actual Railway Postgres connectivity, multi-service networking (avoided by recommended arch), 3.12 runtime behavior.

## Recommended Container Architecture

- A (single container): rejected — couples static UI with API, wastes rebuilds.
- B (static frontend + backend container + managed Postgres, NO redis/worker): RECOMMENDED — smallest architecture running the entire proven product; inline path needs no broker.
- C (B + redis + worker): rejected — pays for and operates infrastructure no request path uses.
- D: none justified.
- Missing prerequisites: the five MUST items below; nothing architectural.

## Critical Container Risks

- CRITICAL: hardcoded 8000 (Railway assigns `$PORT` — boot would fail readiness).
- CRITICAL: no production frontend→backend route (`/api` exists only via dev proxy).
- HIGH: 3.9-validated code shipping on a 3.12 image (ML-dep behavior gap).
- HIGH: silent sqlite fallback could mask a broken `DATABASE_URL` in prod.
- MEDIUM: no `.dockerignore` (bloated/leaky images); alembic never runs at boot (stale-schema drift on managed PG); CORS `*` default.
- LOW: Node unpinned; compose frontend-service myth in old docs (already corrected in README).

## MUST CHANGE

1. Bind backend port from `$PORT` (keep 8000 default) in startup command/config.
2. Define the production frontend API strategy (`VITE_API_URL` build arg or hosted reverse proxy for `/api`).
3. Add `.dockerignore` (exclude docs, benchmarks, tests, data, scripts, frontend/node artifacts).
4. Add an explicit `alembic upgrade head` deploy step (or documented equivalent) before backend start on managed PG.
5. Set production env (`ENV`, `SECRET_KEY`, `API_KEY`, `DATABASE_URL`, narrowed `CORS_ORIGINS`) with the refusal gates as backstop.

## SHOULD CHANGE

1. Align CI/dev Python with the 3.12 image (or pin image to a validated 3.9) and re-run the suite.
2. Loud startup banner echoing effective DB backend (PG vs sqlite fallback) to prevent silent misconfiguration.
3. Pin Node version for the frontend build.
4. Remove or correct stale compose claims (no frontend service; document compose as local-only).
5. Document the disposable-PG recipe irrelevance for prod (managed PG replaces it; `SYNCGUARD_PG_TARGET` optional).

## NOT REQUIRED

Redis/worker services, Celery changes, multi-stage builds beyond cache hygiene, Kubernetes manifests, CDN specifics, metrics platforms, migrations framework replacement, any product feature, threshold/model changes.

## Proposed Docker Implementation Plan

- `Dockerfile` (backend): `python:3.12-slim` (version decision per SHOULD-1) → workdir `/app` → install `backend/requirements.txt` → copy `backend/`, `alembic/`, `alembic.ini` → keep `appuser`, `EXPOSE` informational → `CMD` running `alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT` (shell form for expansion) → keep `/health` HEALTHCHECK.
- Frontend: `npm run build` at CI time; publish `dist/` as static hosting (no container needed; alternatively nginx-static only if a container is mandated).
- `.dockerignore`: `docs/ benchmarks/ data/ scripts/ frontend/ backend/tests/ **/__pycache__/ *.pyc .git .pytest_cache *.db *.log*`.
- Compose (local-only): keep postgres + backend; drop worker/redis unless Celery is ever adopted; add backend `depends_on` postgres healthy + `env_file`.

## Proposed Railway Deployment Plan

1. GitHub repo — READY (5 reviewable commits). 2. Railway project — REQUIRES 8B. 3. PostgreSQL plugin — REQUIRES 8B (wire `DATABASE_URL`). 4. Redis — NOT REQUIRED (excluded). 5. Backend service — REQUIRES 8B (`$PORT`, env, migrate step). 6. Frontend static deploy — REQUIRES 8B (`VITE_API_URL`). 7. Env vars/secrets — REQUIRES 8B. 8. Migrations — REQUIRES 8B (one-time + release hook). 9. Health check `/health` (+`/readyz`) — READY. 10. Smoke test (upload→reconcile→resolve→dry-run→push→verify on managed PG) — REQUIRES 8B execution only.

## Final Decision

**B. NEEDS SMALL PRE-CONTAINER CHANGES** — the product runs as-is locally with zero architectural gaps; every blocker is a bounded container-boundary item (port, API URL, ignorefile, migration step, env), none touching product behavior.

## Evidence / Commands Inspected

`main.py` (lifespan, middleware, `/health`, `/readyz`, bind), `config.py` (all settings + gates), `database.py` (`create_all` fallback chain), `routes.py:273` (broker-conditional Celery), `model_service.py:16` (relative artifact path), `logging.py` (stdout), `api-client.ts` + `vite.config.ts` (`/api` dev-only), `Dockerfile`, `docker-compose.yml` + `config` validation + live `postgres:16` smoke test, `alembic.ini`/`env.py`, both requirements manifests, `pyproject.toml` (py312 vs local 3.9), `.env.example`, `git log` (5 commits), full suite 367 green, frontend build green, Node v22 present, registry-blocked app build (honestly reported).

PHASE 8A STATUS: COMPLETE
CODE CHANGES: 0
DOCKER CHANGES: 0
DEPLOYMENT: NONE
RECOMMENDED ARCHITECTURE: Static frontend + single backend container + managed PostgreSQL; no Redis/worker
FINAL DECISION: B
