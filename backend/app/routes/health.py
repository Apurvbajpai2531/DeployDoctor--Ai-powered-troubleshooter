import time
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import APP_NAME, APP_VERSION, get_settings
from app.database import check_database
from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])

STARTED_AT = time.time()


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Database unavailable"}},
    summary="Application health check",
    description=(
        "Used by Elastic Beanstalk and load balancers. "
        "Returns 200 when the app and database are healthy, 503 otherwise."
    ),
)
def health():
    settings = get_settings()
    db_ok = check_database()
    body = HealthResponse(
        status="ok" if db_ok else "degraded",
        service=APP_NAME,
        version=APP_VERSION,
        environment=settings.environment,
        database="ok" if db_ok else "unavailable",
        uptime_seconds=round(time.time() - STARTED_AT, 2),
        timestamp=datetime.now(timezone.utc),
    )
    if db_ok:
        return body
    return JSONResponse(status_code=503, content=body.model_dump(mode="json"))
