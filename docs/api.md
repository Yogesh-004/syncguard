# API Design

**Base:** `/` (v0) → versioned as `/api/v1` when auth added. OpenAPI at `/docs` and `/redoc`.

## Endpoints

| Method | Path | Body/Header | Resp | Codes |
|--------|------|-------------|------|-------|
| GET | /health | — | {status, app, version, demo_mode} | 200 |
| POST | /sources | {name, source_type, config} | source | 201/422 |
| GET | /sources?page=&limit= | — | {items, total} | 200 |
| GET | /sources/{id} | — | source | 200/404 |
| DELETE | /sources/{id} | — | — | 204/404 |
| POST | /uploads | multipart file + source_id, Idempotency-Key? | {upload_id} | 201/413/422 |
| GET | /uploads/{id} | — | upload status | 200/404 |
| POST | /reconciliation | {source_ids, config{weights, thresholds}}, Idempotency-Key | {job_id} 202 | 202/422 |
| GET | /reconciliation/{id} | — | job | 200/404 |
| GET | /conflicts?status=&risk=&page=&limit= | — | paginated | 200 |
| GET | /conflicts/{id} | — | side-by-side + evidence | 200/404 |
| POST | /conflicts/{id}/resolve | {action: approve|reject|modify|defer, detail} | conflict | 200/422 |
| POST | /conflicts/{id}/reject | {detail} | conflict | 200 |
| GET | /schemas | — | list versions | 200 |
| GET | /schemas/{id} | — | schema | 200/404 |
| GET | /schemas/drift?source_id= | — | {added, removed, renamed, confidence} | 200 |
| GET | /jobs?status= | — | paginated jobs + attempts | 200 |
| GET | /jobs/{id} | — | job detail | 200/404 |
| GET | /audit-logs?request_id=&job_id= | — | paginated | 200 |

## Conventions

- **Validation:** Pydantic schemas on all req/resp; file: 5MB, mime sniff, sanitize filename, block `../`.
- **Pagination:** `?page=1&limit=20` max 100; resp `{items, total, page, limit}`.
- **Errors:** `{detail, code, request_id}` — structured, no stack leak; server logs full trace.
- **Idempotency:** `Idempotency-Key` header/body → DB UNIQUE `idempotency_key`; duplicate returns 200 with existing `job_id`.
- **Security:** CORS allowlist (`CORS_ORIGINS` env), rate limit uploads/reconciliation (slowapi), secure headers.

## Example: POST /reconciliation

```http
POST /reconciliation HTTP/1.1
Idempotency-Key: rec-abc-123
Content-Type: application/json

{"source_ids": [1,2], "config": {"thresholds": {"high": 0.95, "medium": 0.8}}}

→ 202 {"id": 82191, "status": "queued"}
```

Poll `GET /jobs/82191` → `{"status":"processing","progress":62}` → `completed`.

## Auth (Future)

JWT via `Authorization: Bearer`; `deps.get_current_user`; v0 allows anonymous but logs `resolved_by`.
