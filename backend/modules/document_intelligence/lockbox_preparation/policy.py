"""Deterministic allocation and signed-credit policy.

This module carries only the approved proof-of-concept rules. It creates a
recommendation, never a human disposition, approval, export, or ERP action.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping

from invoice_number_rules import normalize_erp_invoice

from .contracts import (
    AllocationLine,
    AllocationRecommendation,
    EffectiveInvoice,
    OpenInvoice,
)
from .errors import PreparationPolicyError


RULE_VERSION = "ADR-001@0.7.0-wave2-increment4a+BR-LOCKBOX-001..044"
REMITTANCE_RECONCILIATION_RULE_VERSION = (
    "BR-LOCKBOX-040@0.7.0-wave2-increment3w"
)
REMITTANCE_ROW_DISAMBIGUATION_RULE_VERSION = (
    "BR-LOCKBOX-041@0.7.0-wave2-increment3x"
)
AMOUNT_TOLERANCE = Decimal("0.01")
_CENT = Decimal("0.01")
_CREDIT_TYPES = {
    "C",
    "CR",
    "CREDIT",
    "CREDIT MEMO",
    "CREDIT ADJUSTMENT",
}
_DEBIT_TYPES = {"D", "DR", "DEBIT"}
_DUE_DATE_COMBINATION_STATE_LIMIT = 50_000


def money(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)


normalize_invoice = normalize_erp_invoice


def effective_invoice(invoice: OpenInvoice) -> EffectiveInvoice:
    raw_type = " ".join(invoice.raw_transaction_type.upper().split())
    signed_source = (
        money(invoice.signed_source_amount)
        if invoice.signed_source_amount is not None
        else money(invoice.open_amount)
    )
    open_amount = money(invoice.open_amount)
    negative_debit = raw_type in _DEBIT_TYPES and signed_source < 0
    is_credit = (
        raw_type in _CREDIT_TYPES
        or negative_debit
        or signed_source < 0
    )
    effective_amount = (
        -abs(open_amount)
        if is_credit
        else abs(open_amount)
    )
    raw_identifier = str(invoice.invoice_number or "").strip()
    normalized_identifier = normalize_invoice(raw_identifier)
    allocation_kind = (
        "service_charge"
        if raw_type == "SC"
        else "invoice"
    )
    open_item_key = invoice.open_item_key or "|".join(
        (
            invoice.customer_number,
            raw_type,
            raw_identifier,
            str(invoice.invoice_count or ""),
        )
    )
    return EffectiveInvoice(
        customer_number=invoice.customer_number,
        invoice_number=raw_identifier,
        open_amount=open_amount,
        effective_amount=effective_amount,
        due_date=invoice.due_date,
        invoice_date=invoice.invoice_date,
        raw_transaction_type=invoice.raw_transaction_type,
        business_type="Credit" if is_credit else "Debit",
        negative_debit_credit=negative_debit,
        aging_bucket=invoice.aging_bucket,
        source_reference=invoice.source_reference,
        normalized_invoice_number=normalized_identifier,
        invoice_count=invoice.invoice_count,
        open_item_key=open_item_key,
        allocation_kind=allocation_kind,
    )


def validate_application(
    invoice: EffectiveInvoice,
    apply_amount: Decimal | str | int | float,
) -> Decimal:
    amount = money(apply_amount)
    if invoice.business_type == "Credit" and amount > 0:
        raise PreparationPolicyError(
            f"ERP-derived credit {invoice.invoice_number} cannot have a "
            "positive application amount."
        )
    return amount


def _line(invoice: EffectiveInvoice, reason: str) -> AllocationLine:
    amount = validate_application(invoice, invoice.effective_amount)
    return AllocationLine(
        customer_number=invoice.customer_number,
        invoice_number=invoice.invoice_number,
        open_amount=invoice.effective_amount,
        apply_amount=amount,
        due_date=invoice.due_date,
        invoice_date=invoice.invoice_date,
        raw_transaction_type=invoice.raw_transaction_type,
        business_type=invoice.business_type,
        negative_debit_credit=invoice.negative_debit_credit,
        aging_bucket=invoice.aging_bucket,
        source_reference=invoice.source_reference,
        reason=reason,
        normalized_invoice_number=invoice.normalized_invoice_number,
        invoice_count=invoice.invoice_count,
        open_item_key=invoice.open_item_key,
        allocation_kind=invoice.allocation_kind,
    )


def _recommendation(
    *,
    check_amount: Decimal,
    method: str,
    invoices: Iterable[EffectiveInvoice],
    reason: str,
    warnings: tuple[str, ...] = (),
) -> AllocationRecommendation:
    allocations = tuple(_line(invoice, reason) for invoice in invoices)
    suggested_total = money(
        sum(
            (line.apply_amount for line in allocations),
            Decimal("0.00"),
        )
    )
    difference = money(check_amount - suggested_total)
    return AllocationRecommendation(
        status="recommended",
        method=method,
        allocations=allocations,
        check_amount=check_amount,
        suggested_total=suggested_total,
        difference=difference,
        reasons=(reason,),
        warnings=warnings,
        can_auto_approve=False,
    )


def _partial_recommendation(
    *,
    check_amount: Decimal,
    method: str,
    invoices: Iterable[EffectiveInvoice],
    reason: str,
    warning: str,
) -> AllocationRecommendation:
    proposed = _recommendation(
        check_amount=check_amount,
        method=method,
        invoices=invoices,
        reason=reason,
        warnings=(warning,),
    )
    return AllocationRecommendation(
        status="review_required",
        method=proposed.method,
        allocations=proposed.allocations,
        check_amount=proposed.check_amount,
        suggested_total=proposed.suggested_total,
        difference=proposed.difference,
        reasons=proposed.reasons,
        warnings=proposed.warnings,
        can_auto_approve=False,
    )


def _eligible_open_items(
    invoices: Iterable[EffectiveInvoice],
) -> tuple[EffectiveInvoice, ...]:
    return tuple(
        invoice
        for invoice in invoices
        if invoice.normalized_invoice_number
        or invoice.allocation_kind == "service_charge"
    )


def _invoice_total(invoices: Iterable[EffectiveInvoice]) -> Decimal:
    return money(
        sum(
            (invoice.effective_amount for invoice in invoices),
            Decimal("0.00"),
        )
    )


def _oldest_prefix_matches(
    invoices: Iterable[EffectiveInvoice],
    target: Decimal,
) -> list[tuple[EffectiveInvoice, ...]]:
    ordered = sorted(
        invoices,
        key=lambda invoice: (
            invoice.due_date or date.max,
            invoice.invoice_date or date.max,
            invoice.normalized_invoice_number,
            invoice.invoice_number,
            invoice.invoice_count or 0,
            invoice.open_item_key,
        ),
    )
    matches: list[tuple[EffectiveInvoice, ...]] = []
    prefix: list[EffectiveInvoice] = []
    for invoice in ordered:
        prefix.append(invoice)
        if abs(_invoice_total(prefix) - target) <= AMOUNT_TOLERANCE:
            matches.append(tuple(prefix))
    return matches


def _unique_complete_due_date_group_combination(
    invoices: Iterable[EffectiveInvoice],
    target: Decimal,
) -> tuple[tuple[date, ...], tuple[EffectiveInvoice, ...]] | None:
    """Return one unique exact combination of complete due-date groups.

    Each due date is indivisible: every eligible signed debit, credit, and
    service charge on a selected date is included.  Dynamic programming keeps
    one representative for each reachable cent total and marks totals with
    multiple distinct group combinations as ambiguous.  The state limit fails
    closed instead of allowing an unbounded subset search.

    A combination may contain one or more complete due-date groups. This is
    required in the over-inclusive-remittance path, which returns before the
    later general ``same_due_date_exact_match`` fallback is reached.
    """

    grouped: dict[date, list[EffectiveInvoice]] = defaultdict(list)
    for invoice in invoices:
        if invoice.due_date is None:
            continue
        if not (
            invoice.normalized_invoice_number
            or invoice.allocation_kind == "service_charge"
        ):
            continue
        grouped[invoice.due_date].append(invoice)

    groups = [
        (
            due_date,
            tuple(
                sorted(
                    group,
                    key=lambda invoice: (
                        invoice.invoice_date or date.max,
                        invoice.normalized_invoice_number,
                        invoice.invoice_number,
                        invoice.invoice_count or 0,
                        invoice.open_item_key,
                    ),
                )
            ),
        )
        for due_date, group in sorted(grouped.items())
        if group
    ]
    if len(groups) < 2:
        return None

    group_cents = [
        int(_invoice_total(group) * 100)
        for _, group in groups
    ]
    target_cents = int(money(target) * 100)
    ambiguous = object()
    states: dict[int, tuple[int, ...] | None] = {0: ()}

    for index, group_total in enumerate(group_cents):
        updated = dict(states)
        for subtotal, combination in states.items():
            candidate = (
                None
                if combination is None
                else (*combination, index)
            )
            combined_total = subtotal + group_total
            existing = updated.get(combined_total, ambiguous)
            if existing is ambiguous:
                updated[combined_total] = candidate
            elif existing != candidate:
                updated[combined_total] = None
        if len(updated) > _DUE_DATE_COMBINATION_STATE_LIMIT:
            return None
        states = updated

    combination = states.get(target_cents)
    if combination is None or len(combination) < 1:
        return None

    selected_dates = tuple(groups[index][0] for index in combination)
    selected_invoices = tuple(
        invoice
        for index in combination
        for invoice in groups[index][1]
    )
    return selected_dates, selected_invoices


def disambiguate_remittance_rows(
    *,
    selected_customer_number: str,
    rejected_candidates: Iterable[Mapping[str, Any]],
    open_invoices: Iterable[OpenInvoice],
) -> dict[str, Any]:
    """Resolve invoice-versus-PO rows only through exact current ERP facts.

    A remittance row may contain both K&M's invoice number and the payer's
    purchase-order number. Both can satisfy the structural 8/9-digit rule, so
    the parser correctly retains the row as ambiguous. After one ERP customer
    is resolved and its complete current open A/R is loaded, this rule may
    select a candidate only when exactly one row number identifies exactly one
    ordinary open item for that same customer and its full signed open amount
    equals the preserved remittance payment amount.

    The original raw candidates and rejection remain immutable evidence.
    Duplicate ERP rows, multiple matching candidates, amount differences,
    credits with the wrong sign, service charges, other customers, invalid
    rows, and any non-ambiguous rejection remain unresolved.
    """

    customer_number = str(selected_customer_number or "").strip()
    effective_open = tuple(
        effective_invoice(invoice) for invoice in open_invoices
    )
    open_by_number: dict[str, list[EffectiveInvoice]] = defaultdict(list)
    for invoice in effective_open:
        if (
            invoice.customer_number == customer_number
            and invoice.allocation_kind == "invoice"
            and invoice.normalized_invoice_number
        ):
            open_by_number[invoice.normalized_invoice_number].append(invoice)

    rows: list[Mapping[str, Any]] = []
    seen_rows: set[tuple[tuple[str, ...], Decimal, str, str]] = set()
    for raw in rejected_candidates:
        row = raw if isinstance(raw, Mapping) else {}
        raw_candidates = tuple(
            dict.fromkeys(
                str(value or "").strip()
                for value in row.get("raw_invoice_candidates", ())
                if str(value or "").strip()
            )
        )
        try:
            row_amount = money(row.get("net_invoice_amount"))
        except Exception:
            row_amount = Decimal("0.00")
        key = (
            raw_candidates,
            row_amount,
            str(row.get("invoice_page") or ""),
            str(row.get("reason") or ""),
        )
        if key in seen_rows:
            continue
        seen_rows.add(key)
        rows.append(row)

    recovered: list[dict[str, Any]] = []
    row_assessments: list[dict[str, Any]] = []
    unresolved_count = 0
    for row_index, row in enumerate(rows):
        reason = str(row.get("reason") or "")
        raw_candidates = tuple(
            dict.fromkeys(
                str(value or "").strip()
                for value in row.get("raw_invoice_candidates", ())
                if str(value or "").strip()
            )
        )
        governed_candidates = tuple(
            dict.fromkeys(
                invoice
                for value in raw_candidates
                if (invoice := normalize_invoice(value))
            )
        )
        try:
            row_amount = money(row.get("net_invoice_amount"))
        except Exception:
            row_amount = Decimal("0.00")

        matching_items: dict[str, EffectiveInvoice] = {}
        candidate_match_counts: dict[str, int] = {}
        if reason == "multiple_governed_invoice_candidates" and row_amount:
            for candidate in governed_candidates:
                matches = tuple(
                    invoice
                    for invoice in open_by_number.get(candidate, ())
                    if invoice.effective_amount == row_amount
                )
                candidate_match_counts[candidate] = len(matches)
                if len(matches) == 1:
                    matching_items[matches[0].open_item_key] = matches[0]

        selected = (
            next(iter(matching_items.values()))
            if len(matching_items) == 1
            else None
        )
        if selected is None:
            unresolved_count += 1
        else:
            recovered.append(
                {
                    "invoice_number": selected.normalized_invoice_number,
                    "net_invoice_amount": str(row_amount),
                    "invoice_page": str(row.get("invoice_page") or ""),
                    "confidence": 1.0,
                    "raw_invoice_candidates": list(raw_candidates),
                    "extraction_source": str(
                        row.get("extraction_source") or "preserved_source"
                    ),
                    "ocr_psm": row.get("ocr_psm"),
                    "source_row_disambiguation_rule_version": (
                        REMITTANCE_ROW_DISAMBIGUATION_RULE_VERSION
                    ),
                    "source_rejection_preserved": True,
                }
            )
        row_assessments.append(
            {
                "row_index": row_index,
                "invoice_page": str(row.get("invoice_page") or ""),
                "rejection_reason": reason,
                "raw_candidate_count": len(raw_candidates),
                "governed_candidate_count": len(governed_candidates),
                "candidate_match_counts": candidate_match_counts,
                "preserved_payment_amount": str(row_amount),
                "status": "resolved" if selected is not None else "unresolved",
                "selected_invoice_number": (
                    selected.normalized_invoice_number if selected else ""
                ),
                "selected_open_item_key": (
                    selected.open_item_key if selected else ""
                ),
            }
        )

    complete = bool(rows and recovered and unresolved_count == 0)
    recovered_total = money(
        sum(
            (money(row["net_invoice_amount"]) for row in recovered),
            Decimal("0.00"),
        )
    )
    return {
        "status": "resolved" if complete else "not_resolved",
        "rule_version": REMITTANCE_ROW_DISAMBIGUATION_RULE_VERSION,
        "selected_customer_number": customer_number,
        "preserved_rejection_count": len(rows),
        "recovered_row_count": len(recovered),
        "unresolved_row_count": unresolved_count,
        "recovered_total": str(recovered_total),
        "recovered_allocations": recovered,
        "row_assessments": row_assessments,
        "all_rows_resolved": complete,
        "original_rejections_preserved": True,
        "recommendation_not_decision": True,
        "can_auto_approve": False,
        "erp_write_performed": False,
    }


def assess_remittance_reconciliation(
    *,
    selected_customer_number: str,
    extracted_invoice_numbers: Iterable[object],
    open_invoices: Iterable[OpenInvoice],
    remittance_allocations: Iterable[Mapping[str, Any]],
    projection_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Prove admitted remit rows against one complete current ERP account.

    This is not a parser-completeness shortcut. It permits the residual rule
    to proceed only when every admitted source row is present exactly once,
    carries its preserved amount, maps to exactly one current open item under
    the selected customer, and matches that item's full signed open amount.
    Source conflicts, row loss, editable-review input, and an open or incorrect
    transaction boundary remain fail-closed.
    """

    customer_number = str(selected_customer_number or "").strip()
    normalized_candidates = tuple(
        dict.fromkeys(
            invoice
            for value in extracted_invoice_numbers
            if (invoice := normalize_invoice(value))
        )
    )
    source_amounts: dict[str, list[Decimal]] = defaultdict(list)
    admitted_source_row_count = 0
    invalid_source_row_count = 0
    for row in remittance_allocations:
        invoice_number = normalize_invoice(row.get("invoice_number"))
        if not invoice_number:
            invalid_source_row_count += 1
            continue
        raw_amount = (
            row.get("net_invoice_amount")
            if "net_invoice_amount" in row
            else row.get("apply_amount")
        )
        try:
            source_amounts[invoice_number].append(money(raw_amount))
            admitted_source_row_count += 1
        except Exception:
            invalid_source_row_count += 1

    current_by_number: dict[str, list[EffectiveInvoice]] = defaultdict(list)
    for invoice in open_invoices:
        effective = effective_invoice(invoice)
        if effective.normalized_invoice_number:
            current_by_number[effective.normalized_invoice_number].append(
                effective
            )

    source_invoice_set = set(source_amounts)
    candidate_invoice_set = set(normalized_candidates)
    invoice_sets_equal = bool(
        normalized_candidates
        and source_invoice_set == candidate_invoice_set
        and admitted_source_row_count == len(normalized_candidates)
        and invalid_source_row_count == 0
    )
    one_source_amount_per_invoice = bool(
        invoice_sets_equal
        and all(
            len(source_amounts[invoice_number]) == 1
            for invoice_number in normalized_candidates
        )
    )
    one_current_open_item_per_invoice = bool(
        normalized_candidates
        and all(
            len(current_by_number.get(invoice_number, ())) == 1
            for invoice_number in normalized_candidates
        )
    )
    all_selected_customer = bool(
        customer_number
        and one_current_open_item_per_invoice
        and all(
            current_by_number[invoice_number][0].customer_number
            == customer_number
            for invoice_number in normalized_candidates
        )
    )
    source_amounts_match_full_open = bool(
        one_source_amount_per_invoice
        and one_current_open_item_per_invoice
        and all(
            abs(
                source_amounts[invoice_number][0]
                - current_by_number[invoice_number][0].effective_amount
            )
            <= AMOUNT_TOLERANCE
            for invoice_number in normalized_candidates
        )
    )
    boundary_rule = str(projection_evidence.get("boundary_rule") or "")
    boundary_closed = bool(projection_evidence.get("boundary_closed"))
    allocation_conflict_count = int(
        projection_evidence.get("allocation_conflict_count") or 0
    )
    removed_allocation_count = int(
        projection_evidence.get("removed_allocation_count") or 0
    )
    customer_conflict_count = int(
        projection_evidence.get("customer_conflict_count") or 0
    )
    review_edits_used = bool(
        projection_evidence.get("review_edits_used_as_extraction")
    )
    eligible = bool(
        invoice_sets_equal
        and one_source_amount_per_invoice
        and one_current_open_item_per_invoice
        and all_selected_customer
        and source_amounts_match_full_open
        and boundary_rule == "next_transaction_information"
        and boundary_closed
        and allocation_conflict_count == 0
        and removed_allocation_count == 0
        and customer_conflict_count == 0
        and not review_edits_used
    )
    return {
        "status": "reconciled" if eligible else "not_reconciled",
        "rule_version": REMITTANCE_RECONCILIATION_RULE_VERSION,
        "selected_customer_number": customer_number,
        "extracted_invoice_count": len(normalized_candidates),
        "source_allocation_row_count": admitted_source_row_count,
        "invalid_source_row_count": invalid_source_row_count,
        "invoice_sets_equal": invoice_sets_equal,
        "one_source_amount_per_invoice": one_source_amount_per_invoice,
        "one_current_open_item_per_invoice": (
            one_current_open_item_per_invoice
        ),
        "all_items_owned_by_selected_customer": all_selected_customer,
        "source_amounts_match_full_signed_open_amounts": (
            source_amounts_match_full_open
        ),
        "boundary_rule": boundary_rule,
        "boundary_closed": boundary_closed,
        "allocation_conflict_count": allocation_conflict_count,
        "removed_allocation_count": removed_allocation_count,
        "customer_conflict_count": customer_conflict_count,
        "review_edits_used_as_extraction": review_edits_used,
        "eligible_for_residual_completion": eligible,
        "recommendation_not_decision": True,
        "can_auto_approve": False,
        "erp_write_performed": False,
    }


