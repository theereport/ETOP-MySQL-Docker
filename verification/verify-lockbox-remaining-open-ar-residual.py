from __future__ import annotations

import sys
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DOCUMENT_INTELLIGENCE = BACKEND / "modules" / "document_intelligence"
for entry in (BACKEND, DOCUMENT_INTELLIGENCE):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from lockbox_preparation.contracts import OpenInvoice
from lockbox_preparation.control_projection import (
    EXPECTED_BOUNDARY_RULE,
    FRESH_SOURCE_PROJECTION_VERSION,
    PROJECTION_VERSION,
    promotion_assessment,
)
from lockbox_preparation.policy import RULE_VERSION, recommend_allocation
from lockbox_preparation.repository import SERVICE_VERSION


def item(
    invoice_number: str,
    amount: str,
    *,
    customer: str = "900001",
    transaction_type: str = "I",
    due_date: date = date(2026, 8, 10),
) -> OpenInvoice:
    return OpenInvoice(
        customer_number=customer,
        invoice_number=invoice_number,
        open_amount=Decimal(amount),
        signed_source_amount=Decimal(amount),
        due_date=due_date,
        raw_transaction_type=transaction_type,
        open_item_key=(
            f"{customer}|{transaction_type}|{invoice_number}|"
        ),
    )


def verify_unique_debit_residual() -> None:
    recommendation = recommend_allocation(
        check_amount="800.00",
        extracted_invoice_numbers=("900000001",),
        open_invoices=(
            item("900000001", "742.35", due_date=date(2026, 7, 10)),
            item("900000002", "26.10", due_date=date(2026, 7, 10)),
            item("900000003", "57.65", due_date=date(2026, 7, 10)),
        ),
        remittance_evidence_complete=True,
    )
    assert recommendation.method == "exact_remittance_plus_unique_open_item"
    assert recommendation.status == "recommended"
    assert [row.invoice_number for row in recommendation.allocations] == [
        "900000001",
        "900000003",
    ]
    assert recommendation.suggested_total == Decimal("800.00")
    assert recommendation.difference == Decimal("0.00")
    assert recommendation.can_auto_approve is False


def verify_unique_credit_residual() -> None:
    recommendation = recommend_allocation(
        check_amount="100.00",
        extracted_invoice_numbers=("900000010",),
        open_invoices=(
            item("900000010", "120.00", due_date=date(2026, 7, 10)),
            item(
                "900000011",
                "-20.00",
                transaction_type="Credit",
                due_date=date(2026, 8, 10),
            ),
            item("900000012", "75.00", due_date=date(2026, 6, 10)),
        ),
        remittance_evidence_complete=True,
    )
    assert recommendation.method == "exact_remittance_plus_unique_open_item"
    assert [row.apply_amount for row in recommendation.allocations] == [
        Decimal("120.00"),
        Decimal("-20.00"),
    ]
    assert recommendation.allocations[-1].business_type == "Credit"
    assert recommendation.difference == Decimal("0.00")


def verify_fail_closed_cases() -> None:
    base_items = (
        item("900000020", "100.00"),
        item("900000021", "37.50"),
    )
    incomplete = recommend_allocation(
        check_amount="137.50",
        extracted_invoice_numbers=("900000020",),
        open_invoices=base_items,
        remittance_evidence_complete=False,
    )
    assert incomplete.method == "partial_exact_remittance"
    assert incomplete.status == "review_required"

    duplicate = recommend_allocation(
        check_amount="137.50",
        extracted_invoice_numbers=("900000020",),
        open_invoices=(*base_items, item("900000022", "37.50")),
        remittance_evidence_complete=True,
    )
    assert duplicate.method == "ambiguous_remittance_residual_open_items"
    assert duplicate.status == "review_required"
    assert [row.invoice_number for row in duplicate.allocations] == [
        "900000020"
    ]

    cross_customer = recommend_allocation(
        check_amount="137.50",
        extracted_invoice_numbers=("900000020",),
        open_invoices=(
            item("900000020", "100.00"),
            item("900000023", "37.50", customer="900002"),
        ),
        remittance_evidence_complete=True,
    )
    assert cross_customer.method == "partial_exact_remittance"
    assert all(
        row.customer_number == "900001"
        for row in cross_customer.allocations
    )


def projection_candidate(*, complete: bool) -> tuple[dict, dict]:
    control = {
        "transaction_id": "synthetic-residual",
        "state": "prepared_exception",
        "result": {},
    }
    candidate = {
        "transaction_id": "synthetic-residual",
        "state": "prepared_balanced",
        "source": {
            "projection_evidence": {
                "removed_allocation_count": 0,
                "allocation_conflict_count": 0,
                "customer_conflict_count": 0,
                "boundary_rule": EXPECTED_BOUNDARY_RULE,
                "boundary_closed": True,
                "remittance_evidence_complete": complete,
            }
        },
        "result": {
            "customer_resolution": {
                "status": "resolved",
                "customer_number": "900001",
                "selection_basis": "payer_supplied_customer_number",
                "confidence_basis": "payer_supplied_customer_number",
                "selected_confidence": 1.0,
                "matching_evidence": {
                    "payer_account_directive_verified": True,
                    "failed_selection_gates": [],
                },
            },
            "recommendation": {
                "status": "recommended",
                "method": "exact_remittance_plus_unique_open_item",
                "difference": "0.00",
                "allocations": [
                    {"business_type": "Debit", "apply_amount": "100.00"},
                    {"business_type": "Credit", "apply_amount": "-20.00"},
                ],
                "can_auto_approve": False,
            },
            "can_auto_approve": False,
            "erp_write_performed": False,
        },
    }
    return control, candidate


def verify_projection_gate() -> None:
    control, candidate = projection_candidate(complete=True)
    admitted, blockers = promotion_assessment(control, candidate)
    assert admitted, blockers

    incomplete = deepcopy(candidate)
    incomplete["source"]["projection_evidence"][
        "remittance_evidence_complete"
    ] = False
    admitted, blockers = promotion_assessment(control, incomplete)
    assert admitted is False
    assert "residual_completion_requires_complete_remittance" in blockers


def verify_versions() -> None:
    assert RULE_VERSION.endswith("increment3x+BR-LOCKBOX-001..041")
    assert SERVICE_VERSION.endswith("increment3x")
    assert PROJECTION_VERSION.endswith("increment3x")
    assert FRESH_SOURCE_PROJECTION_VERSION.endswith("increment3x")


def main() -> None:
    verify_unique_debit_residual()
    verify_unique_credit_residual()
    verify_fail_closed_cases()
    verify_projection_gate()
    verify_versions()
    print(
        "Increment 3V remaining-open-A/R residual verification passed: "
        "one unique same-customer debit or credit may complete a fully "
        "evidenced remit; incomplete, duplicate, cross-customer, approval, "
        "and ERP-write paths remain blocked."
    )


if __name__ == "__main__":
    main()
