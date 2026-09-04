from typing import Literal

from pydantic import BaseModel, Field


ReviewStatus = Literal[
    "balanced",
    "review_required",
    "no_remittance",
    "corrected",
    "held",
    "carryover",
    "approved",
]


class ReviewedAllocation(BaseModel):
    # A held draft may retain an incomplete row. Non-held saves still enforce
    # the required invoice identifier in the review service.
    invoice_number: str = Field(default="", max_length=100)
    net_invoice_amount: float
    invoice_page: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    raw_invoice_candidates: list[str] = Field(default_factory=list)
    extraction_source: str = ""
    ocr_psm: int | None = None
    allocation_kind: Literal["invoice", "service_charge"] = "invoice"
    erp_transaction_type: str = ""
    open_item_key: str = ""
    normalized_invoice_number: str = ""
    invoice_count: int | None = None


class SaveTransactionReviewRequest(BaseModel):
    allocations: list[ReviewedAllocation]
    expected_reviewed_at: str | None
    reviewer: str = ""
    notes: str = ""
    status: ReviewStatus = "corrected"
    override_reason: str = ""
    customer_number: str = Field(default="", max_length=100)
    customer_name: str = Field(default="", max_length=300)
    customer_phone: str = Field(default="", max_length=100)
    customer_address_line_1: str = Field(default="", max_length=300)
    customer_address_line_2: str = Field(default="", max_length=300)
    customer_city: str = Field(default="", max_length=150)
    customer_state: str = Field(default="", max_length=100)
    customer_postal_code: str = Field(default="", max_length=40)
    misc_gl_reason: str = Field(default="", max_length=100)
    misc_gl_location: str = Field(default="", max_length=150)
    misc_gl_department: str = Field(default="", max_length=150)
    misc_gl_amount: float = 0.0


class MiscGlEntry(BaseModel):
    reason: str = ""
    gl_code: str = ""
    location: str = ""
    department: str = ""
    amount: float = 0.0


class AppendCustomerNoteRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    author: str = Field(min_length=1, max_length=200)


class CustomerNote(BaseModel):
    note_id: int
    customer_number: str
    customer_name: str = ""
    body: str
    author: str
    source_job_id: str
    source_transaction_id: str
    source_check_number: str = ""
    created_at: str


class CustomerNoteListResponse(BaseModel):
    customer_number: str
    customer_name: str = ""
    notes: list[CustomerNote] = Field(default_factory=list)


class CustomerDiscount(BaseModel):
    customer_number: str
    is_discount_customer: bool = False
    discount_percent: float = 0.0
    updated_by: str = ""
    updated_at: str = ""


class SaveCustomerDiscountRequest(BaseModel):
    is_discount_customer: bool = False
    discount_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    updated_by: str = Field(default="", max_length=200)


class LockboxReviewQueueExportRequest(BaseModel):
    transaction_ids: list[str] = Field(min_length=1, max_length=10000)
    queue_label: str = Field(default="All transactions", max_length=300)
    reason_code: str = Field(default="", max_length=200)


class ReviewedTransaction(BaseModel):
    transaction_id: str
    envelope_number: int | None
    lockbox: str
    date: str
    batch: int | None
    batch_item: int | None
    check_number: str
    check_amount: float
    aba_routing: str
    account_number: str
    customer_number: str = ""
    printed_customer_number: str = ""
    customer_name: str
    customer_phone: str = ""
    phone_number: str = ""
    customer_address_line_1: str = ""
    customer_address_line_2: str = ""
    address_line_1: str = ""
    address_line_2: str = ""
    customer_city: str = ""
    city: str = ""
    customer_state: str = ""
    state: str = ""
    customer_postal_code: str = ""
    customer_zip: str = ""
    postal_code: str = ""
    customer_identity_strategy: str = ""
    customer_identity_attempts: list[dict] = Field(default_factory=list)
    original_allocations: list[ReviewedAllocation]
    allocations: list[ReviewedAllocation]
    allocation_total: float
    difference: float
    balanced: bool
    status: ReviewStatus
    check_page: int | None
    remittance_pages: list[int]
    remittance_pages_examined: list[int] = Field(default_factory=list)
    remittance_candidate_pages: list[int] = Field(default_factory=list)
    ocr_attempted_pages: list[int] = Field(default_factory=list)
    ocr_successful_pages: list[int] = Field(default_factory=list)
    ocr_attempts: list[dict[str, int]] = Field(default_factory=list)
    rejected_remittance_candidates: list[dict] = Field(default_factory=list)
    remittance_incomplete_pages: list[int] = Field(default_factory=list)
    remittance_ocr_errors: list[str] = Field(default_factory=list)
    remittance_evidence_complete: bool = False
    reviewer: str
    notes: str
    override_reason: str
    misc_gl: MiscGlEntry = Field(default_factory=MiscGlEntry)
    reviewed_at: str | None


class LockboxReviewResponse(BaseModel):
    job_id: str
    parser_version: str = ""
    extraction_version: str = ""
    source_file_name: str
    lockbox: str
    transaction_date: str
    transaction_count: int
    allocation_count: int
    total_check_amount: float
    total_allocation_amount: float
    total_difference: float
    balanced_count: int
    review_count: int
    held_count: int = 0
    carryover_count: int = 0
    approved_count: int
    corrected_count: int
    transactions: list[ReviewedTransaction]
    warnings: list[str]
