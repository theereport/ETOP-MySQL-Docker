from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CONTRACT_VERSION = "freight-logistics-foundation.v1"


class SourceEvidence(BaseModel):
    system: str = "MaddenCo ERP (DTA273)"
    access: Literal["read_only"] = "read_only"
    status: Literal["available"] = "available"
    retrieved_at: str


class RouteSearchResult(BaseModel):
    route_key: str
    route_code: str
    warehouse_number: int | None = None
    warehouse_location_name: str = ""
    status_code: str = ""
    active: bool


class RouteSearchResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    source: SourceEvidence
    count: int
    routes: list[RouteSearchResult]


class RouteScheduleDay(BaseModel):
    day: Literal[
        "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"
    ]
    scheduled: bool
    scheduled_stop_count: int = 0


class WarehouseDirectionLabel(BaseModel):
    direction_name: str = ""
    minimum_weight: int | None = None
    maximum_weight: int | None = None
    quantity_limit: int | None = None
    limit_by: str = ""
    active: bool


class WarehouseLabelEvidence(BaseModel):
    warehouse_number: int | None = None
    warehouse_location_name: str = ""
    directions: list[WarehouseDirectionLabel] = Field(default_factory=list)
    source: str = (
        "WH_DASHBOARD_LOCATIONS / WH_DASHBOARD_ROUTES "
        "(existing warehouse-dashboard application configuration)"
    )
    explanation: str = (
        "warehouse_location_name comes from an exact numeric join of "
        "KMROUTES.RTEWHSE to WH_DASHBOARD_LOCATIONS.LOCATION_NUMBER. "
        "Each listed direction is a WH_DASHBOARD_ROUTES row for that same "
        "warehouse whose INCLUDED_ROUTES text field contains this route's "
        "code as a comma-separated entry (a text-containment match, not a "
        "foreign key). This is dashboard configuration, not MaddenCo "
        "transactional evidence."
    )


class RouteIdentityEvidence(BaseModel):
    route_key: str
    route_code: str
    warehouse_number: int | None = None
    status_code: str = ""
    active: bool
    schedule: list[RouteScheduleDay]
    created_at: str | None = None
    created_by: str = ""
    changed_at: str | None = None
    changed_by: str = ""


class RouteLoadLine(BaseModel):
    store_number: int | None = None
    route: str = ""
    status_code: str = ""
    invoice_number: int | None = None
    customer_number: int | None = None
    line_number: int | None = None
    seq: int | None = None
    product_number: str = ""
    description: str = ""
    weight: float | None = None
    quantity: float | None = None
    created_at: str | None = None
    delivered_at: str | None = None
    delivered: bool
    elapsed_minutes: float | None = None


class RouteLoadEvidence(BaseModel):
    line_count: int
    delivered_count: int
    undelivered_count: int
    total_weight: float
    total_quantity: float
    average_elapsed_minutes: float | None = None
    lines: list[RouteLoadLine]
    source: str = "MaddenCo INWHLOAD"
    explanation: str = (
        "A line is 'delivered' when INWHLOAD.DLVSTAMP holds a real "
        "timestamp; MaddenCo represents an outstanding line with an "
        "absent/zero delivery timestamp, read here as null. "
        "elapsed_minutes is DLVSTAMP minus CRTSTAMP in minutes, computed "
        "only when both timestamps are present. average_elapsed_minutes "
        "is the arithmetic mean of elapsed_minutes across delivered lines "
        "only. None of this is an on-time-delivery percentage or a "
        "performance score."
    )


class CodPaymentCorrection(BaseModel):
    field: str = ""
    before_value: str = ""
    after_value: str = ""
    reason: str = ""
    changed_by: str = ""
    changed_at: str | None = None


class CodPaymentDetailNote(BaseModel):
    notes: str = ""
    created_at: str | None = None
    created_by: str = ""


class CodPayment(BaseModel):
    payment_id: int
    customer_number: int | None = None
    route: str = ""
    payment_type: str = ""
    check_number: str = ""
    auth_number: str = ""
    amount: float
    notes: str = ""
    invoices: str = ""
    received: bool
    received_at: str | None = None
    created_at: str | None = None
    corrections: list[CodPaymentCorrection] = Field(default_factory=list)
    detail_notes: list[CodPaymentDetailNote] = Field(default_factory=list)


class PaymentEvidence(BaseModel):
    payment_count: int
    total_amount: float
    received_count: int
    unreceived_count: int
    payments: list[CodPayment]
    source: str = (
        "MaddenCo WHSIGPAY joined to WHSIGPAYC (by ID cast to text) and "
        "WHSIGPAYD (by ID)"
    )
    explanation: str = (
        "COD payments a driver recorded as collected on this route. "
        "received_count/unreceived_count are direct counts of MaddenCo's "
        "own RECEIVED flag. This module performs no COD reconciliation "
        "and has no authority to mark a payment received or write it "
        "back to MaddenCo."
    )


