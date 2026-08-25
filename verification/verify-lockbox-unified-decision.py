from __future__ import annotations

import importlib.util
import sys
import types
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

from lockbox_preparation.contracts import OpenInvoice
from lockbox_preparation.control_projection import (
    PRIOR_PROJECTED_BALANCED_FLOOR,
    PRIOR_PROJECTED_REVIEW_CEILING,
    PROJECTION_VERSION,
    PROMOTION_METHODS,
    PROMOTION_SELECTION_BASES,
    _recompute_final_exception,
)
from lockbox_preparation.policy import RULE_VERSION, recommend_allocation
from lockbox_preparation.repository import SERVICE_VERSION
from modules.document_intelligence.pnc_lockbox_parser import EXTRACTION_VERSION
from modules.document_intelligence.resolution.payer_parser import (
    check_for_customer_directives,
    explicit_customer_account_directives,
)


def open_item(
    invoice_number: str,
    amount: str,
    transaction_type: str,
    key: str,
) -> OpenInvoice:
    return OpenInvoice(
        customer_number="700001",
        invoice_number=invoice_number,
        open_amount=Decimal(amount),
        signed_source_amount=Decimal(amount),
        due_date=date(2026, 8, 1),
        raw_transaction_type=transaction_type,
        open_item_key=key,
    )


def verify_account_directive() -> None:
    directive = explicit_customer_account_directives(
        "Apply payment to customer account 700001"
    )
    assert [item["customer_number"] for item in directive] == ["700001"]
    assert explicit_customer_account_directives(
        "Account Number 123456789\nRouting Number 021000021"
    ) == []
    conflicting = explicit_customer_account_directives(
        "Post payment to acct 700001\nApply check to acct 700002"
    )
    assert {item["customer_number"] for item in conflicting} == {
        "700001",
        "700002",
    }
    assert "payer_supplied_customer_number" in PROMOTION_SELECTION_BASES
    assert [
        item["customer_number"]
        for item in check_for_customer_directives("FOR 331002")
    ] == ["331002"]
    assert check_for_customer_directives("FOR Invoice 331002") == []
    assert "check_for_customer_number" in PROMOTION_SELECTION_BASES


def verify_invoice_cap_and_service_charge() -> None:
    recommendation = recommend_allocation(
        check_amount="150.00",
        extracted_invoice_numbers=("431700001", "431700002"),
        open_invoices=(
            open_item("431700001", "95.00", "I", "700001|I|431700001|"),
            open_item("431700002", "50.00", "I", "700001|I|431700002|"),
            open_item("17", "5.00", "SC", "700001|SC|17|17"),
        ),
        remittance_allocations=(
            {"invoice_number": "431700001", "net_invoice_amount": "100.00"},
            {"invoice_number": "431700002", "net_invoice_amount": "50.00"},
        ),
        remittance_evidence_complete=True,
    )
    assert recommendation.method == (
        "exact_remittance_invoice_cap_plus_service_charge"
    )
    assert [line.apply_amount for line in recommendation.allocations] == [
        Decimal("95.00"),
        Decimal("50.00"),
        Decimal("5.00"),
    ]
    assert recommendation.difference == Decimal("0.00")
    assert recommendation.can_auto_approve is False
    assert recommendation.method in PROMOTION_METHODS

    ambiguous = recommend_allocation(
        check_amount="100.00",
        extracted_invoice_numbers=("431700001",),
        open_invoices=(
            open_item("431700001", "95.00", "I", "700001|I|431700001|"),
            open_item("11", "5.00", "SC", "700001|SC|11|11"),
            open_item("12", "5.00", "SC", "700001|SC|12|12"),
        ),
        remittance_allocations=({
            "invoice_number": "431700001",
            "net_invoice_amount": "100.00",
        },),
        remittance_evidence_complete=True,
    )
    assert ambiguous.method == "service_charge_residual_review"
    assert ambiguous.status == "review_required"
    assert ambiguous.difference == Decimal("5.00")


def verify_final_reason_and_workspace_gate() -> None:
    projected = {
        "state": "prepared_exception",
        "source": {
            "source_reference": "synthetic-check-page",
            "extraction_version": EXTRACTION_VERSION,
            "extracted_invoice_numbers": ["431700001"],
        },
        "result": {
            "customer_resolution": {
                "status": "resolved",
                "customer_number": "700001",
                "selection_basis": "payer_supplied_customer_number",
                "selected_confidence": 1.0,
            },
            "recommendation": {
                "status": "review_required",
                "method": "no_exact_match",
                "difference": "5.00",
                "allocations": [],
                "can_auto_approve": False,
            },
            "exception_analysis": {
                "primary_reason": {"code": "customer_rank_ambiguity"},
            },
            "control_projection": {
                "outcome": "operator_assist",
                "promotion_blockers": ["candidate_not_balanced"],
            },
            "can_auto_approve": False,
            "erp_write_performed": False,
        },
    }
    _recompute_final_exception(projected, ("candidate_not_balanced",))
    final_state = projected["result"]["final_decision_state"]
    assert final_state["primary_reason_code"] == (
        "customer_resolved_no_exact_allocation"
    )
    assert projected["error"]["stage"] == "allocation_evaluation"
    assert final_state["can_auto_approve"] is False
    assert final_state["erp_write_performed"] is False

    workspace = (
        ROOT
        / "src/modules/document-intelligence/components/LockboxReviewWorkspace.tsx"
    ).read_text(encoding="utf-8")
    draft_gate = (
        ROOT
        / "src/modules/document-intelligence/components/lockboxDraftProjection.ts"
    ).read_text(encoding="utf-8")
    assert "allocationDraftDirtyRef.current" in workspace
    assert "markAllocationDraftDirty(false)" in workspace
    assert "transactionStatus !== 'balanced'" in draft_gate
    assert "transactionStatus !== 'corrected'" in draft_gate
    assert "transactionStatus !== 'approved'" in draft_gate


def main() -> None:
    verify_account_directive()
    verify_invoice_cap_and_service_charge()
    verify_final_reason_and_workspace_gate()
    assert RULE_VERSION.endswith("increment4a+BR-LOCKBOX-001..044")
    assert SERVICE_VERSION.endswith("increment4a")
    assert EXTRACTION_VERSION == "pnc-lockbox-parser@0.7.0-r75.1"
    assert PROJECTION_VERSION.endswith("increment4a")
    assert (
        PRIOR_PROJECTED_BALANCED_FLOOR,
        PRIOR_PROJECTED_REVIEW_CEILING,
    ) == (43, 35)
    print(
        "Increment 4A unified-decision verification passed: explicit payer "
        "account and bounded FOR-line evidence, unique invoice-cap plus SC "
        "allocation, final "
        "reason recomputation, untouched-draft projection, and the accepted "
        "43/35 floor remain read-only and unapproved."
    )


if __name__ == "__main__":
    main()
