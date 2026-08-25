from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
import math
from typing import Any
from uuid import uuid4

from .repository import CreditRiskRepository, credit_risk_repository
from .schemas import (
    AgingEvidence,
    AssessmentCreate,
    AssessmentHistoryResponse,
    AssessmentRecord,
    CreditEvidence,
    CreditLineAnalyticalReference,
    CreditLineCapacityEvidence,
    CreditLineGap,
    CreditLineGovernance,
    CreditLineIntelligenceResponse,
    CreditLineMetric,
    CreditLineProposalCreate,
    CreditLineProposalHistoryResponse,
    CreditLineProposalRecord,
    CreditLineSalesEvidence,
    CreditRiskGovernance,
    CustomerIdentityEvidence,
    CustomerRiskResponse,
    ExposureComponent,
    ExposureEvidence,
    PaymentEvidence,
    OrderDecisionEvidence,
    OrderDecisionGate,
    OrderDecisionGovernance,
    OrderDecisionPreparationResponse,
    OrderRecommendationCreate,
    OrderRecommendationHistoryResponse,
    OrderRecommendationRecord,
    PortfolioBandConcentration,
    PortfolioMonitoringGovernance,
    PortfolioMonitoringItem,
    PortfolioMonitoringResponse,
    PortfolioMonitoringSummary,
    PortfolioReviewCreate,
    PortfolioReviewHistoryResponse,
    PortfolioReviewRecord,
    PriorityAlert,
    PriorityAlertsResponse,
    PriorityAssessmentReference,
    PriorityLiveExposureEvidence,
    PriorityOrderingEvidence,
    PriorityOrderingGovernance,
    PriorityPortfolioItem,
    PriorityPortfolioSummary,
    RiskBand,
    RiskBandSet,
    RiskBandSetResponse,
    SourceEvidence,
    UnavailablePriorityCapability,
    UnavailablePaymentMetric,
)


FULL_EXPOSURE_FORMULA = (
    "open A/R + unbilled shipments + releasable orders - unapplied cash "
    "- valid credits - secured amounts"
)
PARTIAL_EXPOSURE_FORMULA = (
    "open A/R + max(ERP on-order aggregate, 0)"
)
CREDIT_LINE_REFERENCE_FORMULA = (
    "round_to_nearest_500((annualized_sales / 12) * 2)"
)

PRIORITY_ORDERED_CONDITIONS = [
    "review state: overdue, due today, then scheduled",
    "higher latest manual rating",
    "manual-rating deterioration from the prior assessment",
    "current partial exposure over the credit line when live evidence is available",
    "earlier next-review date",
    "lower customer number as the final stable tie-break",
]

DRAFT_BAND_ATTENTION_MEANINGS = {
    "High risk",
    "Very high risk",
    "Default likely",
    "Default or legal",
}


class CreditRiskCustomerNotFound(LookupError):
    """Raised when Customer 360 has no matching ERP customer."""


class CreditRiskSourceUnavailable(RuntimeError):
    """Raised when live Customer 360 facts cannot be retrieved."""


class CreditRiskSourceIntegrityError(RuntimeError):
    """Raised when Customer 360 returns evidence for another customer."""


def _required_number(
    section: dict[str, Any],
    key: str,
    label: str,
) -> float:
    if key not in section:
        raise CreditRiskSourceIntegrityError(
            f"Customer 360 omitted required numeric fact: {label}."
        )

    raw_value = section[key]
    if raw_value is None or raw_value == "" or isinstance(raw_value, bool):
        raise CreditRiskSourceIntegrityError(
            f"Customer 360 returned no valid numeric fact for {label}."
        )

    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise CreditRiskSourceIntegrityError(
            f"Customer 360 returned no valid numeric fact for {label}."
        ) from exc

    if not math.isfinite(value):
        raise CreditRiskSourceIntegrityError(
            f"Customer 360 returned a non-finite numeric fact for {label}."
        )
    return round(value, 2)


