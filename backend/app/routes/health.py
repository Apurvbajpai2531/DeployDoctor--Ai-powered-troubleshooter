import time
from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import APP_NAME, APP_VERSION, get_settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])

STARTED_AT = time.time()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application health check",
    description="Used by Elastic Beanstalk and load balancers to check that the app is running.",
)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=APP_NAME,
        version=APP_VERSION,
        environment=settings.environment,
        uptime_seconds=round(time.time() - STARTED_AT, 2),
        timestamp=datetime.now(timezone.utc),
    )
