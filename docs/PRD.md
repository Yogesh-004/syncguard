# SyncGuard — Product Requirements & Planning Document

> **Version:** 0.1.0 | **Date:** 2026-08-31 | **Status:** Approved for Phase 1 Implementation
> **Location:** `D:\01_Projects\Syncguard\docs\PRD.md`
> **Covers:** Master prompt §56 items 1–13 — PRD, personas, workflows, MVP, non-MVP, architecture, tech justification, DB design, API, roadmap, risks, testing, deployment.

---

## 1. Product Requirements Document

### 1.1 Product Name & Tagline

**SyncGuard** — *Your systems disagree. SyncGuard tells you why.*

Cross-system data reconciliation and integration reliability platform that detects entity mismatches, data conflicts, schema drift, and failed sync jobs across disconnected business systems.

### 1.2 Problem Statement

Businesses run 5–15 overlapping systems (CRM, ERP, Accounting, E-commerce, Payments, Support, internal DBs, 3P APIs). The same customer/transaction exists in multiple systems with formatting differences, missing fields, or renamed columns. Consequences: duplicates, inconsistent reporting, failed integrations, manual reconciliation, silent data loss.

SyncGuard makes these failures **visible, explainable, auditable, and safely resolvable** — not an ETL/iPaaS/MDM replacement, but a developer-friendly reconciliation layer.

### 1.3 Goals

- Ingest CSV/JSON/REST via extensible connectors without engine rewrite.
- Deterministic normalization (name, phone, email, date, address, numeric).
- Layered entity resolution (exact → normalized → fuzzy → weighted explainable score).
- Conflict detection & resolution with audit trail; never silently overwrite.
- Schema drift detection (added/removed/renamed/type-changed).
- Reliable sync: retries, exponential backoff, idempotency, bounded retries.
- Async jobs (Celery+Redis) with 202 Accepted + polling.
- Demo mode (static precomputed) decoupled from backend cold start.
- Measurable: precision/recall/F1, records/sec, sync recovery rate.

### 1.4 Non-Goals (v0)

- Full iPaaS workflow builder, bi-directional write-back, real ML model (deferred).

### 1.5 Success Metrics

- Functional: upload → reconcile → match → conflict → resolve → audit works end-to-end.
- Quality: P/R/F1 reported on 1k/10k/100k synthetic datasets (seeded).
- Reliability: duplicate request idempotency, retry exhaustion visible, no lost failed jobs.
- UX: landing + Explore Demo without backend; live analysis polls job.
- Eng: tests + Ruff + mypy pass, Docker builds, migrations fresh & upgrade.

---

## 2. User Personas

### Primary

| Persona | Role | Pain | Needs |
|---------|------|------|-------|
| **Priya** — Backend/Integration Engineer, 2–5 YOE | Owns CRM↔ERP sync | Silent field rename breaks pipeline; duplicates pile up | Explainable match evidence, API to trigger reconcile, idempotent jobs, logs with request_id/job_id |
| **David** — Data Engineer | Builds reconciliation pipelines | Manual SQL reconciliation; schema drift undetected | Deterministic normalization, configurable weights/thresholds, schema version diff, benchmark harness |
| **Ops Engineer (Alex)** | On-call for sync failures | 3AM failed syncs with no retry visibility | Job status/progress/retry count, exponential backoff, audit log, health endpoint |

### Secondary

| Persona | Role | Pain | Needs |
|---------|------|------|-------|
| **Anjali** — Data Analyst | Reports on customers | Duplicate customers skew dashboards | Conflict rate, match confidence distribution, side-by-side comparison |
| **CTO / Eng Manager** | Evaluates tool | Can't defend reconciliation logic in interview/audit | Architecture doc, decision log, measurable benchmarks |

### Anti-Persona

- Non-technical marketer expecting no-code drag-drop (out of scope v0).

---

## 3. Core Workflows

### 3.1 Upload → Reconciliation (Happy Path)

