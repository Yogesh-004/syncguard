# Synchronization (Phase 3 — Mock)

## Connector
`MockConnector` (`connectors/mock_connector.py`): `health_check/read/get_record/update_record` on an isolated in-memory store. NEVER touches `RecordModel`/source systems. Every UI/API response labels destination `MOCK ...`. No real CRM/ERP is updated — stated in UI, API (`mock:true`), and audit.

## Flow
Resolve → dry-run (creates `sync_jobs` row `DRY_RUN`, no write, shows destination/current/proposed/UPDATE) → Confirm Push (requires `confirm:true` + completed dry-run) → `PROCESSING` → mock write → `SUCCESS` (+verification read-back) or `FAILED` (error+attempt row). Statuses: PENDING/DRY_RUN/CONFIRMED(implicit)/PROCESSING/SUCCESS/FAILED/RETRYING.

## Idempotency
Key = `res-{resolution_id}|{destination}|{value_hash}` (UNIQUE). Repeat push → `ALREADY_APPLIED`, no duplicate write (verified live).

## Retry
Taxonomy: retryable = timeout/conn/408/429/500/502/503; non-retryable = 400/401/403/404/409/422. `POST /sync-jobs/{id}/retry` only for FAILED+retryable, max 3 attempts. Verified: 500 → FAILED → retry → SUCCESS.

## Verification
After write, connector reads back and compares. Mock supports it (in-memory); documented as mock-level verification, not third-party confirmation.

## Migration
`alembic/versions/002_phase3_sync.py` adds nullable `resolution_id/destination/operation/field_name/resolved_value/attempt_count/response_metadata` to `sync_jobs`; existing rows untouched. Run `alembic upgrade head` (also applied to local sqlite DBs).
