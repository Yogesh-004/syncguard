# Security Review (Phase 4, practical — not a pentest)

## Findings
1. Default SECRET_KEY placeholder — MEDIUM. Fix: startup ERROR log if unchanged (implemented `main.py`). Remaining: enforce non-default on boot in prod (not enforced, documented).
2. CORS `allow_origins=*` — MEDIUM. Fix: none (configurable via CORS_ORIGINS env; documented for single-tenant demo). No credentialed cross-origin flows exist.
3. Pickle model artifact — LOW/INFO. Only loads repo-owned `backend/app/models/*.pkl`; never user input. Documented limitation.
4. Secrets in source/logs — NONE FOUND (grep: no keys/tokens/passwords in backend/frontend; logs carry ids/counts only; audit stores field values of the conflict only, no credentials).
5. Path traversal — handled (`_sanitize_filename` + basename; tested). Uploads never executed (parsed as data only).
6. SQL injection — LOW (SQLAlchemy ORM, no raw SQL except `SELECT 1` health probe).
7. Stack traces — not leaked (generic 500 handler; verified no "Traceback" in error responses).
8. Connector destinations — server-derived from conflict records (MOCK-prefixed); `simulate_error` honored only on mock path. No arbitrary command execution.
9. Oversized uploads — enforced (size + row cap 413s). Field-size cap added.
10. DEBUG=false default in `.env.example`; Docker non-root user + HEALTHCHECK on /health.

## API validation (spot-tested)
Unknown IDs → 404; non-numeric IDs → 422; invalid actions → 422; push without confirm/dry-run → 422; cross-object confusion impossible (single-ID endpoints, server-side ownership via FK traversal). No HIGH findings open.
