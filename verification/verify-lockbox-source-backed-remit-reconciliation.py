from __future__ import annotations

import sys
import importlib.util
import types
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DOCUMENT_INTELLIGENCE = BACKEND / "modules" / "document_intelligence"
for entry in (BACKEND, DOCUMENT_INTELLIGENCE):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

if importlib.util.find_spec("fastapi") is None:
    fastapi = types.ModuleType("fastapi")

    class APIRouter:
        def __init__(self, *args, **kwargs):
            self.routes = []

        def _route(self, *args, **kwargs):
            def decorator(function):
                return function

            return decorator

        get = _route
        post = _route
        put = _route

        def include_router(self, router):
            self.routes.append(router)

    fastapi.APIRouter = APIRouter
    fastapi.HTTPException = RuntimeError
    fastapi.File = lambda default=None, *args, **kwargs: default
    fastapi.Query = lambda default=None, *args, **kwargs: default
    fastapi.UploadFile = type("UploadFile", (), {})
    sys.modules["fastapi"] = fastapi
    responses = types.ModuleType("fastapi.responses")
    responses.FileResponse = SimpleNamespace
    sys.modules["fastapi.responses"] = responses

if "core.database" not in sys.modules:
    core_database = types.ModuleType("core.database")
    core_database.madden_database = SimpleNamespace()
    sys.modules["core.database"] = core_database

if importlib.util.find_spec("pytesseract") is None:
    pytesseract = types.ModuleType("pytesseract")
    pytesseract.pytesseract = SimpleNamespace(tesseract_cmd="")
    pytesseract.Output = SimpleNamespace(DICT="dict")
    pytesseract.image_to_string = lambda *args, **kwargs: ""
    pytesseract.image_to_data = lambda *args, **kwargs: {
        "text": [],
        "conf": [],
    }
    sys.modules["pytesseract"] = pytesseract

from invoice_number_rules import (
    ERP_INVOICE_RULE_VERSION,
    NO_REMITTANCE_INVOICE,
    normalize_erp_invoice,
)
from lockbox_preparation.contracts import OpenInvoice
from lockbox_preparation.control_projection import (
    EXPECTED_BOUNDARY_RULE,
    FRESH_SOURCE_PROJECTION_VERSION,
    PROJECTION_VERSION,
    promotion_assessment,
)
from lockbox_preparation.policy import (
    RULE_VERSION,
    assess_remittance_reconciliation,
    recommend_allocation,
)
from lockbox_preparation.repository import SERVICE_VERSION
from modules.document_intelligence.lockbox_preparation.source_loader import (
    merge_extractions,
)


def open_item(
    invoice_number: str,
    amount: str,
    *,
    customer_number: str = "800001",
) -> OpenInvoice:
    return OpenInvoice(
        customer_number=customer_number,
        invoice_number=invoice_number,
        open_amount=Decimal(amount),
        signed_source_amount=Decimal(amount),
        due_date=date(2026, 8, 10),
        raw_transaction_type="I",
        source_reference="synthetic-read-only-current-open-ar",
        open_item_key=f"{customer_number}|I|{invoice_number}",
    )


def source_evidence() -> dict:
    return {
        "boundary_rule": EXPECTED_BOUNDARY_RULE,
        "boundary_closed": True,
        "allocation_conflict_count": 0,
        "removed_allocation_count": 0,
        "customer_conflict_count": 0,
        "review_edits_used_as_extraction": False,
        "remittance_evidence_complete": False,
    }


def verify_preserved_ten_digit_rejection() -> None:
    amounts = ("510.00", "620.00", "730.00", "840.00", "300.00")
    rejections = [
        {
            "raw_invoice_candidates": [str(8000000001 + index)],
            "net_invoice_amount": amount,
            "invoice_page": "12;1",
            "reason": "no_governed_invoice_candidate",
            "extraction_source": "embedded_text",
        }
        for index, amount in enumerate(amounts)
    ]
    source = {
        "transaction_id": "synthetic-ten-digit-remit",
        "transaction_boundary_rule": EXPECTED_BOUNDARY_RULE,
        "transaction_boundary_closed": True,
        "remittance_evidence_complete": False,
        "remittance_incomplete_pages": [12],
        "remittance_ocr_errors": [],
        "rejected_remittance_candidates": rejections,
        "allocations": [],
    }
    merged = merge_extractions(
        {"transactions": [source]},
        {"transactions": [source]},
    )["transactions"][0]

    assert merged["allocations"] == []
    assert merged["remittance_evidence_complete"] is False
    assert merged["rejected_remittance_candidates"] == rejections
    evidence = merged["projection_evidence"]
    assert evidence["source_recovered_allocation_count"] == 0
    assert evidence["source_recovered_rejection_count"] == 0
    assert evidence["unresolved_rejection_count"] == 5
    assert evidence["baseline_evidence_preserved"] is True
    assert evidence["review_edits_used_as_extraction"] is False
    assert normalize_erp_invoice("8000000001") == ""
    assert normalize_erp_invoice(NO_REMITTANCE_INVOICE) == ""


