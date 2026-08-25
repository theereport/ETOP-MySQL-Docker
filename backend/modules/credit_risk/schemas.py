from __future__ import annotations

from datetime import date
import math
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)


CONTRACT_VERSION = "credit-risk-foundation.v1"
PRIORITY_ALERTS_CONTRACT_VERSION = "credit-risk-priority-alerts.v1"
CREDIT_LINE_INTELLIGENCE_CONTRACT_VERSION = (
    "credit-risk-credit-line-intelligence.v1"
)
PORTFOLIO_MONITORING_CONTRACT_VERSION = (
    "credit-risk-portfolio-monitoring.v1"
)
ORDER_DECISION_PREPARATION_CONTRACT_VERSION = (
    "credit-risk-order-decision-preparation.v1"
)


class RiskBandSet(BaseModel):
    band_set_id: str
    version: str
    title: str
    status: Literal["product_owner_supplied_draft"]
    source_record: str
    seeded_at: str
    automated_policy: bool = False
    promotion_authority: Literal["deferred"] = "deferred"


class RiskBand(BaseModel):
    sequence: int
    rating_min: int = Field(ge=1, le=10)
    rating_max: int = Field(ge=1, le=10)
    meaning: str
    typical_response: str


class RiskBandSetResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    band_set: RiskBandSet
    bands: list[RiskBand]


class SourceEvidence(BaseModel):
    system: str
    access: Literal["read_only"] = "read_only"
    status: Literal["available"] = "available"
    retrieved_at: str
    source_transaction_as_of: None = None


class CustomerIdentityEvidence(BaseModel):
    customer_number: int
    customer_name: str
    dba_name: str = ""
    address_lines: list[str] = Field(default_factory=list)
    state_code: int | None = None
    zip_code: str = ""
    phone: str = ""
    email: str = ""
    route_code: str = ""
    store_number: int | None = None
    salesman_number: int | None = None
    customer_type: str = ""
    customer_class: str = ""
    active: bool


class CreditEvidence(BaseModel):
    credit_line: float
    open_ar: float
    erp_on_order_aggregate: float
    customer_360_exposure: float
    customer_360_available_credit: float
    amount_over_limit: float
    utilization_percent: float | None
    terms_code: str = ""
    terms_description: str = ""


ExposureComponentStatus = Literal[
    "available",
    "unavailable",
    "available_unclassified",
]


class ExposureComponent(BaseModel):
    key: str
    label: str
    operation: Literal["add", "subtract", "informational"]
    value: float | None
    calculation_value: float | None
    status: ExposureComponentStatus
    required_for_full_exposure: bool
    included_in_partial_calculation: bool
    source: str | None
    explanation: str


class ExposureEvidence(BaseModel):
    full_formula: str
    full_exposure: None = None
    completeness: Literal["partial"] = "partial"
    known_component_subtotal: float
    operational_reference_formula: str
    partial_exposure: float
    partial_available_credit: float
    missing_required_components: list[str]
    components: list[ExposureComponent]
    warnings: list[str]


class AgingEvidence(BaseModel):
    future: float
    current: float
    days_30: float
    days_60: float
    days_90: float
    days_120: float
    past_due: float
    bucket_total: float
    open_ar_reconciliation_difference: float
    source: str
    status: Literal["available"] = "available"


class UnavailablePaymentMetric(BaseModel):
    value: None = None
    status: Literal["unavailable"] = "unavailable"
    source: None = None
    explanation: str


class PaymentEvidence(BaseModel):
    last_payment_amount: float | None
    last_payment_date: str | None
    last_payment_status: Literal[
        "available",
        "partial",
        "degraded",
        "no_record_in_current_contract",
    ]
    last_payment_explanation: str
    average_days_to_pay: UnavailablePaymentMetric
    weighted_average_days_to_pay: UnavailablePaymentMetric
    days_beyond_terms: UnavailablePaymentMetric
    on_time_percentage: UnavailablePaymentMetric
    late_payment_frequency: UnavailablePaymentMetric
    largest_historical_delinquency: UnavailablePaymentMetric


class CreditRiskGovernance(BaseModel):
    assessment_type: Literal[
        "manual_professional_judgment"
    ] = "manual_professional_judgment"
    automatic_score: bool = False
    decision_effect: Literal["none"] = "none"
    erp_write: bool = False


class AssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manual_rating: StrictInt = Field(ge=1, le=10)
    review_date: date
    next_review_date: date
    analyst_identity: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=5000)

    @field_validator("analyst_identity", "rationale")
    @classmethod
    def require_non_whitespace(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must contain non-whitespace text.")
        return cleaned

    @model_validator(mode="after")
    def validate_review_dates(self) -> "AssessmentCreate":
        if self.next_review_date < self.review_date:
            raise ValueError(
                "next_review_date must be on or after review_date."
            )
        return self


class AssessmentRecord(BaseModel):
    assessment_id: str
    customer_number: int
    customer_name: str
    manual_rating: int = Field(ge=1, le=10)
    band_set_id: str
    band_set_version: str
    band_set_status: str
    band: RiskBand
    review_date: date
    next_review_date: date
    analyst_identity: str
    rationale: str
    created_at: str
    source_as_of: str
    completeness_state: Literal["partial"] = "partial"
    actor_identity_source: Literal[
        "operator_supplied"
    ] = "operator_supplied"
    actor_authority_status: Literal[
        "not_independently_verified"
    ] = "not_independently_verified"
    assessment_classification: Literal[
        "professional_judgment"
    ] = "professional_judgment"
    decision_effect: Literal["none"] = "none"
    evidence_snapshot: dict[str, Any]
    evidence_snapshot_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class CustomerRiskResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    source: SourceEvidence
    customer: CustomerIdentityEvidence
    credit: CreditEvidence
    exposure: ExposureEvidence
    aging: AgingEvidence
    payment: PaymentEvidence
    latest_assessment: AssessmentRecord | None = None
    governance: CreditRiskGovernance = Field(
        default_factory=CreditRiskGovernance
    )


class AssessmentHistoryResponse(BaseModel):
    customer_number: int
    count: int
    assessments: list[AssessmentRecord]


class PriorityAssessmentReference(BaseModel):
    assessment_id: str
    customer_number: int
    customer_name: str
    manual_rating: int = Field(ge=1, le=10)
    band: RiskBand
    review_date: date
    next_review_date: date
    created_at: str
    source_as_of: str
    evidence_snapshot_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class PriorityOrderingEvidence(BaseModel):
    review_state: Literal[
        "overdue",
        "due_today",
        "scheduled",
    ]
    latest_manual_rating: int = Field(ge=1, le=10)
    deterioration_state: Literal[
        "deteriorated",
        "not_deteriorated",
        "insufficient_history",
    ]
    manual_rating_change: int | None
    over_line_state: Literal[
        "over_line",
        "not_over_line",
        "unavailable",
    ]
    next_review_date: date


class PriorityLiveExposureEvidence(BaseModel):
    status: Literal[
        "available",
        "source_unavailable",
        "customer_not_found",
        "source_integrity_error",
    ]
    source: str
    retrieved_at: str | None
    exposure_completeness: Literal["partial"] | None
    credit_line: float | None
    partial_exposure: float | None
    partial_available_credit: float | None
    amount_over_limit: float | None
    is_over_line: bool | None
    explanation: str


class PriorityAlert(BaseModel):
    code: Literal[
        "review_overdue",
        "review_due_today",
        "manual_rating_deteriorated",
        "draft_band_attention",
        "current_partial_exposure_over_line",
        "live_source_degraded",
    ]
    category: Literal[
        "review_schedule",
        "assessment_change",
        "draft_taxonomy",
        "live_exposure",
        "source_gap",
    ]
    evidence_class: Literal[
        "professional_judgment",
        "deterministic_comparison",
        "observed_current",
        "source_limitation",
    ]
    title: str
    explanation: str
    assessment_ids: list[str] = Field(default_factory=list)
    evidence_sha256: list[str] = Field(default_factory=list)
    source_as_of: str | None = None


class PriorityPortfolioItem(BaseModel):
    rank: int = Field(ge=1)
    priority_category: Literal[
        "review_overdue",
        "review_due_today",
        "scheduled_review",
    ]
    customer_number: int
    customer_name: str
    customer_name_source: Literal[
        "live_customer_360",
        "saved_assessment",
    ]
    latest_assessment: PriorityAssessmentReference
    previous_assessment: PriorityAssessmentReference | None
    draft_band_attention: bool
    ordering_evidence: PriorityOrderingEvidence
    live_exposure: PriorityLiveExposureEvidence
    alerts: list[PriorityAlert]
    ordering_reasons: list[str]


class PriorityPortfolioSummary(BaseModel):
    assessed_customer_count: int = Field(ge=0)
    operational_alert_count: int = Field(ge=0)
    overdue_review_count: int = Field(ge=0)
    due_today_review_count: int = Field(ge=0)
    deterioration_count: int = Field(ge=0)
    draft_band_attention_count: int = Field(ge=0)
    over_line_count: int = Field(ge=0)
    live_source_degraded_count: int = Field(ge=0)


class UnavailablePriorityCapability(BaseModel):
    code: Literal[
        "broken_promise_alerts",
        "nsf_alerts",
    ]
    label: str
    status: Literal["unavailable_source_capability"] = (
        "unavailable_source_capability"
    )
    emitted_alerts: Literal[False] = False
    explanation: str


class PriorityOrderingGovernance(BaseModel):
    rule_version: Literal[
        "credit-risk-priority-ordering.v1"
    ] = "credit-risk-priority-ordering.v1"
    classification: Literal[
        "operational_ordering"
    ] = "operational_ordering"
    ordered_conditions: list[str]
    numeric_risk_score: Literal[False] = False
    automatic_credit_decision: Literal[False] = False
    recommendation: Literal[False] = False
    notification: Literal[False] = False
    erp_write: Literal[False] = False
    unavailable_over_line_treatment: str
    explanation: str


class PriorityAlertsResponse(BaseModel):
    contract_version: str = PRIORITY_ALERTS_CONTRACT_VERSION
    generated_at: str
    as_of_date: date
    coverage_statement: str
    unassessed_customers_excluded: Literal[True] = True
    summary: PriorityPortfolioSummary
    ordering: PriorityOrderingGovernance
    unavailable_capabilities: list[UnavailablePriorityCapability]
    items: list[PriorityPortfolioItem]


class CreditRiskErrorDetail(BaseModel):
    code: str
    message: str


CreditLineMetricStatus = Literal["available", "unavailable", "invalid"]


class CreditLineMetric(BaseModel):
    value: float | None
    status: CreditLineMetricStatus
    source: str | None
    as_of: str | None
    explanation: str


class CreditLineSalesEvidence(BaseModel):
    month_to_date: CreditLineMetric
    year_to_date: CreditLineMetric
    last_year: CreditLineMetric
    annualized_sales: CreditLineMetric


class CreditLineCapacityEvidence(BaseModel):
    current_credit_line: CreditLineMetric
    partial_exposure: CreditLineMetric
    available_credit: CreditLineMetric
    high_balance: CreditLineMetric
    monthly_high_balance: CreditLineMetric
    average_daily_balance: CreditLineMetric


class CreditLineAnalyticalReference(BaseModel):
    amount: float | None
    status: CreditLineMetricStatus
    formula: str
    rounding_increment: float
    rule_version: Literal[
        "customer-360-annualized-two-month-line.v1"
    ] = "customer-360-annualized-two-month-line.v1"
    knowledge_class: Literal[
        "analytical_inference"
    ] = "analytical_inference"
    policy_status: Literal[
        "existing_unapproved_analytical_reference"
    ] = "existing_unapproved_analytical_reference"
    automatic_recommendation: Literal[False] = False
    explanation: str


class CreditLineGap(BaseModel):
    code: Literal[
        "full_exposure",
        "seasonal_limit_model",
        "related_account_exposure",
        "approved_line_policy",
        "approval_authority",
    ]
    label: str
    status: Literal["unavailable"] = "unavailable"
    explanation: str


class CreditLineGovernance(BaseModel):
    classification: Literal[
        "decision_support"
    ] = "decision_support"
    reference_is_recommendation: Literal[False] = False
    proposal_is_decision: Literal[False] = False
    proposal_approval_effect: Literal["none"] = "none"
    erp_write: Literal[False] = False
    actor_identity_source: Literal[
        "operator_supplied"
    ] = "operator_supplied"
    actor_authority_status: Literal[
        "not_independently_verified"
    ] = "not_independently_verified"
    statements: list[str] = Field(default_factory=list)


class CreditLineProposalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposed_credit_line: float = Field(ge=0, le=1_000_000_000)
    review_date: date
    analyst_identity: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=5000)

    @field_validator("proposed_credit_line")
    @classmethod
    def finite_proposed_line(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("proposed_credit_line must be finite.")
        return round(value, 2)

    @field_validator("analyst_identity", "rationale")
    @classmethod
    def require_proposal_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must contain non-whitespace text.")
        return cleaned


class CreditLineProposalRecord(BaseModel):
    proposal_id: str
    customer_number: int
    customer_name: str
    proposed_credit_line: float
    current_credit_line: float
    analytical_reference_line: float | None
    review_date: date
    analyst_identity: str
    rationale: str
    created_at: str
    source_as_of: str
    actor_identity_source: Literal[
        "operator_supplied"
    ] = "operator_supplied"
    actor_authority_status: Literal[
        "not_independently_verified"
    ] = "not_independently_verified"
    proposal_classification: Literal[
        "professional_recommendation"
    ] = "professional_recommendation"
    approval_status: Literal[
        "not_submitted_to_governed_approval"
    ] = "not_submitted_to_governed_approval"
    decision_effect: Literal["none"] = "none"
    erp_write: Literal[False] = False
    evidence_snapshot: dict[str, Any]
    evidence_snapshot_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class CreditLineProposalHistoryResponse(BaseModel):
    customer_number: int
    count: int
    proposals: list[CreditLineProposalRecord]


class CreditLineIntelligenceResponse(BaseModel):
    contract_version: str = CREDIT_LINE_INTELLIGENCE_CONTRACT_VERSION
    generated_at: str
    source: SourceEvidence
    customer: CustomerIdentityEvidence
    sales: CreditLineSalesEvidence
    capacity: CreditLineCapacityEvidence
    analytical_reference: CreditLineAnalyticalReference
    current_manual_assessment: AssessmentRecord | None
    latest_professional_proposal: CreditLineProposalRecord | None
    gaps: list[CreditLineGap]
    governance: CreditLineGovernance


class PortfolioReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposition: Literal[
        "reviewed_no_change",
        "reassessment_needed",
        "credit_line_analysis_needed",
        "information_requested",
    ]
    reviewer_identity: str = Field(min_length=1, max_length=200)
    notes: str = Field(min_length=1, max_length=5000)
    follow_up_date: date | None = None

    @field_validator("reviewer_identity", "notes")
    @classmethod
    def require_portfolio_review_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must contain non-whitespace text.")
        return cleaned


class PortfolioReviewRecord(BaseModel):
    portfolio_review_id: str
    customer_number: int
    customer_name: str
    disposition: Literal[
        "reviewed_no_change",
        "reassessment_needed",
        "credit_line_analysis_needed",
        "information_requested",
    ]
    reviewer_identity: str
    notes: str
    follow_up_date: date | None
    created_at: str
    assessment_id: str
    proposal_id: str | None
    actor_identity_source: Literal[
        "operator_supplied"
    ] = "operator_supplied"
    actor_authority_status: Literal[
        "not_independently_verified"
    ] = "not_independently_verified"
    review_classification: Literal[
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


class PortfolioReviewHistoryResponse(BaseModel):
    customer_number: int
    count: int
    reviews: list[PortfolioReviewRecord]


class PortfolioBandConcentration(BaseModel):
    band_meaning: str
    customer_count: int = Field(ge=0)
    partial_exposure: float
    exposure_share_percent: float | None
    exposure_customer_count: int = Field(ge=0)


class PortfolioMonitoringSummary(BaseModel):
    assessed_customer_count: int = Field(ge=0)
    watchlist_customer_count: int = Field(ge=0)
    overdue_review_count: int = Field(ge=0)
    due_today_review_count: int = Field(ge=0)
    degraded_live_source_count: int = Field(ge=0)
    customers_with_proposals: int = Field(ge=0)
    customers_with_recorded_reviews: int = Field(ge=0)
    partial_exposure_customer_count: int = Field(ge=0)
    partial_exposure_total: float


class PortfolioMonitoringItem(BaseModel):
    rank: int = Field(ge=1)
    customer_number: int
    customer_name: str
    assessment_id: str
    watchlist: bool
    review_state: Literal["overdue", "due_today", "scheduled"]
    next_review_date: date
    days_to_review: int
    latest_manual_rating: int = Field(ge=1, le=10)
    band_meaning: str
    partial_exposure: float | None
    partial_exposure_share_percent: float | None
    latest_professional_proposal: CreditLineProposalRecord | None
    latest_portfolio_review: PortfolioReviewRecord | None
    alerts: list[PriorityAlert]
    ordering_reasons: list[str]


class PortfolioMonitoringGovernance(BaseModel):
    classification: Literal[
        "professional_work_management"
    ] = "professional_work_management"
    concentration_scope: Literal[
        "assessed_customers_with_available_partial_exposure"
    ] = "assessed_customers_with_available_partial_exposure"
    approved_portfolio_policy: Literal[False] = False
    automatic_decision: Literal[False] = False
    notification: Literal[False] = False
    erp_write: Literal[False] = False
    statements: list[str] = Field(default_factory=list)


class PortfolioMonitoringResponse(BaseModel):
    contract_version: str = PORTFOLIO_MONITORING_CONTRACT_VERSION
    generated_at: str
    as_of_date: date
    summary: PortfolioMonitoringSummary
    band_concentration: list[PortfolioBandConcentration]
    items: list[PortfolioMonitoringItem]
    governance: PortfolioMonitoringGovernance
    warnings: list[str] = Field(default_factory=list)


class OrderDecisionEvidence(BaseModel):
    contemplated_order_amount: float = Field(gt=0)
    current_credit_line: float
    current_partial_exposure: float
    projected_partial_exposure: float
    projected_partial_available_credit: float
    projected_partial_over_line_amount: float = Field(ge=0)
    projected_partial_utilization_percent: float | None
    order_source: Literal[
        "operator_entered_scenario_not_erp_order"
    ] = "operator_entered_scenario_not_erp_order"
    exposure_scope: Literal[
        "partial_customer_360_evidence"
    ] = "partial_customer_360_evidence"


class OrderDecisionGate(BaseModel):
    code: Literal[
        "current_customer_evidence",
        "current_manual_assessment",
        "erp_order_identity",
        "full_exposure",
        "approved_order_policy",
        "authenticated_decision_authority",
    ]
    status: Literal["available", "unavailable", "operator_entered"]
    explanation: str


class OrderDecisionGovernance(BaseModel):
    classification: Literal[
        "professional_decision_preparation"
    ] = "professional_decision_preparation"
    automatic_recommendation: Literal[False] = False
    automatic_decision: Literal[False] = False
    order_hold_effect: Literal["none"] = "none"
    order_release_effect: Literal["none"] = "none"
    approval_effect: Literal["none"] = "none"
    erp_write: Literal[False] = False
    actor_identity_source: Literal[
        "operator_supplied"
    ] = "operator_supplied"
    actor_authority_status: Literal[
        "not_independently_verified"
    ] = "not_independently_verified"
    statements: list[str] = Field(default_factory=list)


class OrderDecisionPreparationResponse(BaseModel):
    contract_version: str = ORDER_DECISION_PREPARATION_CONTRACT_VERSION
    generated_at: str
    source: SourceEvidence
    customer: CustomerIdentityEvidence
    order_reference: str | None
    evidence: OrderDecisionEvidence
    latest_manual_assessment: AssessmentRecord | None
    latest_professional_proposal: CreditLineProposalRecord | None
    latest_portfolio_review: PortfolioReviewRecord | None
    gates: list[OrderDecisionGate]
    professional_review_required: Literal[True] = True
    governance: OrderDecisionGovernance
    warnings: list[str] = Field(default_factory=list)


OrderRecommendationDisposition = Literal[
    "advance_to_authorized_review",
    "request_additional_information",
    "escalate_for_credit_authority",
    "do_not_advance",
]


class OrderRecommendationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contemplated_order_amount: float = Field(
        gt=0,
        le=1_000_000_000,
    )
    order_reference: str | None = Field(default=None, max_length=100)
    disposition: OrderRecommendationDisposition
    analyst_identity: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=5000)

    @field_validator("contemplated_order_amount")
    @classmethod
    def finite_order_amount(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("contemplated_order_amount must be finite.")
        return round(value, 2)

    @field_validator("order_reference")
    @classmethod
    def clean_order_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("analyst_identity", "rationale")
    @classmethod
    def require_order_recommendation_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must contain non-whitespace text.")
        return cleaned


class OrderRecommendationRecord(BaseModel):
    order_recommendation_id: str
    customer_number: int
    customer_name: str
    contemplated_order_amount: float
    order_reference: str | None
    disposition: OrderRecommendationDisposition
    analyst_identity: str
    rationale: str
    created_at: str
    source_as_of: str
    assessment_id: str | None
    proposal_id: str | None
    current_credit_line: float
    current_partial_exposure: float
    projected_partial_exposure: float
    projected_partial_available_credit: float
    projected_partial_over_line_amount: float = Field(ge=0)
    actor_identity_source: Literal[
        "operator_supplied"
    ] = "operator_supplied"
    actor_authority_status: Literal[
        "not_independently_verified"
    ] = "not_independently_verified"
    recommendation_classification: Literal[
        "professional_recommendation"
    ] = "professional_recommendation"
    decision_status: Literal[
        "not_submitted_to_governed_decision"
    ] = "not_submitted_to_governed_decision"
    decision_effect: Literal["none"] = "none"
    order_effect: Literal["none"] = "none"
    erp_write: Literal[False] = False
    evidence_snapshot: dict[str, Any]
    evidence_snapshot_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class OrderRecommendationHistoryResponse(BaseModel):
    customer_number: int
    count: int = Field(ge=0)
    recommendations: list[OrderRecommendationRecord]
    governance: OrderDecisionGovernance
