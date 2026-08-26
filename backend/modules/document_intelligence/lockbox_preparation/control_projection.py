"""Control-preserving runtime projection through Lockbox Increment 4A.

The accepted Increment 3F R1 generation is immutable control state.  A new
Increment 3I preparation is a supplemental candidate: it may promote only a
control review item that passes every R4 evidence gate.  Candidate regressions
and blocked improvements remain review recommendations and never replace an
accepted balance, human disposition, customer, or source row.

Increment 3S adds a separate first-source projection for a processed Lockbox
that has no historical Increment 3E control generation. The first-source
projection begins every non-human transaction in review and admits only the
same deterministic, exact, no-write promotion gate used by the protected
projection. It never borrows the 78-item control or its counts for another
PDF.

Increment 3T preserves a fresh source's already-classified preparation
exceptions instead of rebuilding them from the synthetic review floor. The
review floor still governs balanced candidates, including every promotion
gate, while technical failures remain distinct from professional-review
exceptions.

Increment 3U gives a complete saved current-open invoice-owner assessment
precedence over stale broad-owner and contact-ranking gates.  It does so only
when the assessment itself proves that every admitted remittance invoice is
currently open under exactly one same selected ERP customer with complete
source evidence.  All original lower-authority evidence remains preserved.

Increment 3V admits one exact residual open item after complete remittance
matching only when that signed item is the unique same-customer match.  It
does not admit a broad subset search, partial application, cross-customer row,
automatic approval, or ERP write.

Increment 3W admits preserved unambiguous 10-digit source rows under the
shared ERP invoice contract and recognizes a complete current-ERP
reconciliation of every admitted remit row as stronger than a stale coarse
page-completeness flag. Original rejections and parser flags remain preserved.

Increment 3X restores the governed 8/9-digit invoice contract and resolves an
invoice-versus-purchase-order row only after one matched customer's current
open A/R proves exactly one candidate with the exact preserved signed amount.
The ambiguous parser row and every raw candidate remain preserved.

Increment 3Z admits one unique exact selection of one or more complete signed
ERP due-date groups when an otherwise verified remittance list is broader than
the check. Partial groups and multiple matching combinations remain in review.

Increment 4A admits one exact six- or seven-digit ERP customer number
(MaddenCo TMCUST.CUNUMBER is decimal(7,0)) read from the check-bounded FOR
line only after stronger invoice-owner, explicit account, and K&M
statement evidence is exhausted.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .reason_codes import build_exception_summary, classify_exception


CONTROL_RULE_VERSION = (
    "ADR-001@0.7.0-wave2-increment3e+BR-LOCKBOX-001..013"
)
CONTROL_SERVICE_VERSION = "lockbox-preparation@0.7.0-wave2-increment3e"
PROJECTION_VERSION = "lockbox-control-projection@0.7.0-wave2-increment4a"
FRESH_SOURCE_PROJECTION_VERSION = (
    "lockbox-fresh-source-projection@0.7.0-wave2-increment4a"
)
EXPECTED_TRANSACTION_COUNT = 78
ACCEPTED_BALANCED_COUNT = 30
ACCEPTED_REVIEW_COUNT = 48
PRIOR_PROJECTED_BALANCED_FLOOR = 43
PRIOR_PROJECTED_REVIEW_CEILING = 35
EXPECTED_BOUNDARY_RULE = "next_transaction_information"
MONEY_TOLERANCE = Decimal("0.01")

PROMOTION_SELECTION_BASES = frozenset(
    {
        "exact_phone_and_zip",
        "unique_current_open_invoice_owner",
        "unique_phone_zip_with_address_confirmation",
        "unique_exact_phone",
        "unique_phone_with_contact_confirmation",
        "unique_exact_address_and_zip",
        "unique_remittance_invoice_owner",
        "payer_supplied_customer_number",
        "km_statement_customer_number",
        "check_for_customer_number",
        "check_phone_number_match",
        "learned_payer_bank_account_mapping",
        "unique_open_ar_bucket_match",
    }
)
PROMOTION_METHODS = frozenset(
    {
        "exact_remittance_invoices",
        "exact_remittance_plus_oldest_open_items",
        "exact_remittance_plus_unique_open_item",
        "same_due_date_exact_match",
        "exact_total_open_balance",
        "exact_aging_bucket_match",
        "oldest_open_items_exact_match",
        "unique_exact_due_date_group_combination",
        "exact_remittance_invoice_cap_plus_service_charge",
    }
)

_CUSTOMER_EVIDENCE_MINIMUMS = {
    "exact_phone_and_zip": 0.97,
    "unique_current_open_invoice_owner": 1.0,
    "unique_phone_zip_with_address_confirmation": 1.0,
    "unique_exact_phone": 0.99,
    "unique_phone_with_contact_confirmation": 1.0,
    "unique_exact_address_and_zip": 1.0,
    "unique_remittance_invoice_owner": 1.0,
    "payer_supplied_customer_number": 1.0,
    "km_statement_customer_number": 1.0,
    "check_for_customer_number": 1.0,
    "check_phone_number_match": 1.0,
    "learned_payer_bank_account_mapping": 1.0,
    "unique_open_ar_bucket_match": 1.0,
}
_CUSTOMER_EVIDENCE_STOP_GATES = frozenset(
    {
        "invoice_owner_conflict",
        "partial_invoice_owner_evidence",
        "contact_candidate_set_incomplete",
        "phone_candidate_set_incomplete",
        "address_candidate_set_incomplete",
        "duplicate_exact_phone",
        "duplicate_exact_phone_zip",
        "unique_phone_postal_conflict",
        "address_phone_conflict",
    }
)


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("999999999.99")


def _selection(result: Mapping[str, Any]) -> tuple[str, str, float]:
    resolution = result.get("customer_resolution") or {}
    number = str(
        resolution.get("customer_number") or ""
    ).strip().removesuffix(".0")
    basis = str(
        resolution.get("confidence_basis")
        or resolution.get("selection_basis")
        or ""
    )
    try:
        confidence = float(resolution.get("selected_confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    return number, basis, confidence


def _customer_number(transaction: Mapping[str, Any]) -> str:
    result = transaction.get("result") or {}
    resolution = result.get("customer_resolution") or {}
    snapshot = result.get("customer_snapshot") or {}
    fields = snapshot.get("fields") or {}
    return str(
        resolution.get("customer_number")
        or fields.get("customer_number")
        or ""
    ).strip().removesuffix(".0")


def _projection_evidence(transaction: Mapping[str, Any]) -> Mapping[str, Any]:
    source = transaction.get("source") or {}
    evidence = source.get("projection_evidence")
    if isinstance(evidence, Mapping):
        return evidence
    original = source.get("original_source") or {}
    evidence = original.get("projection_evidence")
    return evidence if isinstance(evidence, Mapping) else {}


def _matching_evidence(result: Mapping[str, Any]) -> Mapping[str, Any]:
    resolution = result.get("customer_resolution") or {}
    evidence = resolution.get("matching_evidence")
    return evidence if isinstance(evidence, Mapping) else {}


def _current_open_invoice_owner_evidence_is_deterministic(
    result: Mapping[str, Any],
) -> bool:
    """Reconcile the complete saved current-open ownership envelope.

    Broad invoice-owner discovery and contact ranking are lower-authority
    evidence.  Their ambiguity flags may remain preserved after the bounded
    current-open assessment proves that every admitted remittance invoice is
    currently open under exactly one same ERP customer.  Promotion may rely
    on that precedence only when the complete assessment payload reconciles
    to the selected customer, invoice count, owner map, and ERP source times.
    """

    resolution = result.get("customer_resolution") or {}
    candidate_customer, selection_basis, confidence = _selection(result)
    if (
        str(resolution.get("status") or "") != "resolved"
        or not candidate_customer
        or selection_basis != "unique_current_open_invoice_owner"
        or confidence < 1.0
    ):
        return False

    matching = _matching_evidence(result)
    if (
        str(matching.get("selected_basis") or "")
        != "current_open_invoice_owner"
        or str(matching.get("current_open_status") or "") != "resolved"
        or bool(matching.get("payer_account_directive_conflict"))
    ):
        return False

    assessment = result.get("customer_conflict_assessment") or {}
    if not isinstance(assessment, Mapping):
        return False
    if (
        str(assessment.get("status") or "") != "resolved"
        or str(assessment.get("customer_number") or "")
        .strip()
        .removesuffix(".0")
        != candidate_customer
        or str(assessment.get("rule_version") or "")
        != "lockbox-current-open-ar-customer-resolution@1.1.0"
        or bool(assessment.get("missing_current_open_invoices"))
        or bool(assessment.get("unavailable_customer_numbers"))
        or bool(assessment.get("can_auto_approve"))
        or bool(assessment.get("erp_write_performed"))
    ):
        return False

    remittance_invoices = tuple(
        dict.fromkeys(
            str(value or "").strip()
            for value in assessment.get("remittance_invoice_numbers") or ()
            if str(value or "").strip()
        )
    )
    if (
        not remittance_invoices
        or int(matching.get("valid_invoice_count") or 0)
        != len(remittance_invoices)
    ):
        return False

    current_owners = assessment.get("current_open_invoice_owners") or {}
    if not isinstance(current_owners, Mapping):
        return False
    normalized_owner_map = {
        str(invoice or "").strip(): tuple(
            dict.fromkeys(
                str(owner or "").strip().removesuffix(".0")
                for owner in owners or ()
                if str(owner or "").strip()
            )
        )
        for invoice, owners in current_owners.items()
        if str(invoice or "").strip()
    }
    if set(normalized_owner_map) != set(remittance_invoices):
        return False
    if any(
        owners != (candidate_customer,)
        for owners in normalized_owner_map.values()
    ):
        return False

    invoice_sources = assessment.get("current_open_invoice_sources") or {}
    ar_sources = assessment.get("current_open_ar_sources") or {}
    complete_direct_sources = bool(
        isinstance(invoice_sources, Mapping)
        and set(
            str(invoice or "").strip()
            for invoice in invoice_sources
            if str(invoice or "").strip()
        )
        == set(remittance_invoices)
        and all(
            isinstance(invoice_sources.get(invoice), Mapping)
            and str(
                invoice_sources[invoice].get("source_reference") or ""
            ).strip()
            and str(invoice_sources[invoice].get("as_of_time") or "").strip()
            for invoice in remittance_invoices
        )
    )
    complete_open_ar_source = bool(
        isinstance(ar_sources, Mapping)
        and isinstance(ar_sources.get(candidate_customer), Mapping)
        and str(
            ar_sources[candidate_customer].get("source_reference") or ""
        ).strip()
        and str(ar_sources[candidate_customer].get("as_of_time") or "").strip()
    )
    return complete_direct_sources or complete_open_ar_source


def _customer_evidence_is_deterministic(result: Mapping[str, Any]) -> bool:
    """Verify the recorded uniqueness facts for the selected customer.

    Increment 3P used one blanket 0.99 confidence threshold after customer
    resolution.  That contradicted the resolver's intentional 0.97 score for
    one complete exact phone-plus-ZIP owner when street OCR was unavailable.
    Promotion now proves the selected basis from its preserved ERP candidate
    universe instead of treating a presentation score as the ownership fact.
    """

    candidate_customer, selection_basis, confidence = _selection(result)
    if not candidate_customer or selection_basis not in PROMOTION_SELECTION_BASES:
        return False
    minimum = _CUSTOMER_EVIDENCE_MINIMUMS.get(selection_basis, 1.0)
    if confidence < minimum:
        return False

    if selection_basis == "unique_current_open_invoice_owner":
        return _current_open_invoice_owner_evidence_is_deterministic(result)

    evidence = _matching_evidence(result)
    failed_gates = {
        str(value)
        for value in evidence.get("failed_selection_gates") or ()
    }
    if failed_gates & _CUSTOMER_EVIDENCE_STOP_GATES:
        return False
    if bool(evidence.get("invoice_owner_conflict")):
        return False
    if bool(evidence.get("partial_invoice_owner_evidence")):
        return False
    if bool(evidence.get("payer_account_directive_conflict")):
        return False
    if bool(evidence.get("check_for_customer_conflict")):
        return False
    if bool(evidence.get("check_phone_number_conflict")):
        return False
    if bool(evidence.get("learned_payer_bank_account_conflict")):
        return False
    if bool(evidence.get("unique_open_ar_bucket_match_conflict")):
        return False

    if selection_basis in {
        "exact_phone_and_zip",
        "unique_phone_zip_with_address_confirmation",
    }:
        return bool(
            evidence.get("contact_candidate_complete")
            and int(evidence.get("exact_phone_postal_match_count") or 0) == 1
        )
    if selection_basis in {
        "unique_exact_phone",
        "unique_phone_with_contact_confirmation",
    }:
        return bool(
            evidence.get("phone_candidate_complete")
            and int(evidence.get("exact_phone_match_count") or 0) == 1
        )
    if selection_basis == "unique_exact_address_and_zip":
        return bool(
            evidence.get("address_candidate_complete")
            and int(evidence.get("exact_address_postal_match_count") or 0)
            == 1
        )
    if selection_basis == "payer_supplied_customer_number":
        return bool(evidence.get("payer_account_directive_verified"))
    if selection_basis == "km_statement_customer_number":
        return bool(evidence.get("km_statement_customer_verified"))
    if selection_basis == "check_for_customer_number":
        return bool(evidence.get("check_for_customer_verified"))
    if selection_basis == "check_phone_number_match":
        return bool(evidence.get("check_phone_number_verified"))
    if selection_basis == "learned_payer_bank_account_mapping":
        return bool(evidence.get("learned_payer_bank_account_verified"))
    if selection_basis == "unique_open_ar_bucket_match":
        return bool(evidence.get("unique_open_ar_bucket_match_verified"))

    # Complete invoice-owner paths already carry their own 1.0 governed
    # resolution basis.  The conflict checks above remain mandatory.
    return selection_basis in {
        "unique_current_open_invoice_owner",
        "unique_remittance_invoice_owner",
    }


def _nonmaterial_customer_conflict_fields(
    candidate: Mapping[str, Any],
) -> tuple[str, ...]:
    """Identify corroborating-field conflicts outside the ownership proof.

    Increment 3Q correctly preserved conflicts after deterministic customer
    resolution, but treated every multi-field conflict as if it challenged
    the selected ownership basis.  For an ``exact_phone_and_zip`` result, the
    complete unique phone/postal candidate universe is the ownership proof;
    payer/payee name and city are corroborating fields and cannot negate that
    proof by themselves.

    The original assertions and raw conflict list remain preserved.  Name is
    nonblocking after any existing deterministic ownership proof, matching
    Increment 3Q.  City is additionally nonblocking only for a complete,
    unique ``exact_phone_and_zip`` result.  Phone, postal, street, state,
    customer-number, invoice, completeness, uniqueness, and every other
    conflict remain material.
    """

    result = candidate.get("result") or {}
    evidence = _projection_evidence(candidate)
    conflict_fields = tuple(
        str(value)
        for value in evidence.get("customer_conflict_fields") or ()
        if str(value)
    )
    if not conflict_fields or not _customer_evidence_is_deterministic(result):
        return ()

    _, selection_basis, _ = _selection(result)
    allowed_fields = {"customer_name"}
    if selection_basis == "exact_phone_and_zip":
        allowed_fields.add("customer_city")

    nonmaterial: list[str] = []
    for field in conflict_fields:
        if field in allowed_fields:
            nonmaterial.append(field)

    return tuple(dict.fromkeys(nonmaterial))


def _recorded_customer_conflicts_are_nonmaterial(
    candidate: Mapping[str, Any],
) -> bool:
    evidence = _projection_evidence(candidate)
    conflict_fields = {
        str(value)
        for value in evidence.get("customer_conflict_fields") or ()
        if str(value)
    }
    if not conflict_fields:
        return False
    conflict_count = int(evidence.get("customer_conflict_count") or 0)
    if conflict_count != len(conflict_fields):
        return False
    return conflict_fields == set(
        _nonmaterial_customer_conflict_fields(candidate)
    )


def _name_only_payee_conflict_is_overridden(
    candidate: Mapping[str, Any],
) -> bool:
    evidence = _projection_evidence(candidate)
    conflict_fields = {
        str(value)
        for value in evidence.get("customer_conflict_fields") or ()
        if str(value)
    }
    return bool(
        conflict_fields == {"customer_name"}
        and _recorded_customer_conflicts_are_nonmaterial(candidate)
    )


def _remittance_row_disambiguation_is_verified(
    result: Mapping[str, Any],
) -> bool:
    """Verify the complete ERP-backed invoice-versus-PO evidence envelope."""

    assessment = result.get("remittance_row_disambiguation_assessment") or {}
    if not isinstance(assessment, Mapping):
        return False
    recovered_count = int(assessment.get("recovered_row_count") or 0)
    if recovered_count == 0:
        return True

    selected_customer, _, _ = _selection(result)
    recovered = assessment.get("recovered_allocations") or ()
    rows = assessment.get("row_assessments") or ()
    if not isinstance(recovered, (list, tuple)) or not isinstance(
        rows,
        (list, tuple),
    ):
        return False
    if (
        assessment.get("status") != "resolved"
        or assessment.get("rule_version")
        != "BR-LOCKBOX-041@0.7.0-wave2-increment3x"
        or not selected_customer
        or str(assessment.get("selected_customer_number") or "")
        != selected_customer
        or int(assessment.get("preserved_rejection_count") or 0)
        != recovered_count
        or int(assessment.get("unresolved_row_count") or 0) != 0
        or len(recovered) != recovered_count
        or len(rows) != recovered_count
        or not bool(assessment.get("all_rows_resolved"))
        or not bool(assessment.get("original_rejections_preserved"))
        or bool(assessment.get("can_auto_approve"))
        or bool(assessment.get("erp_write_performed"))
    ):
        return False

    selected_rows: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            return False
        match_counts = row.get("candidate_match_counts") or {}
        if not isinstance(match_counts, Mapping):
            return False
        selected_invoice = str(row.get("selected_invoice_number") or "")
        if (
            row.get("status") != "resolved"
            or row.get("rejection_reason")
            != "multiple_governed_invoice_candidates"
            or int(row.get("raw_candidate_count") or 0) < 2
            or int(row.get("governed_candidate_count") or 0) < 2
            or not selected_invoice
            or not str(row.get("selected_open_item_key") or "")
            or sum(int(value or 0) == 1 for value in match_counts.values())
            != 1
            or any(int(value or 0) > 1 for value in match_counts.values())
            or int(match_counts.get(selected_invoice) or 0) != 1
        ):
            return False
        selected_rows.append(selected_invoice)

    recovered_invoices = [
        str(row.get("invoice_number") or "")
        for row in recovered
        if isinstance(row, Mapping)
    ]
    if recovered_invoices != selected_rows:
        return False
    recovered_total = sum(
        (_money(row.get("net_invoice_amount")) for row in recovered),
        Decimal("0.00"),
    )
    return bool(
        _money(recovered_total) == _money(assessment.get("recovered_total"))
        and all(
            isinstance(row, Mapping)
            and bool(row.get("source_rejection_preserved"))
            and row.get("source_row_disambiguation_rule_version")
            == "BR-LOCKBOX-041@0.7.0-wave2-increment3x"
            for row in recovered
        )
    )


def _remittance_completion_is_verified(
    result: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> bool:
    if not _remittance_row_disambiguation_is_verified(result):
        return False
    if bool(evidence.get("remittance_evidence_complete")):
        return True
    assessment = result.get("remittance_completion_assessment") or {}
    selected_customer, _, _ = _selection(result)
    extracted_count = int(assessment.get("extracted_invoice_count") or 0)
    source_row_count = int(
        assessment.get("source_allocation_row_count") or 0
    )
    return bool(
        assessment.get("status") == "reconciled"
        and assessment.get("rule_version")
        == "BR-LOCKBOX-040@0.7.0-wave2-increment3w"
        and selected_customer
        and str(assessment.get("selected_customer_number") or "")
        == selected_customer
        and extracted_count > 0
        and source_row_count == extracted_count
        and bool(assessment.get("invoice_sets_equal"))
        and bool(assessment.get("one_source_amount_per_invoice"))
        and bool(assessment.get("one_current_open_item_per_invoice"))
        and bool(
            assessment.get("all_items_owned_by_selected_customer")
        )
        and bool(
            assessment.get(
                "source_amounts_match_full_signed_open_amounts"
            )
        )
        and assessment.get("boundary_rule") == EXPECTED_BOUNDARY_RULE
        and bool(assessment.get("boundary_closed"))
        and int(assessment.get("allocation_conflict_count") or 0) == 0
        and int(assessment.get("removed_allocation_count") or 0) == 0
        and int(assessment.get("customer_conflict_count") or 0) == 0
        and not bool(assessment.get("review_edits_used_as_extraction"))
        and bool(assessment.get("eligible_for_residual_completion"))
        and not bool(assessment.get("can_auto_approve"))
        and not bool(assessment.get("erp_write_performed"))
    )


def promotion_assessment(
    control: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> tuple[bool, tuple[str, ...]]:
    """Apply the exact control-preserving promotion gate proven by R4."""

    blockers: list[str] = []
    if str(control.get("state") or "") == "prepared_balanced":
        blockers.append("accepted_control_locked")
    if str(control.get("state") or "") == "preexisting_human_disposition":
        blockers.append("human_disposition_locked")

    candidate_state = str(candidate.get("state") or "missing")
    result = candidate.get("result") or {}
    recommendation = result.get("recommendation") or {}
    candidate_customer, _, _ = _selection(result)
    control_customer = _customer_number(control)
    method = str(recommendation.get("method") or "")
    evidence = _projection_evidence(candidate)
    row_assessment = result.get(
        "remittance_row_disambiguation_assessment"
    ) or {}

    if candidate_state != "prepared_balanced":
        blockers.append("candidate_not_balanced")
    if not candidate_customer:
        blockers.append("candidate_customer_missing")
    if control_customer and candidate_customer != control_customer:
        blockers.append("accepted_customer_conflict")
    if not _customer_evidence_is_deterministic(result):
        blockers.append("customer_evidence_not_deterministic")
    if method not in PROMOTION_METHODS:
        blockers.append("allocation_method_not_governed")
    if (
        int(row_assessment.get("recovered_row_count") or 0) > 0
        and not _remittance_row_disambiguation_is_verified(result)
    ):
        blockers.append("remittance_row_disambiguation_not_verified")
    if (
        method in {
            "exact_remittance_plus_oldest_open_items",
            "exact_remittance_plus_unique_open_item",
        }
        and not _remittance_completion_is_verified(result, evidence)
    ):
        blockers.append("residual_completion_requires_complete_remittance")
    if abs(_money(recommendation.get("difference"))) > MONEY_TOLERANCE:
        blockers.append("allocation_not_reconciled")
    if not recommendation.get("allocations"):
        blockers.append("allocation_rows_missing")
    if int(evidence.get("removed_allocation_count") or 0) != 0:
        blockers.append("source_rows_removed")
    if int(evidence.get("allocation_conflict_count") or 0) != 0:
        blockers.append("allocation_evidence_conflict")
    if (
        int(evidence.get("customer_conflict_count") or 0) != 0
        and not _recorded_customer_conflicts_are_nonmaterial(candidate)
    ):
        blockers.append("customer_evidence_conflict")
    if evidence.get("boundary_rule") != EXPECTED_BOUNDARY_RULE:
        blockers.append("incorrect_transaction_boundary")
    if not bool(evidence.get("boundary_closed")):
        blockers.append("transaction_boundary_open")
    if bool(result.get("can_auto_approve")) or bool(
        recommendation.get("can_auto_approve")
    ):
        blockers.append("automatic_approval_reported")
    if bool(result.get("erp_write_performed")):
        blockers.append("erp_write_reported")

    return not blockers, tuple(blockers)


def _supplement_review(
    control: Mapping[str, Any],
    candidate: Mapping[str, Any],
    blockers: tuple[str, ...],
    *,
    projection_version: str = PROJECTION_VERSION,
) -> tuple[dict[str, Any], bool]:
    projected = deepcopy(dict(control))
    projected["job_id"] = candidate.get("job_id")
    candidate_result = candidate.get("result") or {}
    control_result = deepcopy(control.get("result") or {})
    candidate_customer, _, _ = _selection(candidate_result)
    control_customer = _customer_number(control)
    recommendation = candidate_result.get("recommendation") or {}
    resolution = candidate_result.get("customer_resolution") or {}
    actionable = bool(
        candidate_customer
        or recommendation.get("allocations")
        or resolution.get("candidates")
    )

    if not control_customer or candidate_customer == control_customer:
        if recommendation:
            control_result["recommendation"] = deepcopy(recommendation)
        for field in (
            "source",
            "customer_resolution",
            "customer_snapshot",
            "open_ar",
            "customer_group",
            "group_open_ar",
            "remittance_completion_assessment",
            "remittance_row_disambiguation_assessment",
            "customer_conflict_assessment",
            "enterprise_group_assessment",
        ):
            if candidate_result.get(field) is not None:
                control_result[field] = deepcopy(candidate_result[field])
    control_result.pop("exception_analysis", None)
    control_result.update(
        {
            "supplemental_candidate_result": True,
            "prepared_not_approved": True,
            "can_auto_approve": False,
            "erp_write_performed": False,
            "control_projection": {
                "version": projection_version,
                "outcome": (
                    "promotion_blocked"
                    if str(candidate.get("state") or "")
                    == "prepared_balanced"
                    else "operator_assist" if actionable else "review_preserved"
                ),
                "promotion_blockers": list(blockers),
                "recommendation_not_decision": True,
            },
        }
    )
    projected["result"] = control_result
    _recompute_final_exception(
        projected,
        blockers,
        projection_version=projection_version,
    )
    return projected, actionable


def _recompute_final_exception(
    projected: dict[str, Any],
    blockers: tuple[str, ...],
    *,
    projection_version: str = PROJECTION_VERSION,
) -> None:
    """Derive one final review reason from the supplemented decision state."""

    if str(projected.get("state") or "") != "prepared_exception":
        return
    result = deepcopy(projected.get("result") or {})
    resolution = result.get("customer_resolution") or {}
    recommendation = result.get("recommendation") or {}
    resolution_status = str(resolution.get("status") or "")
    allocation_status = str(recommendation.get("status") or "")
    difference = _money(recommendation.get("difference"))
    projection = result.get("control_projection") or {}
    promotion_blocked = (
        projection.get("outcome") == "promotion_blocked" and bool(blockers)
    )

    if promotion_blocked:
        stage = "control_projection"
        message = (
            "A balanced candidate remained in review because protected "
            "projection evidence gates were not satisfied."
        )
    elif resolution_status != "resolved":
        stage = "customer_resolution"
        message = "Final customer evidence still requires professional review."
    else:
        stage = "allocation_evaluation"
        message = (
            "The customer was resolved, but the final governed allocation "
            "did not reconcile exactly."
        )

    error = {
        "type": "PreparationPolicyError",
        "message": message,
        "stage": stage,
        "retry_eligible": False,
    }
    projected["error"] = error
    analysis = classify_exception(
        state="prepared_exception",
        source=projected.get("source") or {},
        result=result,
        error=error,
    )
    result["exception_analysis"] = analysis
    result["final_decision_state"] = {
        "version": projection_version,
        "review_required": True,
        "customer_resolution_status": resolution_status,
        "selected_customer_number": str(
            resolution.get("customer_number") or ""
        ),
        "selected_confidence": resolution.get("selected_confidence"),
        "selection_basis": (
            resolution.get("confidence_basis")
            or resolution.get("selection_basis")
            or ""
        ),
        "allocation_status": allocation_status,
        "allocation_method": str(recommendation.get("method") or ""),
        "allocation_difference": str(difference),
        "primary_reason_code": str(
            ((analysis or {}).get("primary_reason") or {}).get("code") or ""
        ),
        "projection_blockers": list(blockers),
        "prepared_not_approved": True,
        "can_auto_approve": False,
        "erp_write_performed": False,
    }
    projected["result"] = result


def apply_control_projection(
    control_snapshot: Mapping[str, Any],
    candidate_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Project candidate improvements over immutable accepted control state."""

    control = deepcopy(dict(control_snapshot))
    candidate = deepcopy(dict(candidate_snapshot))
    control_transactions = list(control.get("transactions") or [])
    candidate_transactions = list(candidate.get("transactions") or [])
    control_by_id = {
        str(item.get("transaction_id") or ""): item
        for item in control_transactions
    }
    candidate_by_id = {
        str(item.get("transaction_id") or ""): item
        for item in candidate_transactions
    }

    control_balanced = int(control.get("balanced_count") or 0)
    control_review = int(control.get("exception_count") or 0)
    exact_control = bool(
        control.get("rule_version") == CONTROL_RULE_VERSION
        and control.get("service_version") == CONTROL_SERVICE_VERSION
        and control.get("state") == "complete"
        and control.get("complete")
        and int(control.get("expected_count") or 0)
        == EXPECTED_TRANSACTION_COUNT
        and int(control.get("terminal_count") or 0)
        == EXPECTED_TRANSACTION_COUNT
        and control_balanced == ACCEPTED_BALANCED_COUNT
        and control_review == ACCEPTED_REVIEW_COUNT
    )
    exact_candidate_coverage = bool(
        candidate.get("state") == "complete"
        and candidate.get("complete")
        and len(candidate_by_id) == EXPECTED_TRANSACTION_COUNT
        and set(candidate_by_id) == set(control_by_id)
    )
    if not exact_control:
        raise RuntimeError(
            "The exact accepted Increment 3F R1 78/30/48 control was not "
            "available for Increment 3I projection."
        )
    if not exact_candidate_coverage:
        raise RuntimeError(
            "Increment 3I candidate coverage did not exactly match all 78 "
            "accepted control transactions."
        )

    projected_transactions: list[dict[str, Any]] = []
    admitted = 0
    blocked = 0
    operator_assists = 0
    raw_regressions = 0
    control_balances_preserved = 0
    projected_customers_preserved = True
    source_rows_preserved = True
    boundary_safe = True
    automatic_approval_safe = True
    erp_write_safe = True
    signed_credit_safe = True

    for control_transaction in control_transactions:
        transaction_id = str(control_transaction.get("transaction_id") or "")
        candidate_transaction = candidate_by_id[transaction_id]
        control_state = str(control_transaction.get("state") or "")
        candidate_state = str(candidate_transaction.get("state") or "")
        if control_state == "prepared_balanced" and candidate_state != "prepared_balanced":
            raw_regressions += 1

        evidence = _projection_evidence(candidate_transaction)
        source_rows_preserved = source_rows_preserved and int(
            evidence.get("removed_allocation_count") or 0
        ) == 0
        boundary_safe = boundary_safe and bool(
            evidence.get("boundary_rule") == EXPECTED_BOUNDARY_RULE
            and evidence.get("boundary_closed")
        )
        candidate_result = candidate_transaction.get("result") or {}
        candidate_recommendation = candidate_result.get("recommendation") or {}
        automatic_approval_safe = automatic_approval_safe and not bool(
            candidate_result.get("can_auto_approve")
            or candidate_recommendation.get("can_auto_approve")
        )
        erp_write_safe = erp_write_safe and not bool(
            candidate_result.get("erp_write_performed")
        )
        for allocation in candidate_recommendation.get("allocations") or []:
            if str(allocation.get("business_type") or "") == "Credit":
                signed_credit_safe = signed_credit_safe and _money(
                    allocation.get("apply_amount")
                ) <= 0

        if control_state in {
            "prepared_balanced",
            "preexisting_human_disposition",
        }:
            projected = deepcopy(control_transaction)
            projected["job_id"] = candidate.get("job_id")
            result = deepcopy(projected.get("result") or {})
            result["control_projection"] = {
                "version": PROJECTION_VERSION,
                "outcome": (
                    "control_preserved"
                    if control_state == "prepared_balanced"
                    else "human_disposition_preserved"
                ),
                "recommendation_not_decision": True,
            }
            projected["result"] = result
            if control_state == "prepared_balanced":
                control_balances_preserved += 1
        else:
            promotion_admitted, blockers = promotion_assessment(
                control_transaction,
                candidate_transaction,
            )
            if promotion_admitted:
                projected = deepcopy(candidate_transaction)
                result = deepcopy(projected.get("result") or {})
                result["control_projection"] = {
                    "version": PROJECTION_VERSION,
                    "outcome": "promotion_admitted",
                    "promotion_blockers": [],
                    "customer_evidence_verified": True,
                    "nonmaterial_customer_conflict_fields": list(
                        _nonmaterial_customer_conflict_fields(
                            candidate_transaction
                        )
                    ),
                    "name_only_payee_conflict_overridden": (
                        _name_only_payee_conflict_is_overridden(
                            candidate_transaction
                        )
                    ),
                    "recommendation_not_decision": True,
                }
                result["can_auto_approve"] = False
                result["erp_write_performed"] = False
                projected["result"] = result
                admitted += 1
            else:
                if candidate_state == "prepared_balanced":
                    blocked += 1
                projected, actionable = _supplement_review(
                    control_transaction,
                    candidate_transaction,
                    blockers,
                )
                operator_assists += int(
                    actionable and candidate_state != "prepared_balanced"
                )

        projected["projection_control_job_id"] = control.get("job_id")
        projected["projection_candidate_job_id"] = candidate.get("job_id")
        projected_transactions.append(projected)
        control_customer = _customer_number(control_transaction)
        if control_customer and control_customer != _customer_number(projected):
            projected_customers_preserved = False

    balanced_count = sum(
        str(item.get("state") or "") == "prepared_balanced"
        for item in projected_transactions
    )
    exception_count = sum(
        str(item.get("state") or "") == "prepared_exception"
        for item in projected_transactions
    )
    preserved_count = sum(
        str(item.get("state") or "") == "preexisting_human_disposition"
        for item in projected_transactions
    )
    raw_balanced = int(candidate.get("balanced_count") or 0)
    gates = {
        "accepted_control_counts": exact_control,
        "full_transaction_coverage": exact_candidate_coverage,
        "protected_projection_keeps_all_control_balances": (
            control_balances_preserved == ACCEPTED_BALANCED_COUNT
        ),
        "protected_projection_preserves_all_control_customers": (
            projected_customers_preserved
        ),
        "human_dispositions_never_overridden": True,
        "raw_candidate_regressions_never_enter_projection": (
            balanced_count >= ACCEPTED_BALANCED_COUNT
        ),
        "accepted_increment3q_projection_preserved": (
            balanced_count >= PRIOR_PROJECTED_BALANCED_FLOOR
            and exception_count <= PRIOR_PROJECTED_REVIEW_CEILING
        ),
        "promotions_apply_only_to_control_reviews": True,
        "all_promotions_pass_strict_evidence_gate": True,
        "admitted_source_rows_never_disappear": source_rows_preserved,
        "next_transaction_boundary_only": boundary_safe,
        "candidate_balances_reconcile_exactly": all(
            str(item.get("state") or "") != "prepared_balanced"
            or abs(
                _money(
                    ((item.get("result") or {}).get("recommendation") or {}).get(
                        "difference"
                    )
                )
            )
            <= MONEY_TOLERANCE
            for item in candidate_transactions
        ),
        "admitted_promotions_reconcile_exactly": all(
            str(item.get("state") or "") != "prepared_balanced"
            or abs(
                _money(
                    ((item.get("result") or {}).get("recommendation") or {}).get(
                        "difference"
                    )
                )
            )
            <= MONEY_TOLERANCE
            for item in projected_transactions
            if ((item.get("result") or {}).get("control_projection") or {}).get(
                "outcome"
            )
            == "promotion_admitted"
        ),
        "signed_credits_remain_negative": signed_credit_safe,
        "recommendation_never_auto_approves": automatic_approval_safe,
        "no_erp_write_reported": erp_write_safe,
        "human_review_not_used_as_extraction": all(
            not bool(_projection_evidence(item).get("review_edits_used_as_extraction"))
            for item in candidate_transactions
        ),
    }
    if not all(gates.values()):
        failed = ", ".join(name for name, passed in gates.items() if not passed)
        raise RuntimeError(
            "Increment 3I control projection failed closed: " + failed
        )

    candidate.update(
        {
            "transactions": projected_transactions,
            "balanced_count": balanced_count,
            "exception_count": exception_count,
            "preserved_count": preserved_count,
            "terminal_count": len(projected_transactions),
            "final_exception_count": exception_count,
            "exception_reason_summary": build_exception_summary(
                projected_transactions
            ),
            "control_projection_version": PROJECTION_VERSION,
            "control_job_id": control.get("job_id"),
            "control_rule_version": CONTROL_RULE_VERSION,
            "control_service_version": CONTROL_SERVICE_VERSION,
            "raw_candidate_balanced_count": raw_balanced,
            "raw_candidate_exception_count": int(
                candidate_snapshot.get("exception_count") or 0
            ),
            "projected_balanced_count": balanced_count,
            "projected_review_count": exception_count,
            "admitted_promotion_count": admitted,
            "blocked_promotion_count": blocked,
            "operator_assisted_review_count": operator_assists,
            "raw_candidate_regressions_contained": raw_regressions,
            "projected_regression_count": 0,
            "projection_release_gates": gates,
            "projection_eligible": True,
            "recommendation_not_decision": True,
            "can_auto_approve": False,
            "erp_write_performed": False,
        }
    )
    return candidate


