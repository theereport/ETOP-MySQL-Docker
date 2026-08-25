from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)


CONTRACT_VERSION = "financial-close-readiness.v1"
PLANNING_CONTRACT_VERSION = "financial-close-planning.v1"

CloseControlState = Literal[
    "not_started",
    "awaiting_review",
    "attention_required",
    "evidence_sufficient",
    "stale",
]
CloseEvidenceStatus = Literal[
    "not_recorded",
    "reference_recorded",
    "missing",
    "unavailable",
]
ClosePreparationDisposition = Literal[
    "reference_recorded",
    "missing",
    "unavailable",
]
CloseReviewDisposition = Literal[
    "evidence_sufficient",
    "needs_information",
    "not_ready",
    "deferred",
]
CloseReviewCurrency = Literal["not_reviewed", "current", "stale"]
CloseCycleReadiness = Literal[
    "not_started",
    "in_progress",
    "attention_required",
    "evidence_ready",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CloseIdentity(StrictModel):
    person_id: str
    user_id: str
    username: str
    display_name: str
    status: Literal["active", "inactive"]


class FinancialCloseAuthorityBoundary(StrictModel):
    identity_source: Literal[
        "workflow_foundation_local_account"
    ] = "workflow_foundation_local_account"
    authority_effect: Literal["none"] = "none"
    close_effect: Literal["none"] = "none"
    approval_effect: Literal["none"] = "none"
    posting_effect: Literal["none"] = "none"
    erp_write: Literal[False] = False
    statements: list[str] = Field(default_factory=list)


class FinancialCloseSourceCoverage(StrictModel):
    key: str
    label: str
    status: str
    explanation: str


class FinancialCloseDeferredCapability(StrictModel):
    key: str
    label: str
    reason: str


class FinancialCloseGovernance(StrictModel):
    contract_version: Literal[
        "financial-close-readiness.v1"
    ] = CONTRACT_VERSION
    capability_status: Literal[
        "local_evidence_readiness"
    ] = "local_evidence_readiness"
    erp_period_state: Literal["unavailable"] = "unavailable"
    books_close_state: Literal["unavailable"] = "unavailable"
    planning_contract_version: Literal[
        "financial-close-planning.v1"
    ] = PLANNING_CONTRACT_VERSION
    template_authority: Literal[
        "local_user_authored_planning_draft"
    ] = "local_user_authored_planning_draft"
    calendar_effect: Literal["planning_dates_only"] = "planning_dates_only"
    source_coverage: list[FinancialCloseSourceCoverage]
    authority: FinancialCloseAuthorityBoundary
    deferred_capabilities: list[FinancialCloseDeferredCapability]


class CloseControlCounts(StrictModel):
    total: int = Field(ge=0)
    not_started: int = Field(ge=0)
    awaiting_review: int = Field(ge=0)
    attention_required: int = Field(ge=0)
    evidence_sufficient: int = Field(ge=0)
    stale: int = Field(ge=0)


class CloseCycleCreate(StrictModel):
    entity_label: str = Field(min_length=1, max_length=160)
    period_label: str = Field(min_length=1, max_length=120)
    period_start: date
    period_end: date
    target_completion_date: date | None = None
    description: str = Field(default="", max_length=5_000)
    idempotency_key: str = Field(min_length=8, max_length=120)

    @model_validator(mode="after")
    def validate_period(self) -> "CloseCycleCreate":
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        if (self.period_end - self.period_start).days > 370:
            raise ValueError("A local close cycle cannot span more than 370 days.")
        return self


class CloseControlCreate(StrictModel):
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=5_000)
    planned_date: date | None = None
    preparer_user_id: str = Field(min_length=5, max_length=80)
    reviewer_user_id: str = Field(min_length=5, max_length=80)
    idempotency_key: str = Field(min_length=8, max_length=120)


class CloseTemplateItemCreate(StrictModel):
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=5_000)
    planned_offset_days: StrictInt = Field(ge=-3_660, le=3_660)
    preparer_user_id: str = Field(min_length=5, max_length=80)
    reviewer_user_id: str = Field(min_length=5, max_length=80)

    @model_validator(mode="after")
    def validate_separation(self) -> "CloseTemplateItemCreate":
        if self.preparer_user_id == self.reviewer_user_id:
            raise ValueError(
                "Template-item preparer and reviewer must be distinct local users."
            )
        return self


