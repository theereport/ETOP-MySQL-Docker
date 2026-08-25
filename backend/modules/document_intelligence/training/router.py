from fastapi import APIRouter, File, Query, UploadFile

from .schemas import (
    TrainingSessionListResponse,
    TrainingSessionResponse,
    TrainingSummaryResponse,
)
from .service import (
    create_lockbox_training_session,
    get_training_session,
    get_training_sessions,
    get_training_summary,
)

router = APIRouter(prefix="/training", tags=["Document Training"])


@router.post(
    "/jobs/{job_id}/ground-truth",
    response_model=TrainingSessionResponse,
    status_code=201,
)
async def upload_ground_truth(job_id: str, file: UploadFile = File(...)) -> TrainingSessionResponse:
    return TrainingSessionResponse(**(await create_lockbox_training_session(job_id, file)))


@router.get("/sessions", response_model=TrainingSessionListResponse)
def read_training_sessions(limit: int = Query(default=100, ge=1, le=500)) -> TrainingSessionListResponse:
    return TrainingSessionListResponse(
        sessions=[TrainingSessionResponse(**item) for item in get_training_sessions(limit)]
    )


@router.get("/summary", response_model=TrainingSummaryResponse)
def read_training_summary() -> TrainingSummaryResponse:
    return TrainingSummaryResponse(**get_training_summary())


@router.get("/sessions/{session_id}", response_model=TrainingSessionResponse)
def read_training_session(session_id: str) -> TrainingSessionResponse:
    return TrainingSessionResponse(**get_training_session(session_id))
