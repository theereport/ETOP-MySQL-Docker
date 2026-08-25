from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CONTRACT_VERSION = "inventory-purchasing-foundation.v1"


class SourceEvidence(BaseModel):
    system: str = "MaddenCo ERP (DTA273)"
    access: Literal["read_only"] = "read_only"
    status: Literal["available"] = "available"
    retrieved_at: str


class ProductSearchResult(BaseModel):
    product_number: str
    description: str = ""
    search_key: str = ""
    product_class: str = ""
    product_type: str = ""
    brand: str = ""
    unit_of_measure: str = ""
    vendor_code: str = ""
    active: bool
    non_inventory: bool


class ProductSearchResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    source: SourceEvidence
    count: int
    products: list[ProductSearchResult]


class ProductIdentityEvidence(BaseModel):
    product_number: str
    search_key: str = ""
    description: str = ""
    product_class: str = ""
    product_type: str = ""
    brand: str = ""
    size: str = ""
    load_index: str = ""
    speed_rating: str = ""
    manufacturer_product_number: str = ""
    barcode: str = ""
    unit_of_measure: str = ""
    vendor_code: str = ""
    store_number: int | None = None
    warehouse_location: str = ""
    warehouse_alt_location: str = ""
    active: bool
    non_inventory: bool
    allow_po_creation: bool
    date_created: str | None = None
    date_last_received: str | None = None
    date_last_sold: str | None = None


class ProductCostingEvidence(BaseModel):
    vendor_cost: float | None
    actual_cost: float | None
    replacement_cost: float | None
    last_year_cost: float | None
    price_1: float | None
    price_2: float | None
    price_3: float | None
    price_4: float | None
    price_5: float | None
    price_6: float | None
    source: str = "MaddenCo TMPROD"


class ProductInventoryPositionEvidence(BaseModel):
    on_hand: float | None
    on_order: float | None
    allocated: float | None
    configured_minimum: float | None
    configured_maximum: float | None
    inventory_turns: float | None
    ordering_lead_time_days: int | None
    source: str = "MaddenCo TMPROD (product/store master row)"
    explanation: str = (
        "These are MaddenCo's own last-committed values on the product "
        "master row (TMPROD.PDINVENTRY, PDONORDER, PDALLOCATD, PDMIN, "
        "PDMAX, PDINVTURNS, PDLEADTIM). They are not a verified live, "
        "real-time, per-warehouse inventory feed, and ETOP computes no "
        "reorder point, safety stock, or turnover figure of its own from "
        "them."
    )


class MonthEndInventoryPeriod(BaseModel):
    store_number: int | None
    month: int | None
    year: int | None
    vendor_number: str = ""
    class_number: str = ""
    units: float
    total_cost: float
    total_fet: float


class MonthEndInventoryEvidence(BaseModel):
    status: Literal["available", "unavailable_source_capability"] = "available"
    period_count: int
    periods: list[MonthEndInventoryPeriod]
    latest_period_total_units: float | None
    latest_period_total_cost: float | None
    source: str = "MaddenCo EOMINV"
    explanation: str = (
        "EOMINV rows are periodic month-end inventory valuation snapshots "
        "keyed by store, month, year, vendor, and class for this product "
        "(PARTNUM). They are not a live, real-time on-hand quantity feed. "
        "Latest-period totals are a plain sum of UNITS and TOTALCOST across "
        "every store row sharing the most recent year/month present below."
    )


class OpenPurchaseOrderLine(BaseModel):
    po_number: int
    vendor_number: int | None
    po_date: str | None
    date_required: str | None
    status_code: str = ""
    complete: bool
    ship_via: str = ""
    buyer_number: int | None
    ordered_quantity: float
    received_quantity: float
    backorder_quantity: float
    average_unit_cost: float | None
    line_total_cost: float | None


class PurchaseExposureEvidence(BaseModel):
    status: Literal["available", "unavailable_source_capability"] = "available"
    open_order_count: int
    open_order_total_cost: float
    open_orders: list[OpenPurchaseOrderLine]
    source: str = "MaddenCo TMPOHD / TMPODT"
    explanation: str = (
        "Open purchase orders are TMPOHD rows carrying at least one TMPODT "
        "line for this product (TPDPRD) where the header complete flag is "
        "not Y, across every vendor with an open order for this item. "
        "Ordered/received/backorder quantities are summed from this "
        "product's own TMPODT lines on each PO. Line total cost is "
        "SUM(TPDQTYORD * TPDUNTCST) over those lines; average unit cost is "
        "the mean of TPDUNTCST across them."
    )


class ReceivingEvent(BaseModel):
    po_number: int
    vendor_number: int | None
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
        "Cost variance is MaddenCo's own recorded TRCDCOSDIF value for "
        "each receiving line of this product. The vendor number on each "
        "receipt is read from the purchase order header (TMPOHD.TPHNBVND) "
        "the receiving line references, since TTRCVD does not carry the "
        "AP vendor number directly."
    )


class ProductEvidenceGap(BaseModel):
    code: Literal[
        "reorder_point_formula",
        "real_time_onhand_by_warehouse",
        "demand_forecast_turnover_rate",
        "vendor_number_cross_reference",
        "extended_product_attributes",
    ]
    label: str
    status: Literal["unavailable"] = "unavailable"
    explanation: str


class InventoryPurchasingGovernance(BaseModel):
    assessment_type: Literal["evidence_only"] = "evidence_only"
    automatic_score: bool = False
    decision_effect: Literal["none"] = "none"
    erp_write: bool = False


class ProductEvidenceResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    generated_at: str
    source: SourceEvidence
    identity: ProductIdentityEvidence
    costing: ProductCostingEvidence
    inventory_position: ProductInventoryPositionEvidence
    month_end_inventory: MonthEndInventoryEvidence
    purchase_exposure: PurchaseExposureEvidence
    receiving: ReceivingEvidence
    gaps: list[ProductEvidenceGap]
    governance: InventoryPurchasingGovernance = Field(
        default_factory=InventoryPurchasingGovernance
    )


class InventoryNoteCreate(BaseModel):
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


class InventoryNoteRecord(BaseModel):
    note_id: str
    product_number: str
    product_description: str
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


class InventoryNoteHistoryResponse(BaseModel):
    product_number: str
    count: int
    notes: list[InventoryNoteRecord]