def find_unique_due_date_bucket_match(
    *,
    check_amount: Decimal | str | int | float,
    open_invoices: Iterable[OpenInvoice],
) -> tuple[tuple[date, ...], tuple[EffectiveInvoice, ...]] | None:
    """Return a single due-date bucket, or a unique combination of complete
    due-date buckets, that exactly matches ``check_amount`` for one
    candidate customer's current open AR - or None.

    Used as an identity tie-breaker: when no other evidence (phone,
    invoice ownership, payer-supplied number) can select a customer on its
    own, an exact dollar match against a candidate's own current open
    due-date buckets is itself strong, independent evidence that the
    candidate is correct. If more than one single bucket independently
    matches, that is a genuine ambiguity and this returns None rather than
    guessing.
    """

    amount = money(check_amount)
    effective = tuple(
        effective_invoice(invoice) for invoice in open_invoices
    )
    eligible = _eligible_open_items(effective)

    due_date_groups: dict[date, list[EffectiveInvoice]] = defaultdict(list)
    for invoice in eligible:
        if invoice.due_date is not None:
            due_date_groups[invoice.due_date].append(invoice)

    matching_groups = [
        (due_date, tuple(invoices))
        for due_date, invoices in due_date_groups.items()
        if invoices
        and abs(_invoice_total(invoices) - amount) <= AMOUNT_TOLERANCE
    ]
    if len(matching_groups) == 1:
        due_date, invoices = matching_groups[0]
        return (due_date,), invoices
    if len(matching_groups) > 1:
        return None

    return _unique_complete_due_date_group_combination(eligible, amount)


