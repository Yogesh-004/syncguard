"""SyncGuard — Main FastAPI application."""
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.db.database import init_db
from backend.app.api.routes import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting SyncGuard", app_name=settings.APP_NAME, version=settings.APP_VERSION)
    init_db()
    yield
    logger.info("Shutting down SyncGuard")


app = FastAPI(
    title="SyncGuard",
    description="Cross-system data reconciliation and integration reliability platform",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",")] if hasattr(settings, "CORS_ORIGINS") else ["*"]
if not origins or origins == [""]:
    origins = ["*"]

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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", error=str(exc), path=str(request.url))
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "code": "internal_error", "request_id": getattr(request.state, "request_id", "")})


app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "healthy", "app": settings.APP_NAME, "version": settings.APP_VERSION, "demo_mode": settings.DEMO_MODE}


@app.get("/")
async def root():
    return {"message": "Welcome to SyncGuard", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