```text
User: POST /uploads (CSV/JSON, ≤5MB/10k records) → 201 + upload_id
User: POST /reconciliation {source_ids, config {weights, thresholds}} → 202 {job_id}
Frontend polls GET /jobs/{id} → {queued|processing 62%|completed|failed}
Engine: normalize → block → exact → normalized → fuzzy → weighted score → classify → conflict detect → persist matches/conflicts/schema_versions
User: GET /conflicts?status=pending → GET /conflicts/{id} → side-by-side + evidence
User: POST /conflicts/{id}/resolve {action: approve|reject|modify|defer} → audit_logs row
```

### 3.2 Schema Drift Workflow

```text
Ingest new file → hash schema fields → compare to latest SchemaModel.version for source
Detect: added/removed/renamed (RapidFuzz on column names, semantic confidence) / type changed
Persist SchemaModel new version → GET /schemas/drift returns {removed, added, rename_suggestions, affected_pipelines, requires_approval}
UI: Schema tab shows current vs previous + diff highlights
```

### 3.3 Synchronization Job Workflow

```text
POST /jobs (or internal sync trigger) → idempotency_key = hash(payload)+user → 201 or 200 dedup
Attempts table → worker executes with bounded retries (default 5, exponential backoff 2^n + jitter)
Statuses: queued → processing → completed | failed | cancelled (retrying is failed+retry_count<max)
Never loses failed job; GET /jobs shows error, attempt count, next retry at
```

### 3.4 Demo vs Live

- **Demo:** Static `data/demo/` + `frontend/public/demo.json` — landing renders immediately, no backend.
- **Live:** Upload small synthetic dataset → async job as above — frontend shows staged messages: Initializing → Connecting → Loading schema → Matching → Reconciling.

---

## 4. MVP Definition

**Must ship for acceptance (§52):**

**Ingestion:** CSV + JSON connectors via `connectors/base.py` abstraction; REST stub; size/type/path-traversal validation.
**Normalization:** name/phone/email/date/address/numeric deterministic, tested, documented.
**Matching:** 4-stage engine with configurable weights/thresholds; evidence retained per match (field scores, method).
**Classification:** HIGH/MEDIUM/LOW/UNMATCHED with configurable thresholds (default >95 auto-resolve candidate, 80–95 recommend, <80 manual).
**Conflict detection:** structured `conflicts` rows, conflicting_fields JSON.
**Resolution:** auto-resolve/recommend/manual + approve/reject/modify/defer + audit_logs; never silent overwrite.
**Schema drift:** versioned `schema_versions`, added/removed/renamed/type diff.
**Sync reliability:** job statuses, retries with exponential backoff, idempotency at DB+API, audit.
**Async:** Celery+Redis, `POST /reconciliation` returns 202 job_id, `GET /jobs/{id}` progress.
**Backend:** FastAPI + SQLAlchemy + PostgreSQL + Alembic + Pydantic validation + `/health` + `/docs`.
**Frontend (Vite+React+Recharts):** Landing (hero + Explore Demo + Run Live Analysis), Dashboard (overview/reconciliation/conflicts/schema/jobs/audit), side-by-side conflict detail.
**Docker:** Backend+postgres+redis+worker+frontend; non-root, healthcheck, no secrets in image.
**Testing:** Unit (normalization, matching, scoring, schema, retries) + integration (DB+API) + e2e (upload→resolve) + failure cases.
**Docs:** README 22 sections, architecture/database/api/matching/reconciliation/schema-drift/failure-recovery/security/deployment, .env.example, LICENSE, CONTRIBUTING, SECURITY.md
**Data:** `scripts/generate_data.py` seeded synthetic CRM/ERP/Accounting with controlled corruption; `data/demo/` committed.

---

## 5. Non-MVP / Future

| Feature | Reason to Defer | Trigger to Build |
|---------|-----------------|------------------|
| ML entity matching (scikit-learn) | Deterministic baseline must be defensible first | Measured F1 < target and ML beats baseline |
| Bidirectional write-back to source systems | Risk of data loss; needs stronger idempotency + rollback | User demand + audit proves safe |
| Visual workflow builder | Scope creep; competes with iPaaS | Adoption > 100 users |
| Real-time CDC / Debezium | Infra complexity | Need <1min latency, 10M records |
| Multi-tenancy, RBAC, JWT auth | Portfolio demo is single-tenant | Production SaaS hardening |
| Prometheus/Grafana, S3 object storage, sharding | Add after core stable | Perf benchmarks show bottleneck |
| Semantic field mapping with LLMs | Over-engineering for v0 | Schema renames exceed fuzzy accuracy |