def recommend_allocation(
    *,
    check_amount: Decimal | str | int | float,
    extracted_invoice_numbers: Iterable[object],
    open_invoices: Iterable[OpenInvoice],
    remittance_allocations: Iterable[Mapping[str, Any]] = (),
    remittance_evidence_complete: bool = False,
    payment_date: date | None = None,
) -> AllocationRecommendation:
    """Apply the governed exact-evidence allocation ladder.

    ``payment_date`` is retained for the wider recommendation contract. The
    Increment 3P deterministic ladder uses current signed ERP state and never
    derives approval authority from the date.
    """

    amount = money(check_amount)
    normalized_candidates = tuple(
        dict.fromkeys(
            invoice
            for value in extracted_invoice_numbers
            if (invoice := normalize_invoice(value))
        )
    )
    effective = tuple(
        effective_invoice(invoice)
        for invoice in open_invoices
    )
    eligible = _eligible_open_items(effective)
    by_number: dict[str, list[EffectiveInvoice]] = defaultdict(list)
    for invoice in effective:
        if invoice.normalized_invoice_number:
            by_number[invoice.normalized_invoice_number].append(invoice)

    remittance_amounts: dict[str, list[Decimal]] = defaultdict(list)
    for row in remittance_allocations:
        invoice_number = normalize_invoice(row.get("invoice_number"))
        if not invoice_number:
            continue
        raw_amount = (
            row.get("net_invoice_amount")
            if "net_invoice_amount" in row
            else row.get("apply_amount")
        )
        try:
            remittance_amounts[invoice_number].append(money(raw_amount))
        except Exception:
            continue

    if normalized_candidates and all(
        len(by_number.get(invoice, ())) == 1
        for invoice in normalized_candidates
    ):
        exact_invoices = tuple(
            by_number[invoice_number][0]
            for invoice_number in normalized_candidates
        )
        exact_total = money(
            sum(
                (invoice.effective_amount for invoice in exact_invoices),
                Decimal("0.00"),
            )
        )
        if abs(exact_total - amount) <= AMOUNT_TOLERANCE:
            reason = (
                "Valid remittance invoice numbers match current ERP open "
                "invoice/credit amounts exactly."
            )
            return _recommendation(
                check_amount=amount,
                method="exact_remittance_invoices",
                invoices=exact_invoices,
                reason=reason,
            )

        complete_remittance_amounts = bool(
            remittance_evidence_complete
            and all(
                len(remittance_amounts.get(invoice_number, ())) == 1
                for invoice_number in normalized_candidates
            )
        )
        if complete_remittance_amounts:
            remitted_total = money(
                sum(
                    (
                        remittance_amounts[invoice_number][0]
                        for invoice_number in normalized_candidates
                    ),
                    Decimal("0.00"),
                )
            )
            overages = [
                (
                    invoice,
                    money(
                        remittance_amounts[
                            invoice.normalized_invoice_number
                        ][0]
                        - invoice.effective_amount
                    ),
                )
                for invoice in exact_invoices
                if (
                    invoice.business_type == "Debit"
                    and invoice.effective_amount > 0
                    and remittance_amounts[
                        invoice.normalized_invoice_number
                    ][0] - invoice.effective_amount
                    > AMOUNT_TOLERANCE
                )
            ]
            all_rows_are_full_or_overstated_debits = all(
                invoice.business_type == "Debit"
                and invoice.effective_amount > 0
                and remittance_amounts[
                    invoice.normalized_invoice_number
                ][0] - invoice.effective_amount
                >= -AMOUNT_TOLERANCE
                for invoice in exact_invoices
            )
            unchanged_rows = [
                invoice
                for invoice in exact_invoices
                if all(invoice is not item[0] for item in overages)
            ]
            unchanged_rows_match = all(
                abs(
                    remittance_amounts[
                        invoice.normalized_invoice_number
                    ][0] - invoice.effective_amount
                ) <= AMOUNT_TOLERANCE
                for invoice in unchanged_rows
            )
            cap_pattern = bool(
                abs(remitted_total - amount) <= AMOUNT_TOLERANCE
                and all_rows_are_full_or_overstated_debits
                and len(overages) == 1
                and unchanged_rows_match
            )
            if cap_pattern:
                residual = overages[0][1]
                customer_numbers = {
                    invoice.customer_number for invoice in exact_invoices
                }
                matching_service_charges = [
                    invoice
                    for invoice in eligible
                    if invoice.allocation_kind == "service_charge"
                    and invoice.business_type == "Debit"
                    and invoice.customer_number in customer_numbers
                    and invoice.open_item_key not in {
                        selected.open_item_key for selected in exact_invoices
                    }
                    and abs(invoice.effective_amount - residual)
                    <= AMOUNT_TOLERANCE
                ]
                if len(matching_service_charges) == 1:
                    service_charge = matching_service_charges[0]
                    reason = (
                        "One remittance row exceeds its ERP invoice open "
                        "amount; ETOP caps that invoice at the verified open "
                        "amount and applies one unique same-customer service "
                        "charge for the exact remainder."
                    )
                    return _recommendation(
                        check_amount=amount,
                        method=(
                            "exact_remittance_invoice_cap_plus_service_charge"
                        ),
                        invoices=(*exact_invoices, service_charge),
                        reason=reason,
                    )

                warning = (
                    "More than one same-customer service charge matches the "
                    "capped remittance remainder; professional review is "
                    "required."
                    if len(matching_service_charges) > 1
                    else "No unique current same-customer service charge "
                    "matches the capped remittance remainder."
                )
                return _partial_recommendation(
                    check_amount=amount,
                    method="service_charge_residual_review",
                    invoices=exact_invoices,
                    reason=(
                        "The remittance amount exceeds one verified ERP "
                        "invoice open amount."
                    ),
                    warning=warning,
                )

        exact_keys = {invoice.open_item_key for invoice in exact_invoices}
        remittance_customers = {
            invoice.customer_number for invoice in exact_invoices
        }
        remaining = sorted(
            (
                invoice
                for invoice in effective
                if invoice.open_item_key not in exact_keys
                and len(remittance_customers) == 1
                and invoice.customer_number in remittance_customers
                and invoice.due_date is not None
                and (
                    bool(invoice.normalized_invoice_number)
                    or invoice.allocation_kind == "service_charge"
                )
            ),
            key=lambda invoice: (
                invoice.due_date or date.max,
                invoice.invoice_date or date.max,
                invoice.normalized_invoice_number,
                invoice.invoice_number,
                invoice.invoice_count or 0,
                invoice.open_item_key,
            ),
        )
        residual = money(amount - exact_total)
        exact_residual_items = tuple(
            invoice
            for invoice in remaining
            if len(remittance_customers) == 1
            and invoice.customer_number in remittance_customers
            and invoice.allocation_kind == "invoice"
            and abs(invoice.effective_amount - residual) <= AMOUNT_TOLERANCE
        )
        if remittance_evidence_complete and len(exact_residual_items) == 1:
            residual_item = exact_residual_items[0]
            reason = (
                f"{len(exact_invoices)} remittance invoice(s) match current "
                "ERP open items; one unique remaining same-customer "
                f"{residual_item.business_type.lower()} open item exactly "
                "completes the check residual."
            )
            return _recommendation(
                check_amount=amount,
                method="exact_remittance_plus_unique_open_item",
                invoices=(*exact_invoices, residual_item),
                reason=reason,
            )
        if remittance_evidence_complete and len(exact_residual_items) > 1:
            return _partial_recommendation(
                check_amount=amount,
                method="ambiguous_remittance_residual_open_items",
                invoices=exact_invoices,
                reason=(
                    "Valid remittance invoice numbers match current ERP open "
                    "items, but those rows do not equal the complete check "
                    "amount."
                ),
                warning=(
                    "Multiple remaining same-customer open items exactly "
                    "match the residual; professional review is required."
                ),
            )
        residual_matches: list[tuple[date, tuple[EffectiveInvoice, ...]]] = []
        oldest_prefix: list[EffectiveInvoice] = []
        for due_date in sorted(
            {invoice.due_date for invoice in remaining if invoice.due_date}
        ):
            oldest_prefix.extend(
                invoice for invoice in remaining if invoice.due_date == due_date
            )
            prefix_total = money(
                sum(
                    (invoice.effective_amount for invoice in oldest_prefix),
                    Decimal("0.00"),
                )
            )
            if abs(prefix_total - residual) <= AMOUNT_TOLERANCE:
                residual_matches.append((due_date, tuple(oldest_prefix)))

        if remittance_evidence_complete and len(residual_matches) == 1:
            through_date, residual_invoices = residual_matches[0]
            reason = (
                f"{len(exact_invoices)} remittance invoice(s) match current "
                f"ERP open items; the oldest {len(residual_invoices)} "
                "remaining eligible open item(s), through "
                f"{through_date.month}/{through_date.day}/"
                f"{through_date.year % 100:02d}, exactly complete the check."
            )
            return _recommendation(
                check_amount=amount,
                method="exact_remittance_plus_oldest_open_items",
                invoices=(*exact_invoices, *residual_invoices),
                reason=reason,
            )

        # None of the remittance-residual completion methods above found a
        # clean, unique answer (the residual heuristics require agreement
        # with the ORIGINAL remittance-derived invoice numbers, which may be
        # incomplete or partially garbled). Before giving up into review,
        # check whether a clean combination of complete ERP due-date groups
        # exactly matches the check amount for the already-confirmed
        # customer - this covers over-inclusive or partially-misread
        # remittance drafts where the underlying due-date/aging evidence is
        # still unambiguous. Unlike the residual methods above, this does
        # not depend on the remittance-derived invoice numbers being
        # complete or correct.
        eligible_customers = {
            invoice.customer_number for invoice in eligible
        }
        due_date_combination = (
            _unique_complete_due_date_group_combination(eligible, amount)
            if len(eligible_customers) <= 1
            else None
        )
        if due_date_combination is not None:
            due_dates, due_date_invoices = due_date_combination
            due_date_text = ", ".join(
                f"{value.month}/{value.day}/{value.year % 100:02d}"
                for value in due_dates
            )
            reason = (
                "The remittance list did not exactly complete the check, "
                f"but one unique combination of {len(due_dates)} complete "
                "signed current ERP due-date groups exactly matches the "
                f"check: {due_date_text}."
            )
            return _recommendation(
                check_amount=amount,
                method="unique_exact_due_date_group_combination",
                invoices=due_date_invoices,
                reason=reason,
            )

        reason = (
            "Valid remittance invoice numbers match current ERP open items, "
            "but those rows do not equal the complete check amount."
        )
        warning = (
            "Complete governed remittance evidence is required before ETOP "
            "may supplement exact remit rows with oldest open items."
            if not remittance_evidence_complete
            else "No unique oldest-first open-item prefix completed the residual."
        )
        return _partial_recommendation(
            check_amount=amount,
            method="partial_exact_remittance",
            invoices=exact_invoices,
            reason=reason,
            warning=warning,
        )

    if eligible and abs(_invoice_total(eligible) - amount) <= AMOUNT_TOLERANCE:
        reason = (
            "The payment exactly matches the verified customer's complete "
            "signed current ERP open balance, including eligible invoices, "
            "credits, and service charges."
        )
        return _recommendation(
            check_amount=amount,
            method="exact_total_open_balance",
            invoices=eligible,
            reason=reason,
        )

    aging_groups: dict[str, list[EffectiveInvoice]] = defaultdict(list)
    for invoice in eligible:
        bucket = " ".join(str(invoice.aging_bucket or "").upper().split())
        if bucket:
            aging_groups[bucket].append(invoice)
    matching_aging_groups = [
        (bucket, tuple(invoices))
        for bucket, invoices in aging_groups.items()
        if invoices
        and abs(_invoice_total(invoices) - amount) <= AMOUNT_TOLERANCE
    ]
    matching_aging_groups.sort(key=lambda item: (item[0], len(item[1])))
    if len(matching_aging_groups) == 1:
        bucket, invoices = matching_aging_groups[0]
        reason = (
            f"The payment exactly matches all {len(invoices)} signed current "
            f"ERP open item(s) in aging bucket {bucket}."
        )
        return _recommendation(
            check_amount=amount,
            method="exact_aging_bucket_match",
            invoices=invoices,
            reason=reason,
        )
    if len(matching_aging_groups) > 1:
        return AllocationRecommendation(
            status="review_required",
            method="ambiguous_aging_bucket_matches",
            allocations=(),
            check_amount=amount,
            suggested_total=Decimal("0.00"),
            difference=amount,
            reasons=(),
            warnings=(
                "Multiple complete aging buckets match the check amount; "
                "professional review is required.",
            ),
            can_auto_approve=False,
        )

    due_date_groups: dict[date, list[EffectiveInvoice]] = defaultdict(list)
    for invoice in eligible:
        if invoice.due_date is not None and (
            invoice.normalized_invoice_number
            or invoice.allocation_kind == "service_charge"
        ):
            due_date_groups[invoice.due_date].append(invoice)

    matching_groups = [
        (due_date, tuple(invoices))
        for due_date, invoices in due_date_groups.items()
        if invoices
        and abs(
            money(
                sum(
                    (
                        invoice.effective_amount
                        for invoice in invoices
                    ),
                    Decimal("0.00"),
                )
            )
            - amount
        )
        <= AMOUNT_TOLERANCE
    ]
    matching_groups.sort(key=lambda item: (item[0], len(item[1])))

    if len(matching_groups) == 1:
        due_date, invoices = matching_groups[0]
        reason = (
            f"Check amount exactly matches all {len(invoices)} open "
            f"invoice(s) due "
            f"{due_date.month}/{due_date.day}/{due_date.year % 100:02d}."
        )
        return _recommendation(
            check_amount=amount,
            method="same_due_date_exact_match",
            invoices=invoices,
            reason=reason,
        )

    oldest_matches = (
        _oldest_prefix_matches(eligible, amount)
        if not matching_groups
        else []
    )
    if not matching_groups and not oldest_matches:
        # Neither a single due-date group nor a chronological oldest-item
        # prefix matched on its own. Before giving up, check whether a
        # combination of two or more complete due-date groups exactly
        # matches - e.g. a past-due bucket plus a current bucket. This is
        # tried only when the oldest-prefix search found nothing at all
        # (not merely ambiguous): if oldest-prefix already found multiple
        # candidate prefixes, that is a genuine human-relevant ambiguity
        # about which items are being paid, and this combination search
        # must not silently pick one interpretation over another.
        due_date_combination = _unique_complete_due_date_group_combination(
            eligible, amount
        )
        if due_date_combination is not None:
            due_dates, due_date_invoices = due_date_combination
            due_date_text = ", ".join(
                f"{value.month}/{value.day}/{value.year % 100:02d}"
                for value in due_dates
            )
            reason = (
                "No single due-date group matches the check amount, but "
                f"one unique combination of {len(due_dates)} complete "
                "signed current ERP due-date groups exactly matches the "
                f"check: {due_date_text}."
            )
            return _recommendation(
                check_amount=amount,
                method="unique_exact_due_date_group_combination",
                invoices=due_date_invoices,
                reason=reason,
            )

    if len(oldest_matches) == 1:
        invoices = oldest_matches[0]
        through_date = invoices[-1].due_date
        through_text = (
            f" through {through_date.month}/{through_date.day}/"
            f"{through_date.year % 100:02d}"
            if through_date is not None
            else ""
        )
        reason = (
            f"The oldest {len(invoices)} signed current ERP open item(s)"
            f"{through_text} exactly match the payment."
        )
        return _recommendation(
            check_amount=amount,
            method="oldest_open_items_exact_match",
            invoices=invoices,
            reason=reason,
        )

    warnings: tuple[str, ...]
    if len(matching_groups) > 1:
        warnings = (
            "Multiple complete due-date groups match the check amount; "
            "professional review is required.",
        )
    elif len(oldest_matches) > 1:
        warnings = (
            "Multiple chronological oldest-item prefixes match the check "
            "amount; professional review is required.",
        )
    else:
        warnings = (
            "No exact remittance or unique complete due-date allocation "
            "matched the check amount.",
        )
    return AllocationRecommendation(
        status="review_required",
        method=(
            "ambiguous_due_date_groups"
            if len(matching_groups) > 1
            else "ambiguous_oldest_item_prefixes"
            if len(oldest_matches) > 1
            else "no_exact_match"
        ),
        allocations=(),
        check_amount=amount,
        suggested_total=Decimal("0.00"),
        difference=amount,
        reasons=(),
        warnings=warnings,
        can_auto_approve=False,
    )


