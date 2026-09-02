# Deployment

## Local

```bash
docker compose up  # backend:8000, postgres:5432, redis:6379, worker, frontend:5173
# health: http://localhost:8000/health  docs: /docs
```

## Frontend (Static)

- Build `npm run build` → `dist/` → **Cloudflare Pages** (preferred) or Vercel/Render Static.
- Env `VITE_API_URL`. Landing + Explore Demo use `public/demo.json` — no backend needed for first paint.

## Backend (Container)

- `Dockerfile` python:3.12-slim, `pip install -r requirements.txt` cached, non-root, `HEALTHCHECK CMD python -c "urllib.request.urlopen('http://localhost:8000/health')"`.
- Deploy to **Render** (Docker, env vars, HTTPS, health endpoint). Portable to AWS ECS/Azure ACI/GCP Cloud Run — no platform APIs.

## Database

- **Supabase** (or Neon) managed Postgres. `DATABASE_URL` from env. Local compose uses `postgres:16-alpine` with `pg_isready` healthcheck.

## Env

```
DATABASE_URL, REDIS_URL, CELERY_BROKER_URL, CELERY_RESULT_BACKEND
SECRET_KEY, CORS_ORIGINS, MAX_UPLOAD_SIZE_MB, DEMO_MODE
```

## CI/CD

`.github/workflows/tests.yml` (pytest+ruff) and `docker.yml` (build). No secrets in repo.
