from typing import Literal

from pydantic import BaseModel, Field


LockboxReviewStatus = Literal[
    "balanced",
    "review_required",
    "no_remittance",
    "corrected",
    "held",
    "approved",
]


class BoundingBoxModel(BaseModel):
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0


class LockboxAllocationModel(BaseModel):
    invoice_number: str
    net_invoice_amount: float
    invoice_page: str
    confidence: float = 0.75
    raw_invoice_candidates: list[str] = Field(default_factory=list)
    extraction_source: str = ""
    ocr_psm: int | None = None
    allocation_kind: Literal["invoice", "service_charge"] = "invoice"
    erp_transaction_type: str = ""
    open_item_key: str = ""
    normalized_invoice_number: str = ""
    invoice_count: int | None = None


class LockboxTransactionModel(BaseModel):
    transaction_id: str
    envelope_number: int | None = None
    lockbox: str = ""
    date: str = ""
    batch: int | None = None
    batch_item: int | None = None
    check_number: str = ""
    check_amount: float = 0.0
    aba_routing: str = ""
    account_number: str = ""

    customer_number: str = ""
    printed_customer_number: str = ""
    customer_name: str = ""
    customer_phone: str = ""
    customer_address_line_1: str = ""
    customer_address_line_2: str = ""
    customer_city: str = ""
    customer_state: str = ""
    customer_postal_code: str = ""
    customer_identity_confidence: float = 0.0
    customer_identity_evidence: list[str] = Field(default_factory=list)
    customer_identity_strategy: str = ""
    customer_identity_attempts: list[dict] = Field(default_factory=list)
    customer_identity_block: BoundingBoxModel = Field(
        default_factory=BoundingBoxModel
    )
    check_region: BoundingBoxModel = Field(
        default_factory=BoundingBoxModel
    )

    allocations: list[LockboxAllocationModel] = Field(default_factory=list)
    original_allocations: list[LockboxAllocationModel] = Field(default_factory=list)

    allocation_total: float = 0.0
    difference: float = 0.0
    balanced: bool = False
    status: LockboxReviewStatus = "review_required"

    check_page: int | None = None
    remittance_pages: list[int] = Field(default_factory=list)
    remittance_pages_examined: list[int] = Field(default_factory=list)
    remittance_candidate_pages: list[int] = Field(default_factory=list)
    ocr_attempted_pages: list[int] = Field(default_factory=list)
    ocr_successful_pages: list[int] = Field(default_factory=list)
    ocr_attempts: list[dict[str, int]] = Field(default_factory=list)
    rejected_remittance_candidates: list[dict] = Field(default_factory=list)
    remittance_incomplete_pages: list[int] = Field(default_factory=list)
    remittance_ocr_errors: list[str] = Field(default_factory=list)
    remittance_evidence_complete: bool = False

    reviewer: str = ""
    notes: str = ""
    override_reason: str = ""


class LockboxProcessingResponse(BaseModel):
    job_id: str
    parser_version: str = ""
    extraction_version: str = ""
    pnc_lockbox_header_rule_version: str = ""
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
    transactions: list[LockboxTransactionModel]
    warnings: list[str]


class LockboxTransactionReviewRequest(BaseModel):
    allocations: list[LockboxAllocationModel]
    reviewer: str = ""
    notes: str = ""
    status: Literal["corrected", "held", "approved"]
    override_reason: str = ""

    customer_number: str = ""
    customer_name: str = ""
    customer_phone: str = ""
    customer_address_line_1: str = ""
    customer_address_line_2: str = ""
    customer_city: str = ""
    customer_state: str = ""
    customer_postal_code: str = ""


class CustomerMatchSuggestion(BaseModel):
    profile_id: int
    customer_name: str
    customer_phone: str = ""
    customer_address_line_1: str = ""
    customer_address_line_2: str = ""
    customer_city: str = ""
    customer_state: str = ""
    customer_postal_code: str = ""
    confidence: float
    matched_on: list[str] = Field(default_factory=list)
    times_confirmed: int = 0


class CustomerSuggestionListResponse(BaseModel):
    job_id: str
    transaction_id: str
    suggestions: list[CustomerMatchSuggestion]