---

## 6. Architecture Proposal

### 6.1 Layers

```text
React (Vite, Recharts)  — static demo.json for cold-start
        ↓ HTTPS
FastAPI (api/routes → deps) — validation, pagination, rate limit, CORS, secure headers
        ↓
Application Services (services/normalization|matching|reconciliation|resolution|schema_analyzer|synchronization|audit)
        ↓
Domain Logic (connectors/base, utils/scoring|hashing)
        ↓
Infrastructure (SQLAlchemy models, Celery tasks, Redis broker, HTTPX for REST connectors, Pandas for bulk)
        ↓
Postgres (primary) + Redis (queue+result) + Worker (Celery)
```

Route handlers are thin: validate → service call → return schema. No business logic in routes.

### 6.2 Component Diagram

```text
[Browser] → [Cloudflare Pages / Vercel static]
             └─ demo.json (precomputed)
[Browser — Live] → POST /reconciliation → FastAPI → Postgres (jobs) → Redis → Celery Worker → Services → Postgres
                                                                                 → AuditLogs
[Connectors] CSV/JSON/REST implement BaseConnector.fetch() → normalized records
```

### 6.3 Key Decisions

- Sync writes to reconciliation_jobs/sync_jobs with `idempotency_key UNIQUE` at DB level — catch races even if API dedup missed.
- Celery task updates `progress` field; polling, not websockets (simpler, portable).
- Pandas only for CSV bulk parsing; not for matching (matching is pure Python + RapidFuzz for transparency).

See `docs/architecture.md` for deep dive.

---

## 7. Technology Justification

| Tech | Why | Alternative Considered | Why Not |
|------|-----|------------------------|---------|
| **Python 3.12+** | Required by spec; modern typing | 3.11 | 3.12 has better `type` params, perf |
| **FastAPI** | Async, Pydantic v2 validation, auto OpenAPI, interview-defensible | Flask/Django | Flask no async/validation; Django heavy for API-only |
| **Pydantic** | Request/response schemas, settings, validation | dataclasses | No validation/OpenAPI |
| **SQLAlchemy 2.0** | Mature ORM, async Ready, Alembic | Tortoise | Smaller community, fewer docs |
| **PostgreSQL 16** | JSONB for flexible record_data, FKs, indexes, prod-grade | SQLite | SQLite no concurrent writes, no JSONB |
| **Alembic** | Versioned migrations, fresh+upgrade | raw SQL | No version control |
| **Pandas** | Fast CSV/JSON ingest, dtype inference | csv stdlib | Manual handling slower, more bugs |
| **RapidFuzz** | Fast fuzzy (Levenshtein), MIT, drop-in for fuzzywuzzy | difflib | difflib slower, worse recall |
| **Celery + Redis** | Spec-required; reliable retries, beat, proven | RQ / FastAPI BackgroundTasks | RQ fewer features; BackgroundTasks loses jobs on restart |
| **HTTPX** | Async REST connector, timeout/retries | requests | requests sync blocks workers |
| **React + Vite + Recharts** | Spec-required; Vite fast HMR, Recharts declarative | Plotly | Plotly heavier bundle |
| **Docker + Compose** | Portable, Render/AWS/GCP ready | Podman | Docker is standard |
| **Ruff + mypy + Pytest** | Lint/format/type/test | Black+isort | Ruff replaces both, faster |

Dependency rule enforced: stdlib first; existing dep first; new dep needs measured win.

---

## 8. Database Design Proposal

### 8.1 ERD (text)

```text
sources 1—∞ records
sources 1—∞ schema_versions
records ∞—∞ matches (via record_a_id, record_b_id, entity_group_id)
matches 1—∞ conflicts
conflicts 1—∞ resolution_logs
reconciliation_jobs 1—∞ attempts
reconciliation_jobs 1—∞ sync_jobs
sync_jobs 1—∞ sync_attempts
audit_logs (polymorphic, FKs optional, indexed on request_id/job_id/source_id)
users (future auth; v0 anonymous with audit resolved_by string)
```

### 8.2 Tables (see docs/database.md for full DDL)

