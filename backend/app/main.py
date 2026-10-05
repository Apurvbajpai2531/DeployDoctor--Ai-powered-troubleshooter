import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from app.config import APP_NAME, APP_VERSION, PROJECT_ROOT, get_settings
from app.logging_config import setup_logging
from app.routes import analysis, health, upload
from app.services.ai_service import AIServiceError
from app.utils.ratelimit import limiter

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


app.state.limiter = limiter


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


DOCS_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}

# The frontend uses no inline scripts or styles, so a strict policy works.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    # Reject oversized bodies up front using Content-Length. In production nginx
    # enforces the same cap (.platform/nginx/conf.d/uploads.conf).
    if request.method in {"POST", "PUT", "PATCH"}:
        length = request.headers.get("content-length")
        if length is not None:
            try:
                too_big = int(length) > settings.max_request_bytes
            except ValueError:
                return JSONResponse(
                    status_code=400, content={"detail": "Invalid Content-Length header."}
                )
            if too_big:
                logger.warning(
                    "Rejected oversized request: %s %s (%s bytes)",
                    request.method,
                    request.url.path,
                    length,
                )
                return JSONResponse(
                    status_code=413, content={"detail": "Request body too large."}
                )
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    headers = response.headers
    headers["X-Content-Type-Options"] = "nosniff"
    headers["X-Frame-Options"] = "DENY"
    headers["Referrer-Policy"] = "no-referrer"
    headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    headers["Cross-Origin-Opener-Policy"] = "same-origin"
    path = request.url.path
    if path not in DOCS_PATHS:  # Swagger UI needs a CDN and inline scripts
        headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    if path.startswith("/api/"):
        headers["Cache-Control"] = "no-store"  # per-session data must not be cached
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

@app.exception_handler(AIServiceError)
async def ai_error_handler(request: Request, exc: AIServiceError):
    logger.warning("AI error on %s: %s", request.url.path, type(exc).__name__)
    headers = {"Retry-After": "10"} if exc.http_status == 429 else None
    return JSONResponse(
        status_code=exc.http_status,
        content={"detail": exc.user_message},
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Report where and why only. Never echo the submitted input back: it can be a
    # huge log and may contain secrets.
    errors = [
        {
            "loc": [str(part) for part in err.get("loc", ())],
            "msg": err.get("msg", "Invalid input"),
            "type": err.get("type", ""),
        }
        for err in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning("Rate limit exceeded on %s", request.url.path)
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please wait a minute and try again."},
        headers={"Retry-After": "60"},
    )


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
