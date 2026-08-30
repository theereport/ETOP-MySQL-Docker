from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CONTRACT_VERSION = "accounts-payable-intelligence.v1"
CONTROL_CONTRACT_VERSION = "accounts-payable-control-readiness.v1"
VENDOR_CASH_CONTRACT_VERSION = "accounts-payable-vendor-cash-intelligence.v1"
EXCEPTION_OPERATIONS_CONTRACT_VERSION = (
    "accounts-payable-exception-operations.v1"
)
SourceStatus = Literal[
    "available",
    "partial",
    "unavailable",
    "not_connected",
    "degraded",
]
InvoiceStatus = Literal[
    "review_required",
    "evidence_available",
]


class SourceCoverageItem(BaseModel):
    key: str
    label: str
    status: SourceStatus
    source: str | None
    as_of: str | None
    record_count: int | None
    explanation: str


class APMetric(BaseModel):
    value: int | float | None
    status: SourceStatus
    source: str | None
    as_of: str | None
    explanation: str


class AccountsPayableMetrics(BaseModel):
    imported_invoice_count: APMetric
    review_required_count: APMetric
    exception_count: APMetric
    duplicate_candidate_count: APMetric
    ocr_processed_count: APMetric
    ocr_average_confidence: APMetric
    extracted_invoice_total: APMetric
    current_ap_balance: APMetric
    due_today_count: APMetric
    due_today_amount: APMetric
    past_due_count: APMetric
    past_due_amount: APMetric
    due_within_7_days_amount: APMetric
    discounts_available: APMetric
    average_approval_time: APMetric


class APGovernance(BaseModel):
    erp_access: Literal["not_connected"] = "not_connected"
    erp_write: Literal[False] = False
    approval_effect: Literal["none"] = "none"
    payment_effect: Literal["none"] = "none"
    automatic_approval: Literal[False] = False
    source_authority: Literal[
        "document_intelligence_extracted_evidence"
    ] = "document_intelligence_extracted_evidence"
    statements: list[str] = Field(default_factory=list)


class DeferredCapability(BaseModel):
    key: str
    label: str
    status: Literal["unavailable"] = "unavailable"
    reason: str
    missing_sources: list[str] = Field(default_factory=list)


class APOverviewResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    generated_at: str
    metrics: AccountsPayableMetrics
    source_coverage: list[SourceCoverageItem]
    governance: APGovernance
    deferred_capabilities: list[DeferredCapability]
    warnings: list[str] = Field(default_factory=list)


class APInvoiceSummary(BaseModel):
    ap_invoice_id: str
    document_job_id: str
    document_result_id: str
    source_record_index: int | None
    source_file_name: str
    vendor_number: str | None
    vendor_name: str | None
    invoice_number: str | None
    invoice_date: str | None
    received_at: str | None
    due_date: str | None
    purchase_order_number: str | None
    subtotal: float | None
    tax: float | None
    freight: float | None
    discount: float | None
    total_amount: float | None
    currency: str | None
    terms: str | None
    status: InvoiceStatus
    review_required: bool
    ocr_review_required: bool
    classification_confidence: float | None
    ocr_confidence: float | None
    exception_count: int
    duplicate_candidate_count: int
    warnings: list[str] = Field(default_factory=list)
    processed_at: str | None
    source_as_of: str
    last_synced_at: str


class APInvoiceFilters(BaseModel):
    statuses: list[str]


class APInvoiceListResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    items: list[APInvoiceSummary]
    total: int
    limit: int
    offset: int
    filter_options: APInvoiceFilters
    source_coverage: list[SourceCoverageItem]
    governance: APGovernance
    deferred_capabilities: list[DeferredCapability]
    warnings: list[str] = Field(default_factory=list)


class APExtractedField(BaseModel):
    field_name: str
    label: str
    value: str | float | bool | None
    normalized_value: str | float | bool | None
    confidence: float | None
    source: str
    page: int | None
    location: str | None
    validation_status: str
    explanation: str
    authority: str
    rule_version: str | None


class APExceptionEvidence(BaseModel):
    code: str
    label: str
    severity: Literal["high", "medium", "low"]
    explanation: str
    evidence: list[str] = Field(default_factory=list)
    source: str | None


class APDuplicateEvidence(BaseModel):
    candidate_id: str
    candidate_ap_invoice_id: str
    candidate_invoice_number: str | None
    candidate_vendor_name: str | None
    candidate_amount: float | None
    confidence: None = None
    match_factors: list[str]
    amount_corroboration: Literal[
        "matched",
        "unavailable",
    ]
    date_corroboration: Literal[
        "matched",
        "unavailable",
    ]
    explanation: str


