from fastapi import APIRouter
from fastapi.responses import FileResponse

from .schemas import (
    AppendCustomerNoteRequest,
    CustomerDiscount,
    CustomerNoteListResponse,
    LockboxReviewQueueExportRequest,
    LockboxReviewResponse,
    SaveCustomerDiscountRequest,
    SaveTransactionReviewRequest,
)
from .service import (
    append_transaction_customer_note,
    create_carryover_export,
    create_review_queue_export,
    create_reviewed_export,
    get_customer_discount,
    get_lockbox_review,
    get_transaction_customer_notes,
    list_carryover_transactions,
    save_customer_discount,
    save_transaction_review,
)

router = APIRouter(
    prefix="/api/v1/documents",
    tags=["Lockbox Review"],
)


@router.get(
    "/jobs/{job_id}/lockbox/review",
    response_model=LockboxReviewResponse,
)
def read_lockbox_review(job_id: str) -> LockboxReviewResponse:
    return LockboxReviewResponse(**get_lockbox_review(job_id))


@router.put(
    "/jobs/{job_id}/lockbox/review/{transaction_id}",
    response_model=LockboxReviewResponse,
)
def update_lockbox_transaction_review(
    job_id: str,
    transaction_id: str,
    payload: SaveTransactionReviewRequest,
) -> LockboxReviewResponse:
    return LockboxReviewResponse(
        **save_transaction_review(job_id, transaction_id, payload.model_dump())
    )


@router.get(
    "/jobs/{job_id}/lockbox/review/{transaction_id}/customer-notes",
    response_model=CustomerNoteListResponse,
)
def read_lockbox_customer_notes(
    job_id: str,
    transaction_id: str,
) -> CustomerNoteListResponse:
    return CustomerNoteListResponse(
        **get_transaction_customer_notes(job_id, transaction_id)
    )


@router.post(
    "/jobs/{job_id}/lockbox/review/{transaction_id}/customer-notes",
    response_model=CustomerNoteListResponse,
    status_code=201,
)
def create_lockbox_customer_note(
    job_id: str,
    transaction_id: str,
    payload: AppendCustomerNoteRequest,
) -> CustomerNoteListResponse:
    return CustomerNoteListResponse(
        **append_transaction_customer_note(
            job_id,
            transaction_id,
            payload.model_dump(),
        )
    )


@router.get(
    "/jobs/{job_id}/lockbox/reviewed-export",
    response_class=FileResponse,
)
def export_reviewed_lockbox(job_id: str) -> FileResponse:
    output = create_reviewed_export(job_id)
    return FileResponse(
        path=output,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        filename=output.name,
    )


@router.post(
    "/jobs/{job_id}/lockbox/review-queue-export",
    response_class=FileResponse,
)
def export_lockbox_review_queue(
    job_id: str,
    payload: LockboxReviewQueueExportRequest,
) -> FileResponse:
    output = create_review_queue_export(
        job_id,
        payload.transaction_ids,
        payload.queue_label,
        payload.reason_code,
    )
    return FileResponse(
        path=output,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        filename=output.name,
    )


@router.get(
    "/lockbox/customer-discount/{customer_number}",
    response_model=CustomerDiscount,
)
def read_lockbox_customer_discount(customer_number: str) -> CustomerDiscount:
    return CustomerDiscount(**get_customer_discount(customer_number))


@router.put(
    "/lockbox/customer-discount/{customer_number}",
    response_model=CustomerDiscount,
)
def update_lockbox_customer_discount(
    customer_number: str,
    payload: SaveCustomerDiscountRequest,
) -> CustomerDiscount:
    return CustomerDiscount(
        **save_customer_discount(customer_number, payload.model_dump())
    )


@router.get("/lockbox/carryover")
def read_carryover_transactions() -> dict:
    return {"transactions": list_carryover_transactions()}


@router.get(
    "/lockbox/carryover/export",
    response_class=FileResponse,
)
def export_carryover_transactions(customer_number: str = "") -> FileResponse:
    output = create_carryover_export(customer_number)
    return FileResponse(
        path=output,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        filename=output.name,
    )