| Table | PK | Key Columns | Indexes | Notes |
|-------|----|-------------|---------|-------|
| `sources` | id | name, source_type, config JSON | is_active | Soft active flag |
| `records` | id | source_id FK, source_record_id, data JSON, normalized_data JSON | (source_id, source_record_id) UNIQUE, is_processed | Raw vs normalized separated |
| `schemas` | id | source_id FK, fields JSON, version | (source_id, version) UNIQUE | Version incremented on drift |
| `matches` | id | record_a/b FK, confidence, evidence JSON, entity_group_id | entity_group_id, confidence | Groups transitively matched entities |
| `conflicts` | id | record_a/b/match FK, conflicting_fields JSON, risk_level, resolution_status | resolution_status, risk_level | auto_resolvable bool |
| `resolution_logs` | id | conflict_id FK, action | conflict_id | Append-only audit |
| `reconciliation_jobs` | id | job_type, status, idempotency_key UNIQUE, progress | idempotency_key, status | Bounded retries |
| `sync_jobs` | id | reconciliation_job_id FK, idempotency_key UNIQUE | status | Idempotent downstream |
| `attempts` / `sync_attempts` | id | job_id FK, attempt_number | job_id | Retry history |
| `audit_logs` | id | request_id, job_id, source_id, action, entity_type/id | request_id, job_id, created_at | Structured observability |

### 8.3 Indexing & Constraints

- Partial indexes on `conflicts WHERE resolution_status='pending'` for dashboard.
- GIN on `records.data` JSONB (if migrated to JSONB) for field search.
- `idempotency_key UNIQUE` is the correctness guarantee for idempotency — not just app logic.
- FKs with `ON DELETE RESTRICT` for audit safety; soft delete via `is_active`.

### 8.4 Transaction Boundaries

- Upload: single TX for records batch + schema version.
- Reconciliation: per-pair match in short TX; job progress update outside long TX.
- Resolution: `conflicts` update + `resolution_logs` insert in one TX.

---

## 9. API Proposal

Base: `/api/v1` (or root for v0 per current `api/routes.py`). Correct methods/statuses/validation/pagination/filtering/structured errors.

| Method | Path | Auth | Description | Status |
|--------|------|------|-------------|--------|
| GET | `/health` | none | Liveness | 200 |
| POST | `/sources` | optional | Create source (type: csv/json/rest) | 201 |
| GET | `/sources` | optional | List with pagination | 200 |
| GET | `/sources/{id}` | optional | Detail | 200/404 |
| DELETE | `/sources/{id}` | optional | Soft delete | 204 |
| POST | `/uploads` | optional | File upload (multipart, 5MB, mime sniff) | 201/413/422 |
| GET | `/uploads/{id}` | optional | Upload status | 200 |
| POST | `/reconciliation` | optional | Start job (Idempotency-Key header) | 202 {job_id} |
| GET | `/reconciliation/{id}` | optional | Job detail | 200 |
| GET | `/conflicts` | optional | List ?status=&risk=&page=&limit= | 200 |
| GET | `/conflicts/{id}` | optional | Detail side-by-side | 200 |
| POST | `/conflicts/{id}/resolve` | optional | approve/reject/modify/defer | 200 + audit |
| POST | `/conflicts/{id}/reject` | optional | alias | 200 |
| GET | `/schemas` | optional | List versions | 200 |
| GET | `/schemas/{id}` | optional | Version detail | 200 |
| GET | `/schemas/drift` | optional | Latest drift report | 200 |
| GET | `/jobs` | optional | List reconciliation+sync | 200 |
| GET | `/jobs/{id}` | optional | Detail + attempts | 200 |
| GET | `/audit-logs` | optional | ?request_id=&job_id=&entity_type= | 200 |

**Validation:** Pydantic schemas for all req/resp; file: size, magic bytes, schema, sanitize filename, prevent traversal.
**Errors:** `{detail, code, request_id}` — never leak stack trace; log full trace server-side.
**Pagination:** `?page=1&limit=20` (max 100); response `{items, total, page, limit}`.
**Idempotency:** `Idempotency-Key` header or body key → DB UNIQUE lookup → 200 return existing or 201 create.
**Security:** CORS allowlist (env), rate limit (slowapi) on uploads/reconciliation, secure headers (HSTS, X-Content-Type-Options).

