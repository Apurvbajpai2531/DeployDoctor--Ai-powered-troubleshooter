import logging
from pathlib import PurePath

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.config import get_settings
from app.schemas.analysis import UploadResponse
from app.utils.ratelimit import limiter

logger = logging.getLogger("deploydoctor.upload")

router = APIRouter(prefix="/api", tags=["Upload"])

ALLOWED_EXTENSIONS = {".log", ".txt", ".out"}


@router.post(
    "/upload-log",
    response_model=UploadResponse,
    summary="Upload a log file",
    description=(
        "Validates a .log/.txt/.out file and returns its text so the UI can "
        "show it in the editor. Nothing is stored and nothing is executed."
    ),
    responses={
        400: {"description": "Invalid file"},
        413: {"description": "File or log text too large"},
    },
)
@limiter.limit(get_settings().upload_rate_limit)
async def upload_log(
    request: Request, file: UploadFile = File(...)
) -> UploadResponse:
    settings = get_settings()

    # Never use the client's path; keep only the base name for display
    filename = PurePath(file.filename or "upload.log").name
    if PurePath(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only .log, .txt and .out files are accepted.",
        )

    # Read at most limit + 1 bytes so oversized files are never fully loaded
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_upload_bytes} byte limit.",
        )
    if not data.strip():
        raise HTTPException(status_code=400, detail="The file is empty.")
    if b"\x00" in data:
        raise HTTPException(status_code=400, detail="Binary files are not accepted.")

    text = data.decode("utf-8", errors="replace").strip()
    if len(text) > settings.max_log_chars:
        raise HTTPException(
            status_code=413,
            detail=f"Log text exceeds the {settings.max_log_chars} character limit.",
        )

    logger.info("Log file accepted: %s bytes, %s chars", len(data), len(text))
    return UploadResponse(
        filename=filename,
        size_bytes=len(data),
        characters=len(text),
        text=text,
    )
