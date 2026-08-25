from fastapi import APIRouter, File, Query, UploadFile

from .parsers import parser_registry
from .schemas import (
    DocumentJobListResponse,
    DocumentJobResponse,
    DocumentProcessResponse,
    ModuleHealthResponse,
    ParserListResponse,
)
from .service import (
    create_upload_job,
    get_health,
    get_job,
    get_job_result,
    list_jobs,
    process_job,
)

router = APIRouter(
    prefix="/api/v1/documents",
    tags=["Document Intelligence"],
)


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


@router.get("/jobs/{job_id}", response_model=DocumentJobResponse)
def read_document_job(job_id: str) -> DocumentJobResponse:
    return DocumentJobResponse(**get_job(job_id))


@router.get("/jobs", response_model=DocumentJobListResponse)
def read_document_jobs(
    limit: int = Query(default=50, ge=1, le=200),
) -> DocumentJobListResponse:
    return DocumentJobListResponse(
        jobs=[DocumentJobResponse(**job) for job in list_jobs(limit)]
    )
