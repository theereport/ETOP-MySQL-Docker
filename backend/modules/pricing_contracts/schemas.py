from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CONTRACT_VERSION = "pricing-contracts-foundation.v1"


class SourceEvidence(BaseModel):
    system: str = "MaddenCo ERP (DTA273)"
    access: Literal["read_only"] = "read_only"
    status: Literal["available"] = "available"
    retrieved_at: str


class DiscountRecord(BaseModel):
    """One TMDISC row, mapped without inventing a "final price".

    `fixed_amount`, `override_price`, `factor`, and `price_code` are all
    literal stored values from the same row. MaddenCo's own pricing engine
    decides which of these mechanics applies at sale time using inputs this
    module does not have visibility into, so no single "effective price"
    is computed here.
    """

    record_key: str
    customer_number: int
    vendor_code: str
    product_class: str
    product_class_label: str = ""
    product_class_item_type: str = ""
    product_class_active: bool | None = None
    product_number: str
    product_type: str
    delete_code: str = ""
    active: bool
    fixed_amount: float
    chain: int
    factor: float
    override_price: float
    price_code: int
    date_added: str | None = None
    date_changed: str | None = None
    time_added: str = ""
    time_changed: str = ""
    added_by: str = ""
    changed_by: str = ""


class PricingEvidenceGap(BaseModel):
    code: Literal[
        "vendor_rebate_accrual_ledger",
        "contract_compliance_scoring",
        "vendor_code_identity_resolution",
        "price_code_mechanism_mapping",
    ]
    label: str
    status: Literal["unavailable"] = "unavailable"
    explanation: str


class PricingContractsGovernance(BaseModel):
    assessment_type: Literal["evidence_only"] = "evidence_only"
    automatic_score: bool = False
    decision_effect: Literal["none"] = "none"
    erp_write: bool = False


class DiscountSearchResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    source: SourceEvidence
    count: int
    discounts: list[DiscountRecord]
    gaps: list[PricingEvidenceGap]
    governance: PricingContractsGovernance = Field(
        default_factory=PricingContractsGovernance
    )


class DiscountEvidenceResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    generated_at: str
    source: SourceEvidence
    discount: DiscountRecord
    gaps: list[PricingEvidenceGap]
    governance: PricingContractsGovernance = Field(
        default_factory=PricingContractsGovernance
    )


class CustomerClassRecord(BaseModel):
    id: int
    class_num: str
    class_name: str
    active: bool
    created_at: str | None = None
    created_by: str = ""
    changed_at: str | None = None
    changed_by: str = ""


class CustomerClassResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    source: SourceEvidence
    count: int
    customer_classes: list[CustomerClassRecord]


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class PricingNoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_number: int = Field(ge=0)
    vendor_code: str | None = Field(default=None, max_length=3)
    product_class: str | None = Field(default=None, max_length=2)
    product_number: str | None = Field(default=None, max_length=15)
    product_type: str | None = Field(default=None, max_length=3)
    author_identity: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=5000)

    @field_validator(
        "vendor_code", "product_class", "product_number", "product_type"
    )
    @classmethod
    def blank_scope_to_none(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @field_validator("author_identity", "note")
    @classmethod
    def require_non_whitespace(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must contain non-whitespace text.")
        return cleaned


class PricingNoteRecord(BaseModel):
    note_id: str
    customer_number: int
    vendor_code: str | None = None
    product_class: str | None = None
    product_number: str | None = None
    product_type: str | None = None
    author_identity: str
    note: str
    created_at: str
    source_as_of: str
    matched_discount_count: int
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


class PricingNoteHistoryResponse(BaseModel):
    customer_number: int
    count: int
    notes: list[PricingNoteRecord]