def _source_section(
    summary: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    value = summary.get(key)
    if not isinstance(value, dict):
        raise CreditRiskSourceIntegrityError(
            f"Customer 360 returned no valid {key} evidence object."
        )
    return value


def _payment_amount(activity: dict[str, Any]) -> tuple[float | None, str]:
    if "last_payment_amount" not in activity:
        return None, "missing"

    raw_value = activity["last_payment_amount"]
    if raw_value is None or raw_value == "":
        return None, "missing"
    if isinstance(raw_value, bool):
        return None, "invalid"

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None, "invalid"
    if not math.isfinite(value):
        return None, "invalid"
    return round(value, 2), "valid"


def _payment_date(activity: dict[str, Any]) -> tuple[str | None, str]:
    if "last_payment_date" not in activity:
        return None, "missing"

    raw_value = activity["last_payment_date"]
    if raw_value is None or raw_value == "":
        return None, "missing"
    if not isinstance(raw_value, str):
        return str(raw_value), "invalid"

    value = raw_value.strip()
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return value, "invalid"
    if parsed.isoformat() != value:
        return value, "invalid"
    return value, "valid"


def _now() -> datetime:
    return datetime.now(UTC)


def _unavailable_metric(name: str) -> UnavailablePaymentMetric:
    return UnavailablePaymentMetric(
        explanation=(
            f"{name} is unavailable until a governed payment-history "
            "source is connected."
        )
    )


def _optional_credit_line_metric(
    section: dict[str, Any],
    key: str,
    *,
    label: str,
    source: str,
    as_of: str,
) -> CreditLineMetric:
    if key not in section or section[key] is None or section[key] == "":
        return CreditLineMetric(
            value=None,
            status="unavailable",
            source=None,
            as_of=None,
            explanation=f"{label} is absent from the current source contract.",
        )
    raw_value = section[key]
    if isinstance(raw_value, bool):
        return CreditLineMetric(
            value=None,
            status="invalid",
            source=source,
            as_of=as_of,
            explanation=f"{label} is present but is not valid numeric evidence.",
        )
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return CreditLineMetric(
            value=None,
            status="invalid",
            source=source,
            as_of=as_of,
            explanation=f"{label} is present but is not valid numeric evidence.",
        )
    if not math.isfinite(value):
        return CreditLineMetric(
            value=None,
            status="invalid",
            source=source,
            as_of=as_of,
            explanation=f"{label} is present but is not finite numeric evidence.",
        )
    return CreditLineMetric(
        value=round(value, 2),
        status="available",
        source=source,
        as_of=as_of,
        explanation=f"{label} is available from the current read-only Customer 360 response.",
    )


class CreditRiskService:
    """Build source-grounded manual Credit Risk assessment evidence."""

    def __init__(
        self,
        *,
        repository: CreditRiskRepository = credit_risk_repository,
        customer_summary_service: Any | None = None,
        clock: Callable[[], datetime] = _now,
        id_factory: Callable[[], str] | None = None,
        proposal_id_factory: Callable[[], str] | None = None,
        portfolio_review_id_factory: Callable[[], str] | None = None,
        order_recommendation_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._customer_summary_service = customer_summary_service
        self._clock = clock
        self._id_factory = id_factory or (
            lambda: f"cr-assessment-{uuid4().hex}"
        )
        self._proposal_id_factory = proposal_id_factory or (
            lambda: f"cr-line-proposal-{uuid4().hex}"
        )
        self._portfolio_review_id_factory = (
            portfolio_review_id_factory
            or (lambda: f"cr-portfolio-review-{uuid4().hex}")
        )
        self._order_recommendation_id_factory = (
            order_recommendation_id_factory
            or (lambda: f"cr-order-recommendation-{uuid4().hex}")
        )

    def _customer_service(self) -> Any:
        if self._customer_summary_service is None:
            # Resolve the shared Customer 360 singleton only when live facts
            # are requested. This avoids creating a second ERP repository and
            # keeps local history/band reads independent of ERP availability.
            from modules.customer_360.service import customer_service

            self._customer_summary_service = customer_service
        return self._customer_summary_service

    def list_bands(self) -> RiskBandSetResponse:
        stored = self._repository.get_current_band_set()
        return RiskBandSetResponse(
            band_set=RiskBandSet(**stored["band_set"]),
            bands=[RiskBand(**band) for band in stored["bands"]],
        )

    def get_customer_risk(
        self,
        customer_number: int,
    ) -> CustomerRiskResponse:
        snapshot = self._load_live_snapshot(customer_number)
        latest = self._repository.get_latest_assessment(customer_number)
        snapshot["latest_assessment"] = (
            AssessmentRecord(**latest) if latest is not None else None
        )
        return CustomerRiskResponse(**snapshot)

    def list_assessments(
        self,
        customer_number: int,
    ) -> AssessmentHistoryResponse:
        records = [
            AssessmentRecord(**record)
            for record in self._repository.list_assessments(
                customer_number
            )
        ]
        return AssessmentHistoryResponse(
            customer_number=customer_number,
            count=len(records),
            assessments=records,
        )

    def get_priority_alerts(self) -> PriorityAlertsResponse:
        """Project assessed-customer work in a deterministic review order.

        This is a transient operational projection over immutable manual
        assessments plus best-effort live Customer 360 evidence. It creates no
        score, Recommendation, Decision, notification, or source-system write.
        """

        generated_at = self._clock().astimezone(UTC)
        as_of_date = generated_at.date()
        stored_records = self._repository.list_latest_assessments_by_customer(
            limit_per_customer=2
        )
        records_by_customer: dict[int, list[AssessmentRecord]] = {}
        for stored_record in stored_records:
            assessment = AssessmentRecord(**stored_record)
            records_by_customer.setdefault(
                assessment.customer_number,
                [],
            ).append(assessment)

        ranked_candidates: list[
            tuple[tuple[int, int, int, int, date, int], PriorityPortfolioItem]
        ] = []
        for customer_number, history in records_by_customer.items():
            latest = history[0]
            previous = history[1] if len(history) > 1 else None
            next_review_date = latest.next_review_date

            if next_review_date < as_of_date:
                review_state = "overdue"
                review_category = "review_overdue"
                review_order = 0
            elif next_review_date == as_of_date:
                review_state = "due_today"
                review_category = "review_due_today"
                review_order = 1
            else:
                review_state = "scheduled"
                review_category = "scheduled_review"
                review_order = 2

            manual_rating_change = (
                latest.manual_rating - previous.manual_rating
                if previous is not None
                else None
            )
            draft_band_attention = self._is_draft_band_attention(latest)
            if previous is None:
                deterioration_state = "insufficient_history"
            elif manual_rating_change is not None and manual_rating_change > 0:
                deterioration_state = "deteriorated"
            else:
                deterioration_state = "not_deteriorated"

            live_exposure, live_customer_name = self._priority_live_exposure(
                customer_number
            )
            if live_exposure.is_over_line is True:
                over_line_state = "over_line"
            elif live_exposure.is_over_line is False:
                over_line_state = "not_over_line"
            else:
                over_line_state = "unavailable"

            latest_reference = self._priority_assessment_reference(latest)
            previous_reference = (
                self._priority_assessment_reference(previous)
                if previous is not None
                else None
            )
            alerts = self._priority_alerts_for_customer(
                as_of_date=as_of_date,
                latest=latest,
                previous=previous,
                review_state=review_state,
                manual_rating_change=manual_rating_change,
                draft_band_attention=draft_band_attention,
                live_exposure=live_exposure,
            )
            ordering_reasons = self._priority_ordering_reasons(
                as_of_date=as_of_date,
                latest=latest,
                previous=previous,
                review_state=review_state,
                manual_rating_change=manual_rating_change,
                live_exposure=live_exposure,
            )

            item = PriorityPortfolioItem(
                rank=1,
                priority_category=review_category,
                customer_number=customer_number,
                customer_name=(
                    live_customer_name or latest.customer_name
                ),
                customer_name_source=(
                    "live_customer_360"
                    if live_customer_name
                    else "saved_assessment"
                ),
                latest_assessment=latest_reference,
                previous_assessment=previous_reference,
                draft_band_attention=draft_band_attention,
                ordering_evidence=PriorityOrderingEvidence(
                    review_state=review_state,
                    latest_manual_rating=latest.manual_rating,
                    deterioration_state=deterioration_state,
                    manual_rating_change=manual_rating_change,
                    over_line_state=over_line_state,
                    next_review_date=next_review_date,
                ),
                live_exposure=live_exposure,
                alerts=alerts,
                ordering_reasons=ordering_reasons,
            )
            sort_key = (
                review_order,
                -latest.manual_rating,
                -(1 if deterioration_state == "deteriorated" else 0),
                -(1 if over_line_state == "over_line" else 0),
                next_review_date,
                customer_number,
            )
            ranked_candidates.append((sort_key, item))

        ranked_candidates.sort(key=lambda candidate: candidate[0])
        items = [
            item.model_copy(update={"rank": position})
            for position, (_, item) in enumerate(
                ranked_candidates,
                start=1,
            )
        ]

        return PriorityAlertsResponse(
            generated_at=generated_at.isoformat(),
            as_of_date=as_of_date,
            coverage_statement=(
                f"{len(items)} customer"
                f"{'s' if len(items) != 1 else ''} with saved manual Credit "
                "Risk assessments are included. Customers without a saved "
                "manual assessment are excluded and were not evaluated."
            ),
            summary=PriorityPortfolioSummary(
                assessed_customer_count=len(items),
                operational_alert_count=sum(
                    1
                    for item in items
                    for alert in item.alerts
                    if alert.category != "source_gap"
                ),
                overdue_review_count=sum(
                    item.ordering_evidence.review_state == "overdue"
                    for item in items
                ),
                due_today_review_count=sum(
                    item.ordering_evidence.review_state == "due_today"
                    for item in items
                ),
                deterioration_count=sum(
                    item.ordering_evidence.deterioration_state
                    == "deteriorated"
                    for item in items
                ),
                draft_band_attention_count=sum(
                    item.draft_band_attention for item in items
                ),
                over_line_count=sum(
                    item.ordering_evidence.over_line_state == "over_line"
                    for item in items
                ),
                live_source_degraded_count=sum(
                    item.live_exposure.status != "available"
                    for item in items
                ),
            ),
            ordering=PriorityOrderingGovernance(
                ordered_conditions=PRIORITY_ORDERED_CONDITIONS,
                unavailable_over_line_treatment=(
                    "Unavailable live exposure is never treated as zero or as "
                    "an observed over-line condition. The source gap remains "
                    "visible and ordering proceeds to the next stable condition."
                ),
                explanation=(
                    "This queue is deterministic operational ordering for "
                    "professional review. It is not an automatic credit risk "
                    "score, recommendation, approval, or decision."
                ),
            ),
            unavailable_capabilities=[
                UnavailablePriorityCapability(
                    code="broken_promise_alerts",
                    label="Broken-promise alerts",
                    explanation=(
                        "No governed promise-to-pay source is connected, so "
                        "ETOP does not emit or infer broken-promise alerts."
                    ),
                ),
                UnavailablePriorityCapability(
                    code="nsf_alerts",
                    label="NSF alerts",
                    explanation=(
                        "No governed returned-payment or NSF source is "
                        "connected, so ETOP does not emit or infer NSF alerts."
                    ),
                ),
            ],
            items=items,
        )

    def _priority_live_exposure(
        self,
        customer_number: int,
    ) -> tuple[PriorityLiveExposureEvidence, str | None]:
        try:
            snapshot = CustomerRiskResponse(
                **self._load_live_snapshot(customer_number)
            )
        except CreditRiskSourceUnavailable:
            return (
                PriorityLiveExposureEvidence(
                    status="source_unavailable",
                    source="MaddenCo ERP through shared Customer 360",
                    retrieved_at=None,
                    exposure_completeness=None,
                    credit_line=None,
                    partial_exposure=None,
                    partial_available_credit=None,
                    amount_over_limit=None,
                    is_over_line=None,
                    explanation=(
                        "Live Customer 360 facts are unavailable. Assessment-"
                        "derived and review-date signals remain available; no "
                        "current over-line condition is inferred."
                    ),
                ),
                None,
            )
        except CreditRiskCustomerNotFound:
            return (
                PriorityLiveExposureEvidence(
                    status="customer_not_found",
                    source="MaddenCo ERP through shared Customer 360",
                    retrieved_at=None,
                    exposure_completeness=None,
                    credit_line=None,
                    partial_exposure=None,
                    partial_available_credit=None,
                    amount_over_limit=None,
                    is_over_line=None,
                    explanation=(
                        "The assessed customer was not found in the current "
                        "Customer 360 source. Saved assessment evidence is "
                        "retained; no current over-line condition is inferred."
                    ),
                ),
                None,
            )
        except CreditRiskSourceIntegrityError:
            return (
                PriorityLiveExposureEvidence(
                    status="source_integrity_error",
                    source="MaddenCo ERP through shared Customer 360",
                    retrieved_at=None,
                    exposure_completeness=None,
                    credit_line=None,
                    partial_exposure=None,
                    partial_available_credit=None,
                    amount_over_limit=None,
                    is_over_line=None,
                    explanation=(
                        "Live Customer 360 evidence failed customer or numeric "
                        "integrity checks. Saved assessment evidence is retained; "
                        "no current over-line condition is inferred."
                    ),
                ),
                None,
            )

        return (
            PriorityLiveExposureEvidence(
                status="available",
                source=snapshot.source.system,
                retrieved_at=snapshot.source.retrieved_at,
                exposure_completeness=snapshot.exposure.completeness,
                credit_line=snapshot.credit.credit_line,
                partial_exposure=snapshot.exposure.partial_exposure,
                partial_available_credit=(
                    snapshot.exposure.partial_available_credit
                ),
                amount_over_limit=snapshot.credit.amount_over_limit,
                is_over_line=snapshot.credit.amount_over_limit > 0,
                explanation=(
                    "Current over-line evidence uses the live partial exposure "
                    "reference. Full exposure remains unavailable and no credit "
                    "action is implied."
                ),
            ),
            snapshot.customer.customer_name,
        )

    @staticmethod
    def _priority_assessment_reference(
        assessment: AssessmentRecord,
    ) -> PriorityAssessmentReference:
        return PriorityAssessmentReference(
            assessment_id=assessment.assessment_id,
            customer_number=assessment.customer_number,
            customer_name=assessment.customer_name,
            manual_rating=assessment.manual_rating,
            band=assessment.band,
            review_date=assessment.review_date,
            next_review_date=assessment.next_review_date,
            created_at=assessment.created_at,
            source_as_of=assessment.source_as_of,
            evidence_snapshot_sha256=(
                assessment.evidence_snapshot_sha256
            ),
        )

    @staticmethod
    def _is_draft_band_attention(
        assessment: AssessmentRecord,
    ) -> bool:
        return (
            assessment.band_set_status == "product_owner_supplied_draft"
            and assessment.band.meaning in DRAFT_BAND_ATTENTION_MEANINGS
            and 7 <= assessment.manual_rating <= 10
        )

    @staticmethod
    def _priority_alerts_for_customer(
        *,
        as_of_date: date,
        latest: AssessmentRecord,
        previous: AssessmentRecord | None,
        review_state: str,
        manual_rating_change: int | None,
        draft_band_attention: bool,
        live_exposure: PriorityLiveExposureEvidence,
    ) -> list[PriorityAlert]:
        latest_ids = [latest.assessment_id]
        latest_hashes = [latest.evidence_snapshot_sha256]
        alerts: list[PriorityAlert] = []

        if review_state == "overdue":
            days_overdue = (as_of_date - latest.next_review_date).days
            alerts.append(
                PriorityAlert(
                    code="review_overdue",
                    category="review_schedule",
                    evidence_class="professional_judgment",
                    title="Review overdue",
                    explanation=(
                        f"The latest manual assessment scheduled the next "
                        f"review for {latest.next_review_date.isoformat()}, "
                        f"which is {days_overdue} day"
                        f"{'s' if days_overdue != 1 else ''} before the "
                        f"portfolio as-of date {as_of_date.isoformat()}."
                    ),
                    assessment_ids=latest_ids,
                    evidence_sha256=latest_hashes,
                    source_as_of=latest.source_as_of,
                )
            )
        elif review_state == "due_today":
            alerts.append(
                PriorityAlert(
                    code="review_due_today",
                    category="review_schedule",
                    evidence_class="professional_judgment",
                    title="Review due today",
                    explanation=(
                        "The latest manual assessment's next-review date "
                        f"equals the portfolio as-of date {as_of_date.isoformat()}."
                    ),
                    assessment_ids=latest_ids,
                    evidence_sha256=latest_hashes,
                    source_as_of=latest.source_as_of,
                )
            )

        if (
            previous is not None
            and manual_rating_change is not None
            and manual_rating_change > 0
        ):
            alerts.append(
                PriorityAlert(
                    code="manual_rating_deteriorated",
                    category="assessment_change",
                    evidence_class="deterministic_comparison",
                    title="Manual rating deteriorated",
                    explanation=(
                        f"The latest manual rating is {latest.manual_rating}, "
                        f"up {manual_rating_change} from the prior manual "
                        f"rating of {previous.manual_rating}."
                    ),
                    assessment_ids=[
                        latest.assessment_id,
                        previous.assessment_id,
                    ],
                    evidence_sha256=[
                        latest.evidence_snapshot_sha256,
                        previous.evidence_snapshot_sha256,
                    ],
                    source_as_of=latest.source_as_of,
                )
            )

        if draft_band_attention:
            alerts.append(
                PriorityAlert(
                    code="draft_band_attention",
                    category="draft_taxonomy",
                    evidence_class="professional_judgment",
                    title="Draft high-risk band attention",
                    explanation=(
                        f"The latest saved manual rating is "
                        f"{latest.manual_rating} ({latest.band.meaning}) in "
                        f"Product Owner draft taxonomy "
                        f"{latest.band_set_version}. This is a saved "
                        "professional assessment label, not an approved "
                        "automatic policy, score, recommendation, or action."
                    ),
                    assessment_ids=latest_ids,
                    evidence_sha256=latest_hashes,
                    source_as_of=latest.source_as_of,
                )
            )

        if live_exposure.is_over_line is True:
            alerts.append(
                PriorityAlert(
                    code="current_partial_exposure_over_line",
                    category="live_exposure",
                    evidence_class="observed_current",
                    title="Current partial exposure is over line",
                    explanation=(
                        f"Live partial exposure exceeds the credit line by "
                        f"{live_exposure.amount_over_limit:.2f}. Full exposure "
                        "remains incomplete."
                    ),
                    assessment_ids=[],
                    evidence_sha256=[],
                    source_as_of=live_exposure.retrieved_at,
                )
            )
        elif live_exposure.status != "available":
            alerts.append(
                PriorityAlert(
                    code="live_source_degraded",
                    category="source_gap",
                    evidence_class="source_limitation",
                    title="Live exposure unavailable",
                    explanation=live_exposure.explanation,
                    assessment_ids=latest_ids,
                    evidence_sha256=latest_hashes,
                    source_as_of=None,
                )
            )

        return alerts

    @staticmethod
    def _priority_ordering_reasons(
        *,
        as_of_date: date,
        latest: AssessmentRecord,
        previous: AssessmentRecord | None,
        review_state: str,
        manual_rating_change: int | None,
        live_exposure: PriorityLiveExposureEvidence,
    ) -> list[str]:
        if review_state == "overdue":
            review_reason = (
                f"Review is overdue as of {as_of_date.isoformat()}."
            )
        elif review_state == "due_today":
            review_reason = (
                f"Review is due on {as_of_date.isoformat()}."
            )
        else:
            review_reason = (
                f"Next review is scheduled for "
                f"{latest.next_review_date.isoformat()}."
            )

        reasons = [
            review_reason,
            (
                f"Latest professional assessment is manual rating "
                f"{latest.manual_rating} ({latest.band.meaning}) under draft "
                f"taxonomy {latest.band_set_version}."
            ),
        ]
        if previous is None:
            reasons.append(
                "Deterioration comparison is unavailable because only one "
                "manual assessment exists."
            )
        elif manual_rating_change is not None and manual_rating_change > 0:
            reasons.append(
                f"Manual rating deteriorated by {manual_rating_change} from "
                f"the prior assessment."
            )
        else:
            reasons.append(
                "The latest manual rating did not deteriorate relative to "
                "the prior assessment."
            )

        if live_exposure.is_over_line is True:
            reasons.append(
                "Live partial exposure is currently over the credit line; "
                "full exposure remains incomplete."
            )
        elif live_exposure.is_over_line is False:
            reasons.append(
                "Live partial exposure is not currently over the credit line; "
                "full exposure remains incomplete."
            )
        else:
            reasons.append(
                "Live over-line evidence is unavailable and is not treated as "
                "zero or as an observed over-line condition."
            )
        return reasons

    def create_assessment(
        self,
        customer_number: int,
        payload: AssessmentCreate,
    ) -> AssessmentRecord:
        snapshot = CustomerRiskResponse(
            **self._load_live_snapshot(customer_number)
        ).model_dump(mode="json")
        snapshot.pop("latest_assessment", None)

        band_configuration = self.list_bands()
        selected_band = next(
            (
                band
                for band in band_configuration.bands
                if band.rating_min
                <= payload.manual_rating
                <= band.rating_max
            ),
            None,
        )
        if selected_band is None:
            raise RuntimeError(
                "The current Credit Risk band configuration does not cover "
                f"manual rating {payload.manual_rating}."
            )

        snapshot["risk_band_configuration"] = (
            band_configuration.model_dump(mode="json")
        )
        created_at = self._clock().astimezone(UTC).isoformat()
        source_as_of = snapshot["source"]["retrieved_at"]
        band_set = band_configuration.band_set

        record = {
            "assessment_id": self._id_factory(),
            "customer_number": customer_number,
            "customer_name": snapshot["customer"]["customer_name"],
            "manual_rating": payload.manual_rating,
            "band_set_id": band_set.band_set_id,
            "band_set_version": band_set.version,
            "band_set_status": band_set.status,
            "band": selected_band.model_dump(mode="json"),
            "review_date": payload.review_date.isoformat(),
            "next_review_date": payload.next_review_date.isoformat(),
            "analyst_identity": payload.analyst_identity,
            "rationale": payload.rationale,
            "created_at": created_at,
            "source_as_of": source_as_of,
            "completeness_state": snapshot["exposure"]["completeness"],
            "actor_identity_source": "operator_supplied",
            "actor_authority_status": "not_independently_verified",
            "assessment_classification": "professional_judgment",
            "decision_effect": "none",
            "evidence_snapshot": snapshot,
        }

        return AssessmentRecord(
            **self._repository.create_assessment(record)
        )

    def get_credit_line_intelligence(
        self,
        customer_number: int,
    ) -> CreditLineIntelligenceResponse:
        summary = self._load_customer_summary(customer_number)
        live_snapshot = CustomerRiskResponse(
            **self._load_live_snapshot(customer_number, summary=summary)
        )
        generated_at = self._clock().astimezone(UTC).isoformat()
        sales_source = "Customer 360 sales (MaddenCo TMCUST)"
        credit_source = "Customer 360 credit (MaddenCo TMCUST)"
        source_as_of = live_snapshot.source.retrieved_at
        source_sales = (
            summary.get("sales")
            if isinstance(summary.get("sales"), dict)
            else {}
        )
        source_credit = (
            summary.get("credit")
            if isinstance(summary.get("credit"), dict)
            else {}
        )

        month_to_date = _optional_credit_line_metric(
            source_sales,
            "month_to_date",
            label="Month-to-date sales",
            source=sales_source,
            as_of=source_as_of,
        )
        year_to_date = _optional_credit_line_metric(
            source_sales,
            "year_to_date",
            label="Year-to-date sales",
            source=sales_source,
            as_of=source_as_of,
        )
        last_year = _optional_credit_line_metric(
            source_sales,
            "last_year",
            label="Prior-year sales",
            source=sales_source,
            as_of=source_as_of,
        )
        annualized_sales = _optional_credit_line_metric(
            source_sales,
            "annualized_sales",
            label="Annualized sales",
            source=(
                "Customer 360 analytical calculation over MaddenCo "
                "TMCUST.CUYTDSALES"
            ),
            as_of=source_as_of,
        )
        source_reference = _optional_credit_line_metric(
            source_sales,
            "expected_credit_line",
            label="Existing Customer 360 expected credit line",
            source="Customer 360 existing analytical calculation",
            as_of=source_as_of,
        )
        reference_amount: float | None = None
        reference_status = source_reference.status
        reference_explanation = (
            "The reference is unavailable because annualized sales or the "
            "existing Customer 360 result is unavailable."
        )
        if (
            annualized_sales.status == "available"
            and annualized_sales.value is not None
            and source_reference.status == "available"
            and source_reference.value is not None
        ):
            recomputed = float(
                round(
                    ((annualized_sales.value / 12.0) * 2.0) / 500.0
                )
                * 500
            )
            if abs(recomputed - source_reference.value) <= 0.01:
                reference_amount = round(source_reference.value, 2)
                reference_status = "available"
                reference_explanation = (
                    "Recomputed from the source-present annualized sales and "
                    "matched the existing Customer 360 two-month/$500 "
                    "reference. It is analytical context, not approved credit "
                    "policy or an automatic recommendation."
                )
            else:
                reference_status = "invalid"
                reference_explanation = (
                    "The existing Customer 360 reference did not reproduce "
                    "from its stated annualized-sales formula, so ETOP withheld "
                    "the amount instead of presenting conflicting inference."
                )

        current_line = CreditLineMetric(
            value=live_snapshot.credit.credit_line,
            status="available",
            source=credit_source,
            as_of=source_as_of,
            explanation="Current ERP credit line returned by Customer 360.",
        )
        partial_exposure = CreditLineMetric(
            value=live_snapshot.exposure.partial_exposure,
            status="available",
            source="Credit Risk partial exposure contract",
            as_of=source_as_of,
            explanation=(
                "Open A/R plus the nonnegative ERP on-order aggregate. Full "
                "exposure remains unavailable."
            ),
        )
        available_credit = CreditLineMetric(
            value=live_snapshot.exposure.partial_available_credit,
            status="available",
            source="Credit Risk partial exposure contract",
            as_of=source_as_of,
            explanation=(
                "Current line less partial exposure; this is not full "
                "available credit."
            ),
        )

        latest_assessment = self._repository.get_latest_assessment(
            customer_number
        )
        latest_proposal = self._repository.get_latest_credit_line_proposal(
            customer_number
        )
        return CreditLineIntelligenceResponse(
            generated_at=generated_at,
            source=live_snapshot.source,
            customer=live_snapshot.customer,
            sales=CreditLineSalesEvidence(
                month_to_date=month_to_date,
                year_to_date=year_to_date,
                last_year=last_year,
                annualized_sales=annualized_sales,
            ),
            capacity=CreditLineCapacityEvidence(
                current_credit_line=current_line,
                partial_exposure=partial_exposure,
                available_credit=available_credit,
                high_balance=_optional_credit_line_metric(
                    source_credit,
                    "high_balance",
                    label="Historical high balance",
                    source=credit_source,
                    as_of=source_as_of,
                ),
                monthly_high_balance=_optional_credit_line_metric(
                    source_credit,
                    "monthly_high_balance",
                    label="Monthly high balance",
                    source=credit_source,
                    as_of=source_as_of,
                ),
                average_daily_balance=_optional_credit_line_metric(
                    source_credit,
                    "average_daily_balance",
                    label="Average daily balance",
                    source=credit_source,
                    as_of=source_as_of,
                ),
            ),
            analytical_reference=CreditLineAnalyticalReference(
                amount=reference_amount,
                status=reference_status,
                formula=CREDIT_LINE_REFERENCE_FORMULA,
                rounding_increment=500.0,
                explanation=reference_explanation,
            ),
            current_manual_assessment=(
                AssessmentRecord(**latest_assessment)
                if latest_assessment is not None
                else None
            ),
            latest_professional_proposal=(
                CreditLineProposalRecord(**latest_proposal)
                if latest_proposal is not None
                else None
            ),
            gaps=self._credit_line_gaps(),
            governance=CreditLineGovernance(
                statements=[
                    "The analytical reference reproduces existing Customer 360 logic; it is not approved policy.",
                    "A saved proposal is operator-supplied professional recommendation evidence, not a decision or approval.",
                    "No credit line, terms, order, hold, release, notification, export, posting, or ERP record is changed.",
                ]
            ),
        )

    def list_credit_line_proposals(
        self,
        customer_number: int,
    ) -> CreditLineProposalHistoryResponse:
        records = [
            CreditLineProposalRecord(**record)
            for record in self._repository.list_credit_line_proposals(
                customer_number
            )
        ]
        return CreditLineProposalHistoryResponse(
            customer_number=customer_number,
            count=len(records),
            proposals=records,
        )

    def create_credit_line_proposal(
        self,
        customer_number: int,
        payload: CreditLineProposalCreate,
    ) -> CreditLineProposalRecord:
        intelligence = self.get_credit_line_intelligence(customer_number)
        evidence_snapshot = intelligence.model_dump(mode="json")
        created_at = self._clock().astimezone(UTC).isoformat()
        record = {
            "proposal_id": self._proposal_id_factory(),
            "customer_number": customer_number,
            "customer_name": intelligence.customer.customer_name,
            "proposed_credit_line": payload.proposed_credit_line,
            "current_credit_line": (
                intelligence.capacity.current_credit_line.value
            ),
            "analytical_reference_line": (
                intelligence.analytical_reference.amount
            ),
            "review_date": payload.review_date.isoformat(),
            "analyst_identity": payload.analyst_identity,
            "rationale": payload.rationale,
            "created_at": created_at,
            "source_as_of": intelligence.source.retrieved_at,
            "actor_identity_source": "operator_supplied",
            "actor_authority_status": "not_independently_verified",
            "proposal_classification": "professional_recommendation",
            "approval_status": "not_submitted_to_governed_approval",
            "decision_effect": "none",
            "erp_write": False,
            "evidence_snapshot": evidence_snapshot,
        }
        return CreditLineProposalRecord(
            **self._repository.create_credit_line_proposal(record)
        )

    def get_portfolio_monitoring(self) -> PortfolioMonitoringResponse:
        priority = self.get_priority_alerts()
        exposure_values = [
            float(item.live_exposure.partial_exposure)
            for item in priority.items
            if item.live_exposure.status == "available"
            and item.live_exposure.partial_exposure is not None
        ]
        exposure_total = round(sum(exposure_values), 2)
        band_totals: dict[str, dict[str, float | int]] = {}
        items: list[PortfolioMonitoringItem] = []
        proposal_count = 0
        review_count = 0

        for item in priority.items:
            proposal_row = self._repository.get_latest_credit_line_proposal(
                item.customer_number
            )
            review_row = self._repository.get_latest_portfolio_review(
                item.customer_number
            )
            proposal = (
                CreditLineProposalRecord(**proposal_row)
                if proposal_row is not None
                else None
            )
            review = (
                PortfolioReviewRecord(**review_row)
                if review_row is not None
                else None
            )
            proposal_count += int(proposal is not None)
            review_count += int(review is not None)

            partial_exposure = (
                float(item.live_exposure.partial_exposure)
                if item.live_exposure.status == "available"
                and item.live_exposure.partial_exposure is not None
                else None
            )
            exposure_share = (
                round((partial_exposure / exposure_total) * 100, 2)
                if partial_exposure is not None and exposure_total != 0
                else None
            )
            band_name = item.latest_assessment.band.meaning
            aggregate = band_totals.setdefault(
                band_name,
                {"customer_count": 0, "partial_exposure": 0.0,
                 "exposure_customer_count": 0},
            )
            aggregate["customer_count"] = int(
                aggregate["customer_count"]
            ) + 1
            if partial_exposure is not None:
                aggregate["partial_exposure"] = round(
                    float(aggregate["partial_exposure"])
                    + partial_exposure,
                    2,
                )
                aggregate["exposure_customer_count"] = int(
                    aggregate["exposure_customer_count"]
                ) + 1

            items.append(
                PortfolioMonitoringItem(
                    rank=item.rank,
                    customer_number=item.customer_number,
                    customer_name=item.customer_name,
                    assessment_id=item.latest_assessment.assessment_id,
                    watchlist=item.draft_band_attention,
                    review_state=item.ordering_evidence.review_state,
                    next_review_date=(
                        item.ordering_evidence.next_review_date
                    ),
                    days_to_review=(
                        item.ordering_evidence.next_review_date
                        - priority.as_of_date
                    ).days,
                    latest_manual_rating=(
                        item.ordering_evidence.latest_manual_rating
                    ),
                    band_meaning=band_name,
                    partial_exposure=partial_exposure,
                    partial_exposure_share_percent=exposure_share,
                    latest_professional_proposal=proposal,
                    latest_portfolio_review=review,
                    alerts=item.alerts,
                    ordering_reasons=item.ordering_reasons,
                )
            )

        concentration = [
            PortfolioBandConcentration(
                band_meaning=band_name,
                customer_count=int(values["customer_count"]),
                partial_exposure=round(
                    float(values["partial_exposure"]), 2
                ),
                exposure_share_percent=(
                    round(
                        float(values["partial_exposure"])
                        / exposure_total
                        * 100,
                        2,
                    )
                    if exposure_total != 0
                    else None
                ),
                exposure_customer_count=int(
                    values["exposure_customer_count"]
                ),
            )
            for band_name, values in band_totals.items()
        ]
        concentration.sort(
            key=lambda band: (
                -band.partial_exposure,
                -band.customer_count,
                band.band_meaning.casefold(),
            )
        )

        return PortfolioMonitoringResponse(
            generated_at=priority.generated_at,
            as_of_date=priority.as_of_date,
            summary=PortfolioMonitoringSummary(
                assessed_customer_count=len(items),
                watchlist_customer_count=sum(item.watchlist for item in items),
                overdue_review_count=sum(
                    item.review_state == "overdue" for item in items
                ),
                due_today_review_count=sum(
                    item.review_state == "due_today" for item in items
                ),
                degraded_live_source_count=sum(
                    item.live_exposure.status != "available"
                    for item in priority.items
                ),
                customers_with_proposals=proposal_count,
                customers_with_recorded_reviews=review_count,
                partial_exposure_customer_count=len(exposure_values),
                partial_exposure_total=exposure_total,
            ),
            band_concentration=concentration,
            items=items,
            governance=PortfolioMonitoringGovernance(
                statements=[
                    "The queue covers assessed customers only; it is not a scan of the full ERP customer population.",
                    "Exposure concentration uses current partial exposure only where that evidence is available.",
                    "Saved portfolio reviews are append-only work metadata, not credit decisions or approvals.",
                ]
            ),
            warnings=[
                "Draft high-risk bands support a working watchlist but are not approved automatic policy.",
                "Industry, region, parent-account, full-exposure, and authenticated assignment sources are not connected.",
            ],
        )

    def list_portfolio_reviews(
        self,
        customer_number: int,
    ) -> PortfolioReviewHistoryResponse:
        records = [
            PortfolioReviewRecord(**record)
            for record in self._repository.list_portfolio_reviews(
                customer_number
            )
        ]
        return PortfolioReviewHistoryResponse(
            customer_number=customer_number,
            count=len(records),
            reviews=records,
        )

    def create_portfolio_review(
        self,
        customer_number: int,
        payload: PortfolioReviewCreate,
    ) -> PortfolioReviewRecord:
        monitoring = self.get_portfolio_monitoring()
        item = next(
            (
                candidate
                for candidate in monitoring.items
                if candidate.customer_number == customer_number
            ),
            None,
        )
        if item is None:
            raise CreditRiskCustomerNotFound(
                f"Customer {customer_number} has no saved Credit Risk assessment and is not in the monitored portfolio."
            )
        created_at = self._clock().astimezone(UTC).isoformat()
        record = {
            "portfolio_review_id": self._portfolio_review_id_factory(),
            "customer_number": item.customer_number,
            "customer_name": item.customer_name,
            "disposition": payload.disposition,
            "reviewer_identity": payload.reviewer_identity,
            "notes": payload.notes,
            "follow_up_date": (
                payload.follow_up_date.isoformat()
                if payload.follow_up_date is not None
                else None
            ),
            "created_at": created_at,
            "assessment_id": item.assessment_id,
            "proposal_id": (
                item.latest_professional_proposal.proposal_id
                if item.latest_professional_proposal is not None
                else None
            ),
            "actor_identity_source": "operator_supplied",
            "actor_authority_status": "not_independently_verified",
            "review_classification": "professional_workflow_metadata",
            "decision_effect": "none",
            "erp_write": False,
            "evidence_snapshot": item.model_dump(mode="json"),
        }
        return PortfolioReviewRecord(
            **self._repository.create_portfolio_review(record)
        )

    def get_order_decision_preparation(
        self,
        customer_number: int,
        contemplated_order_amount: float,
        order_reference: str | None = None,
    ) -> OrderDecisionPreparationResponse:
        if (
            isinstance(contemplated_order_amount, bool)
            or not math.isfinite(contemplated_order_amount)
            or contemplated_order_amount <= 0
        ):
            raise ValueError(
                "contemplated_order_amount must be a positive finite amount."
            )
        amount = round(float(contemplated_order_amount), 2)
        intelligence = self.get_credit_line_intelligence(customer_number)
        current_line = float(
            intelligence.capacity.current_credit_line.value or 0.0
        )
        current_partial = float(
            intelligence.capacity.partial_exposure.value or 0.0
        )
        projected_partial = round(current_partial + amount, 2)
        projected_available = round(current_line - projected_partial, 2)
        projected_over = round(max(projected_partial - current_line, 0.0), 2)
        projected_utilization = (
            round((projected_partial / current_line) * 100, 2)
            if current_line > 0
            else None
        )
        latest_review_row = self._repository.get_latest_portfolio_review(
            customer_number
        )
        latest_review = (
            PortfolioReviewRecord(**latest_review_row)
            if latest_review_row is not None
            else None
        )
        assessment_available = intelligence.current_manual_assessment is not None
        return OrderDecisionPreparationResponse(
            generated_at=self._clock().astimezone(UTC).isoformat(),
            source=intelligence.source,
            customer=intelligence.customer,
            order_reference=(order_reference or "").strip() or None,
            evidence=OrderDecisionEvidence(
                contemplated_order_amount=amount,
                current_credit_line=current_line,
                current_partial_exposure=current_partial,
                projected_partial_exposure=projected_partial,
                projected_partial_available_credit=projected_available,
                projected_partial_over_line_amount=projected_over,
                projected_partial_utilization_percent=projected_utilization,
            ),
            latest_manual_assessment=intelligence.current_manual_assessment,
            latest_professional_proposal=(
                intelligence.latest_professional_proposal
            ),
            latest_portfolio_review=latest_review,
            gates=[
                OrderDecisionGate(
                    code="current_customer_evidence",
                    status="available",
                    explanation=(
                        "Current read-only Customer 360 evidence is available for "
                        "the selected customer."
                    ),
                ),
                OrderDecisionGate(
                    code="current_manual_assessment",
                    status=("available" if assessment_available else "unavailable"),
                    explanation=(
                        "The latest append-only manual assessment is available."
                        if assessment_available
                        else "No manual Credit Risk assessment has been recorded."
                    ),
                ),
                OrderDecisionGate(
                    code="erp_order_identity",
                    status="operator_entered",
                    explanation=(
                        "The contemplated amount/reference is operator entered; "
                        "no ERP order header or line identity is connected."
                    ),
                ),
                OrderDecisionGate(
                    code="full_exposure",
                    status="unavailable",
                    explanation=(
                        "Five governed full-exposure components remain unavailable."
                    ),
                ),
                OrderDecisionGate(
                    code="approved_order_policy",
                    status="unavailable",
                    explanation=(
                        "No approved order hold/release policy or threshold is configured."
                    ),
                ),
                OrderDecisionGate(
                    code="authenticated_decision_authority",
                    status="unavailable",
                    explanation=(
                        "Authentication, delegated limits, and decision authority "
                        "are not connected."
                    ),
                ),
            ],
            governance=OrderDecisionGovernance(
                statements=[
                    "Projected values are arithmetic over current partial exposure plus an operator-entered scenario amount.",
                    "A professional recommendation remains separate from an authorized Decision.",
                    "No order, line, terms, hold, release, approval, notification, export, posting, or ERP record is changed.",
                ]
            ),
            warnings=[
                "Projected partial available credit is not full true available credit.",
                "The scenario may not correspond to a current ERP order and cannot be used as execution authority.",
            ],
        )

    def create_order_recommendation(
        self,
        customer_number: int,
        payload: OrderRecommendationCreate,
    ) -> OrderRecommendationRecord:
        preparation = self.get_order_decision_preparation(
            customer_number,
            payload.contemplated_order_amount,
            payload.order_reference,
        )
        record = {
            "order_recommendation_id": self._order_recommendation_id_factory(),
            "customer_number": customer_number,
            "customer_name": preparation.customer.customer_name,
            "contemplated_order_amount": (
                preparation.evidence.contemplated_order_amount
            ),
            "order_reference": preparation.order_reference,
            "disposition": payload.disposition,
            "analyst_identity": payload.analyst_identity,
            "rationale": payload.rationale,
            "created_at": self._clock().astimezone(UTC).isoformat(),
            "source_as_of": preparation.source.retrieved_at,
            "assessment_id": (
                preparation.latest_manual_assessment.assessment_id
                if preparation.latest_manual_assessment is not None
                else None
            ),
            "proposal_id": (
                preparation.latest_professional_proposal.proposal_id
                if preparation.latest_professional_proposal is not None
                else None
            ),
            "current_credit_line": preparation.evidence.current_credit_line,
            "current_partial_exposure": (
                preparation.evidence.current_partial_exposure
            ),
            "projected_partial_exposure": (
                preparation.evidence.projected_partial_exposure
            ),
            "projected_partial_available_credit": (
                preparation.evidence.projected_partial_available_credit
            ),
            "projected_partial_over_line_amount": (
                preparation.evidence.projected_partial_over_line_amount
            ),
            "actor_identity_source": "operator_supplied",
            "actor_authority_status": "not_independently_verified",
            "recommendation_classification": "professional_recommendation",
            "decision_status": "not_submitted_to_governed_decision",
            "decision_effect": "none",
            "order_effect": "none",
            "erp_write": False,
            "evidence_snapshot": preparation.model_dump(mode="json"),
        }
        return OrderRecommendationRecord(
            **self._repository.create_order_recommendation(record)
        )

    def list_order_recommendations(
        self,
        customer_number: int,
    ) -> OrderRecommendationHistoryResponse:
        records = [
            OrderRecommendationRecord(**record)
            for record in self._repository.list_order_recommendations(
                customer_number
            )
        ]
        return OrderRecommendationHistoryResponse(
            customer_number=customer_number,
            count=len(records),
            recommendations=records,
            governance=OrderDecisionGovernance(
                statements=[
                    "History is append-only professional recommendation evidence; it contains no order or ERP action."
                ]
            ),
        )

    @staticmethod
    def _credit_line_gaps() -> list[CreditLineGap]:
        return [
            CreditLineGap(
                code="full_exposure",
                label="Full exposure",
                explanation=(
                    "Unbilled shipments, releasable orders, unapplied cash, "
                    "valid credits, and secured amounts are not separately "
                    "governed."
                ),
            ),
            CreditLineGap(
                code="seasonal_limit_model",
                label="Seasonal limit model",
                explanation=(
                    "No governed multi-period sales or seasonal-capacity model "
                    "is connected."
                ),
            ),
            CreditLineGap(
                code="related_account_exposure",
                label="Related-account exposure",
                explanation=(
                    "Parent, affiliate, and linked-account exposure are not "
                    "assembled by the current Credit Risk source contract."
                ),
            ),
            CreditLineGap(
                code="approved_line_policy",
                label="Approved credit-line policy",
                explanation=(
                    "The existing two-month sales calculation is an analytical "
                    "reference and has not been promoted into approved policy."
                ),
            ),
            CreditLineGap(
                code="approval_authority",
                label="Approval authority and routing",
                explanation=(
                    "Authentication, delegated limits, approval tiers, and "
                    "segregation-of-duties routing remain unavailable."
                ),
            ),
        ]

    def _load_customer_summary(
        self,
        customer_number: int,
    ) -> dict[str, Any]:
        try:
            summary = self._customer_service().summary(customer_number)
        except Exception as exc:
            raise CreditRiskSourceUnavailable(
                "Customer 360 could not retrieve the read-only ERP facts."
            ) from exc
        if summary is None:
            raise CreditRiskCustomerNotFound(
                f"Customer {customer_number} was not found."
            )
        if not isinstance(summary, dict):
            raise CreditRiskSourceIntegrityError(
                "Customer 360 returned an invalid customer summary envelope."
            )
        return summary

    def _load_live_snapshot(
        self,
        customer_number: int,
        *,
        summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if summary is None:
            summary = self._load_customer_summary(customer_number)

        try:
            returned_customer_number = int(summary["customer_number"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CreditRiskSourceIntegrityError(
                "Customer 360 returned no valid customer identity for the "
                f"requested customer {customer_number}."
            ) from exc

        if returned_customer_number != customer_number:
            raise CreditRiskSourceIntegrityError(
                "Customer 360 returned customer "
                f"{returned_customer_number} for requested customer "
                f"{customer_number}; no Credit Risk evidence was attached."
            )

        retrieved_at = self._clock().astimezone(UTC).isoformat()
        general = _source_section(summary, "general")
        source_credit = _source_section(summary, "credit")
        source_aging = _source_section(summary, "aging")
        activity = _source_section(summary, "activity")

        customer_name = str(
            summary.get("customer_name") or ""
        ).strip()
        if not customer_name:
            raise CreditRiskSourceIntegrityError(
                "Customer 360 returned no customer name for the requested "
                f"customer {customer_number}."
            )

        credit_line = _required_number(
            source_credit,
            "credit_limit",
            "credit line",
        )
        open_ar = _required_number(
            source_credit,
            "balance",
            "open A/R",
        )
        on_order_aggregate = _required_number(
            source_credit,
            "raw_on_order",
            "ERP on-order aggregate",
        )
        on_order_calculation_value = max(on_order_aggregate, 0.0)
        partial_exposure = round(
            open_ar + on_order_calculation_value,
            2,
        )
        partial_available_credit = round(
            credit_line - partial_exposure,
            2,
        )
        amount_over_limit = round(
            max(partial_exposure - credit_line, 0.0),
            2,
        )
        utilization_percent = (
            round((partial_exposure / credit_line) * 100, 2)
            if credit_line > 0
            else None
        )

        aging_values = {
            "future": _required_number(
                source_aging,
                "future",
                "future aging",
            ),
            "current": _required_number(
                source_aging,
                "current",
                "current aging",
            ),
            "days_30": _required_number(
                source_aging,
                "days_30",
                "30-day aging",
            ),
            "days_60": _required_number(
                source_aging,
                "days_60",
                "60-day aging",
            ),
            "days_90": _required_number(
                source_aging,
                "days_90",
                "90-day aging",
            ),
            "days_120": _required_number(
                source_aging,
                "days_120",
                "120-plus-day aging",
            ),
        }
        past_due = round(
            aging_values["days_30"]
            + aging_values["days_60"]
            + aging_values["days_90"]
            + aging_values["days_120"],
            2,
        )
        bucket_total = round(sum(aging_values.values()), 2)

        last_payment_amount, amount_state = _payment_amount(activity)
        last_payment_date, date_state = _payment_date(activity)
        states = {amount_state, date_state}
        if "invalid" in states:
            last_payment_status = "degraded"
            last_payment_explanation = (
                "Customer 360 returned malformed last-payment evidence; "
                "the invalid field is not treated as available."
            )
        elif states == {"valid"}:
            last_payment_status = "available"
            last_payment_explanation = (
                "Amount and date are available from the current Customer "
                "360 contract."
            )
        elif states == {"missing"}:
            last_payment_status = "no_record_in_current_contract"
            last_payment_explanation = (
                "No last-payment amount or date is present in the current "
                "Customer 360 contract."
            )
        else:
            last_payment_status = "partial"
            last_payment_explanation = (
                "Only one of last-payment amount or date is present in the "
                "current Customer 360 contract."
            )

        source = SourceEvidence(
            system="MaddenCo ERP through shared Customer 360",
            retrieved_at=retrieved_at,
        )
        customer = CustomerIdentityEvidence(
            customer_number=returned_customer_number,
            customer_name=customer_name,
            dba_name=str(general.get("dba_name") or "").strip(),
            address_lines=list(general.get("address_lines") or []),
            state_code=general.get("state_code"),
            zip_code=str(general.get("zip_code") or "").strip(),
            phone=str(general.get("phone") or "").strip(),
            email=str(general.get("email") or "").strip(),
            route_code=str(general.get("route_code") or "").strip(),
            store_number=general.get("store_number"),
            salesman_number=general.get("salesman_number"),
            customer_type=str(
                general.get("customer_type") or ""
            ).strip(),
            customer_class=str(
                general.get("customer_class") or ""
            ).strip(),
            active=bool(general.get("active")),
        )
        credit = CreditEvidence(
            credit_line=credit_line,
            open_ar=open_ar,
            erp_on_order_aggregate=on_order_aggregate,
            customer_360_exposure=partial_exposure,
            customer_360_available_credit=partial_available_credit,
            amount_over_limit=amount_over_limit,
            utilization_percent=utilization_percent,
            terms_code=str(
                source_credit.get("terms_code") or ""
            ).strip(),
            terms_description=str(
                source_credit.get("terms_description") or ""
            ).strip(),
        )
        exposure = ExposureEvidence(
            full_formula=FULL_EXPOSURE_FORMULA,
            known_component_subtotal=open_ar,
            operational_reference_formula=PARTIAL_EXPOSURE_FORMULA,
            partial_exposure=partial_exposure,
            partial_available_credit=partial_available_credit,
            missing_required_components=[
                "unbilled_shipments",
                "releasable_orders",
                "unapplied_cash",
                "valid_credits",
                "secured_amounts",
            ],
            components=self._exposure_components(
                open_ar=open_ar,
                on_order_aggregate=on_order_aggregate,
                on_order_calculation_value=on_order_calculation_value,
            ),
            warnings=[
                "Full exposure is unavailable because five required "
                "components do not have governed source contracts.",
                "The ERP on-order aggregate is available, but it has not "
                "been proven to represent separate unbilled shipments or "
                "releasable orders and is excluded from full exposure.",
                "Partial exposure and available credit are operational "
                "references from Customer 360, not complete true exposure.",
            ],
        )
        aging = AgingEvidence(
            **aging_values,
            past_due=past_due,
            bucket_total=bucket_total,
            open_ar_reconciliation_difference=round(
                open_ar - bucket_total,
                2,
            ),
            source=(
                "Customer 360 signed MaddenCo aging buckets; bucket total "
                "is recomputed without the legacy total_aging field."
            ),
        )
        payment = PaymentEvidence(
            last_payment_amount=last_payment_amount,
            last_payment_date=last_payment_date,
            last_payment_status=last_payment_status,
            last_payment_explanation=last_payment_explanation,
            average_days_to_pay=_unavailable_metric(
                "Average days to pay"
            ),
            weighted_average_days_to_pay=_unavailable_metric(
                "Weighted average days to pay"
            ),
            days_beyond_terms=_unavailable_metric(
                "Days beyond terms"
            ),
            on_time_percentage=_unavailable_metric(
                "On-time percentage"
            ),
            late_payment_frequency=_unavailable_metric(
                "Late-payment frequency"
            ),
            largest_historical_delinquency=_unavailable_metric(
                "Largest historical delinquency"
            ),
        )

        return {
            "source": source,
            "customer": customer,
            "credit": credit,
            "exposure": exposure,
            "aging": aging,
            "payment": payment,
            "latest_assessment": None,
            "governance": CreditRiskGovernance(),
        }

    @staticmethod
    def _exposure_components(
        *,
        open_ar: float,
        on_order_aggregate: float,
        on_order_calculation_value: float,
    ) -> list[ExposureComponent]:
        unavailable = (
            (
                "unbilled_shipments",
                "Unbilled shipments",
                "add",
            ),
            (
                "releasable_orders",
                "Releasable orders",
                "add",
            ),
            (
                "unapplied_cash",
                "Unapplied cash",
                "subtract",
            ),
            (
                "valid_credits",
                "Valid credits",
                "subtract",
            ),
            (
                "secured_amounts",
                "Secured amounts",
                "subtract",
            ),
        )

        components = [
            ExposureComponent(
                key="open_ar",
                label="Open A/R",
                operation="add",
                value=open_ar,
                calculation_value=open_ar,
                status="available",
                required_for_full_exposure=True,
                included_in_partial_calculation=True,
                source="Customer 360 credit.balance (TMCUST.CUBALANCE)",
                explanation=(
                    "Current signed open A/R supplied by Customer 360."
                ),
            )
        ]
        components.extend(
            ExposureComponent(
                key=key,
                label=label,
                operation=operation,
                value=None,
                calculation_value=None,
                status="unavailable",
                required_for_full_exposure=True,
                included_in_partial_calculation=False,
                source=None,
                explanation=(
                    f"{label} has no governed source contract in Increment 1."
                ),
            )
            for key, label, operation in unavailable
        )
        components.append(
            ExposureComponent(
                key="erp_on_order_aggregate",
                label="ERP on-order aggregate",
                operation="informational",
                value=on_order_aggregate,
                calculation_value=on_order_calculation_value,
                status="available_unclassified",
                required_for_full_exposure=False,
                included_in_partial_calculation=True,
                source=(
                    "Customer 360 credit.raw_on_order "
                    "(TMCUST.CUONORDER + TMCUST.CUONORDAR)"
                ),
                explanation=(
                    "Customer 360 includes the nonnegative portion in its "
                    "operational exposure. The aggregate is not mapped to "
                    "unbilled shipments or releasable orders, so it is not "
                    "used as either full-formula component."
                ),
            )
        )
        return components


credit_risk_service = CreditRiskService()
