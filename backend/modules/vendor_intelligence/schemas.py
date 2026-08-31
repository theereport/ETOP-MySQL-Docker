from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CONTRACT_VERSION = "vendor-intelligence-foundation.v1"


class SourceEvidence(BaseModel):
    system: str = "MaddenCo ERP (DTA273)"
    access: Literal["read_only"] = "read_only"
    status: Literal["available"] = "available"
    retrieved_at: str


class VendorSearchResult(BaseModel):
    vendor_number: int
    vendor_name: str
    contact_name: str = ""
    phone: str = ""
    email: str = ""
    zip_code: str = ""
    active: bool
    po_required: bool


class VendorSearchResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    source: SourceEvidence
    count: int
    vendors: list[VendorSearchResult]


class VendorIdentityEvidence(BaseModel):
    vendor_number: int
    vendor_name: str
    sort_name: str = ""
    contact_name: str = ""
    address_lines: list[str] = Field(default_factory=list)
    zip_code: str = ""
    country: str = ""
    phone: str = ""
    fax: str = ""
    email: str = ""
    active: bool
    vendor_type: str = ""
    store_number: int | None = None
    terms_code: str = ""
    po_required: bool
    do_not_create_ap_from_receiving: bool
    is_1099: bool
    tax_1099_code: str = ""
    tax_1099_manual_amount: float | None = None
    federal_id_on_file: bool
    payment_type: str = ""
    bank_account_type: str = ""
    eft_bank_info_on_file: bool = False


class DiscountCaptureMetric(BaseModel):
    value: float | None
    status: Literal["available", "unavailable"]
    explanation: str


class VendorPurchaseVolumeEvidence(BaseModel):
    month_to_date: float
    year_to_date: float
    last_year: float
    discount_month_to_date: float
    discount_year_to_date: float
    discount_lost_month_to_date: float
    discount_lost_year_to_date: float
    discount_capture_rate_month_to_date: DiscountCaptureMetric
    discount_capture_rate_year_to_date: DiscountCaptureMetric
    amount_last_paid: float | None
    date_last_paid: str | None
    check_number_last_paid: int | None
    source: str = "MaddenCo PMVEND"
    discount_explanation: str = (
        "Discount taken and discount lost are MaddenCo's own recorded "
        "PMVEND totals. The capture rate is discount taken divided by "
        "(discount taken + discount lost) for the same period, expressed "
        "as a percentage; it is a stated arithmetic ratio, not an "
        "approved vendor performance score."
    )


class OpenPurchaseOrder(BaseModel):
    po_number: int
    po_date: str | None
    date_required: str | None
    status_code: str
    complete: bool
    total_cost: float
    ship_via: str = ""
    buyer_number: int | None
    ordered_quantity: float
    received_quantity: float
    backorder_quantity: float
    line_count: int


class PurchaseOrderEvidence(BaseModel):
    open_order_count: int
    open_order_total_cost: float
    open_orders: list[OpenPurchaseOrder]
    source: str = "MaddenCo TMPOHD / TMPODT"
    explanation: str = (
        "Open purchase orders are TMPOHD rows for this vendor where the "
        "complete flag is not Y. Ordered/received/backorder quantities are "
        "summed from TMPODT lines for each PO."
    )


class ReceivingEvent(BaseModel):
    po_number: int
    product_number: str
    product_description: str = ""
    quantity: float
    actual_cost: float | None
    po_cost: float | None
    cost_variance: float | None
    dot_number: str = ""
    dot_date: str | None
    received_date: str | None


class ReceivingEvidence(BaseModel):
    receipt_count: int
    total_cost_variance: float | None
    cost_variance_completeness: Literal["complete", "partial", "unavailable"]
    recent_receipts: list[ReceivingEvent]
    source: str = "MaddenCo TTRCVD joined to TMPOHD"
    explanation: str = (
        "TRCDCOSDIF (MaddenCo's dedicated cost-variance field) is confirmed "
        "never populated with a real value in this instance, and actual "
        "cost is always copied from PO cost when recorded - there is no "
        "usable price/cost variance signal in receiving data here."
    )


