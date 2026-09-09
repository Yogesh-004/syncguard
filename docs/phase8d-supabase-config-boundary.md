# Phase 8D-A — Supabase Docker Configuration Boundary

## Original problem

`docker-compose.yml` hardcoded `DATABASE_URL: postgresql://postgres:postgres@postgres:5432/syncguard` in the backend service, so no `.env` value could override it — there was no configuration boundary for an external database such as Supabase.

## Configuration change

- Base compose: `DATABASE_URL: ${DATABASE_URL:-postgresql://postgres:postgres@postgres:5432/syncguard}` — interpolated with the Phase 8C local default preserved. Unset env behaves exactly as before.
- NEW `docker-compose.supabase.yml`: detaches backend from the local postgres service (`depends_on: !reset []`, compose v5.3.0 verified) and requires `DATABASE_URL`, `SECRET_KEY`, `API_KEY` from the environment (`${VAR:?message}` — fails before anything starts when unset). No application-code awareness of Supabase; the app receives a DSN through the existing SQLAlchemy/psycopg2 path.
- NEW `.env.supabase.example`: placeholder-only connection template (`?sslmode=require` documented for managed TLS) plus optional separate sync-target note. Committable by design.
- `.gitignore`: added `.env.*` with `!.env.example` / `!.env.supabase.example` exceptions, so future credential files are ignored by default while examples stay committable.
- Incidental hardening found during validation: boot logs printed the full `DATABASE_URL` including password — `init_db` now logs a redacted `scheme://user@host/db` form (verified live: `postgresql://postgres@postgres/syncguard`). Driver error text (host/port/user, no password) unchanged.

## Local Docker regression

- `docker compose config` resolves local default unchanged; backend recreated on the interpolated config and booted healthy (migrations → serving).
- Full 22/22 container E2E re-ran green after the change (health, auth, reconcile, presence, resolve, dry-run, confirm, verified push, replay, stale rejection, audit).
- Full backend suite 383/383 green.

## External DATABASE_URL mechanism

`DATABASE_URL=... docker compose -f docker-compose.yml -f docker-compose.supabase.yml config` resolves the external value into the backend service with no local dependency; with vars unset, compose aborts with explicit `*_must be set in the environment*` messages. The sync target (`SYNCGUARD_PG_TARGET`, separate container/database) is untouched by the override.

## Security verification

- No Supabase host/password/project reference/keys anywhere in compose files, env examples, Dockerfile, or source (verified by inspection + secret-pattern scan; only `PASTE_*` placeholders exist).
- `.env` ignored; `.env.*` now ignored by default; example files contain zero credentials.
- Frontend receives no `DATABASE_URL` (bundle scan from Phase 8C stands; no frontend changes this phase).
- Boot/log output redacted as above; no secrets in the committed diff (inspected before commit).

## Files changed

- `docker-compose.yml` (interpolation; comment)
- `docker-compose.supabase.yml` (new)
- `.env.supabase.example` (new, placeholders only)
- `.gitignore` (`.env.*` default-ignore + example exceptions)
- `backend/app/db/database.py` (DSN redaction in boot logs only)
- This document

## Tests

- Config resolution: base default + override external + missing-var abort (manual `compose config` matrix, recorded above).
- Regression: full backend suite 383/383; 22/22 container E2E; secret-pattern scan clean.
- No new unit tests: the change is declarative config (covered by resolution matrix) plus a two-line log redaction exercised by every boot.

## Explicit statement

"Supabase connectivity remains UNVERIFIED until a real Supabase PostgreSQL connection is supplied."

---

PHASE 8D-A STATUS: COMPLETE
LOCAL DOCKER REGRESSION: PASS
EXTERNAL DATABASE CONFIGURATION: PASS
SUPABASE CONNECTION: UNVERIFIED
PRODUCT FEATURES ADDED: 0
APPLICATION CODE CHANGED: 1 file (log redaction only; no behavior change)
READY FOR REAL SUPABASE CONNECTION: YES
