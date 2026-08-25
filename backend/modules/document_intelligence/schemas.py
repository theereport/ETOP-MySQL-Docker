from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


JobStatus = Literal["uploaded", "processing", "completed", "failed"]
DocumentType = Literal[
    "pnc_lockbox",
    "bank_report",
    "vendor_invoice",
    "statement",
    "unknown",
]


class DocumentJobResponse(BaseModel):
    job_id: str
    original_file_name: str
    stored_file_name: str
    content_type: str
    file_size_bytes: int
    source_sha256: str | None = None
    intake_document_type: DocumentType | None = None
    intake_source: str | None = None
    duplicate_of_job_id: str | None = None
    document_type: DocumentType
    confidence: float
    status: JobStatus
    message: str
    created_at: datetime
    updated_at: datetime

class DocumentJobListResponse(BaseModel):
    jobs: list[DocumentJobResponse]
    total: int = 0
    limit: int = 0
    offset: int = 0


class DocumentProcessResponse(BaseModel):
    job: DocumentJobResponse
    classifier: str
    classification_evidence: list[str]
    extraction: dict[str, Any]
    parsed: dict[str, Any]
    processing_run_id: str | None = None
    processing_run_number: int | None = None
    processor_version: str | None = None
    source_sha256: str | None = None


class DocumentProcessingRunSummary(BaseModel):
    processing_run_id: str
    job_id: str
    run_number: int
    processor_version: str
    source_sha256: str | None = None
    status: Literal["completed", "failed"]
    classifier: str | None = None
    parser: str | None = None
    parser_version: str | None = None
    ocr_engine: str | None = None
    ocr_engine_version: str | None = None
    message: str
    created_at: datetime
    completed_at: datetime


class DocumentProcessingRunListResponse(BaseModel):
    job_id: str
    runs: list[DocumentProcessingRunSummary]


class DocumentProcessingRunDetail(BaseModel):
    processing_run_id: str
    job_id: str
    run_number: int
    processor_version: str
    source_sha256: str | None = None
    status: Literal["completed", "failed"]
    classifier: str | None = None
    classification_evidence: list[str]
    extraction: dict[str, Any]
    parsed: dict[str, Any]
    message: str
    created_at: datetime
    completed_at: datetime


class VendorInvoiceIntakeResponse(BaseModel):
    intake_status: Literal["processed", "failed"]
    job: DocumentJobResponse
    result: DocumentProcessResponse | None = None
    review_required: bool
    message: str


class ParserListResponse(BaseModel):
    parsers: list[dict[str, str]]


class ModuleHealthResponse(BaseModel):
    status: str
    module: str
    version: str
    database_exists: bool
    upload_directory_exists: bool
    job_count: int
    capabilities: dict[str, bool]