def _fresh_source_review_control(
    candidate_transaction: Mapping[str, Any],
) -> dict[str, Any]:
    """Create an in-memory review floor without changing stored evidence."""

    control = deepcopy(dict(candidate_transaction))
    control["state"] = "prepared_exception"
    control["result"] = {}
    control["error"] = {
        "type": "FreshSourceReviewFloor",
        "message": (
            "A new source begins in professional review before deterministic "
            "promotion gates are evaluated."
        ),
        "stage": "fresh_source_projection",
        "retry_eligible": False,
    }
    return control


def apply_fresh_source_projection(
    candidate_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Create the first governed projection for one new immutable PDF.

    A fresh source cannot use the accepted 78-transaction control because
    source job and PDF hash are part of the control identity. Instead every
    non-human transaction starts from an in-memory review floor. Only a raw
    ``prepared_balanced`` candidate that passes ``promotion_assessment`` may
    enter the prepared-and-balanced projection. Stored candidate rows and
    events remain unchanged.
    """

    candidate = deepcopy(dict(candidate_snapshot))
    candidate_transactions = list(candidate.get("transactions") or [])
    expected_count = int(candidate.get("expected_count") or 0)
    terminal_count = int(candidate.get("terminal_count") or 0)
    transaction_ids = [
        str(item.get("transaction_id") or "")
        for item in candidate_transactions
    ]
    terminal_states = {
        "prepared_balanced",
        "prepared_exception",
        "preexisting_human_disposition",
    }
    raw_state_counts = {
        state: sum(
            str(item.get("state") or "") == state
            for item in candidate_transactions
        )
        for state in terminal_states
    }
    full_candidate_coverage = bool(
        candidate.get("state") == "complete"
        and candidate.get("complete")
        and expected_count > 0
        and terminal_count == expected_count
        and len(candidate_transactions) == expected_count
        and len(set(transaction_ids)) == expected_count
        and all(transaction_ids)
        and all(
            str(item.get("state") or "") in terminal_states
            for item in candidate_transactions
        )
        and sum(raw_state_counts.values()) == expected_count
        and int(candidate.get("balanced_count") or 0)
        == raw_state_counts["prepared_balanced"]
        and int(candidate.get("exception_count") or 0)
        == raw_state_counts["prepared_exception"]
        and int(candidate.get("preserved_count") or 0)
        == raw_state_counts["preexisting_human_disposition"]
    )
    if not full_candidate_coverage:
        raise RuntimeError(
            "Fresh-source projection requires one complete, reconciled "
            "terminal candidate for every extracted transaction."
        )

    projected_transactions: list[dict[str, Any]] = []
    admitted = 0
    blocked = 0
    operator_assists = 0
    automatic_approval_safe = True
    erp_write_safe = True
    human_review_not_extraction = True

    for candidate_transaction in candidate_transactions:
        candidate_state = str(candidate_transaction.get("state") or "")
        candidate_result = candidate_transaction.get("result") or {}
        recommendation = candidate_result.get("recommendation") or {}
        evidence = _projection_evidence(candidate_transaction)
        automatic_approval_safe = automatic_approval_safe and not bool(
            candidate_result.get("can_auto_approve")
            or recommendation.get("can_auto_approve")
        )
        erp_write_safe = erp_write_safe and not bool(
            candidate_result.get("erp_write_performed")
        )
        human_review_not_extraction = (
            human_review_not_extraction
            and not bool(evidence.get("review_edits_used_as_extraction"))
        )

        if candidate_state == "preexisting_human_disposition":
            projected = deepcopy(candidate_transaction)
            result = deepcopy(projected.get("result") or {})
            result["control_projection"] = {
                "version": FRESH_SOURCE_PROJECTION_VERSION,
                "mode": "fresh_source_initial",
                "outcome": "human_disposition_preserved",
                "recommendation_not_decision": True,
            }
            result["can_auto_approve"] = False
            result["erp_write_performed"] = False
            projected["result"] = result
        elif candidate_state == "prepared_exception":
            # The candidate is already on the required fresh-source review
            # floor. Preserve its terminal error and versioned exception
            # analysis exactly; rebuilding it from an empty synthetic control
            # discards the measured reason and can falsely relabel an ordinary
            # professional-review item as a technical preparation failure.
            projected = deepcopy(candidate_transaction)
            result = deepcopy(projected.get("result") or {})
            result["control_projection"] = {
                "version": FRESH_SOURCE_PROJECTION_VERSION,
                "mode": "fresh_source_initial",
                "outcome": "review_preserved",
                "promotion_blockers": [],
                "recommendation_not_decision": True,
            }
            result["can_auto_approve"] = False
            result["erp_write_performed"] = False
            projected["result"] = result
            preserved_customer, _, _ = _selection(result)
            preserved_resolution = result.get("customer_resolution") or {}
            preserved_recommendation = result.get("recommendation") or {}
            operator_assists += int(
                bool(
                    preserved_customer
                    or preserved_recommendation.get("allocations")
                    or preserved_resolution.get("candidates")
                )
            )
        else:
            review_control = _fresh_source_review_control(
                candidate_transaction
            )
            promotion_admitted, blockers = promotion_assessment(
                review_control,
                candidate_transaction,
            )
            if promotion_admitted:
                projected = deepcopy(candidate_transaction)
                result = deepcopy(projected.get("result") or {})
                result["control_projection"] = {
                    "version": FRESH_SOURCE_PROJECTION_VERSION,
                    "mode": "fresh_source_initial",
                    "outcome": "promotion_admitted",
                    "promotion_blockers": [],
                    "customer_evidence_verified": True,
                    "nonmaterial_customer_conflict_fields": list(
                        _nonmaterial_customer_conflict_fields(
                            candidate_transaction
                        )
                    ),
                    "name_only_payee_conflict_overridden": (
                        _name_only_payee_conflict_is_overridden(
                            candidate_transaction
                        )
                    ),
                    "recommendation_not_decision": True,
                }
                result["can_auto_approve"] = False
                result["erp_write_performed"] = False
                projected["result"] = result
                admitted += 1
            else:
                if candidate_state == "prepared_balanced":
                    blocked += 1
                projected, actionable = _supplement_review(
                    review_control,
                    candidate_transaction,
                    blockers,
                    projection_version=FRESH_SOURCE_PROJECTION_VERSION,
                )
                projection = (
                    (projected.get("result") or {}).get(
                        "control_projection"
                    )
                    or {}
                )
                projection["mode"] = "fresh_source_initial"
                operator_assists += int(
                    actionable and candidate_state != "prepared_balanced"
                )

        projected["projection_control_job_id"] = ""
        projected["projection_candidate_job_id"] = candidate.get("job_id")
        projected_transactions.append(projected)

    balanced_count = sum(
        str(item.get("state") or "") == "prepared_balanced"
        for item in projected_transactions
    )
    exception_count = sum(
        str(item.get("state") or "") == "prepared_exception"
        for item in projected_transactions
    )
    preserved_count = sum(
        str(item.get("state") or "")
        == "preexisting_human_disposition"
        for item in projected_transactions
    )
    admitted_transactions = [
        item
        for item in projected_transactions
        if (
            ((item.get("result") or {}).get("control_projection") or {}).get(
                "outcome"
            )
            == "promotion_admitted"
        )
    ]
    admitted_source_rows_safe = all(
        int(_projection_evidence(item).get("removed_allocation_count") or 0)
        == 0
        for item in admitted_transactions
    )
    admitted_boundaries_safe = all(
        _projection_evidence(item).get("boundary_rule")
        == EXPECTED_BOUNDARY_RULE
        and bool(_projection_evidence(item).get("boundary_closed"))
        for item in admitted_transactions
    )
    admitted_credits_safe = all(
        _money(allocation.get("apply_amount")) <= 0
        for item in admitted_transactions
        for allocation in (
            ((item.get("result") or {}).get("recommendation") or {}).get(
                "allocations"
            )
            or []
        )
        if str(allocation.get("business_type") or "") == "Credit"
    )
    admitted_balances_reconcile = all(
        abs(
            _money(
                ((item.get("result") or {}).get("recommendation") or {}).get(
                    "difference"
                )
            )
        )
        <= MONEY_TOLERANCE
        for item in admitted_transactions
    )
    gates = {
        "fresh_source_identity_not_borrowed": True,
        "full_transaction_coverage": full_candidate_coverage,
        "all_nonhuman_transactions_begin_in_review": True,
        "all_balances_pass_strict_evidence_gate": (
            balanced_count == admitted
        ),
        "admitted_source_rows_never_disappear": admitted_source_rows_safe,
        "admitted_next_transaction_boundary_only": (
            admitted_boundaries_safe
        ),
        "admitted_balances_reconcile_exactly": (
            admitted_balances_reconcile
        ),
        "admitted_signed_credits_remain_negative": admitted_credits_safe,
        "recommendation_never_auto_approves": automatic_approval_safe,
        "no_erp_write_reported": erp_write_safe,
        "human_review_not_used_as_extraction": human_review_not_extraction,
    }
    if not all(gates.values()):
        failed = ", ".join(
            name for name, passed in gates.items() if not passed
        )
        raise RuntimeError(
            "Fresh-source projection failed closed: " + failed
        )

    candidate.update(
        {
            "transactions": projected_transactions,
            "balanced_count": balanced_count,
            "exception_count": exception_count,
            "preserved_count": preserved_count,
            "terminal_count": len(projected_transactions),
            "final_exception_count": exception_count,
            "exception_reason_summary": build_exception_summary(
                projected_transactions
            ),
            "control_projection_version": (
                FRESH_SOURCE_PROJECTION_VERSION
            ),
            "projection_mode": "fresh_source_initial",
            "control_job_id": "",
            "control_rule_version": "",
            "control_service_version": "",
            "raw_candidate_balanced_count": int(
                candidate_snapshot.get("balanced_count") or 0
            ),
            "raw_candidate_exception_count": int(
                candidate_snapshot.get("exception_count") or 0
            ),
            "projected_balanced_count": balanced_count,
            "projected_review_count": exception_count,
            "admitted_promotion_count": admitted,
            "blocked_promotion_count": blocked,
            "operator_assisted_review_count": operator_assists,
            "projected_regression_count": 0,
            "projection_release_gates": gates,
            "projection_eligible": True,
            "recommendation_not_decision": True,
            "can_auto_approve": False,
            "erp_write_performed": False,
        }
    )
    return candidate
