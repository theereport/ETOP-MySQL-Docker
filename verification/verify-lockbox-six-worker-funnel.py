from __future__ import annotations

import os
import inspect
import importlib.util
import sys
import types
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

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

from customer_match_service import CustomerMatchInput, rank_customer_matches
from modules.document_intelligence.lockbox_preparation.contracts import OpenInvoice
from modules.document_intelligence.lockbox_preparation.coordinator import (
    DEFAULT_READ_WORKERS,
    MAX_READ_WORKERS,
)
from modules.document_intelligence.lockbox_preparation.policy import (
    RULE_VERSION,
    recommend_allocation,
)
from modules.document_intelligence.pnc_lockbox_parser import (
    DEFAULT_OCR_WORKERS,
    EXTRACTION_VERSION,
    MAX_OCR_WORKERS,
    _ocr_worker_count,
    parse_pnc_lockbox,
)


CUSTOMERS = [
    {
        "customer_number": "700001",
        "customer_name": "SYNTHETIC NORTH SERVICE",
        "phone": "3125550101",
        "address_line_1": "1400 CONTROL ROAD",
        "city": "EXAMPLEVILLE",
        "state": "IL",
        "postal_code": "60601",
    },
    {
        "customer_number": "700002",
        "customer_name": "SYNTHETIC SOUTH SERVICE",
        "phone": "3125550102",
        "address_line_1": "88 SAMPLE STREET",
        "city": "EXAMPLEVILLE",
        "state": "IL",
        "postal_code": "60601",
    },
]


def verify_workers() -> None:
    assert (DEFAULT_OCR_WORKERS, MAX_OCR_WORKERS) == (6, 8)
    assert (DEFAULT_READ_WORKERS, MAX_READ_WORKERS) == (6, 8)
    parser_source = inspect.getsource(parse_pnc_lockbox)
    assert "ThreadPoolExecutor" in parser_source
    assert 'thread_name_prefix="etop-lockbox-ocr"' in parser_source
    assert "zip(planned_pages, futures, strict=True)" in parser_source
    prior = os.environ.pop("ETOP_LOCKBOX_OCR_WORKERS", None)
    try:
        assert _ocr_worker_count() == 6
        os.environ["ETOP_LOCKBOX_OCR_WORKERS"] = "99"
        assert _ocr_worker_count() == 8
        os.environ["ETOP_LOCKBOX_OCR_WORKERS"] = "invalid"
        assert _ocr_worker_count() == 6
    finally:
        if prior is None:
            os.environ.pop("ETOP_LOCKBOX_OCR_WORKERS", None)
        else:
            os.environ["ETOP_LOCKBOX_OCR_WORKERS"] = prior


def verify_customer_funnel() -> None:
    resolved = rank_customer_matches(
        CUSTOMERS,
        CustomerMatchInput(
            address_line_1="1400 Control Rd.",
            postal_code="60601-1234",
        ),
        address_candidate_complete=True,
    )
    assert resolved["auto_select"] is True
    assert resolved["recommended_customer"]["customer_number"] == "700001"
    assert resolved["selected_basis"] == "exact_address_and_zip"

    incomplete = rank_customer_matches(
        CUSTOMERS,
        CustomerMatchInput(
            address_line_1="1400 Control Road",
            postal_code="60601",
        ),
        address_candidate_complete=False,
    )
    assert incomplete["auto_select"] is False
    assert "address_candidate_set_incomplete" in incomplete[
        "failed_selection_gates"
    ]

    duplicate = {**CUSTOMERS[0], "customer_number": "700003"}
    ambiguous = rank_customer_matches(
        [*CUSTOMERS, duplicate],
        CustomerMatchInput(
            address_line_1="1400 Control Road",
            postal_code="60601",
        ),
        address_candidate_complete=True,
    )
    assert ambiguous["auto_select"] is False
    assert ambiguous["exact_address_postal_match_count"] == 2


def open_item(
    number: str,
    amount: str,
    due_date: date,
    *,
    transaction_type: str = "I",
    signed: str | None = None,
    aging: str = "",
) -> OpenInvoice:
    return OpenInvoice(
        customer_number="700001",
        invoice_number=number,
        open_amount=Decimal(amount),
        signed_source_amount=Decimal(signed if signed is not None else amount),
        due_date=due_date,
        raw_transaction_type=transaction_type,
        aging_bucket=aging,
        open_item_key=f"700001|{transaction_type}|{number}|",
    )


def verify_allocation_funnel() -> None:
    total = recommend_allocation(
        check_amount=Decimal("140.00"),
        extracted_invoice_numbers=(),
        open_invoices=(
            open_item("431400001", "150.00", date(2026, 5, 10)),
            open_item(
                "431400002",
                "20.00",
                date(2026, 6, 10),
                transaction_type="C",
                signed="-20.00",
            ),
            open_item(
                "4",
                "10.00",
                date(2026, 7, 10),
                transaction_type="SC",
            ),
        ),
    )
    assert total.method == "exact_total_open_balance"
    assert total.difference == Decimal("0.00")
    assert any(line.allocation_kind == "service_charge" for line in total.allocations)
    assert any(line.apply_amount < 0 for line in total.allocations)
    assert total.can_auto_approve is False

    oldest = recommend_allocation(
        check_amount=Decimal("150.00"),
        extracted_invoice_numbers=(),
        open_invoices=(
            open_item("431500001", "100.00", date(2026, 5, 10)),
            open_item("431500002", "50.00", date(2026, 6, 10)),
            open_item("431500003", "75.00", date(2026, 7, 10)),
        ),
    )
    assert oldest.method == "oldest_open_items_exact_match"
    assert oldest.difference == Decimal("0.00")
    assert oldest.can_auto_approve is False


def main() -> None:
    verify_workers()
    verify_customer_funnel()
    verify_allocation_funnel()
    assert RULE_VERSION.endswith("increment3x+BR-LOCKBOX-001..041")
    assert EXTRACTION_VERSION.endswith("increment3p")
    print(
        "Increment 3P worker regression passed: six bounded OCR/read workers, "
        "complete exact street+ZIP resolution, and exact signed balance "
        "fallbacks remained deterministic, read-only, and unapproved."
    )


if __name__ == "__main__":
    main()
