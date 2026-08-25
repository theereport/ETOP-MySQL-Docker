from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .schemas import EvidenceCoverageItem, EvidenceGovernance, EvidenceSourceReference


APSpendReadinessStatus = Literal[
    "available",
    "partial",
    "unavailable",
    "degraded",
]
APSpendQuestionStatus = Literal[
    "answered",
    "needs_clarification",
    "unavailable",
    "no_evidence",
    "degraded",
]
APSpendIntent = Literal["total_spend", "top_vendor", "top_vendor_by_month"]
APSpendTimeBasis = Literal[
    "erp_accounting_year",
    "erp_accounting_period",
    "calendar_invoice_date",
]


class StrictEvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class APSpendMappingCheck(StrictEvidenceModel):
    key: str
    label: str
    status: APSpendReadinessStatus
    source: str
    required_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    incompatible_fields: list[str] = Field(default_factory=list)
    runtime_data_type: str | None = None
    explanation: str


class APSpendDateBasisReadiness(StrictEvidenceModel):
    key: str
    label: str
    status: APSpendReadinessStatus
    source_fields: list[str]
    explanation: str


class APSpendMeasureDefinition(StrictEvidenceModel):
    key: Literal["signed_posted_ap_gl_distribution_amount"] = (
        "signed_posted_ap_gl_distribution_amount"
    )
    label: Literal["Signed posted AP GL-distribution amount"] = (
        "Signed posted AP GL-distribution amount"
    )
    source_table: Literal["PMGLDS"] = "PMGLDS"
    amount_field: Literal["PMGAMTINV"] = "PMGAMTINV"
    sign_treatment: Literal["signed_as_stored"] = "signed_as_stored"
    ranking_basis: Literal["net_signed_amount_descending"] = (
        "net_signed_amount_descending"
    )
    interpretation: str
    excluded_meanings: list[str]


class APSpendReadinessResponse(StrictEvidenceModel):
    contract_version: str
    generated_at: str
    status: APSpendReadinessStatus
    source_schema: str
    mapping_checks: list[APSpendMappingCheck]
    date_bases: list[APSpendDateBasisReadiness]
    measure: APSpendMeasureDefinition
    local_data_dictionary_status: APSpendReadinessStatus
    local_data_dictionary_path: str | None
    product_owner_mappings_needed: list[str]
    governance: EvidenceGovernance
    warnings: list[str]


class APSpendParsedQuestion(StrictEvidenceModel):
    parser_version: str
    original_question: str
    normalized_question: str
    intent: APSpendIntent | None
    division: str | None
    account: str | None
    time_basis: APSpendTimeBasis | None
    year: int | None
    month: int | None
    accounting_period: int | None
    range_start: str | None
    range_end_exclusive: str | None
    interpretation_notes: list[str]
    missing_slots: list[str]
    ambiguous_slots: list[str]
    unavailable_slots: list[str]


class APSpendAmountSummary(StrictEvidenceModel):
    distribution_row_count: int
    amount_available_row_count: int
    missing_amount_row_count: int
    invoice_identity_count: int
    vendor_count: int
    positive_distribution_amount: float
    negative_distribution_amount: float
    net_signed_amount: float


class APSpendVendorRank(StrictEvidenceModel):
    rank: int
    vendor_number: str
    vendor_name: str | None
    distribution_row_count: int
    amount_available_row_count: int
    missing_amount_row_count: int
    invoice_identity_count: int
    positive_distribution_amount: float
    negative_distribution_amount: float
    net_signed_amount: float


class APSpendMonthlyPeriod(StrictEvidenceModel):
    calendar_year: int
    calendar_month: int
    range_start: str
    range_end_exclusive: str
    status: Literal["available", "no_evidence"]
    leaders: list[APSpendVendorRank]
    ranking_complete: bool
    leader_set_complete: bool
    explanation: str


class APSpendQuestionResponse(StrictEvidenceModel):
    contract_version: str
    generated_at: str
    evidence_as_of: str | None
    status: APSpendQuestionStatus
    answer_text: str
    parsed: APSpendParsedQuestion
    readiness: APSpendReadinessResponse
    total: APSpendAmountSummary | None
    ranking: list[APSpendVendorRank]
    leaders: list[APSpendVendorRank]
    monthly_periods: list[APSpendMonthlyPeriod]
    ranking_row_limit: int
    monthly_period_limit: int
    monthly_leader_limit: int
    ranking_complete: bool | None
    leader_set_complete: bool | None
    evidence_consistency: Literal[
        "single_read_only_consistent_snapshot",
        "no_financial_query",
        "consistent_snapshot_query_failed",
    ]
    coverage: list[EvidenceCoverageItem]
    source_references: list[EvidenceSourceReference]
    governance: EvidenceGovernance
    evidence_sha256: str
    warnings: list[str]
    suggested_questions: list[str]
