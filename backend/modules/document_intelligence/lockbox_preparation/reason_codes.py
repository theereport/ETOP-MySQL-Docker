"""Versioned, deterministic reasons for Lockbox preparation exceptions.

This module explains existing preparation outcomes. It does not change
customer ranking, allocation policy, approval state, export eligibility, or
ERP behavior. Historical Increment 2D records can be classified from their
preserved source/result/error envelope without rerunning OCR or ERP reads.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from .states import TransactionState


CLASSIFIER_VERSION = "lockbox-exception-reasons@1.3.0-increment3p"
_AMOUNT_TOLERANCE = Decimal("0.01")


@dataclass(frozen=True)
class ReasonDefinition:
    code: str
    category: str
    label: str
    description: str
    review_guidance: str


_DEFINITIONS = (
    ReasonDefinition(
        code="customer_not_found",
        category="customer",
        label="No reliable customer found",
        description=(
            "Stored ERP and document evidence did not identify a customer."
        ),
        review_guidance=(
            "Inspect the source evidence and search the read-only ERP "
            "customer base."
        ),
    ),
    ReasonDefinition(
        code="customer_conflict",
        category="customer",
        label="Multiple possible customers",
        description=(
            "Stored evidence identifies more than one possible ERP customer."
        ),
        review_guidance=(
            "Compare all candidates and source evidence; do not select one "
            "automatically."
        ),
    ),
    ReasonDefinition(
        code="customer_candidate_unconfirmed",
        category="customer",
        label="Single customer candidate needs confirmation",
        description=(
            "One ERP customer candidate was retained, but no governed "
            "primary identity rule selected it."
        ),
        review_guidance=(
            "Confirm the candidate against the preserved source and ERP "
            "evidence before selection."
        ),
    ),
    ReasonDefinition(
        code="customer_rank_ambiguity",
        category="customer",
        label="Ranked customer candidates remain ambiguous",
        description=(
            "Multiple ranked customers were found without authoritative "
            "invoice ownership or one unique complete phone/ZIP match."
        ),
        review_guidance=(
            "Compare the candidates; address, ZIP, and name support review "
            "but do not select one automatically."
        ),
    ),
    ReasonDefinition(
        code="invoice_owner_evidence_incomplete",
        category="customer",
        label="Current invoice-owner evidence incomplete",
        description=(
            "At least one admitted invoice owner was missing, partial, "
            "duplicated, split, or unavailable."
        ),
        review_guidance=(
            "Keep the transaction in review until every admitted invoice has "
            "complete current-open ownership evidence."
        ),
    ),
    ReasonDefinition(
        code="exact_contact_duplicate",
        category="customer",
        label="Phone and ZIP identify multiple customers",
        description=(
            "More than one ERP customer has the same normalized full phone "
            "and five-digit ZIP pair."
        ),
        review_guidance=(
            "Do not break the tie with name or address scoring; verify the "
            "customer manually."
        ),
    ),
    ReasonDefinition(
        code="exact_contact_candidate_set_incomplete",
        category="service",
        label="Phone and ZIP candidate set incomplete",
        description=(
            "The bounded ERP read could not establish the complete universe "
            "of exact phone/ZIP candidates."
        ),
        review_guidance=(
            "Retain the item in review and rerun only after the read can "
            "establish candidate-set completeness."
        ),
    ),
    ReasonDefinition(
        code="customer_resolution_unavailable",
        category="service",
        label="Customer matching unavailable",
        description=(
            "The read-only customer resolution dependency was unavailable."
        ),
        review_guidance=(
            "Retry after the local dependency is healthy; retain the item in "
            "review until then."
        ),
    ),
    ReasonDefinition(
        code="customer_resolved_no_exact_allocation",
        category="allocation",
        label="Customer matched—allocation needs review",
        description=(
            "The customer was resolved, but no exact supported allocation "
            "balanced the payment."
        ),
        review_guidance=(
            "Review remittance and current ERP open items within the verified "
            "customer."
        ),
    ),
    ReasonDefinition(
        code="projection_evidence_gate_blocked",
        category="evidence",
        label="Balanced candidate needs evidence verification",
        description=(
            "The final candidate balanced, but one or more protected "
            "projection evidence gates did not permit automatic preparation."
        ),
        review_guidance=(
            "Inspect the recorded projection blockers and preserved source "
            "evidence before accepting the recommendation."
        ),
    ),
    ReasonDefinition(
        code="linked_customer_allocation_review",
        category="allocation",
        label="Linked customer invoices need verification",
        description=(
            "Exact remittance invoices were found across customer accounts "
            "linked by TMCUST.CUNUMENT."
        ),
        review_guidance=(
            "Verify every customer number, invoice, and apply amount; the "
            "relationship does not authorize cross-customer application."
        ),
    ),
    ReasonDefinition(
        code="enterprise_group_incomplete",
        category="customer",
        label="Linked customer group evidence incomplete",
        description=(
            "TMCUST.CUNUMENT was nonzero, but the bounded group read did not "
            "establish a complete linked-account verification set."
        ),
        review_guidance=(
            "Keep the payment in review; verify the matched account, "
            "enterprise account, and linked customer membership before "
            "relying on a single-account allocation."
        ),
    ),
    ReasonDefinition(
        code="multiple_valid_allocations",
        category="allocation",
        label="Multiple possible allocations",
        description=(
            "More than one complete allocation satisfies the current exact "
            "matching rule."
        ),
        review_guidance=(
            "Use source evidence and professional judgment; do not select a "
            "candidate arbitrarily."
        ),
    ),
    ReasonDefinition(
        code="credit_or_short_pay_variance",
        category="allocation",
        label="Credit or amount variance",
        description=(
            "A stored proposed allocation is nonzero but remains out of "
            "balance, indicating a credit or partial-payment variance that "
            "requires review."
        ),
        review_guidance=(
            "Review signed credits, apply amounts, and the remaining variance."
        ),
    ),
    ReasonDefinition(
        code="ocr_or_remittance_evidence_incomplete",
        category="evidence",
        label="OCR/remittance evidence incomplete",
        description=(
            "Normalized remittance invoices or required source provenance are "
            "missing from the stored evidence."
        ),
        review_guidance=(
            "Inspect the preserved source pages and correct document evidence "
            "before relying on a recommendation."
        ),
    ),
    ReasonDefinition(
        code="customer_master_unavailable",
        category="service",
        label="Customer master unavailable",
        description=(
            "The verified customer was known, but authoritative customer "
            "master detail could not be loaded."
        ),
        review_guidance=(
            "Retry the read-only customer-master request when the local ERP "
            "dependency is healthy."
        ),
    ),
    ReasonDefinition(
        code="open_ar_unavailable",
        category="service",
        label="Open AR unavailable",
        description=(
            "Current read-only ERP invoice and credit evidence could not be "
            "loaded."
        ),
        review_guidance=(
            "Retry after the local ERP dependency is healthy; do not infer "
            "open balances."
        ),
    ),
    ReasonDefinition(
        code="allocation_evaluation_failed",
        category="system",
        label="Allocation evaluation failed",
        description=(
            "Customer and ERP evidence reached allocation analysis, but the "
            "deterministic evaluation did not complete."
        ),
        review_guidance=(
            "Retain the transaction in review and inspect the recorded failure."
        ),
    ),
    ReasonDefinition(
        code="preparation_failure",
        category="system",
        label="Preparation failed",
        description=(
            "A local read or preparation step failed before a more specific "
            "reason could be established."
        ),
        review_guidance=(
            "Inspect the recorded stage and retry only when the failure is "
            "marked eligible."
        ),
    ),
    ReasonDefinition(
        code="unclassified_exception",
        category="system",
        label="Unclassified preparation exception",
        description=(
            "The preserved exception does not yet map to a specific governed "
            "reason."
        ),
        review_guidance=(
            "Keep the item in professional review and use it as a candidate "
            "for classifier improvement."
        ),
    ),
)

REASON_DEFINITIONS = {
    definition.code: definition for definition in _DEFINITIONS
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _source_payload(
    source: Mapping[str, Any],
    result: Mapping[str, Any],
) -> Mapping[str, Any]:
    result_source = _mapping(result.get("source"))
    return result_source or source


def _customer_resolution(
    result: Mapping[str, Any],
) -> Mapping[str, Any]:
    resolution = _mapping(result.get("customer_resolution"))
    if resolution:
        return resolution
    evidence = _mapping(result.get("evidence"))
    return _mapping(evidence.get("customer_resolution"))


def _conflict_assessment(
    result: Mapping[str, Any],
) -> Mapping[str, Any]:
    direct = _mapping(result.get("customer_conflict_assessment"))
    if direct:
        return direct
    evidence = _mapping(result.get("evidence"))
    return _mapping(evidence.get("customer_conflict_assessment"))


def _evidence_is_incomplete(source: Mapping[str, Any]) -> bool:
    invoices = source.get("extracted_invoice_numbers")
    has_invoices = bool(
        isinstance(invoices, (list, tuple))
        and any(str(value or "").strip() for value in invoices)
    )
    source_reference = str(source.get("source_reference") or "").strip()
    extraction_version = str(
        source.get("extraction_version") or ""
    ).strip().lower()
    has_extraction_version = extraction_version not in {"", "unknown"}
    return not (has_invoices and source_reference and has_extraction_version)


def _has_amount_variance(
    recommendation: Mapping[str, Any],
) -> bool:
    check_amount = _decimal(recommendation.get("check_amount"))
    suggested_total = _decimal(recommendation.get("suggested_total"))
    difference = _decimal(recommendation.get("difference"))
    if difference is None and None not in {check_amount, suggested_total}:
        difference = check_amount - suggested_total
    if difference is None or abs(difference) <= _AMOUNT_TOLERANCE:
        return False
    allocations = recommendation.get("allocations")
    return bool(
        (suggested_total is not None and suggested_total != 0)
        or (isinstance(allocations, (list, tuple)) and allocations)
    )


def _definition_payload(code: str) -> dict[str, str]:
    return asdict(REASON_DEFINITIONS[code])


def classify_exception(
    *,
    state: str,
    source: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
    error: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Classify one terminal exception without changing stored evidence."""

    if state != TransactionState.PREPARED_EXCEPTION.value:
        return None

    source_payload = _source_payload(
        _mapping(source),
        _mapping(result),
    )
    result_payload = _mapping(result)
    error_payload = _mapping(error)
    resolution = _customer_resolution(result_payload)
    matching_evidence = _mapping(resolution.get("matching_evidence"))
    conflict_assessment = _conflict_assessment(result_payload)
    recommendation = _mapping(result_payload.get("recommendation"))
    resolution_status = str(resolution.get("status") or "").strip()
    allocation_method = str(
        recommendation.get("method") or ""
    ).strip()
    stage = str(error_payload.get("stage") or "").strip()

    if stage == "control_projection":
        primary_code = "projection_evidence_gate_blocked"
    elif resolution_status == "ambiguous":
        conflict_status = str(
            conflict_assessment.get("status") or ""
        ).strip()
        candidate_count = len(
            resolution.get("candidates")
            if isinstance(resolution.get("candidates"), (list, tuple))
            else []
        )
        exact_contact_count = _integer(
            matching_evidence.get("exact_phone_postal_match_count") or 0
        )
        contact_complete = bool(
            matching_evidence.get("contact_candidate_complete", True)
        )
        if conflict_status in {
            "incomplete",
            "not_found",
            "evidence_unavailable",
        } or bool(
            matching_evidence.get("partial_invoice_owner_evidence")
        ):
            primary_code = "invoice_owner_evidence_incomplete"
        elif exact_contact_count > 1:
            primary_code = "exact_contact_duplicate"
        elif exact_contact_count and not contact_complete:
            primary_code = "exact_contact_candidate_set_incomplete"
        elif (
            candidate_count == 1
            and not bool(matching_evidence.get("invoice_owner_conflict"))
        ):
            primary_code = "customer_candidate_unconfirmed"
        elif (
            candidate_count > 1
            and not bool(matching_evidence.get("invoice_owner_conflict"))
            and conflict_status not in {"ambiguous", "resolved"}
        ):
            primary_code = "customer_rank_ambiguity"
        else:
            primary_code = "customer_conflict"
    elif resolution_status == "not_found":
        primary_code = "customer_not_found"
    elif resolution_status == "unavailable":
        primary_code = "customer_resolution_unavailable"
    elif stage == "customer_master":
        primary_code = "customer_master_unavailable"
    elif stage in {"open_ar", "enterprise_group_open_ar"}:
        primary_code = "open_ar_unavailable"
    elif stage == "enterprise_group_evidence":
        primary_code = "enterprise_group_incomplete"
    elif allocation_method == "enterprise_group_exact_remittance_review":
        primary_code = "linked_customer_allocation_review"
    elif allocation_method == "ambiguous_due_date_groups":
        primary_code = "multiple_valid_allocations"
    elif _has_amount_variance(recommendation):
        primary_code = "credit_or_short_pay_variance"
    elif (
        resolution_status == "resolved"
        and (
            recommendation.get("status") == "review_required"
            or allocation_method == "no_exact_match"
        )
    ):
        primary_code = "customer_resolved_no_exact_allocation"
    elif stage == "allocation_evaluation":
        primary_code = "allocation_evaluation_failed"
    elif stage in {"read_or_prepare", "preparation"} or stage:
        primary_code = "preparation_failure"
    else:
        primary_code = "unclassified_exception"

    contributing_codes: list[str] = []
    if _evidence_is_incomplete(source_payload):
        contributing_codes.append(
            "ocr_or_remittance_evidence_incomplete"
        )
    if (
        primary_code != "credit_or_short_pay_variance"
        and _has_amount_variance(recommendation)
    ):
        contributing_codes.append("credit_or_short_pay_variance")

    primary = _definition_payload(primary_code)
    contributing = [
        _definition_payload(code)
        for code in dict.fromkeys(contributing_codes)
        if code != primary_code
    ]
    reason_codes = [
        primary_code,
        *(item["code"] for item in contributing),
    ]
    return {
        "classifier_version": CLASSIFIER_VERSION,
        "primary_reason": primary,
        "contributing_reasons": contributing,
        "reason_codes": reason_codes,
        "stage": stage,
        "customer_resolution_status": resolution_status,
        "allocation_method": allocation_method,
        "retry_eligible": bool(
            error_payload.get("retry_eligible", False)
        ),
        "requires_human_review": True,
        "can_auto_approve": False,
        "erp_write_performed": False,
    }


