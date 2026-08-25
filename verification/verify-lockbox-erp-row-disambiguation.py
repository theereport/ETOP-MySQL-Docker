from __future__ import annotations

import runpy
import sys
from copy import deepcopy
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DOCUMENT_INTELLIGENCE = BACKEND / "modules" / "document_intelligence"
for entry in (BACKEND, DOCUMENT_INTELLIGENCE):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

# Reuse the governed optional-dependency stubs from the retained 3W verifier.
runpy.run_path(
    str(
        ROOT
        / "verification"
        / "verify-lockbox-source-backed-remit-reconciliation.py"
    ),
    run_name="increment3x_stub_loader",
)

from lockbox_preparation.contracts import OpenInvoice
from lockbox_preparation.control_projection import (
    EXPECTED_BOUNDARY_RULE,
    promotion_assessment,
)
from lockbox_preparation.policy import (
    REMITTANCE_ROW_DISAMBIGUATION_RULE_VERSION,
    disambiguate_remittance_rows,
    recommend_allocation,
)


CUSTOMER = "830001"
ROWS = (
    ("430830101", "00083001", "510.11"),
    ("430830102", "00083002", "620.22"),
    ("430830103", "00083003", "730.33"),
    ("430830104", "00083004", "840.44"),
    ("430830105", "00083005", "300.55"),
)


def rejected_rows() -> tuple[dict, ...]:
    return tuple(
        {
            "raw_invoice_candidates": [invoice, purchase_order],
            "net_invoice_amount": amount,
            "invoice_page": "12;1",
            "reason": "multiple_governed_invoice_candidates",
            "extraction_source": "ocr_visual_row",
            "ocr_psm": 11,
        }
        for invoice, purchase_order, amount in ROWS
    )


def open_invoices() -> tuple[OpenInvoice, ...]:
    return tuple(
        OpenInvoice(
            customer_number=CUSTOMER,
            invoice_number=invoice,
            open_amount=Decimal(amount),
            signed_source_amount=Decimal(amount),
            due_date=date(2026, 8, 10),
            raw_transaction_type="Debit",
            source_reference="synthetic-read-only-current-open-ar",
            open_item_key=f"{CUSTOMER}|Debit|{invoice}",
        )
        for invoice, _, amount in ROWS
    )


def projection_evidence() -> dict:
    return {
        "boundary_rule": EXPECTED_BOUNDARY_RULE,
        "boundary_closed": True,
        "allocation_conflict_count": 0,
        "removed_allocation_count": 0,
        "customer_conflict_count": 0,
        "review_edits_used_as_extraction": False,
        "remittance_evidence_complete": False,
    }


def verify_exact_invoice_po_resolution() -> tuple[dict, dict]:
    assessment = disambiguate_remittance_rows(
        selected_customer_number=CUSTOMER,
        rejected_candidates=rejected_rows(),
        open_invoices=open_invoices(),
    )
    assert assessment["status"] == "resolved"
    assert assessment["rule_version"] == (
        REMITTANCE_ROW_DISAMBIGUATION_RULE_VERSION
    )
    assert assessment["recovered_row_count"] == 5
    assert assessment["unresolved_row_count"] == 0
    assert assessment["original_rejections_preserved"] is True
    assert [
        row["invoice_number"]
        for row in assessment["recovered_allocations"]
    ] == [row[0] for row in ROWS]
    assert all(
        row["source_rejection_preserved"]
        for row in assessment["recovered_allocations"]
    )

    check_amount = sum(
        (Decimal(amount) for _, _, amount in ROWS),
        Decimal("0.00"),
    )
    recommendation = recommend_allocation(
        check_amount=check_amount,
        extracted_invoice_numbers=tuple(row[0] for row in ROWS),
        open_invoices=open_invoices(),
        remittance_allocations=tuple(
            assessment["recovered_allocations"]
        ),
        remittance_evidence_complete=True,
    )
    assert recommendation.method == "exact_remittance_invoices"
    assert recommendation.difference == Decimal("0.00")
    assert len(recommendation.allocations) == 5
    assert recommendation.can_auto_approve is False

    control = {
        "transaction_id": "synthetic-row-disambiguation",
        "state": "prepared_exception",
        "result": {},
    }
    candidate = {
        "transaction_id": "synthetic-row-disambiguation",
        "state": "prepared_balanced",
        "source": {"projection_evidence": projection_evidence()},
        "result": {
            "customer_resolution": {
                "status": "resolved",
                "customer_number": CUSTOMER,
                "selection_basis": "payer_supplied_customer_number",
                "confidence_basis": "payer_supplied_customer_number",
                "selected_confidence": 1.0,
                "matching_evidence": {
                    "payer_account_directive_verified": True,
                    "failed_selection_gates": [],
                },
            },
            "remittance_row_disambiguation_assessment": assessment,
            "recommendation": asdict(recommendation),
            "can_auto_approve": False,
            "erp_write_performed": False,
        },
    }
    admitted, blockers = promotion_assessment(control, candidate)
    assert admitted, blockers
    return control, candidate


