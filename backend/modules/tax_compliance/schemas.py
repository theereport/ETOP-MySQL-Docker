from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CONTRACT_VERSION = "tax-compliance-foundation.v1"


class SourceEvidence(BaseModel):
    system: str = "MaddenCo ERP (DTA273)"
    access: Literal["read_only"] = "read_only"
    status: Literal["available"] = "available"
    retrieved_at: str


class TaxAuthorityRecord(BaseModel):
    tax_authority: int
    state_code: int
    state_abbreviation: str = ""
    description: str = ""
    tax_type_code: str = ""
    rate_percent: float | None = None
    max_tax_amount: float | None = None
    fet_applicable: bool
    selectable_from_prompt: bool
    next_tax_authority: int | None = None
    next_state_code: int | None = None
    active: bool
    date_created: str | None = None
    date_changed: str | None = None
    created_by: str = ""
    changed_by: str = ""


class TaxAuthoritySearchResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    source: SourceEvidence
    count: int
    authorities: list[TaxAuthorityRecord]
    explanation: str = (
        "Every row is a direct read of MaddenCo TMTAX (tax authority rate "
        "master). rate_percent and max_tax_amount are TTAXRATPCT/"
        "TTAXAMTMAX exactly as stored (raw decimal fraction and dollar "
        "cap); this module performs no rate calculation."
    )


class TaxExemptionCodeRecord(BaseModel):
    exempt_code: str
    state_code: int
    description: str = ""
    tax_type_code: str = ""
    override_or_percent_code: str = ""
    percent_taxable: float | None = None
    rate_percent: float | None = None
    max_taxable_per_line: float | None = None
    active: bool
    date_created: str | None = None
    date_changed: str | None = None
    created_by: str = ""
    changed_by: str = ""


class TaxExemptionCodeSearchResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    source: SourceEvidence
    count: int
    exemption_codes: list[TaxExemptionCodeRecord]
    explanation: str = (
        "Every row is a direct read of MaddenCo TMTAXE (tax exemption code "
        "master), keyed by (TTXECODEXE, TTXECODSTE). override_or_percent_code "
        "is the raw TTXEOORP flag value as stored; MaddenCo does not expose "
        "a decode table for it in this schema, so it is passed through "
        "unmodified rather than guessed at."
    )


class TaxComplianceGap(BaseModel):
    code: Literal[
        "exemption_certificate_document_storage",
        "jurisdiction_nexus_table",
        "tax_compliance_risk_score",
    ]
    label: str
    status: Literal["unavailable"] = "unavailable"
    explanation: str


class TaxComplianceGovernance(BaseModel):
    assessment_type: Literal["evidence_only"] = "evidence_only"
    automatic_score: bool = False
    decision_effect: Literal["none"] = "none"
    erp_write: bool = False


class CustomerExemptionCheckResult(BaseModel):
    customer_number: int
    customer_name: str = ""
    state_code: int | None = None
    exemption_code_on_file: str = ""
    fet_exempt: bool
    exemption_certificate_expiration_date: str | None = None
    expiration_status: Literal[
        "current",
        "expired",
        "no_expiration_date_on_file",
    ]
    match_status: Literal[
        "matched",
        "no_matching_exemption_code_found",
        "no_exemption_code_on_customer",
    ]
    matched_exemption_codes: list[TaxExemptionCodeRecord] = Field(
        default_factory=list
    )


class CustomerExemptionCheckResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    generated_at: str
    source: SourceEvidence
    result: CustomerExemptionCheckResult
    gaps: list[TaxComplianceGap]
    governance: TaxComplianceGovernance = Field(
        default_factory=TaxComplianceGovernance
    )


class CustomerExemptionCheckBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_numbers: list[int] = Field(min_length=1, max_length=25)


class CustomerExemptionCheckBatchResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    generated_at: str
    source: SourceEvidence
    checked_count: int
    not_found_customer_numbers: list[int]
    results: list[CustomerExemptionCheckResult]
    gaps: list[TaxComplianceGap]
    governance: TaxComplianceGovernance = Field(
        default_factory=TaxComplianceGovernance
    )


class TaxComplianceNoteCreate(BaseModel):
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


class TaxComplianceNoteRecord(BaseModel):
    note_id: str
    customer_number: int
    customer_name: str
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


class TaxComplianceNoteHistoryResponse(BaseModel):
    customer_number: int
    count: int
    notes: list[TaxComplianceNoteRecord]
