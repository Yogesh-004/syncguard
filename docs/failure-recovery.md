# Failure Recovery

## Jobs

Statuses: `queued → processing → completed | failed | cancelled`. `retrying` is `failed` with `retry_count < max_retries`.

## Retries

- Bounded (default `max_retries=5`).
- Exponential backoff: `delay = base * 2^attempt + jitter`.
- Persisted in `attempts` / `sync_attempts` with `started_at/completed_at/error_message`.

## Idempotency

- API: `Idempotency-Key` header → DB `UNIQUE(idempotency_key)` lookup; duplicate returns existing job 200.
- DB constraint is the safety net for races.
- Worker function is idempotent: re-executing same key produces same result, no duplicate `matches`.

## Observability

Structured logs: `request_id` (middleware), `job_id`, `source_id`, `duration_ms`, `status`, `error`, `retry_count`. Never swallows exceptions; errors are explicit, logged, actionable. Frontend polls and shows `FAILED attempt 3/5 error: HTTP 500 retry scheduled`.

## Handling Failures

- DB down → job stays `queued`, healthcheck fails, no jobs lost.
- Upstream API 500/timeout → attempt recorded, retry with backoff.
- Retry exhaustion → `failed`, visible in Jobs + Audit, manual retry allowed.