def decorate_transaction(
    transaction: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a response copy with a backward-compatible reason analysis."""

    decorated = dict(transaction)
    result = _mapping(decorated.get("result"))
    stored_analysis = _mapping(result.get("exception_analysis"))
    analysis = stored_analysis or classify_exception(
        state=str(decorated.get("state") or ""),
        source=_mapping(decorated.get("source")),
        result=result,
        error=_mapping(decorated.get("error")),
    )
    decorated["exception_analysis"] = analysis
    return decorated


def build_exception_summary(
    transactions: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate a stable exception funnel for one preparation job."""

    exception_analyses: list[Mapping[str, Any]] = []
    for transaction in transactions:
        decorated = decorate_transaction(transaction)
        analysis = _mapping(decorated.get("exception_analysis"))
        if analysis:
            exception_analyses.append(analysis)

    primary_counts: dict[str, int] = {}
    contributing_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    retry_eligible_count = 0
    unclassified_count = 0

    for analysis in exception_analyses:
        primary = _mapping(analysis.get("primary_reason"))
        primary_code = str(primary.get("code") or "unclassified_exception")
        primary_counts[primary_code] = primary_counts.get(primary_code, 0) + 1
        category = str(primary.get("category") or "system")
        category_counts[category] = category_counts.get(category, 0) + 1
        if primary_code == "unclassified_exception":
            unclassified_count += 1
        if analysis.get("retry_eligible"):
            retry_eligible_count += 1
        for reason in analysis.get("contributing_reasons", []):
            code = str(_mapping(reason).get("code") or "")
            if code:
                contributing_counts[code] = (
                    contributing_counts.get(code, 0) + 1
                )

    def reason_rows(counts: Mapping[str, int]) -> list[dict[str, Any]]:
        return [
            {
                **_definition_payload(definition.code),
                "count": int(counts[definition.code]),
            }
            for definition in _DEFINITIONS
            if counts.get(definition.code)
        ]

    return {
        "classifier_version": CLASSIFIER_VERSION,
        "total_exception_count": len(exception_analyses),
        "classified_exception_count": (
            len(exception_analyses) - unclassified_count
        ),
        "unclassified_exception_count": unclassified_count,
        "retry_eligible_count": retry_eligible_count,
        "by_primary_reason": reason_rows(primary_counts),
        "by_contributing_reason": reason_rows(contributing_counts),
        "by_category": [
            {"category": category, "count": count}
            for category, count in sorted(category_counts.items())
        ],
        "prepared_not_approved": True,
        "can_auto_approve": False,
        "erp_write_performed": False,
    }
