from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CONTRACT_VERSION = "sales-order-visibility-foundation.v1"


class SourceEvidence(BaseModel):
    system: str = "MaddenCo ERP (DTA273)"
    access: Literal["read_only"] = "read_only"
    status: Literal["available"] = "available"
    retrieved_at: str


class InvoiceSearchResult(BaseModel):
    invoice_number: int
    customer_number: int
    customer_name: str = ""
    invoice_date: str | None
    type_code: str = ""
    total_amount: float
    void: bool
    route_code: str = ""
    store_number: int | None = None
    po_number: str = ""


class InvoiceSearchResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    source: SourceEvidence
    count: int
    invoices: list[InvoiceSearchResult]


class InvoiceHeaderEvidence(BaseModel):
    invoice_number: int
    customer_number: int
    customer_name: str = ""
    invoice_date: str | None
    due_date: str | None
    created_date: str | None
    changed_date: str | None
    type_code: str = ""
    void: bool
    hold_reason: str = ""
    direct_ship: bool
    pickup: bool
    route_code: str = ""
    store_number: int | None = None
    po_number: str = ""
    reference_number: str = ""
    terms_code: str = ""
    tax_exempt_code: str = ""
    customer_class: str = ""
    customer_type: str = ""
    type_of_sale: str = ""
    ship_to_lines: list[str] = Field(default_factory=list)
    ship_to_zip: str = ""
    tracking_number: str = ""
    total_amount: float
    total_units: float
    total_discount: float
    line_count: int | None = None
    invoice_count: int | None = None
    selling_salesman: int | None = None
    customer_salesman: int | None = None
    originating_salesman: int | None = None
    class_salesman: int | None = None
    status: str = ""
    status_secondary: str = ""


class InvoiceLineItem(BaseModel):
    line_number: int
    type_code: str = ""
    delete_code: str = ""
    product_number: str = ""
    product_description: str = ""
    product_vendor: str = ""
    brand: str = ""
    product_class: str = ""
    quantity: float
    quantity_ordered: float
    quantity_backorder: float
    unit_price: float
    extended_price: float
    actual_cost: float | None
    replacement_cost: float | None
    fet: float | None
    dot_number: str = ""
    dot_date: str | None
    tire_position: str = ""
    vehicle_make: str = ""
    vehicle_model: str = ""
    vehicle_year: int | None = None
    mileage: float | None = None


class InvoiceLineEvidence(BaseModel):
    line_count: int
    total_extended_price: float
    total_quantity: float
    lines: list[InvoiceLineItem]
    source: str = "MaddenCo TMIHSL joined to TMIHSI on invoice/line number"
    explanation: str = (
        "Extended price per line is TIHLQTY (quantity) multiplied by "
        "TIHLPRC (unit price); TMIHSL does not store its own extended-"
        "amount column. Vehicle fit fields (make/model/year/mileage) are "
        "read from TMIHSI for the matching invoice and line number when "
        "present."
    )


class InvoiceMemo(BaseModel):
    line_number: int | None = None
    type_code: str = ""
    message: str = ""
    created_date: str | None
    created_by: str = ""
    print_on_invoice: bool


class InvoiceMemoEvidence(BaseModel):
    memo_count: int
    memos: list[InvoiceMemo]
    source: str = "MaddenCo TMIHSM"


class InvoiceAuthorization(BaseModel):
    authorization_type: str = ""
    type_code: str = ""
    amount_authorized: float | None
    date_requested: str | None
    date_authorized: str | None
    time_requested: str = ""
    time_authorized: str = ""
    salesman_requested: int | None = None
    salesman_authorized: int | None = None
    requested_by: str = ""
    authorized_by: str = ""
    text: str = ""


class InvoiceAuthorizationEvidence(BaseModel):
    authorization_count: int
    authorizations: list[InvoiceAuthorization]
    source: str = "MaddenCo TMIHSA"
    explanation: str = (
        "Credit authorization requests/grants recorded against this "
        "invoice. This is MaddenCo's own authorization log, not a "
        "computed credit-risk judgment."
    )


class DeliveryManifestLine(BaseModel):
    store_number: int | None = None
    route: str = ""
    status: str = ""
    line_number: int | None = None
    sequence: int | None = None
    product_number: str = ""
    description: str = ""
    weight: float | None = None
    quantity: float | None = None
    created_at: str | None
    delivered_at: str | None
    delivered: bool


class DeliveryEvidence(BaseModel):
    manifest_status: Literal["records_found", "no_records_found"]
    total_line_count: int
    delivered_line_count: int
    undelivered_line_count: int
    is_fully_delivered: bool | None
    lines: list[DeliveryManifestLine]
    source: str = "MaddenCo INWHLOAD"
    explanation: str = (
        "A line is delivered when INWHLOAD.DLVSTAMP is not null. "
        "'no_records_found' means this invoice has no warehouse-load "
        "manifest rows at all (for example a will-call/pickup invoice "
        "never routed to a delivery route) — it is not evidence that "
        "delivery failed."
    )


class SalesOrderEvidenceGap(BaseModel):
    code: Literal[
        "open_order_queue",
        "fulfillment_sla_definition",
        "extended_price_not_stored",
        "delivery_manifest_optional",
    ]
    label: str
    status: Literal["unavailable"] = "unavailable"
    explanation: str


class SalesOrderVisibilityGovernance(BaseModel):
    assessment_type: Literal["evidence_only"] = "evidence_only"
    automatic_score: bool = False
    decision_effect: Literal["none"] = "none"
    erp_write: bool = False


class InvoiceEvidenceResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    generated_at: str
    source: SourceEvidence
    header: InvoiceHeaderEvidence
    lines: InvoiceLineEvidence
    memos: InvoiceMemoEvidence
    authorizations: InvoiceAuthorizationEvidence
    delivery: DeliveryEvidence
    gaps: list[SalesOrderEvidenceGap]
    governance: SalesOrderVisibilityGovernance = Field(
        default_factory=SalesOrderVisibilityGovernance
    )


class SalesSummaryRow(BaseModel):
    customer_number: int | None = None
    product_number: str = ""
    product_class: str = ""
    product_type: str = ""
    customer_class: str = ""
    customer_type: str = ""
    commission_code: str = ""
    vendor_number: str = ""
    store_number: int | None = None
    year_period: int | None = None
    sales: float
    units: float
    actual_cost: float | None
    replacement_cost: float | None
    fet: float | None


class SalesSummaryResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    generated_at: str
    source: SourceEvidence
    row_count: int
    total_sales: float
    total_units: float
    total_actual_cost: float
    rows: list[SalesSummaryRow]
    source_table: str = "MaddenCo TMSALE"
    explanation: str = (
        "TMSALE is a pre-aggregated sales summary fact table (by customer, "
        "product, class, type, and year-period), not an invoice-level "
        "list. Totals here are plain sums of the TMSALE rows returned for "
        "the requested filter."
    )


class OrderNoteCreate(BaseModel):
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


class OrderNoteRecord(BaseModel):
    note_id: str
    invoice_number: int
    customer_number: int | None = None
    customer_name: str = ""
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


class OrderNoteHistoryResponse(BaseModel):
    invoice_number: int
    count: int
    notes: list[OrderNoteRecord]
