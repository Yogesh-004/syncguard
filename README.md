# SyncGuard — Your systems disagree. SyncGuard tells you why.

**Cross-system data reconciliation and integration reliability platform.**

> Detect data conflicts, schema changes, and sync failures across disconnected business systems — with explainable matching and auditable resolution.

[![Tests](https://img.shields.io/badge/tests-26%20passed-brightgreen)](#testing) [![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688)](#) [![React](https://img.shields.io/badge/React-Vite-61DAFB)](#)

Live demo (static, no backend needed) + Live Analysis (async jobs) — see [Deployment](#deployment).

---

## 1. Product Overview

SyncGuard ingests CSV/JSON/REST, normalizes deterministically, matches entities with explainable weighted scoring, detects conflicts, tracks schema drift, and provides reliable sync with retries/idempotency — all async via Celery+Redis and audited.

## 2. Problem

Same customer exists differently in CRM/ERP/Accounting (e.g., `Ravi Kumar` vs `RAVI KUMAR` vs `Ravi K.`, phone `+91 9876543210` vs `9876543210` vs `NULL`, schema `amount` → `transaction_amount`). Leads to duplicates, bad reporting, failed integrations, manual reconciliation.

## 3. Why It Matters

Inconsistent data causes revenue leakage, compliance risk, and ops toil. SyncGuard makes failures visible, explainable, and safely resolvable without silently overwriting.

## 4. Product Demo

- Explore Demo: static `frontend/public/demo.json` renders immediately (cold-start safe).
- Run Live Analysis: upload ≤5MB/10k CSV/JSON → 202 `{job_id}` → poll `GET /jobs/{id}` with staged loader.

## 5. Architecture

```
React (Vite, Recharts) static demo fallback
  → FastAPI thin routes → Services (normalization/matching/reconciliation/schema/sync/audit)
  → SQLAlchemy (Postgres/SQLite fallback) + Celery (Redis)
  → Workers with exponential backoff + DB UNIQUE idempotency
```
See `docs/architecture.md`.

## 6. Core Features

Ingestion (extensible BaseConnector), deterministic normalization, 4-stage matching, configurable weighted scoring, conflict detection, resolution (approve/reject/modify/defer + audit), schema drift, sync jobs with retries/idempotency, async jobs, dashboard.

## 7. Technology Stack

Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2.0, PostgreSQL 16 (SQLite fallback local), Alembic, Pandas, RapidFuzz, Celery+Redis, HTTPX, React+Vite+Recharts, Docker.

## 8. Matching Methodology

Exact identifiers → normalized comparison → fuzzy (RapidFuzz ratio, threshold 85) → weighted score `Σ(score*weight)/Σweights` (default name 0.4, email 0.3, phone 0.3). Every match stores `evidence` + `matched_fields`. Thresholds configurable ( >95 HIGH auto-resolve candidate, 80–95 MEDIUM recommend, <80 LOW manual).

## 9. Reconciliation Methodology

For each matched pair, diff fields (mismatch/missing/type), persist `conflicts.conflicting_fields` JSON, assess risk, flag `auto_resolvable`. See `docs/reconciliation.md`.

## 10. Schema Drift Detection

Hashes schema fields, compares to previous version, reports added/removed/renamed (fuzzy on column names, confidence) + type changes, `requires_approval`. See `docs/schema-drift.md`.

## 11. Failure Recovery

Statuses `queued→processing→completed|failed|cancelled`, bounded retries (5) with `2^n + jitter` backoff, persisted in `attempts`/`sync_attempts`, idempotency via DB `UNIQUE(idempotency_key)`, never loses failed jobs. See `docs/failure-recovery.md`.

## 12. Security

Synthetic data only, 5MB/mime/traversal validation, CORS allowlist, rate limits, never commit secrets (.env.example), secure headers, `SECURITY.md`.

## 13. Testing

`pytest` 26 tests: normalization, matching, reconciliation, schema + integration (health/docs). Run `python -m pytest -v`. E2E: upload→reconciliation→conflict→resolve.

## 14. Benchmark Results

Use `scripts/generate_data.py` + `benchmarks/` — synthetic CRM/ERP/Accounting with seeded corruption (typos, missing, conflicting amounts). Measure precision/recall/F1, records/sec, sync recovery. Report only measured numbers (no fabrication).

## 15. Local Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env  # set DATABASE_URL, REDIS_URL
alembic upgrade head
uvicorn backend.app.main:app --reload
cd frontend && npm install && npm run dev  # http://localhost:3000 → proxies /api to :8000
```

## 16. Docker Setup

```bash
docker compose up  # backend:8000, postgres:5432, redis:6379, worker, frontend:3000
# health: http://localhost:8000/health  docs: /docs  demo: /demo.json
```

Production Dockerfile: `python:3.12-slim`, non-root, layer cache, HEALTHCHECK, no secrets.

## 17. API Documentation

OpenAPI at `/docs` and `/redoc`. Key endpoints:

```
GET  /health
POST /sources  GET /sources  GET /sources/{id}  DELETE /sources/{id}
POST /uploads  GET /uploads/{id}
POST /reconciliation  GET /reconciliation/{id}  (202 Accepted)
GET  /conflicts  GET /conflicts/{id}  POST /conflicts/{id}/resolve
GET  /schemas  GET /schemas/{id}  GET /schemas/drift
GET  /jobs  GET /jobs/{id}
GET  /audit-logs
```
Idempotency via `Idempotency-Key` header → DB UNIQUE. Pagination `?page=&limit=`. See `docs/api.md`.

## 18. Deployment

- Frontend static: Cloudflare Pages / Vercel — `npm run build` → `dist/`, `VITE_API_URL` env.
- Backend: Render (Docker, env vars, HTTPS, health check), portable to ECS/ACI/Cloud Run.
- DB: Supabase managed Postgres; local sqlite fallback when postgres down.

## 19. Limitations

- Single-tenant, no RBAC/JWT yet (audit logs anon `resolved_by` string).
- No bidirectional write-back, no real-time CDC, no distributed matching (>100k needs blocking/indexing).
- ML matching deferred — deterministic baseline first.

## 20. Future Improvements

Blocking keys, PgBouncer, read replicas, S3 uploads, Spark matching, Prometheus/Grafana, JWT+RBAC, ML comparison vs baseline.

## 21. Screenshots

Landing hero + Dashboard health + Conflict side-by-side + Jobs polling — see `frontend/src/pages/`.

## 22. Live Demo

Static landing renders without backend. Live Analysis uploads synthetic data, polls job, displays explainable evidence. Warning: do not upload confidential production data to public demo.

---

## Additional Docs

`docs/PRD.md` (13-part plan), `docs/architecture.md`, `docs/database.md`, `docs/api.md`, `docs/matching-engine.md`, `docs/reconciliation.md`, `docs/schema-drift.md`, `docs/failure-recovery.md`, `docs/security.md`, `docs/deployment.md`.

License: MIT. See `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`.