def verify_current_erp_reconciliation_residual() -> dict:
    invoices = (
        open_item("800000101", "6000.00"),
        open_item("800000102", "4200.00"),
        open_item("800000103", "75.00"),
        open_item("800000104", "17.25"),
    )
    remit = (
        {"invoice_number": "800000101", "net_invoice_amount": "6000.00"},
        {"invoice_number": "800000102", "net_invoice_amount": "4200.00"},
    )
    assessment = assess_remittance_reconciliation(
        selected_customer_number="800001",
        extracted_invoice_numbers=("800000101", "800000102"),
        open_invoices=invoices,
        remittance_allocations=remit,
        projection_evidence=source_evidence(),
    )
    assert assessment["status"] == "reconciled"
    assert assessment["eligible_for_residual_completion"] is True

    recommendation = recommend_allocation(
        check_amount="10275.00",
        extracted_invoice_numbers=("800000101", "800000102"),
        open_invoices=invoices,
        remittance_allocations=remit,
        remittance_evidence_complete=assessment[
            "eligible_for_residual_completion"
        ],
    )
    assert recommendation.method == "exact_remittance_plus_unique_open_item"
    assert recommendation.difference == Decimal("0.00")
    assert [row.invoice_number for row in recommendation.allocations] == [
        "800000101",
        "800000102",
        "800000103",
    ]
    return assessment


def projection_candidate(assessment: dict) -> tuple[dict, dict]:
    control = {
        "transaction_id": "synthetic-remit-reconciliation",
        "state": "prepared_exception",
        "result": {},
    }
    candidate = {
        "transaction_id": "synthetic-remit-reconciliation",
        "state": "prepared_balanced",
        "source": {"projection_evidence": source_evidence()},
        "result": {
            "customer_resolution": {
                "status": "resolved",
                "customer_number": "800001",
                "selection_basis": "payer_supplied_customer_number",
                "confidence_basis": "payer_supplied_customer_number",
                "selected_confidence": 1.0,
                "matching_evidence": {
                    "payer_account_directive_verified": True,
                    "failed_selection_gates": [],
                },
            },
            "remittance_completion_assessment": assessment,
            "recommendation": {
                "status": "recommended",
                "method": "exact_remittance_plus_unique_open_item",
                "difference": "0.00",
                "allocations": [
                    {"apply_amount": "6000.00"},
                    {"apply_amount": "4200.00"},
                    {"apply_amount": "75.00"},
                ],
                "can_auto_approve": False,
            },
            "can_auto_approve": False,
            "erp_write_performed": False,
        },
    }
    return control, candidate


def verify_projection_and_fail_closed_boundaries(assessment: dict) -> None:
    control, candidate = projection_candidate(assessment)
    admitted, blockers = promotion_assessment(control, candidate)
    assert admitted, blockers

    for field in (
        "invoice_sets_equal",
        "one_source_amount_per_invoice",
        "one_current_open_item_per_invoice",
        "all_items_owned_by_selected_customer",
        "source_amounts_match_full_signed_open_amounts",
        "boundary_closed",
        "eligible_for_residual_completion",
    ):
        blocked = deepcopy(candidate)
        blocked["result"]["remittance_completion_assessment"][field] = False
        admitted, blockers = promotion_assessment(control, blocked)
        assert admitted is False
        assert "residual_completion_requires_complete_remittance" in blockers

    for field in (
        "allocation_conflict_count",
        "removed_allocation_count",
        "customer_conflict_count",
    ):
        blocked = deepcopy(candidate)
        blocked["result"]["remittance_completion_assessment"][field] = 1
        admitted, blockers = promotion_assessment(control, blocked)
        assert admitted is False
        assert "residual_completion_requires_complete_remittance" in blockers

    blocked = deepcopy(candidate)
    blocked["result"]["remittance_completion_assessment"][
        "review_edits_used_as_extraction"
    ] = True
    admitted, blockers = promotion_assessment(control, blocked)
    assert admitted is False
    assert "residual_completion_requires_complete_remittance" in blockers

    ambiguous_source = {
        "transaction_id": "synthetic-ambiguous-source",
        "transaction_boundary_rule": EXPECTED_BOUNDARY_RULE,
        "transaction_boundary_closed": True,
        "remittance_evidence_complete": False,
        "remittance_incomplete_pages": [12],
        "rejected_remittance_candidates": [
            {
                "raw_invoice_candidates": ["8000000001", "8000000002"],
                "net_invoice_amount": "500.00",
                "invoice_page": "12;1",
                "reason": "no_governed_invoice_candidate",
            }
        ],
        "allocations": [],
    }
    ambiguous = merge_extractions(
        {"transactions": [ambiguous_source]},
        {"transactions": [ambiguous_source]},
    )["transactions"][0]
    assert ambiguous["allocations"] == []
    assert ambiguous["remittance_evidence_complete"] is False
    assert ambiguous["projection_evidence"]["unresolved_rejection_count"] == 1


def verify_versions() -> None:
    assert ERP_INVOICE_RULE_VERSION == "erp-invoice-number-admission@1.2.0"
    assert RULE_VERSION.endswith("increment4a+BR-LOCKBOX-001..044")
    assert SERVICE_VERSION.endswith("increment4a")
    assert PROJECTION_VERSION.endswith("increment4a")
    assert FRESH_SOURCE_PROJECTION_VERSION.endswith("increment4a")


def main() -> None:
    verify_preserved_ten_digit_rejection()
    assessment = verify_current_erp_reconciliation_residual()
    verify_projection_and_fail_closed_boundaries(assessment)
    verify_versions()
    print(
        "Increment 3X retained source-backed remit reconciliation passed: "
        "10-digit values remain rejected while exact current-ERP remit "
        "evidence can complete recommendations; ambiguity, conflicts, review edits, "
        "automatic approval, and ERP writes remain blocked."
    )


if __name__ == "__main__":
    main()
