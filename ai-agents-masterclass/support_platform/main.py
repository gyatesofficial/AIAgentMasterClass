"""
main.py - FastAPI Application Entry Point
==========================================
The main FastAPI application for the AI Customer Support Platform.

Run with:
    uvicorn support_platform.main:app --reload --port 8080

Or from the CourseFiles directory:
    python -m uvicorn support_platform.main:app --reload

API Documentation (auto-generated):
    http://localhost:8080/docs       - Swagger UI
    http://localhost:8080/redoc      - ReDoc

Endpoints:
    POST /tickets          - Submit a new ticket
    GET  /tickets          - List tickets
    GET  /tickets/{id}     - Get ticket status
    POST /tickets/{id}/resolve  - Manually resolve
    GET  /health           - System health check
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from support_platform.api.routes import router
from support_platform.config import settings

# ──────────────────────────────────────────────────────────────
# Logging configuration
# ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Lifespan events (startup / shutdown)
# ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Code before `yield` runs on startup.
    Code after `yield` runs on shutdown.

    This is where you initialize connections and load data.
    """
    # ── Startup ─────────────────────────────────────────────
    logger.info("Starting AI Customer Support Platform")
    logger.info(f"Environment: {settings.app_env}")
    logger.info(f"Default model: {settings.default_model}")

    # Validate configuration
    issues = settings.validate_for_production()
    if issues:
        for issue in issues:
            logger.warning(f"Config warning: {issue}")
    else:
        logger.info("Configuration validated OK")

    # Test database connection
    try:
        from support_platform.database.models import check_db_connection
        if check_db_connection():
            logger.info("Database connection OK")
        else:
            logger.warning("Database not reachable — using in-memory fallback")
    except Exception as e:
        logger.warning(f"Database check failed: {e}")

    # Test Redis connection
    try:
        import redis
        r = redis.from_url(settings.redis_url, socket_timeout=2)
        r.ping()
        logger.info("Redis connection OK")
    except Exception as e:
        logger.warning(f"Redis not available: {e}")

    # Test ChromaDB connection
    try:
        import httpx
        resp = httpx.get(f"{settings.chroma_url}/api/v1", timeout=2)
        if resp.status_code == 200:
            logger.info("ChromaDB connection OK")
        else:
            logger.warning(f"ChromaDB returned status {resp.status_code}")
    except Exception as e:
        logger.warning(f"ChromaDB not available: {e}")

    logger.info("Startup complete — ready to accept requests")

    yield  # Application runs here

    # ── Shutdown ─────────────────────────────────────────────
    logger.info("Shutting down AI Customer Support Platform")


# ──────────────────────────────────────────────────────────────
# FastAPI application
# ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Customer Support Platform",
    description=(
        "An AI-powered customer support platform built with FastAPI, LangGraph, "
        "and OpenAI/Anthropic. Part of the 'AI Agents: From Architecture to Production' course.\n\n"
        "GitHub: https://github.com/gyatesofficial/AIAgentMasterClass"
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── Middleware ────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request logging middleware ────────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests and their response status."""
    start_time = __import__("time").time()
    response = await call_next(request)
    duration_ms = int((__import__("time").time() - start_time) * 1000)

    logger.info(
        f"{request.method} {request.url.path} "
        f"→ {response.status_code} ({duration_ms}ms)"
    )
    return response


# ── Error handlers ────────────────────────────────────────────

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all error handler — never expose stack traces in production."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    if settings.is_development:
        # Show details in development
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": str(exc),
                "type": type(exc).__name__,
            },
        )
    else:
        # Generic message in production (don't leak internals)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": "An unexpected error occurred. Please try again or contact support.",
            },
        )


# ── Routes ────────────────────────────────────────────────────

app.include_router(router, prefix="/api/v1")

# Also mount at root for backwards compatibility
app.include_router(router)


# ── Root endpoint ─────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint — redirect to docs."""
    return {
        "name": "AI Customer Support Platform",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "course": "AI Agents: From Architecture to Production",
        "github": "https://github.com/gyatesofficial/AIAgentMasterClass",
    }


# ──────────────────────────────────────────────────────────────
# Run directly (development mode)
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    print("\n" + "=" * 60)
    print("  AI Customer Support Platform")
    print("=" * 60)
    print(f"\n  Environment: {settings.app_env}")
    print(f"  API docs:    http://localhost:8080/docs")
    print(f"  Health:      http://localhost:8080/health")
    print()

    uvicorn.run(
        "support_platform.main:app",
        host="0.0.0.0",
        port=8080,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )
