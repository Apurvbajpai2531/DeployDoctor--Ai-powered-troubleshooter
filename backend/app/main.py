import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import APP_NAME, APP_VERSION, PROJECT_ROOT, get_settings
from app.logging_config import setup_logging
from app.routes import analysis, health, upload

settings = get_settings()
setup_logging(settings.log_level, json_logs=settings.is_production)
logger = logging.getLogger("deploydoctor")

FRONTEND_DIR = PROJECT_ROOT / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting %s v%s | environment=%s | groq_configured=%s | database_configured=%s",
        APP_NAME,
        APP_VERSION,
        settings.environment,
        settings.groq_configured,
        bool(settings.effective_database_url),
    )
    yield
    logger.info("Shutting down %s", APP_NAME)


app = FastAPI(
    title=f"{APP_NAME} API",
    description=(
        "AI-powered DevOps deployment troubleshooter. "
        "Find the failure. Understand the cause. Fix the deployment."
    ),
    version=APP_VERSION,
    lifespan=lifespan,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Unhandled error on %s %s",
            request.method,
            request.url.path,
            extra={"request_id": request_id},
        )
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-ms"] = str(duration_ms)

    level = logging.DEBUG if request.url.path == "/health" else logging.INFO
    logger.log(
        level,
        "%s %s -> %s (%sms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Session-ID"],
    expose_headers=["X-Request-ID", "X-Process-Time-ms"],
)

app.include_router(health.router)
app.include_router(analysis.router)
app.include_router(upload.router)

# Serve the frontend (added in Phase 9). Safe to run before it exists.
if FRONTEND_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def root():
    index = FRONTEND_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return JSONResponse(
        {
            "service": APP_NAME,
            "version": APP_VERSION,
            "status": "running",
            "docs": "/docs",
            "health": "/health",
        }
    )