class APTimelineEvent(BaseModel):
    event_id: str
    event_type: Literal[
        "document_received",
        "document_processed",
        "ap_invoice_imported",
        "ap_invoice_source_refreshed",
    ]
    label: str
    occurred_at: str | None
    recorded_at: str
    source: str
    actor: str | None
    details: str
    source_evidence_sha256: str | None


class APSourceDocument(BaseModel):
    job_id: str
    result_id: str
    file_name: str
    file_endpoint: str
    content_type: str | None
    document_type: str
    status: str
    classifier: str | None
    parser_name: str | None
    parser_version: str | None
    classification_confidence: float | None
    classification_evidence: list[str]
    created_at: str | None
    updated_at: str | None
    result_created_at: str | None
    result_updated_at: str | None


class APInvoiceDetailResponse(APInvoiceSummary):
    contract_version: str = CONTRACT_VERSION
    source_document: APSourceDocument
    extracted_fields: list[APExtractedField]
    exceptions: list[APExceptionEvidence]
    duplicate_evidence: list[APDuplicateEvidence]
    timeline: list[APTimelineEvent]
    source_coverage: list[SourceCoverageItem]
    governance: APGovernance
    deferred_capabilities: list[DeferredCapability]
    provenance: list[str]
    source_evidence_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    evidence_revision_count: int


class APErpLedgerRefreshResponse(BaseModel):
    job_id: str
    status: Literal["queued", "completed"]


class APVendorTermsReferenceRecord(BaseModel):
    terms_code: str
    discount_percent: float
    num_periods: int | None = None
    num_months: int | None = None
    num_days: int | None = None
    second_period: int | None = None
    third_period: int | None = None
    next_period: int | None = None
    day_of_month: int | None = None
    cutoff_day: int | None = None
    description: str
    updated_at: str


class APVendorTermsReferenceListResponse(BaseModel):
    items: list[APVendorTermsReferenceRecord]


class APVendorTermsReferenceUpsert(BaseModel):
    discount_percent: float = 0
    num_periods: int | None = None
    num_months: int | None = None
    num_days: int | None = None
    second_period: int | None = None
    third_period: int | None = None
    next_period: int | None = None
    day_of_month: int | None = None
    cutoff_day: int | None = None
    description: str = ""


WarehouseApprovalStatus = Literal[
    "needs_approval",
    "approved_by_warehouse",
    "approved_and_entered_by_ap",
]


class APWarehouseApprovalItem(BaseModel):
    vendor_number: str
    vendor_name: str | None = None
    invoice_number: str
    invoice_date: str | None = None
    due_date: str | None = None
    amount_invoiced: float
    amount_discount: float
    on_hold: bool
    gl_account: str | None = None
    gl_division: str | None = None
    gl_department: str | None = None
    status: WarehouseApprovalStatus
    last_actor_identity: str | None = None
    last_action_at: str | None = None
    linked_ap_invoice_id: str | None = None


class APWarehouseApprovalQueueResponse(BaseModel):
    contract_version: str = "accounts-payable-warehouse-approval-queue.v1"
    division: str | None = None
    available_divisions: list[str]
    needs_approval: list[APWarehouseApprovalItem]
    approved_by_warehouse: list[APWarehouseApprovalItem]
    approved_and_entered_by_ap: list[APWarehouseApprovalItem]
    governance: APGovernance


class APWarehouseApprovalActionCreate(BaseModel):
    vendor_number: str = Field(min_length=1)
    invoice_number: str = Field(min_length=1)
    to_status: WarehouseApprovalStatus
    actor_identity: str = Field(min_length=1)
    notes: str = ""


class APWarehouseApprovalActionRecord(BaseModel):
    action_id: str
    vendor_number: str
    invoice_number: str
    from_status: WarehouseApprovalStatus
    to_status: WarehouseApprovalStatus
    actor_identity: str
    actor_identity_source: Literal["operator_supplied", "sso"]
    notes: str
    created_at: str


class APSyncResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    status: Literal["completed", "completed_with_warnings"]
    imported_count: int
    updated_count: int
    unchanged_count: int
    skipped_count: int
    eligible_job_count: int
    duplicate_candidate_count: int
    imported_event_count: int
    sync_id: str
    started_at: str
    completed_at: str
    message: str
    source_coverage: list[SourceCoverageItem]
    governance: APGovernance
    deferred_capabilities: list[DeferredCapability]
    warnings: list[str] = Field(default_factory=list)


