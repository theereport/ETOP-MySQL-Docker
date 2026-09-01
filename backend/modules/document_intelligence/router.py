from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse

from .learning_schemas import (
    GenerateLearningExamplesResponse,
    LearningExampleListResponse,
    LearningSummaryResponse,
)
from .learning_store import (
    create_examples,
    get_summary,
    list_examples,
)
from .parsers import parser_registry
from .review_schemas import (
    DocumentReviewResponse,
    DocumentReviewSaveRequest,
)
from .review_store import (
    get_review,
    pack_review_fields,
)
from .schemas import (
    DocumentJobListResponse,
    DocumentJobResponse,
    DocumentProcessingRunDetail,
    DocumentProcessingRunListResponse,
    DocumentProcessResponse,
    ModuleHealthResponse,
    ParserListResponse,
    VendorInvoiceIntakeResponse,
)
from .service import (
    count_jobs,
    create_upload_job,
    create_vendor_invoice_intake,
    delete_job,
    get_health,
    get_job,
    get_job_processing_run,
    get_job_processing_runs,
    get_job_result,
    get_managed_job_pdf_path,
    list_jobs,
    process_job,
    save_current_job_review,
)
from .lockbox_schemas import (
    CustomerSuggestionListResponse,
    LockboxProcessingResponse,
)
from .training.router import router as training_router
from .lockbox_service import (
    create_lockbox_export,
    get_customer_suggestions,
    get_lockbox_result,
    process_lockbox,
)


router = APIRouter(
    prefix="/api/v1/documents",
    tags=["Document Intelligence"],
)

router.include_router(training_router)


@router.get("/health", response_model=ModuleHealthResponse)
def document_intelligence_health() -> ModuleHealthResponse:
    return ModuleHealthResponse(**get_health())


@router.get("/parsers", response_model=ParserListResponse)
def list_registered_parsers() -> ParserListResponse:
    return ParserListResponse(parsers=parser_registry.list_parsers())


@router.post("/upload", response_model=DocumentJobResponse, status_code=201)
async def upload_document(file: UploadFile = File(...)) -> DocumentJobResponse:
    return DocumentJobResponse(**(await create_upload_job(file)))


@router.post(
    "/vendor-invoices/upload",
    response_model=VendorInvoiceIntakeResponse,
    status_code=201,
)
async def upload_vendor_invoice(
    file: UploadFile = File(...),
) -> VendorInvoiceIntakeResponse:
    """Preserve and process one AP vendor invoice through PSS-007.

    This route constrains parser selection only. It never approves an invoice,
    authorizes payment, posts, writes to ERP, or performs external AI work.
    """

    return VendorInvoiceIntakeResponse(**(await create_vendor_invoice_intake(file)))


@router.post(
    "/jobs/{job_id}/process",
    response_model=DocumentProcessResponse,
)
def process_document_job(job_id: str) -> DocumentProcessResponse:
    return DocumentProcessResponse(**process_job(job_id))


@router.get(
    "/jobs/{job_id}/result",
    response_model=DocumentProcessResponse,
)
def read_document_result(job_id: str) -> DocumentProcessResponse:
    return DocumentProcessResponse(**get_job_result(job_id))


@router.get(
    "/jobs/{job_id}/runs",
    response_model=DocumentProcessingRunListResponse,
)
def read_document_processing_runs(
    job_id: str,
) -> DocumentProcessingRunListResponse:
    return DocumentProcessingRunListResponse(
        job_id=job_id,
        runs=get_job_processing_runs(job_id),
    )


@router.get(
    "/jobs/{job_id}/runs/{processing_run_id}",
    response_model=DocumentProcessingRunDetail,
)
def read_document_processing_run(
    job_id: str,
    processing_run_id: str,
) -> DocumentProcessingRunDetail:
    return DocumentProcessingRunDetail(
        **get_job_processing_run(job_id, processing_run_id)
    )


@router.get(
    "/jobs/{job_id}/file",
    response_class=FileResponse,
)
def get_document_file(job_id: str) -> FileResponse:
    job = get_job(job_id)
    stored_path = get_managed_job_pdf_path(job_id)

    original_file_name = job.get("original_file_name") or stored_path.name

    return FileResponse(
        path=str(stored_path),
        media_type="application/pdf",
        filename=original_file_name,
        content_disposition_type="inline",
    )


@router.get("/jobs/{job_id}", response_model=DocumentJobResponse)
def read_document_job(job_id: str) -> DocumentJobResponse:
    return DocumentJobResponse(**get_job(job_id))


@router.delete("/jobs/{job_id}", status_code=204)
def remove_document_job(job_id: str) -> None:
    delete_job(job_id)


