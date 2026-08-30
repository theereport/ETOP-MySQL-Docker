from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


EvidenceStatus = Literal[
    "available",
    "partial",
    "unavailable",
    "degraded",
    "candidate_only",
    "unmapped",
]


class EvidenceSourceReference(BaseModel):
    source_system: str
    source_schema: str
    source_object: str
    access: Literal["read_only"] = "read_only"
    retrieved_at: str
    contract_version: str


class EvidenceCoverageItem(BaseModel):
    key: str
    label: str
    status: EvidenceStatus
    source: str | None = None
    as_of: str | None = None
    record_count: int | None = None
    complete: bool | None = None
    explanation: str


class CreditOpenItem(BaseModel):
    open_item_key: str
    customer_number: str
    invoice_number: str
    invoice_count: int | None
    invoice_date: str | None
    due_date: str | None
    original_amount: float
    open_amount: float
    raw_open_amount: float
    debit_credit: str
    transaction_type: str
    reference_number: str
    selling_store: str | None
    days_past_due: int | None
    aging_bucket: str


class CreditOpenARCollection(BaseModel):
    status: EvidenceStatus
    items: list[CreditOpenItem]
    retrieved_count: int
    row_limit: int
    complete: bool
    retrieved_signed_open_amount: float
    customer_master_balance: float
    reconciliation_difference: float | None
    explanation: str


class RelatedCustomerEvidence(BaseModel):
    customer_number: str
    customer_name: str
    enterprise_number: str | None
    relationship: Literal[
        "selected_customer",
        "enterprise_anchor",
        "linked_customer",
    ]
    credit_limit: float
    balance: float
    erp_on_order_aggregate: float
    partial_exposure: float


class RelatedAccountCollection(BaseModel):
    status: EvidenceStatus
    relationship_basis: str
    group_scope: str
    enterprise_number: str | None
    accounts: list[RelatedCustomerEvidence]
    retrieved_count: int
    complete: bool
    partial_group_credit_limit: float | None
    partial_group_exposure: float | None
    explanation: str


class CreditCurrentEvidence(BaseModel):
    credit_limit: float
    balance: float
    erp_on_order_aggregate: float
    partial_exposure: float
    partial_available_credit: float
    terms_code: str
    terms_description: str
    last_payment_amount: float | None
    last_payment_date: str | None


class EvidenceGovernance(BaseModel):
    source_authority: str
    erp_access: Literal["read_only"] = "read_only"
    erp_write: Literal[False] = False
    recommendation_effect: Literal["none"] = "none"
    decision_effect: Literal["none"] = "none"
    execution_effect: Literal["none"] = "none"
    automatic_selection: Literal[False] = False
    statements: list[str]


class CreditERPEvidenceResponse(BaseModel):
    contract_version: str
    generated_at: str
    customer_number: int
    customer_name: str
    current: CreditCurrentEvidence
    open_ar: CreditOpenARCollection
    related_accounts: RelatedAccountCollection
    coverage: list[EvidenceCoverageItem]
    source_references: list[EvidenceSourceReference]
    governance: EvidenceGovernance
    evidence_sha256: str
    warnings: list[str]


class APMappingCandidate(BaseModel):
    category: str
    table_name: str
    required_fields_matched: list[str]
    missing_fields: list[str]
    matched_columns: dict[str, list[str]]
    evidence_columns: list[str]
    selection_state: Literal[
        "candidate_only",
        "confirmed_source_record",
    ] = "candidate_only"
    source_rows_read: Literal[False] = False


class APMappingCategory(BaseModel):
    key: str
    label: str
    status: EvidenceStatus
    required_fields: list[str]
    candidates: list[APMappingCandidate]
    explanation: str


class APMappingReadinessResponse(BaseModel):
    contract_version: str
    generated_at: str
    source_schema: str
    schema_catalog_status: EvidenceStatus
    catalog_complete: bool
    inspected_column_count: int
    categories: list[APMappingCategory]
    governance: EvidenceGovernance
    next_required_action: str
    warnings: list[str]


class APLocalInvoiceIdentity(BaseModel):
    ap_invoice_id: str
    vendor_number: str | None
    vendor_name: str | None
    invoice_number: str | None
    invoice_date: str | None
    due_date: str | None
    purchase_order_number: str | None
    total_amount: float | None
    source_evidence_sha256: str


class APERPInvoiceLookupIdentity(BaseModel):
    lookup_origin: Literal["local_imported_invoice", "direct_erp_search"]
    vendor_number: str
    invoice_number: str
    local_ap_invoice_id: str | None = None


class APVendorSearchCandidate(BaseModel):
    vendor_number: str
    vendor_name: str | None
    sort_name: str | None
    match_basis: list[Literal["exact_vendor_number", "vendor_name_contains"]]