class DeliveryException(BaseModel):
    customer_number: int | None = None
    route: str = ""
    invoice_number: int | None = None
    line_number: int | None = None
    quantity: float | None = None
    option_code: str = ""
    notes: str = ""
    approved: bool
    credit_invoice_number: int | None = None
    approval_notes: str = ""
    approved_by: str = ""
    created_at: str | None = None
    approved_at: str | None = None


class ExceptionEvidence(BaseModel):
    exception_count: int
    approved_count: int
    unapproved_count: int
    exceptions: list[DeliveryException]
    source: str = "MaddenCo WHSIGNOTE"
    explanation: str = (
        "Driver-submitted delivery exception/credit-request notes. "
        "approved reflects MaddenCo's own recorded APPROVED flag; this "
        "module does not approve, deny, or otherwise write back any "
        "exception."
    )


class DeliveryAdjustment(BaseModel):
    route: str = ""
    invoice_number: int | None = None
    customer_number: int | None = None
    line_number: int | None = None
    seq: int | None = None
    line_type: str = ""
    product_number: str = ""
    description: str = ""
    quantity: float | None = None
    created_at: str | None = None
    uploaded_at: str | None = None


class AdjustmentEvidence(BaseModel):
    adjustment_count: int
    adjustments: list[DeliveryAdjustment]
    source: str = "MaddenCo WHSIGADJ"
    explanation: str = (
        "Driver-recorded line-level quantity adjustments uploaded from "
        "the delivery device. This is MaddenCo's own record, not a "
        "computed exception score."
    )


class SignatureCaptureSession(BaseModel):
    serial_number: str = ""
    route: str = ""
    session_type: str = ""
    created_at: str | None = None
    created_by: str = ""


class SignatureCaptureEvidence(BaseModel):
    session_count: int
    sessions: list[SignatureCaptureSession]
    source: str = "MaddenCo WHSIGRTE"
    explanation: str = (
        "Records when a handheld signature-capture device opened a "
        "session for this route. This is not a proof-of-delivery "
        "completeness metric."
    )


class SignatureImage(BaseModel):
    customer_number: int | None = None
    invoice_number: int | None = None
    signer_name: str = ""
    file_name: str = ""
    created_at: str | None = None
    uploaded_at: str | None = None


class ImageEvidence(BaseModel):
    image_count: int
    images: list[SignatureImage]
    source: str = "MaddenCo WHSIGIMG joined to INWHLOAD (by customer + invoice)"
    explanation: str = (
        "Lists recorded proof-of-delivery signature image filenames only "
        "for invoices on this route's load manifest. This module does "
        "not retrieve, store, or display the underlying image file."
    )


class RouteEvidenceGap(BaseModel):
    code: Literal[
        "route_profitability_formula",
        "on_time_delivery_definition",
        "cod_reconciliation_authority",
        "proof_of_delivery_image_retrieval",
        "route_code_global_uniqueness",
    ]
    label: str
    status: Literal["unavailable"] = "unavailable"
    explanation: str


class FreightLogisticsGovernance(BaseModel):
    assessment_type: Literal["evidence_only"] = "evidence_only"
    automatic_score: bool = False
    decision_effect: Literal["none"] = "none"
    erp_write: bool = False


class RouteEvidenceResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    generated_at: str
    source: SourceEvidence
    identity: RouteIdentityEvidence
    warehouse_label: WarehouseLabelEvidence
    load: RouteLoadEvidence
    payments: PaymentEvidence
    exceptions: ExceptionEvidence
    adjustments: AdjustmentEvidence
    signature_sessions: SignatureCaptureEvidence
    images: ImageEvidence
    gaps: list[RouteEvidenceGap]
    governance: FreightLogisticsGovernance = Field(
        default_factory=FreightLogisticsGovernance
    )


class RouteNoteCreate(BaseModel):
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


class RouteNoteRecord(BaseModel):
    note_id: str
    route_code: str
    warehouse_number: int | None = None
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


class RouteNoteHistoryResponse(BaseModel):
    route_code: str
    count: int
    notes: list[RouteNoteRecord]


__all__ = [
    "CONTRACT_VERSION",
    "SourceEvidence",
    "RouteSearchResult",
    "RouteSearchResponse",
    "RouteScheduleDay",
    "WarehouseDirectionLabel",
    "WarehouseLabelEvidence",
    "RouteIdentityEvidence",
    "RouteLoadLine",
    "RouteLoadEvidence",
    "CodPaymentCorrection",
    "CodPaymentDetailNote",
    "CodPayment",
    "PaymentEvidence",
    "DeliveryException",
    "ExceptionEvidence",
    "DeliveryAdjustment",
    "AdjustmentEvidence",
    "SignatureCaptureSession",
    "SignatureCaptureEvidence",
    "SignatureImage",
    "ImageEvidence",
    "RouteEvidenceGap",
    "FreightLogisticsGovernance",
    "RouteEvidenceResponse",
    "RouteNoteCreate",
    "RouteNoteRecord",
    "RouteNoteHistoryResponse",
]