See `docs/api.md`.

---

## 10. Development Roadmap

20 phases, sequential, each with *explain → files → implement → test → verify startup → integrate → report* (per §47).

| Phase | Scope | Gate |
|-------|-------|------|
| 1 | Domain & planning (this doc) | PRD approved |
| 2 | Python setup (pyproject, requirements, Ruff, mypy, pytest) | `pytest` green, `ruff check` clean |
| 3 | Normalization engine | Unit tests for name/phone/email/date/address/numeric |
| 4 | Deterministic matching (exact + normalized) | Tests for exact/prefix/contains |
| 5 | Fuzzy matching (RapidFuzz) + weighted scorer | Tests for fuzzy thresholds, evidence |
| 6 | Conflict detection | Tests for missing/conflicting fields |
| 7 | Resolution engine + audit | Tests for approve/reject/defer + audit rows |
| 8 | PostgreSQL + SQLAlchemy + Alembic | Fresh + upgrade migration works |
| 9 | FastAPI (health, sources, uploads, reconciliation, conflicts, schemas, jobs, audit) | `uvicorn` starts, `/docs` works |
| 10 | Background jobs (Celery+Redis, 202+poll) | Job lifecycle queued→processing→completed |
| 11 | Schema drift detection | Tests for added/removed/renamed/type |
| 12 | Sync reliability (retries, backoff, idempotency) | Failure injection tests pass |
| 13 | React frontend (landing demo + live + dashboard) | Responsive, static demo without backend |
| 14 | Docker (multi-service, healthcheck, non-root) | `docker compose up` → app healthy |
| 15 | Testing suite expansion (unit/integration/e2e/failure) | Coverage + all suites green |
| 16 | CI/CD (GitHub Actions tests.yml, docker.yml) | PR runs tests |
| 17 | Deployment (frontend Cloudflare/Vercel, backend Render, DB Supabase) | HTTPS health, env vars |
| 18 | Benchmarking (1k/10k/100k + corruption, measure P/R/F1, perf) | Report with real numbers only |
| 19 | Security review (file upload, CORS, no secrets, PII note) | `SECURITY.md` + .env.example |
| 20 | Docs + launch (README 22 sections, screenshots, demo data) | Acceptance criteria met |

Current repo already scaffolds phases 2–13 partially; roadmap is to harden sequentially.

---

## 11. Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| False matches (over-normalization) | High | Data corruption if auto-resolved | Conservative address normalization; high threshold for auto-resolve; always keep evidence; human approval for 80–95 |
| Backend cold start (Render free) → blank landing | High | Visitor bounces | Static demo.json + precomputed metrics; landing never fetches backend first paint |
| Postgres/Redis down | Medium | Jobs lost | Health checks; job persists before queue; failed jobs stay visible; no BackgroundTasks that vanish |
| Large file OOM (10k+ records) | Medium | Crash | Streaming CSV via Pandas chunks; 5MB/10k limit configurable; reject malformed early |
| Schema rename missed (amount → transaction_amount) | Medium | Silent incomplete processing | Rename suggestion via fuzzy on column names + type similarity confidence; requires approval |
| Idempotency race (duplicate POST) | Medium | Duplicate downstream | DB UNIQUE on idempotency_key; API returns existing; worker is idempotent function |
| Dependency bloat (adding sklearn prematurely) | Low | Deploy complexity, slower builds | Rule: deterministic first; ML only if measured F1 improvement |
| PII in demo/repo | Low but severe | Privacy breach | Synthetic data only; docs warn "Do not upload confidential data to public demo" |
| CORS misconfig exposing API | Low | Abuse | Allowlist via CORS_ORIGINS env, rate limit uploads |

### Scaling Discussion (100K → 10M)

- Batching + blocking keys (email domain, phone prefix) to avoid O(n²) matching.
- DB indexing, partitioning by source_id, read replicas.
- Queue-based: increase Celery concurrency, separate queues (reconcile vs sync).
- Connection pooling (PgBouncer), Redis cluster.
- Caching normalized records; object storage (S3) for uploads.
- Distributed matching (Spark/Dask) — not v0, but architecture allows swapping matching service.