class APErrorDetail(BaseModel):
    code: str
    message: str


class SourceInvoiceProjection(BaseModel):
    """Internal validated projection passed from source adapter to storage."""

    ap_invoice_id: str
    source_key: str
    document_job_id: str
    document_result_id: str
    source_record_index: int | None
    source_file_name: str
    content_type: str | None
    document_type: Literal["vendor_invoice"]
    document_status: str
    classifier: str | None
    classification_confidence: float | None
    classification_evidence: list[str]
    parser_name: str | None
    parser_version: str | None
    vendor_number: str | None
    vendor_name: str | None
    normalized_vendor_identity: str | None
    invoice_number: str | None
    normalized_invoice_number: str | None
    invoice_date: str | None
    due_date: str | None
    purchase_order_number: str | None
    subtotal: str | None
    tax: str | None
    freight: str | None
    discount: str | None
    total_amount: str | None
    currency: str | None
    terms: str | None
    classification_confidence_source: str | None
    ocr_confidence: float | None
    field_evidence: list[dict[str, Any]]
    exceptions: list[dict[str, Any]]
    warnings: list[str]
    base_review_required: bool
    ocr_review_required: bool
    received_at: str | None
    processed_at: str | None
    source_result_created_at: str | None
    source_result_updated_at: str | None
    source_as_of: str
    source_evidence_sha256: str
    source_snapshot: dict[str, Any]


class APControlGate(BaseModel):
    code: str
    label: str
    status: Literal["passed", "blocked", "unavailable"]
    source: str | None
    explanation: str


class APSegregationCheck(BaseModel):
    code: str
    label: str
    status: Literal["passed", "blocked", "not_applicable"]
    identities: list[str] = Field(default_factory=list)
    explanation: str


class APControlCaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intended_action: Literal["approval_review", "payment_preparation"]
    requested_by: str = Field(min_length=1, max_length=200)
    assigned_reviewer: str = Field(min_length=1, max_length=200)
    payment_preparer: str | None = Field(default=None, max_length=200)
    notes: str = Field(min_length=1, max_length=5000)

    @field_validator(
        "requested_by",
        "assigned_reviewer",
        "payment_preparer",
        "notes",
    )
    @classmethod
    def trim_control_case_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must contain non-whitespace text.")
        return cleaned


class APControlReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_identity: str = Field(min_length=1, max_length=200)
    disposition: Literal[
        "evidence_ready",
        "needs_information",
        "duplicate_review_required",
        "not_ready",
    ]
    notes: str = Field(min_length=1, max_length=5000)

    @field_validator("reviewer_identity", "notes")
    @classmethod
    def trim_control_review_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must contain non-whitespace text.")
        return cleaned


class APControlReviewRecord(BaseModel):
    review_id: str
    control_case_id: str
    reviewer_identity: str
    disposition: Literal[
        "evidence_ready",
        "needs_information",
        "duplicate_review_required",
        "not_ready",
    ]
    notes: str
    created_at: str
    actor_identity_source: Literal[
        "operator_supplied"
    ] = "operator_supplied"
    actor_authority_status: Literal[
        "not_independently_verified"
    ] = "not_independently_verified"
    approval_effect: Literal["none"] = "none"
    payment_effect: Literal["none"] = "none"


class APControlCaseSummary(BaseModel):
    control_case_id: str
    ap_invoice_id: str
    intended_action: Literal["approval_review", "payment_preparation"]
    requested_by: str
    assigned_reviewer: str
    payment_preparer: str | None
    notes: str
    created_at: str
    invoice: APInvoiceSummary
    control_status: Literal[
        "control_review_pending",
        "evidence_ready",
        "needs_information",
        "duplicate_review_required",
        "not_ready",
    ]
    latest_review: APControlReviewRecord | None
    document_evidence_ready: bool
    evidence_current: bool
    evidence_gates: list[APControlGate]
    segregation_checks: list[APSegregationCheck]
    approval_authority_status: Literal[
        "unavailable"
    ] = "unavailable"
    payment_authorization_status: Literal[
        "unavailable"
    ] = "unavailable"
    can_enter_governed_approval: Literal[False] = False
    can_authorize_payment: Literal[False] = False


class APControlCaseDetail(APControlCaseSummary):
    contract_version: str = CONTROL_CONTRACT_VERSION
    reviews: list[APControlReviewRecord]
    source_evidence_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    evidence_snapshot: dict[str, Any]
    evidence_snapshot_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    source_coverage: list[SourceCoverageItem]
    governance: APGovernance
    deferred_capabilities: list[DeferredCapability]
    warnings: list[str] = Field(default_factory=list)


