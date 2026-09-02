# Architecture

## Overview

SyncGuard is a layered, service-oriented system:

```
React (Vite) — static demo fallback
  ↓ HTTPS / JSON
FastAPI — routes (thin) → deps → services → domain
  ↓
Services: normalization, matching, reconciliation, resolution, schema_analyzer, synchronization, audit
  ↓
Domain: connectors (CSV/JSON/REST via BaseConnector), utils (scoring, hashing)
  ↓
Infra: SQLAlchemy (Postgres), Celery (Redis broker), HTTPX, Pandas
```

**Principle:** correctness + explainability + reliability + maintainability > tech count.

## Why Each Component

- **FastAPI:** async, Pydantic validation, auto OpenAPI, testability. Keeps route handlers thin.
- **Postgres:** JSONB flexibility + relational integrity; needed for idempotency UNIQUE, FKs, audit history.
- **SQLAlchemy 2.0 + Alembic:** migrations for fresh + upgrade; typed models.
- **Redis + Celery:** durable queue; retries survive backend restarts (vs in-memory BackgroundTasks).
- **RapidFuzz:** pure-Python fuzzy, fast, deterministic scores for matching.
- **Pandas:** chunked CSV ingest; not used for matching (keep matching transparent).

## Request Flow (Live Analysis)

1. `POST /uploads` → validate size/mime/traversal → store records + SchemaModel v1 → 201.
2. `POST /reconciliation {source_ids}` → create `reconciliation_jobs` row with `idempotency_key` UNIQUE → enqueue Celery task → 202 `{job_id}`.
3. Worker: `SELECT records WHERE source_id IN (...)` → normalize (deterministic fns) → block by email domain/phone prefix → pairwise `MatchingEngine.compute_score` → classify by thresholds → persist `matches` (+ evidence) → detect `conflicts` (field diffs) → update `progress` → audit log.
4. Frontend polls `GET /jobs/{id}` (2s) → renders progress then results.

## Cold-Start Strategy

Landing and `Explore Demo` use `frontend/public/demo.json` + `data/demo/records.*` precomputed. No `fetch(/health)` on first paint. Only `Run Live Analysis` hits backend → 202 immediately → staged loader messages.

## Module Boundaries

- `api/routes.py` — HTTP only; calls `services/*`.
- `services/` — pure business logic, unit-testable without HTTP/DB.
- `connectors/` — `BaseConnector.fetch() -> List[Dict]`; CSV/JSON/REST each extend; new connector = new file + register in factory.
- `workers/tasks.py` — Celery tasks wrap services; handle retries/backoff.

## Scaling Path

- **Now:** single worker, Postgres single instance.
- **100K–10M:** blocking keys, DB indexes/partitioning, PgBouncer, Redis cluster, increase Celery concurrency, separate queues, read replicas, S3 for uploads, Spark for distributed matching (swap matching service).

## Decision Log

- DB UNIQUE for idempotency, not just app check — prevents races.
- Polling over websockets — simpler, portable, works on free hosting.
- No ORM business logic — services own logic.