---

## 12. Testing Strategy

### Unit (pytest)

- `test_normalization.py` — name/phone/email/date/address/numeric edge cases, determinism, idempotence.
- `test_matching.py` — exact/prefix/contains/fuzzy, RapidFuzz scores, weighted scorer, evidence shape.
- `test_reconciliation.py` — threshold classification, risk levels.
- `test_schema_analyzer.py` — added/removed/renamed/type detection, Levenshtein rename confidence.
- `test_retry.py` (new) — exponential backoff calc, bounded retries, jitter.

### Integration

- `test_api.py` — FastAPI TestClient: health, sources CRUD, uploads validation (size/mime/traversal), reconciliation 202, jobs polling, conflicts resolve + audit, idempotency duplicate returns same id.
- DB tests with real Postgres (docker-compose test profile or sqlite fallback) — FKs, UNIQUE idempotency_key, TX boundaries.

### E2E

- `upload → reconciliation → match → conflict → resolution` via API client.
- Schema drift: upload v1 then v2 with renamed column → drift detected.

### Failure Tests

- Invalid/malformed CSV/JSON, missing fields, type mismatches.
- DB failure injection (connection drop) → job marked failed, retry scheduled.
- API 500/timeout mock (HTTPX mock) → sync job retries with backoff.
- Duplicate idempotency key → no duplicate job.
- Retry exhaustion (max 5) → status failed, visible in jobs.
- Never only test happy path; each success case has a failure twin.

### Tooling

- `pytest --cov=backend --cov-fail-under=70` (target 80 for services).
- `ruff check . && ruff format --check .`
- `mypy backend/app --ignore-missing-imports`
- CI runs on push/PR.

---

## 13. Deployment Strategy

### Frontend (Static)

- **Preferred:** Cloudflare Pages (or Vercel/Render Static). Build `npm run build` → `dist/` uploaded. Env `VITE_API_URL` points to backend. Landing uses `public/demo.json` so no backend needed for first paint. Meets §32/§35 cold-start requirement.

### Backend (Container)

- **Preferred:** Render (Docker). `Dockerfile` python:3.12-slim, non-root user, layer cache (requirements first), HEALTHCHECK to `/health`, env-based config, no secrets baked. Must remain portable to AWS ECS / Azure ACI / GCP Cloud Run — no Render-specific API used.

### Database

- **Portfolio:** Supabase managed Postgres (or Neon). `DATABASE_URL` via env. Never commit credentials; `.env.example` template only. Local: docker-compose postgres:16-alpine with healthcheck `pg_isready`.

### Compose (Local)

```yaml
backend → 8000, postgres → 5432, redis → 6379, worker (celery -A backend.app.workers.celery_app worker --concurrency=2), frontend → 5173 (vite)
```

All services have `depends_on: condition: service_healthy` where applicable.

### Env Vars

```text
DATABASE_URL, REDIS_URL, CELERY_BROKER_URL, CELERY_RESULT_BACKEND
SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
CORS_ORIGINS, MAX_UPLOAD_SIZE_MB, DEMO_MODE, LOG_LEVEL
```

### Observability (§36)

- Structured logging (structlog or stdlib + JSON) with `request_id` (middleware), `job_id`, `source_id`, duration, status, error, retry_count.
- Prometheus/Grafana deferred until core stable.

### Cold Start UX

- Landing: static + demo.json.
- On `POST /reconciliation`: immediate 202 + job_id; frontend shows staged loader; polling interval 2s with backoff.

---

## 14. Approvals

| Role | Name | Sign-off |
|------|------|----------|
| TPM | — | ☐ Approved to proceed Phase 2 |
| Security | — | ☐ Upload validation + secrets reviewed |
| Eng Lead | — | ☐ Architecture + DB + API approved |

> **Next step:** Implement Phase 2 onward one phase at a time, per §47 rules: explain → files → code → tests → fix → verify imports/startup/integration → report.

---

*End of PRD. Detailed design docs follow: `architecture.md`, `database.md`, `api.md`, `matching-engine.md`, `reconciliation.md`, `schema-drift.md`, `failure-recovery.md`, `security.md`, `deployment.md`.*