class APControlCaseListResponse(BaseModel):
    contract_version: str = CONTROL_CONTRACT_VERSION
    items: list[APControlCaseSummary]
    total: int
    limit: int
    offset: int
    source_coverage: list[SourceCoverageItem]
    governance: APGovernance
    deferred_capabilities: list[DeferredCapability]
    warnings: list[str] = Field(default_factory=list)


class APVendorInsight(BaseModel):
    vendor_key: str
    identity_basis: Literal["vendor_number", "vendor_name", "unidentified"]
    vendor_number: str | None
    vendor_name: str | None
    invoice_count: int = Field(ge=0)
    known_total_count: int = Field(ge=0)
    extracted_total_amount: float
    due_date_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    exception_invoice_count: int = Field(ge=0)
    duplicate_candidate_invoice_count: int = Field(ge=0)
    ocr_average_confidence: float | None
    evidence_alerts: list[str] = Field(default_factory=list)


class APCashWindow(BaseModel):
    code: Literal[
        "past_due",
        "due_today",
        "next_7_days",
        "days_8_to_14",
        "days_15_to_30",
        "beyond_30_days",
        "due_date_unavailable",
    ]
    label: str
    invoice_count: int = Field(ge=0)
    known_amount_count: int = Field(ge=0)
    extracted_amount: float
    explanation: str


class APVendorCashCoverage(BaseModel):
    imported_invoice_count: int = Field(ge=0)
    identified_vendor_invoice_count: int = Field(ge=0)
    due_date_invoice_count: int = Field(ge=0)
    known_amount_invoice_count: int = Field(ge=0)
    review_required_invoice_count: int = Field(ge=0)
    source_as_of: str | None


class APVendorCashGovernance(BaseModel):
    classification: Literal[
        "document_evidence_analytics"
    ] = "document_evidence_analytics"
    current_payable_status_known: Literal[False] = False
    cash_requirement_authority: Literal[
        "not_authoritative"
    ] = "not_authoritative"
    vendor_performance_score: Literal[False] = False
    payment_proposal: Literal[False] = False
    payment_authorization: Literal[False] = False
    erp_write: Literal[False] = False
    statements: list[str] = Field(default_factory=list)


class APVendorCashIntelligenceResponse(BaseModel):
    contract_version: str = VENDOR_CASH_CONTRACT_VERSION
    generated_at: str
    as_of_date: date
    coverage: APVendorCashCoverage
    vendors: list[APVendorInsight]
    cash_windows: list[APCashWindow]
    governance: APVendorCashGovernance
    source_coverage: list[SourceCoverageItem]
    deferred_capabilities: list[DeferredCapability]
    warnings: list[str] = Field(default_factory=list)


class APCashScenarioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of_date: date
    horizon_days: Literal[7, 14, 30, 60, 90]
    include_review_required: bool = False
    prepared_by: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=5000)

    @field_validator("prepared_by", "rationale")
    @classmethod
    def trim_cash_scenario_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must contain non-whitespace text.")
        return cleaned


class APCashScenarioRecord(BaseModel):
    cash_scenario_id: str
    as_of_date: date
    horizon_days: int
    horizon_end_date: date
    include_review_required: bool
    prepared_by: str
    rationale: str
    created_at: str
    included_invoice_count: int = Field(ge=0)
    included_known_amount_count: int = Field(ge=0)
    extracted_amount: float
    excluded_review_required_count: int = Field(ge=0)
    excluded_missing_due_date_count: int = Field(ge=0)
    excluded_missing_amount_count: int = Field(ge=0)
    actor_identity_source: Literal[
        "operator_supplied"
    ] = "operator_supplied"
    actor_authority_status: Literal[
        "not_independently_verified"
    ] = "not_independently_verified"
    scenario_classification: Literal[
        "analytical_scenario"
    ] = "analytical_scenario"
    current_payable_status_known: Literal[False] = False
    approval_effect: Literal["none"] = "none"
    payment_effect: Literal["none"] = "none"
    erp_write: Literal[False] = False
    evidence_snapshot: dict[str, Any]
    evidence_snapshot_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class APCashScenarioHistoryResponse(BaseModel):
    contract_version: str = VENDOR_CASH_CONTRACT_VERSION
    count: int = Field(ge=0)
    scenarios: list[APCashScenarioRecord]
    governance: APVendorCashGovernance
    warnings: list[str] = Field(default_factory=list)