def verify_fail_closed_boundaries(control: dict, candidate: dict) -> None:
    amount_mismatch = list(rejected_rows())
    amount_mismatch[0] = {
        **amount_mismatch[0],
        "net_invoice_amount": "510.12",
    }
    assessment = disambiguate_remittance_rows(
        selected_customer_number=CUSTOMER,
        rejected_candidates=amount_mismatch,
        open_invoices=open_invoices(),
    )
    assert assessment["status"] == "not_resolved"
    assert assessment["unresolved_row_count"] == 1

    duplicate_candidate_invoices = (
        *open_invoices(),
        OpenInvoice(
            customer_number=CUSTOMER,
            invoice_number="00083001",
            open_amount=Decimal("510.11"),
            signed_source_amount=Decimal("510.11"),
            due_date=date(2026, 8, 10),
            raw_transaction_type="Debit",
            source_reference="synthetic-read-only-current-open-ar",
            open_item_key=f"{CUSTOMER}|Debit|00083001",
        ),
    )
    assessment = disambiguate_remittance_rows(
        selected_customer_number=CUSTOMER,
        rejected_candidates=rejected_rows(),
        open_invoices=duplicate_candidate_invoices,
    )
    assert assessment["status"] == "not_resolved"
    assert assessment["unresolved_row_count"] == 1

    wrong_customer = disambiguate_remittance_rows(
        selected_customer_number="830002",
        rejected_candidates=rejected_rows(),
        open_invoices=open_invoices(),
    )
    assert wrong_customer["status"] == "not_resolved"
    assert wrong_customer["recovered_row_count"] == 0

    non_ambiguous = list(rejected_rows())
    non_ambiguous[0] = {
        **non_ambiguous[0],
        "reason": "no_governed_invoice_candidate",
    }
    assessment = disambiguate_remittance_rows(
        selected_customer_number=CUSTOMER,
        rejected_candidates=non_ambiguous,
        open_invoices=open_invoices(),
    )
    assert assessment["status"] == "not_resolved"

    tampered = deepcopy(candidate)
    tampered_assessment = tampered["result"][
        "remittance_row_disambiguation_assessment"
    ]
    first = tampered_assessment["row_assessments"][0]
    first["candidate_match_counts"]["00083001"] = 1
    admitted, blockers = promotion_assessment(control, tampered)
    assert admitted is False
    assert "remittance_row_disambiguation_not_verified" in blockers


def main() -> None:
    control, candidate = verify_exact_invoice_po_resolution()
    verify_fail_closed_boundaries(control, candidate)
    print(
        "Increment 3X ERP-backed remittance-row disambiguation passed: one "
        "invoice-versus-PO candidate may be selected only by exact same-customer "
        "current-open ownership and signed amount; ambiguity, mismatches, "
        "cross-customer evidence, automatic approval, and ERP writes remain blocked."
    )


if __name__ == "__main__":
    main()