class CloseTemplateCreate(StrictModel):
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=5_000)
    items: list[CloseTemplateItemCreate] = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=8, max_length=120)


class CloseTemplateVersionCreate(StrictModel):
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=5_000)
    change_note: str = Field(min_length=3, max_length=2_000)
    items: list[CloseTemplateItemCreate] = Field(min_length=1, max_length=100)
    expected_latest_version: StrictInt = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=120)


class CloseTemplateInstantiate(StrictModel):
    entity_label: str = Field(min_length=1, max_length=160)
    period_label: str = Field(min_length=1, max_length=120)
    period_start: date
    period_end: date
    calendar_anchor_date: date
    target_completion_date: date | None = None
    description: str = Field(default="", max_length=5_000)
    idempotency_key: str = Field(min_length=8, max_length=120)

    @model_validator(mode="after")
    def validate_period(self) -> "CloseTemplateInstantiate":
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        if (self.period_end - self.period_start).days > 370:
            raise ValueError("A local close cycle cannot span more than 370 days.")
        return self


class ClosePreparationCreate(StrictModel):
    disposition: ClosePreparationDisposition
    evidence_reference: str | None = Field(default=None, max_length=2_000)
    note: str = Field(min_length=1, max_length=5_000)
    expected_control_version: StrictInt = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=120)

    @field_validator("evidence_reference")
    @classmethod
    def normalize_evidence_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_evidence_reference(self) -> "ClosePreparationCreate":
        if self.disposition == "reference_recorded" and not self.evidence_reference:
            raise ValueError(
                "evidence_reference is required when disposition is reference_recorded"
            )
        return self


class CloseReviewCreate(StrictModel):
    disposition: CloseReviewDisposition
    note: str = Field(min_length=1, max_length=5_000)
    expected_control_version: StrictInt = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=120)


class CloseEvent(StrictModel):
    event_id: str
    cycle_id: str
    control_id: str | None
    event_type: str
    actor: CloseIdentity
    occurred_at: datetime
    details: dict[str, object]
    previous_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    record_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    authority_effect: Literal["none"] = "none"
    close_effect: Literal["none"] = "none"


class CloseTemplateItem(StrictModel):
    item_id: str
    template_id: str
    template_version: int = Field(ge=1)
    ordinal: int = Field(ge=1)
    title: str
    description: str
    planned_offset_days: int
    preparer: CloseIdentity
    reviewer: CloseIdentity
    item_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class CloseTemplateVersion(StrictModel):
    template_id: str
    version: int = Field(ge=1)
    title: str
    description: str
    change_note: str
    status: Literal[
        "local_user_authored_planning_draft"
    ] = "local_user_authored_planning_draft"
    created_by: CloseIdentity
    created_at: datetime
    previous_version_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    version_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    items: list[CloseTemplateItem]
    policy_effect: Literal["none"] = "none"
    automation_effect: Literal["none"] = "none"


class CloseTemplateEvent(StrictModel):
    event_id: str
    template_id: str
    event_type: Literal[
        "template_created",
        "template_version_created",
        "cycle_instantiated",
    ]
    actor: CloseIdentity
    occurred_at: datetime
    details: dict[str, object]
    sequence: int = Field(ge=1)
    previous_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    record_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    authority_effect: Literal["none"] = "none"
    policy_effect: Literal["none"] = "none"
    automation_effect: Literal["none"] = "none"


class CloseTemplateEventIntegrity(StrictModel):
    valid: bool
    checked_records: int = Field(ge=0)
    first_invalid_event_id: str | None
    algorithm: Literal["sha256_hash_chain"] = "sha256_hash_chain"


class CloseTemplateSummary(StrictModel):
    template_id: str
    title: str
    description: str
    latest_version: int = Field(ge=1)
    version_count: int = Field(ge=1)
    item_count: int = Field(ge=1)
    latest_version_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    status: Literal[
        "local_user_authored_planning_draft"
    ] = "local_user_authored_planning_draft"
    created_by: CloseIdentity
    created_at: datetime
    policy_effect: Literal["none"] = "none"
    automation_effect: Literal["none"] = "none"


class CloseTemplateDetail(CloseTemplateSummary):
    versions: list[CloseTemplateVersion]
    events: list[CloseTemplateEvent]
    integrity: CloseTemplateEventIntegrity


