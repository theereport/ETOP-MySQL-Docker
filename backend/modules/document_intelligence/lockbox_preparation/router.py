"""Runtime API contract for durable Lockbox preparation.

Registration is owned by the Document Intelligence manifest and remains
separate from production provider binding. Importing this router does not
start, approve, export, or post any work.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .errors import IdempotencyConflictError
from .service import DurableLockboxPreparationService


class StartDurablePreparationRequest(BaseModel):
    source_file_hash: str = Field(default="", max_length=128)
    correlation_id: str = Field(default="", max_length=200)
    idempotency_key: str = Field(default="", max_length=300)


class ResumeDurablePreparationRequest(BaseModel):
    retry_exceptions: bool = False


router = APIRouter(
    prefix="/api/v1/documents",
    tags=["Durable Lockbox Preparation"],
)

_service: DurableLockboxPreparationService | None = None


def configure_durable_lockbox_preparation(
    service: DurableLockboxPreparationService,
) -> None:
    global _service
    _service = service


def _configured_service() -> DurableLockboxPreparationService:
    if _service is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Durable Lockbox preparation is not yet bound to the "
                "approved local read-only services."
            ),
        )
    return _service


@router.post("/jobs/{source_job_id}/lockbox/preparation/start")
def start_durable_preparation(
    source_job_id: str,
    payload: StartDurablePreparationRequest,
) -> dict:
    try:
        return _configured_service().start_source_job(
            source_job_id,
            payload.source_file_hash,
            correlation_id=payload.correlation_id,
            idempotency_key=payload.idempotency_key,
            background=True,
        )
    except (KeyError, FileNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except IdempotencyConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/lockbox/preparation/{job_id}/resume")
def resume_durable_preparation(
    job_id: str,
    payload: ResumeDurablePreparationRequest,
) -> dict:
    try:
        return _configured_service().resume(
            job_id,
            retry_exceptions=payload.retry_exceptions,
            background=True,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/lockbox/preparation/{job_id}")
def durable_preparation_status(
    job_id: str,
    include_transactions: bool = Query(default=True),
) -> dict:
    try:
        return _configured_service().status(
            job_id,
            include_transactions=include_transactions,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/jobs/{source_job_id}/lockbox/preparation/current")
def current_durable_preparation(
    source_job_id: str,
    include_transactions: bool = Query(default=True),
) -> dict:
    try:
        return _configured_service().current_source_job(
            source_job_id,
            include_transactions=include_transactions,
        )
    except (KeyError, FileNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/lockbox/preparation/{job_id}/history")
def durable_preparation_history(job_id: str) -> dict:
    try:
        return {
            "job_id": job_id,
            "events": _configured_service().history(job_id),
        }
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/lockbox/preparation/{job_id}/exception-summary")
def durable_preparation_exception_summary(job_id: str) -> dict:
    try:
        return _configured_service().exception_summary(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