class APInvoiceSearchCandidate(BaseModel):
    vendor_number: str
    vendor_name: str | None
    invoice_number: str
    posted_header_row_count: int
    latest_invoice_date: str | None
    latest_due_date: str | None


class APInvoiceSearchQuery(BaseModel):
    vendor_query: str | None
    invoice_number: str | None
    row_limit: int


class APInvoiceSearchResponse(BaseModel):
    contract_version: str
    generated_at: str
    query: APInvoiceSearchQuery
    vendor_candidates: list[APVendorSearchCandidate]
    invoice_candidates: list[APInvoiceSearchCandidate]
    vendor_candidate_complete: bool
    invoice_candidate_complete: bool
    source_references: list[EvidenceSourceReference]
    governance: EvidenceGovernance
    sensitive_fields_excluded: list[str]
    evidence_sha256: str
    warnings: list[str]


class APVendorEvidence(BaseModel):
    status: EvidenceStatus
    vendor_number: str
    vendor_name: str | None
    sort_name: str | None
    vendor_type_code: str | None
    delete_code: str | None
    terms_code: str | None
    po_required_code: str | None
    no_ap_from_receipt_code: str | None
    default_gl_division: str | None
    default_gl_department: str | None
    default_gl_account: str | None
    last_paid_date: str | None
    last_paid_amount: float | None
    explanation: str


class APPostedInvoiceHeaderEvidence(BaseModel):
    vendor_number: str
    invoice_number: str
    payment_number: int | None
    invoice_amount: float
    discount_amount: float
    invoice_description: str | None
    invoice_date: str | None
    due_date: str | None
    created_date: str | None
    changed_date: str | None
    check_number: str | None
    check_date: str | None
    hold_flag: str | None
    selection_code: str | None
    discount_taken_code: str | None
    gl_reference: str | None
    check_gl_reference: str | None
    void_gl_reference: str | None
    void_check_gl_reference: str | None
    accounting_period: int | None
    accounting_year: int | None


class APInvoiceDetailEvidence(BaseModel):
    sequence_number: int | None
    line_description: str | None
    line_amount: float
    quantity: float
    gl_division: str | None
    gl_department: str | None
    gl_account: str | None
    po_receiver_reference: str | None
    customer_number: str | None
    job_number: str | None


class APGLDistributionEvidence(BaseModel):
    sequence_number: str | None
    payment_number: int | None
    invoice_amount: float
    quantity: float
    description: str | None
    invoice_date: str | None
    gl_division: str | None
    gl_department: str | None
    gl_account: str | None
    gl_account_description: str | None
    accounting_period: int | None
    accounting_year: int | None
    program_code: str | None


class APInputInvoiceHeaderEvidence(BaseModel):
    vendor_number: str
    invoice_number: str
    invoice_amount: float
    discount_amount: float
    discountable_amount: float
    invoice_description: str | None
    invoice_date: str | None
    due_date: str | None
    created_date: str | None
    changed_date: str | None
    raw_status_code: str | None
    payment_count: int | None
    accounting_period: int | None
    accounting_year: int | None


class APInputPaymentSplitEvidence(BaseModel):
    sequence_number: int | None
    payment_amount: float
    discount_amount: float
    discountable_amount: float
    discount_percent: float
    due_date: str | None


class APBoundedCollection(BaseModel):
    status: EvidenceStatus
    retrieved_count: int
    row_limit: int
    complete: bool
    explanation: str


class APERPEvidenceResponse(BaseModel):
    contract_version: str
    generated_at: str
    lookup_identity: APERPInvoiceLookupIdentity
    local_invoice: APLocalInvoiceIdentity | None
    vendor_master: APVendorEvidence
    posted_headers: list[APPostedInvoiceHeaderEvidence]
    posted_header_collection: APBoundedCollection
    posted_details: list[APInvoiceDetailEvidence]
    posted_detail_collection: APBoundedCollection
    gl_distributions: list[APGLDistributionEvidence]
    gl_distribution_collection: APBoundedCollection
    input_headers: list[APInputInvoiceHeaderEvidence]
    input_header_collection: APBoundedCollection
    input_details: list[APInvoiceDetailEvidence]
    input_detail_collection: APBoundedCollection
    input_payment_splits: list[APInputPaymentSplitEvidence]
    input_payment_collection: APBoundedCollection
    coverage: list[EvidenceCoverageItem]
    source_references: list[EvidenceSourceReference]
    governance: EvidenceGovernance
    sensitive_fields_excluded: list[str]
    evidence_sha256: str
    warnings: list[str]


class ERPEvidenceGatewayStatus(BaseModel):
    contract_version: str
    service: str
    status: Literal["ready"] = "ready"
    access: Literal["read_only"] = "read_only"
    write_methods_exposed: Literal[False] = False
    supported_queries: list[str] = Field(default_factory=list)
    unavailable_actions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
