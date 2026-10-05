from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.analysis import AnalysisListResponse, AnalysisOut
from app.services import analysis_service
from app.utils.session import get_session_id

router = APIRouter(prefix="/api", tags=["Analyses"])

NOT_FOUND = HTTPException(status_code=404, detail="Analysis not found")


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