@router.get("/jobs", response_model=DocumentJobListResponse)
def read_document_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DocumentJobListResponse:
    return DocumentJobListResponse(
        jobs=[
            DocumentJobResponse(**job)
            for job in list_jobs(limit, offset=offset)
        ],
        total=count_jobs(),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/vendor-invoices/jobs",
    response_model=DocumentJobListResponse,
)
def read_vendor_invoice_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DocumentJobListResponse:
    return DocumentJobListResponse(
        jobs=[
            DocumentJobResponse(**job)
            for job in list_jobs(
                limit,
                document_type="vendor_invoice",
                offset=offset,
            )
        ],
        total=count_jobs(document_type="vendor_invoice"),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/jobs/{job_id}/review",
    response_model=DocumentReviewResponse,
)
def read_document_review(job_id: str) -> DocumentReviewResponse:
    get_job(job_id)
    return DocumentReviewResponse(**get_review(job_id))


@router.put(
    "/jobs/{job_id}/review",
    response_model=DocumentReviewResponse,
)
def update_document_review(
    job_id: str,
    payload: DocumentReviewSaveRequest,
) -> DocumentReviewResponse:
    get_job(job_id)

    unavailable_fields = payload.unavailable_fields
    if unavailable_fields is None:
        # Additive compatibility for existing review clients: omission keeps
        # a disposition only while it belongs to the expected current run.
        existing_review = get_review(job_id)["review"]
        unavailable_fields = (
            [
                field_name
                for field_name in existing_review.get(
                    "unavailable_fields",
                    [],
                )
                if field_name not in payload.corrected_fields
            ]
            if existing_review.get("processing_run_id")
            == payload.expected_processing_run_id
            else []
        )

    try:
        review = save_current_job_review(
            job_id,
            expected_processing_run_id=payload.expected_processing_run_id,
            status=payload.status,
            reviewer=payload.reviewer.strip(),
            notes=payload.notes.strip(),
            corrected_fields=pack_review_fields(
                payload.corrected_fields,
                unavailable_fields,
            ),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return DocumentReviewResponse(**review)


@router.get(
    "/learning/summary",
    response_model=LearningSummaryResponse,
)
def read_learning_summary() -> LearningSummaryResponse:
    return LearningSummaryResponse(**get_summary())


@router.get(
    "/learning/examples",
    response_model=LearningExampleListResponse,
)
def read_learning_examples(
    limit: int = Query(default=100, ge=1, le=500),
) -> LearningExampleListResponse:
    return LearningExampleListResponse(**list_examples(limit))


@router.post(
    "/jobs/{job_id}/learning",
    response_model=GenerateLearningExamplesResponse,
)
def create_job_learning_examples(
    job_id: str,
) -> GenerateLearningExamplesResponse:
    job = get_job(job_id)
    result = get_job_result(job_id)
    review = get_review(job_id)["review"]
    if review.get("processing_run_id") != result.get("processing_run_id"):
        raise HTTPException(
            status_code=409,
            detail=(
                "Learning evidence cannot be generated from a review that does "
                "not match the current processing run. Reload and review the current run."
            ),
        )
    corrected_fields = review.get("corrected_fields", {})

    if not corrected_fields:
        return GenerateLearningExamplesResponse(
            created=0,
            skipped=0,
            examples=[],
        )

    parsed = result.get("parsed", {})
    if not isinstance(parsed, dict):
        parsed = {}

    return GenerateLearningExamplesResponse(
        **create_examples(
            job_id=job_id,
            document_type=job.get("document_type", "unknown"),
            original_fields=parsed,
            corrected_fields=corrected_fields,
            reviewer=review.get("reviewer", ""),
            source_status=review.get("status", "pending"),
        )
    )


@router.post(
    "/jobs/{job_id}/lockbox/process",
    response_model=LockboxProcessingResponse,
)
def process_pnc_lockbox_job(
    job_id: str,
) -> LockboxProcessingResponse:
    path = get_managed_job_pdf_path(job_id)
    return LockboxProcessingResponse(**process_lockbox(job_id, path))


@router.get(
    "/jobs/{job_id}/lockbox/result",
    response_model=LockboxProcessingResponse,
)
def read_pnc_lockbox_result(
    job_id: str,
) -> LockboxProcessingResponse:
    try:
        result = get_lockbox_result(job_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return LockboxProcessingResponse(**result)


@router.get(
    "/jobs/{job_id}/lockbox/review/{transaction_id}/customer-suggestions",
    response_model=CustomerSuggestionListResponse,
)
def read_customer_match_suggestions(
    job_id: str,
    transaction_id: str,
    limit: int = Query(default=5, ge=1, le=20),
) -> CustomerSuggestionListResponse:
    try:
        result = get_customer_suggestions(job_id, transaction_id, limit)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return CustomerSuggestionListResponse(**result)


@router.get(
    "/jobs/{job_id}/lockbox/export",
    response_class=FileResponse,
)
def export_pnc_lockbox_file(job_id: str) -> FileResponse:
    try:
        output = create_lockbox_export(job_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return FileResponse(
        path=output,
        media_type=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
        filename=output.name,
    )