class OpenPayableInvoice(BaseModel):
    invoice_number: str
    invoice_amount: float
    discount_amount: float
    invoice_date: str | None
    due_date: str | None
    on_hold: bool
    period: int | None
    year: int | None


class PaidPayableInvoice(BaseModel):
    invoice_number: str
    invoice_amount: float
    invoice_date: str | None
    due_date: str | None
    status: str = ""
    amount_paid: float | None
    discount_taken: float | None


class PayablesEvidence(BaseModel):
    open_invoice_count: int
    open_invoice_total: float
    open_invoices: list[OpenPayableInvoice]
    recent_paid_invoices: list[PaidPayableInvoice]
    source: str = "MaddenCo PMHD (open) / PTHD+PTPY (paid history)"


class VendorEvidenceGap(BaseModel):
    code: Literal[
        "vendor_scorecard",
        "on_time_delivery_definition",
        "quality_and_chargeback_data",
        "terms_description_text",
        "city_state_fields",
        "rebate_accrual",
    ]
    label: str
    status: Literal["unavailable"] = "unavailable"
    explanation: str


class VendorIntelligenceGovernance(BaseModel):
    assessment_type: Literal["evidence_only"] = "evidence_only"
    automatic_score: bool = False
    decision_effect: Literal["none"] = "none"
    erp_write: bool = False


class VendorPerformanceSummary(BaseModel):
    window_days: int
    po_count: int
    quantity_ordered: float
    quantity_received: float
    quantity_backorder: float
    fill_rate_percent: float | None
    fill_rate_status: Literal["available", "unavailable"]
    on_time_delivery_status: Literal["unavailable"] = "unavailable"
    quality_and_chargeback_status: Literal["unavailable"] = "unavailable"
    source: str = "MaddenCo TMPOHD / TMPODT"
    explanation: str = (
        "Fill rate is quantity received divided by quantity ordered across "
        "this vendor's purchase-order lines in the trailing window - a "
        "real, computed signal. On-time delivery and quality/chargeback "
        "performance are not shown as 'unavailable pending connection': no "
        "table in this MaddenCo instance carries that data at all "
        "(TMPOHD's requested-delivery-date field is populated on 0.003% "
        "of rows, and there is no returns/chargeback/quality table), so "
        "no signal is computed for them rather than approximated."
    )


class VendorEvidenceResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    generated_at: str
    source: SourceEvidence
    identity: VendorIdentityEvidence
    purchase_volume: VendorPurchaseVolumeEvidence
    purchase_orders: PurchaseOrderEvidence
    receiving: ReceivingEvidence
    performance: VendorPerformanceSummary
    payables: PayablesEvidence
    gaps: list[VendorEvidenceGap]
    governance: VendorIntelligenceGovernance = Field(
        default_factory=VendorIntelligenceGovernance
    )


class VendorNoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author_identity: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=5000)

    @field_validator("author_identity", "note")
    @classmethod
    def require_non_whitespace(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must contain non-whitespace text.")
        return cleaned


class VendorNoteRecord(BaseModel):
    note_id: str
    vendor_number: int
    vendor_name: str
    author_identity: str
    note: str
    created_at: str
    source_as_of: str
    actor_identity_source: Literal["operator_supplied"] = "operator_supplied"
    actor_authority_status: Literal[
        "not_independently_verified"
    ] = "not_independently_verified"
    note_classification: Literal[
        "professional_workflow_metadata"
    ] = "professional_workflow_metadata"
    decision_effect: Literal["none"] = "none"
    erp_write: Literal[False] = False
    evidence_snapshot: dict[str, Any]
    evidence_snapshot_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class VendorNoteHistoryResponse(BaseModel):
    vendor_number: int
    count: int
    notes: list[VendorNoteRecord]
