# Database Design

## ERD

```
sources 1──∞ records
sources 1──∞ schemas (versions)
records ∞──∞ matches (record_a_id, record_b_id)
matches 1──∞ conflicts
conflicts 1──∞ resolution_logs
reconciliation_jobs 1──∞ attempts
reconciliation_jobs 1──∞ sync_jobs
sync_jobs 1──∞ sync_attempts
audit_logs — polymorphic (FKs optional, indexed)
```

## Tables

| Table | PK | Uniques | Key Fields |
|-------|----|---------|------------|
| sources | id | — | name, source_type, config JSON, is_active |
| records | id | (source_id, source_record_id) | data JSON, raw_data, normalized_data, is_processed |
| schemas | id | (source_id, version) | fields JSON, field_count |
| matches | id | — | record_a/b FK, confidence, matched_fields JSON, evidence JSON, entity_group_id |
| conflicts | id | — | record_a/b/match FK, conflicting_fields JSON, risk_level, resolution_status, auto_resolvable |
| resolution_logs | id | — | conflict_id FK, action, detail |
| reconciliation_jobs | id | idempotency_key | job_type, status, progress, retry_count/max_retries |
| sync_jobs | id | idempotency_key | reconciliation_job_id FK, status |
| attempts / sync_attempts | id | — | job_id FK, attempt_number, status |
| audit_logs | id | — | request_id, job_id, source_id, action, entity_type/id, details JSON |

## Indexing

- `records(source_id, source_record_id)` UNIQUE + `is_processed`.
- `matches(entity_group_id)`, `matches(confidence)`.
- Partial `conflicts(status) WHERE resolution_status='pending'`.
- `reconciliation_jobs(idempotency_key)` UNIQUE — idempotency guarantee.
- `audit_logs(request_id, job_id, created_at)` composite.

## Why This Shape

- **Normalized but not over-normalized:** `records.data` JSON keeps flexible ingest; FKs preserve integrity where it matters (jobs/attempts/audit).
- **History:** `schemas` versioned; `resolution_logs` append-only; `records` keeps raw vs normalized.
- **Concurrency:** short TX per match; progress updates outside long TX.
- **Soft delete:** `sources.is_active` not `DELETE CASCADE` for audit safety.

## Migrations

- Alembic in `backend/app/db/migrations/`; support `alembic upgrade head` (fresh) and incremental.
- Never hand-edit DB; change via migration.

## Query Patterns

- Dashboard: `SELECT count(*) FROM conflicts WHERE status='pending' GROUP BY risk_level` — benefits from partial index.
- Matching: `SELECT * FROM records WHERE source_id IN (?) AND is_processed=false` — batched.
- Drift: `SELECT * FROM schemas WHERE source_id=? ORDER BY version DESC LIMIT 2`.