def recommend_enterprise_group_allocation(
    *,
    primary_customer_number: str,
    check_amount: Decimal | str | int | float,
    extracted_invoice_numbers: Iterable[object],
    primary_open_invoices: Iterable[OpenInvoice],
    group_open_invoices: Iterable[OpenInvoice],
    remittance_allocations: Iterable[Mapping[str, Any]] = (),
    remittance_evidence_complete: bool = False,
) -> AllocationRecommendation:
    """Expose exact linked-account remittance matches for human verification.

    CUNUMENT permits ETOP to retrieve related accounts. It does not establish
    cross-customer application authority, so linked-account evidence is used
    only for exact remittance invoices and remains review-required whenever an
    allocation row belongs to an account other than the matched customer.
    """

    primary = recommend_allocation(
        check_amount=check_amount,
        extracted_invoice_numbers=extracted_invoice_numbers,
        open_invoices=primary_open_invoices,
        remittance_allocations=remittance_allocations,
        remittance_evidence_complete=remittance_evidence_complete,
        payment_date=None,
    )
    amount = money(check_amount)
    normalized_candidates = tuple(
        dict.fromkeys(
            invoice
            for value in extracted_invoice_numbers
            if (invoice := normalize_invoice(value))
        )
    )
    if not normalized_candidates:
        return primary

    effective = tuple(
        effective_invoice(invoice)
        for invoice in group_open_invoices
    )
    by_number: dict[str, list[EffectiveInvoice]] = defaultdict(list)
    for invoice in effective:
        if invoice.normalized_invoice_number:
            by_number[invoice.normalized_invoice_number].append(invoice)

    if not all(
        len(by_number.get(invoice_number, ())) == 1
        for invoice_number in normalized_candidates
    ):
        return primary

    exact_invoices = tuple(
        by_number[invoice_number][0]
        for invoice_number in normalized_candidates
    )
    exact_total = money(
        sum(
            (invoice.effective_amount for invoice in exact_invoices),
            Decimal("0.00"),
        )
    )
    if abs(exact_total - amount) > AMOUNT_TOLERANCE:
        return primary

    linked_customers = {
        invoice.customer_number
        for invoice in exact_invoices
        if invoice.customer_number != primary_customer_number
    }
    if not linked_customers:
        return primary

    reason = (
        "Valid remittance invoice numbers match current ERP open items "
        "across TMCUST CUNUMENT-linked customer accounts exactly."
    )
    proposal = _recommendation(
        check_amount=amount,
        method="enterprise_group_exact_remittance_review",
        invoices=exact_invoices,
        reason=reason,
        warnings=(
            "The proposed rows include a linked ERP customer account; "
            "cross-customer application requires professional verification.",
        ),
    )
    return AllocationRecommendation(
        status="review_required",
        method=proposal.method,
        allocations=proposal.allocations,
        check_amount=proposal.check_amount,
        suggested_total=proposal.suggested_total,
        difference=proposal.difference,
        reasons=proposal.reasons,
        warnings=proposal.warnings,
        can_auto_approve=False,
    )
