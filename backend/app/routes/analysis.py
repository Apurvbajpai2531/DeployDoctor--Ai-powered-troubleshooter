from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.analysis import (
    AnalysisListResponse,
    AnalysisOut,
    AnalyzeRequest,
    AnalyzeResponse,
)
from app.services import analysis_service
from app.utils.session import get_session_id

router = APIRouter(prefix="/api", tags=["Analyses"])

NOT_FOUND = HTTPException(status_code=404, detail="Analysis not found")


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    status_code=201,
    summary="Analyze a deployment/application log",
    description=(
        "Sends the log to the AI, validates the structured diagnosis, saves it, "
        "and returns it. Commands in the result are recommendations only; "
        "nothing is ever executed."
    ),
    responses={
        400: {"description": "Missing or invalid X-Session-ID header"},
        422: {"description": "Invalid input (empty log, too long, unknown category)"},
        429: {"description": "AI service is rate limited"},
        502: {"description": "AI service failed"},
        503: {"description": "AI service not configured"},
        504: {"description": "AI service timed out"},
    },
)
def analyze(
    payload: AnalyzeRequest,
    session_id: str = Depends(get_session_id),
    db: Session = Depends(get_db),
):
    row, degraded = analysis_service.create_analysis(
        db, session_id, payload.log_text, payload.category
    )
    data = AnalysisOut.model_validate(row).model_dump()
    return AnalyzeResponse(**data, degraded=degraded)


@router.get(
    "/analyses",
    response_model=AnalysisListResponse,
    summary="List previous analyses",
    description="Returns this session's analyses, newest first.",
)
def list_analyses(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session_id: str = Depends(get_session_id),
    db: Session = Depends(get_db),
):
    rows, total = analysis_service.list_analyses(db, session_id, limit, offset)
    return AnalysisListResponse(items=rows, total=total, limit=limit, offset=offset)


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisOut,
    summary="Get one analysis",
    responses={404: {"description": "Analysis not found"}},
)
def get_analysis(
    analysis_id: int,
    session_id: str = Depends(get_session_id),
    db: Session = Depends(get_db),
):
    row = analysis_service.get_analysis(db, session_id, analysis_id)
    if row is None:
        raise NOT_FOUND
    return row


@router.delete(
    "/analyses/{analysis_id}",
    status_code=204,
    summary="Delete one analysis",
    responses={404: {"description": "Analysis not found"}},
)
def delete_analysis(
    analysis_id: int,
    session_id: str = Depends(get_session_id),
    db: Session = Depends(get_db),
):
    if not analysis_service.delete_analysis(db, session_id, analysis_id):
        raise NOT_FOUND
    return Response(status_code=204)
