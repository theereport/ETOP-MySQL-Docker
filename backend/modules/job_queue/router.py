"""Runtime API contract for the cross-module background job queue.

Mounted under /api/v1/platform, which already resolves to the baseline
`dashboard` module grant every signed-in user has (see
`modules/workflow_foundation/access_policy.py`) - the same grant
`modules/platform_search` piggybacks on. This module reports job
progress; it does not itself start, approve, export, or post any work.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .service import JobQueueService, job_queue_service

router = APIRouter(
    prefix="/api/v1/platform/job-queue",
    tags=["ETOP Platform Job Queue"],
)

VALID_STATUSES = ("queued", "running", "completed", "failed")


def _service() -> JobQueueService:
    return job_queue_service


@router.get("/jobs")
def list_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None),
) -> dict:
    statuses: tuple[str, ...] | None = None
    if status:
        statuses = tuple(
            value.strip() for value in status.split(",") if value.strip()
        )
        invalid = [value for value in statuses if value not in VALID_STATUSES]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown job status: {', '.join(invalid)}",
            )
    return {
        "data": _service().list_jobs(limit=limit, statuses=statuses),
    }


@router.get("/summary")
def job_summary(
    recent_limit: int = Query(default=10, ge=1, le=50),
) -> dict:
    return {"data": _service().summary(recent_limit=recent_limit)}


@router.post("/jobs/{job_id}/acknowledge")
def acknowledge_job(job_id: str) -> dict:
    _service().acknowledge(job_id)
    return {"data": {"job_id": job_id, "acknowledged": True}}