class APExceptionReason(BaseModel):
    code: str
    label: str
    severity: Literal["high", "medium", "low", "review"]
    source: Literal[
        "saved_exception",
        "duplicate_candidate",
        "ocr_review",
        "source_review_flag",
    ]
    explanation: str


APExceptionActionDisposition = Literal[
    "investigating",
    "information_requested",
    "document_correction_needed",
    "duplicate_review_complete",
    "ready_for_control_case",
]


class APExceptionActionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposition: APExceptionActionDisposition
    owner_identity: str = Field(min_length=1, max_length=200)
    actor_identity: str = Field(min_length=1, max_length=200)
    notes: str = Field(min_length=1, max_length=5000)
    follow_up_date: date | None = None

    @field_validator("owner_identity", "actor_identity", "notes")
    @classmethod
    def require_exception_action_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must contain non-whitespace text.")
        return cleaned


class APExceptionActionRecord(BaseModel):
    action_id: str
    ap_invoice_id: str
    disposition: APExceptionActionDisposition
    owner_identity: str
    actor_identity: str
    notes: str
    follow_up_date: date | None
    created_at: str
    source_evidence_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    actor_identity_source: Literal[
        "operator_supplied"
    ] = "operator_supplied"
    owner_identity_source: Literal[
        "operator_supplied"
    ] = "operator_supplied"
    authority_status: Literal[
        "not_independently_verified"
    ] = "not_independently_verified"
    action_classification: Literal[
        "professional_workflow_metadata"
    ] = "professional_workflow_metadata"
    approval_effect: Literal["none"] = "none"
    payment_effect: Literal["none"] = "none"
    erp_write: Literal[False] = False
    evidence_snapshot: dict[str, Any]
    evidence_snapshot_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class APExceptionQueueItem(BaseModel):
    queue_rank: int = Field(ge=1)
    ap_invoice_id: str
    vendor_number: str | None
    vendor_name: str | None
    invoice_number: str | None
    invoice_date: str | None
    due_date: str | None
    total_amount: float | None
    source_file_name: str
    source_as_of: str
    source_evidence_sha256: str
    exception_count: int = Field(ge=0)
    duplicate_candidate_count: int = Field(ge=0)
    ocr_review_required: bool
    reasons: list[APExceptionReason]
    work_state: Literal[
        "unworked",
        "follow_up_scheduled",
        "follow_up_overdue",
        "source_changed",
        "documented_for_next_step",
        "documented",
    ]
    latest_action: APExceptionActionRecord | None


class APExceptionOperationsSummary(BaseModel):
    queue_count: int = Field(ge=0)
    unworked_count: int = Field(ge=0)
    follow_up_scheduled_count: int = Field(ge=0)
    follow_up_overdue_count: int = Field(ge=0)
    source_changed_count: int = Field(ge=0)
    documented_count: int = Field(ge=0)
    duplicate_review_count: int = Field(ge=0)
    ocr_review_count: int = Field(ge=0)
    known_amount_count: int = Field(ge=0)
    extracted_amount: float


class APExceptionOperationsGovernance(BaseModel):
    classification: Literal[
        "professional_exception_work_management"
    ] = "professional_exception_work_management"
    queue_ordering: Literal[
        "deterministic_evidence_and_follow_up_state"
    ] = "deterministic_evidence_and_follow_up_state"
    approved_sla: Literal[False] = False
    authenticated_assignment: Literal[False] = False
    automatic_resolution: Literal[False] = False
    approval_effect: Literal["none"] = "none"
    payment_effect: Literal["none"] = "none"
    erp_write: Literal[False] = False
    statements: list[str] = Field(default_factory=list)


class APExceptionOperationsResponse(BaseModel):
    contract_version: str = EXCEPTION_OPERATIONS_CONTRACT_VERSION
    generated_at: str
    as_of_date: date
    summary: APExceptionOperationsSummary
    items: list[APExceptionQueueItem]
    source_coverage: list[SourceCoverageItem]
    governance: APExceptionOperationsGovernance
    deferred_capabilities: list[DeferredCapability]
    warnings: list[str] = Field(default_factory=list)


class APExceptionActionHistoryResponse(BaseModel):
    contract_version: str = EXCEPTION_OPERATIONS_CONTRACT_VERSION
    ap_invoice_id: str
    count: int = Field(ge=0)
    actions: list[APExceptionActionRecord]
    governance: APExceptionOperationsGovernance
