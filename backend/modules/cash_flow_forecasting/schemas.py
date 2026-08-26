from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


CONTRACT_VERSION = "cash-flow-forecasting.v1"

HORIZON_WEEKS = 14


class SourceEvidence(BaseModel):
    system: str = (
        "MaddenCo ERP (DTA273) + K&M Banking "
        "(Consolidated Daily Bank Balances.xlsx)"
    )
    access: Literal["read_only"] = "read_only"
    status: Literal["available", "unavailable_source_capability"] = "available"
    retrieved_at: str


class StartingCashPosition(BaseModel):
    business_day: str | None
    net_available: float | None
    line_of_credit_balance: float | None
    line_of_credit_available: float | None
    line_of_credit_withholding: float | None
    status: Literal["available", "unavailable_source_capability"] = "available"
    source: str = (
        r"F:\Accounting\Shared\Banking\Consolidated Daily Bank Balances.xlsx "
        "(Sheet1), last business-day row on or before the as-of date"
    )
    explanation: str = (
        "Net Available is the bank file's own computed figure (bank "
        "balances minus outstanding checks). It is not netted against the "
        "Line of Credit balance; both are reported exactly as recorded."
    )


class WeeklyProjection(BaseModel):
    week_index: int
    week_start: str
    week_end: str
    projected_ar: float
    projected_ap: float | None
    projected_ap_on_hold: float | None
    projected_other: float
    projected_net_change: float | None
    projected_ending_balance: float | None


class PriorYearWeekComparison(BaseModel):
    week_index: int
    week_start: str
    week_end: str
    prior_year_week_start: str
    prior_year_week_end: str

    prior_year_projected_ar: float
    prior_year_projected_ap: float | None
    prior_year_projected_other: float
    prior_year_projected_ending_balance: float | None

    prior_year_actual_ar: float | None
    prior_year_actual_ap: float | None
    prior_year_actual_other: float | None
    prior_year_actual_ending_balance: float | None

    prior_year_variance_ar: float | None
    prior_year_variance_ap: float | None
    prior_year_variance_other: float | None
    prior_year_variance_ending_balance: float | None

    current_year_week_closed: bool
    current_year_actual_ar: float | None = None
    current_year_actual_ap: float | None = None
    current_year_actual_other: float | None = None
    current_year_actual_ending_balance: float | None = None
    current_year_variance_ar: float | None = None
    current_year_variance_ap: float | None = None
    current_year_variance_other: float | None = None
    current_year_variance_ending_balance: float | None = None


class CashFlowForecastGap(BaseModel):
    code: Literal[
        "due_date_baseline_only",
        "other_bucket_pattern_detection",
        "variance_is_category_not_narrative",
        "no_automatic_recalibration",
        "victory_bank_excluded",
        "ap_hold_timing_unknown",
        "bank_file_unavailable",
        "prior_year_ap_projection_unavailable",
        "ap_cache_not_refreshed",
    ]
    label: str
    status: Literal["unavailable"] = "unavailable"
    explanation: str


class CashFlowForecastGovernance(BaseModel):
    assessment_type: Literal["evidence_only"] = "evidence_only"
    automatic_score: bool = False
    decision_effect: Literal["none"] = "none"
    erp_write: bool = False


class CashFlowForecastResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    generated_at: str
    as_of: str
    horizon_weeks: int = HORIZON_WEEKS
    source: SourceEvidence
    starting_position: StartingCashPosition
    weeks: list[WeeklyProjection]
    prior_year_comparison: list[PriorYearWeekComparison]
    gaps: list[CashFlowForecastGap]
    governance: CashFlowForecastGovernance = Field(
        default_factory=CashFlowForecastGovernance
    )


class CashFlowSnapshotSummary(BaseModel):
    snapshot_id: str
    as_of: str
    generated_at: str
    horizon_weeks: int


class CashFlowSnapshotHistoryResponse(BaseModel):
    count: int
    snapshots: list[CashFlowSnapshotSummary]


class CashFlowAccuracyWeek(BaseModel):
    week_start: str
    week_end: str
    projected_ar: float
    projected_ap: float
    projected_other: float
    projected_ending_balance: float | None
    actual_ar: float
    actual_ap: float
    actual_other: float
    actual_ending_balance: float | None
    variance_ar: float
    variance_ap: float
    variance_other: float
    variance_ending_balance: float | None
    recorded_at: str


class CashFlowAccuracyHistoryResponse(BaseModel):
    count: int
    weeks: list[CashFlowAccuracyWeek]
    explanation: str = (
        "Each row compares what this module projected for a week (using "
        "the due-date baseline and the other-bucket pattern detector) "
        "against what actually posted to the tracked cash accounts that "
        "week, once the week closed. This is an accuracy record for a "
        "human to review - nothing here is fed back into future "
        "projections automatically."
    )