class CloseTemplateListResponse(StrictModel):
    contract_version: Literal[
        "financial-close-planning.v1"
    ] = PLANNING_CONTRACT_VERSION
    items: list[CloseTemplateSummary]
    total: int = Field(ge=0)
    template_authority: Literal[
        "local_user_authored_planning_draft"
    ] = "local_user_authored_planning_draft"
    policy_effect: Literal["none"] = "none"
    automation_effect: Literal["none"] = "none"


class CloseCycleTemplateLineage(StrictModel):
    snapshot_id: str
    template_id: str
    template_version: int = Field(ge=1)
    template_title: str
    template_version_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    calendar_anchor_date: date
    planning_date_rule: Literal[
        "calendar_anchor_plus_offset_days"
    ] = "calendar_anchor_plus_offset_days"
    instantiated_by: CloseIdentity
    instantiated_at: datetime
    snapshot_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    policy_effect: Literal["none"] = "none"
    automation_effect: Literal["none"] = "none"


class CloseControlTemplateLineage(StrictModel):
    snapshot_id: str
    template_id: str
    template_version: int = Field(ge=1)
    template_item_id: str
    template_item_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    planned_offset_days: int
    planning_date_rule: Literal[
        "calendar_anchor_plus_offset_days"
    ] = "calendar_anchor_plus_offset_days"


class CloseControlSummary(StrictModel):
    control_id: str
    cycle_id: str
    title: str
    description: str
    planned_date: date | None
    preparer: CloseIdentity
    reviewer: CloseIdentity
    state: CloseControlState
    evidence_status: CloseEvidenceStatus
    review_currency: CloseReviewCurrency
    version: int = Field(ge=1)
    latest_preparation_at: datetime | None
    latest_review_at: datetime | None
    created_by: CloseIdentity
    created_at: datetime
    updated_at: datetime
    authority_effect: Literal["none"] = "none"
    close_effect: Literal["none"] = "none"
    template_lineage: CloseControlTemplateLineage | None = None


class CloseCycleSummary(StrictModel):
    cycle_id: str
    entity_label: str
    period_label: str
    period_start: date
    period_end: date
    target_completion_date: date | None
    description: str
    created_by: CloseIdentity
    created_at: datetime
    version: int = Field(ge=1)
    control_counts: CloseControlCounts
    readiness: CloseCycleReadiness
    readiness_scope: Literal[
        "local_evidence_readiness_only"
    ] = "local_evidence_readiness_only"
    erp_period_state: Literal["unavailable"] = "unavailable"
    close_effect: Literal["none"] = "none"
    template_lineage: CloseCycleTemplateLineage | None = None


class CloseCycleDetail(CloseCycleSummary):
    controls: list[CloseControlSummary]
    events: list[CloseEvent]
    evidence_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class CloseEventIntegrity(StrictModel):
    valid: bool
    checked_records: int = Field(ge=0)
    first_invalid_event_id: str | None
    algorithm: Literal["sha256_hash_chain"] = "sha256_hash_chain"


class CloseControlEventList(StrictModel):
    items: list[CloseEvent]
    integrity: CloseEventIntegrity


class CloseCycleListResponse(StrictModel):
    contract_version: Literal[
        "financial-close-readiness.v1"
    ] = CONTRACT_VERSION
    items: list[CloseCycleSummary]
    total: int = Field(ge=0)
    governance: FinancialCloseGovernance


__all__ = [
    "CONTRACT_VERSION",
    "PLANNING_CONTRACT_VERSION",
    "CloseControlCreate",
    "CloseControlEventList",
    "CloseControlState",
    "CloseControlSummary",
    "CloseCycleCreate",
    "CloseCycleDetail",
    "CloseCycleListResponse",
    "CloseCycleReadiness",
    "CloseCycleTemplateLineage",
    "CloseEvent",
    "CloseEventIntegrity",
    "CloseEvidenceStatus",
    "CloseIdentity",
    "ClosePreparationCreate",
    "CloseReviewCreate",
    "CloseControlTemplateLineage",
    "CloseTemplateCreate",
    "CloseTemplateDetail",
    "CloseTemplateEvent",
    "CloseTemplateEventIntegrity",
    "CloseTemplateInstantiate",
    "CloseTemplateItem",
    "CloseTemplateItemCreate",
    "CloseTemplateListResponse",
    "CloseTemplateSummary",
    "CloseTemplateVersion",
    "CloseTemplateVersionCreate",
    "FinancialCloseGovernance",
]
