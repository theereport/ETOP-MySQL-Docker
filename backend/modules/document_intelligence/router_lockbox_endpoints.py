"""
Merge these imports and routes into the existing document-intelligence
router.py.

The route code expects your existing `get_job(job_id)` service function to
return a dictionary containing `stored_path`.
"""

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

from .lockbox_schemas import (
    LockboxProcessingResponse,
)
from .lockbox_service import (
    create_lockbox_export,
    get_lockbox_result,
    process_lockbox,
)


@router.post(
    "/jobs/{job_id}/lockbox/process",
    response_model=LockboxProcessingResponse,
)
def process_pnc_lockbox_job(
    job_id: str,
) -> LockboxProcessingResponse:
    job = get_job(job_id)
    stored_path = job.get(
        "stored_path"
    )

    if not stored_path:
        raise HTTPException(
            status_code=404,
            detail="Stored PDF path is missing.",
        )

    path = Path(
        stored_path
    ).resolve()

    if (
        not path.exists()
        or path.suffix.lower() != ".pdf"
    ):
        raise HTTPException(
            status_code=404,
            detail="Stored PNC PDF was not found.",
        )

    result = process_lockbox(
        job_id,
        path,
    )

    return LockboxProcessingResponse(
        **result
    )


@router.get(
    "/jobs/{job_id}/lockbox/result",
    response_model=LockboxProcessingResponse,
)
def read_pnc_lockbox_result(
    job_id: str,
) -> LockboxProcessingResponse:
    try:
        result = get_lockbox_result(
            job_id
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    return LockboxProcessingResponse(
        **result
    )


@router.get(
    "/jobs/{job_id}/lockbox/export",
    response_class=FileResponse,
)
def export_pnc_lockbox_file(
    job_id: str,
) -> FileResponse:
    try:
        output = create_lockbox_export(
            job_id
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    return FileResponse(
        path=output,
        media_type=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
        filename=output.name,
    )
