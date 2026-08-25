"""
Merge these imports and endpoints into your existing document-intelligence
router.py.

Your current router already imports `get_job` from `.service`. The endpoints
use it only to confirm that the document job exists.
"""

from fastapi import HTTPException

from .review_schemas import (
    DocumentReviewResponse,
    DocumentReviewSaveRequest,
)
from .review_store import get_review, save_review


@router.get(
    "/jobs/{job_id}/review",
    response_model=DocumentReviewResponse,
)
def read_document_review(
    job_id: str,
) -> DocumentReviewResponse:
    # Your existing service raises its normal not-found exception if needed.
    get_job(job_id)

    return DocumentReviewResponse(
        **get_review(job_id)
    )


@router.put(
    "/jobs/{job_id}/review",
    response_model=DocumentReviewResponse,
)
def update_document_review(
    job_id: str,
    payload: DocumentReviewSaveRequest,
) -> DocumentReviewResponse:
    get_job(job_id)

    try:
        review = save_review(
            job_id,
            status=payload.status,
            reviewer=payload.reviewer.strip(),
            notes=payload.notes.strip(),
            corrected_fields=payload.corrected_fields,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    return DocumentReviewResponse(**review)
