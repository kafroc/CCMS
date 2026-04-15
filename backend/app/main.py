import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.logging_middleware import AuditLogMiddleware, record_error
from app.worker.worker import init_arq_pool, close_arq_pool
from app.routers import auth, users, ai_models, tasks, toes
from app.routers.threats import router as threats_router
from app.routers.security import router as security_router
from app.routers.tests import router as tests_router
from app.routers.risk import router as risk_router
from app.routers.export_st import router as export_router
from app.routers.system import router as system_router


# ── Fail fast on unsafe configuration ────────────────────────────────
_config_errors = settings.validate_for_runtime()
for _w in settings.warnings:
    log.warning("[config] %s", _w)
if _config_errors:
    for _e in _config_errors:
        log.error("[config] %s", _e)
    if settings.is_production:
        log.error(
            "[config] Refusing to start in production with unsafe configuration. "
            "Fix the above in your .env and restart."
        )
        # FastAPI hasn't been created yet, so exit cleanly.
        sys.exit(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: initialize DB and ARQ connection pool on startup, release on shutdown"""
    await init_db()
    await init_arq_pool()
    yield
    await close_arq_pool()
    await close_db()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/api/docs" if settings.is_development else None,
    redoc_url="/api/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

# ── CORS ────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Audit logging middleware ────────────────────────────────────────
app.add_middleware(AuditLogMiddleware)


# ── Global exception handler ──────────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # 5xx deserve a structured ErrorLog; 4xx are expected client mistakes.
    if exc.status_code >= 500:
        await record_error(request, exc)
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "msg": exc.detail or "error", "data": None},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if settings.is_development:
        import traceback
        traceback.print_exc()
    # Persist for the in-app log viewer.
    await record_error(request, exc)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "msg": "Internal server error", "data": None},
    )


# ── Register routes ──────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(ai_models.router)
app.include_router(tasks.router)
app.include_router(toes.router)
app.include_router(threats_router)
app.include_router(security_router)
app.include_router(tests_router)
app.include_router(risk_router)
app.include_router(export_router)
app.include_router(system_router)


@app.get("/api/health")
async def health():
    """Health check"""
    return {"code": 0, "msg": "ok", "data": {"version": "0.1.0"}}
