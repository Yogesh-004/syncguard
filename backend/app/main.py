"""SyncGuard — Main FastAPI application."""
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.core.config import settings, require_production_secrets
from backend.app.core.logging import logger
from backend.app.db.database import init_db
from backend.app.api.routes import router as api_router


PUBLIC_PATHS = {"/", "/health", "/readyz", "/docs", "/openapi.json", "/redoc"}


def _api_key_configured() -> str:
    return (settings.API_KEY or "").strip()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting SyncGuard", app_name=settings.APP_NAME, version=settings.APP_VERSION)
    require_production_secrets(settings.ENV, settings.SECRET_KEY)
    if settings.SECRET_KEY == "change-me-in-production":
        logger.error("SECURITY: SECRET_KEY is the default placeholder — override it in production")
    if not _api_key_configured():
        logger.error("SECURITY: SYNCGUARD_API_KEY / API_KEY is not configured — all API routes are open (development only)")
    init_db()
    yield
    logger.info("Shutting down SyncGuard")


app = FastAPI(
    title="SyncGuard",
    description="Cross-system data reconciliation and integration reliability platform",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

def cors_origins(raw: object) -> list:
    """Parse CORS_ORIGINS identically for app wiring and tests."""
    origins = [o.strip() for o in str(raw or "").split(",")] if raw is not None else ["*"]
    if not origins or origins == [""]:
        origins = ["*"]
    return origins


origins = cors_origins(getattr(settings, "CORS_ORIGINS", "*"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    """Application-level API-key boundary (not enterprise identity management).

    Enforced server-side whenever API_KEY is configured. Unset key means
    development-open mode (logged at startup). Docs/health stay public.
    """
    import hmac
    expected = _api_key_configured()
    if expected and request.url.path not in PUBLIC_PATHS:
        provided = request.headers.get("X-API-Key", "")
        if not provided or not hmac.compare_digest(provided, expected):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", error=str(exc), path=str(request.url))
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "code": "internal_error", "request_id": getattr(request.state, "request_id", "")})


app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "healthy", "app": settings.APP_NAME, "version": settings.APP_VERSION, "demo_mode": settings.DEMO_MODE}


@app.get("/readyz")
async def ready():
    """Readiness: database + model artifact. Lightweight, truthful."""
    from pathlib import Path
    checks = {}
    try:
        from backend.app.db.database import get_engine
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            conn.execute(_text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"unavailable: {type(e).__name__}"
    model_path = Path(__file__).resolve().parent / "models" / "febrl3_ml.pkl"
    checks["model"] = "ok" if model_path.exists() else "missing"
    ready = all(v == "ok" for v in checks.values())
    return {"ready": ready, "checks": checks}


@app.get("/")
async def root():
    return {"message": "Welcome to SyncGuard", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
