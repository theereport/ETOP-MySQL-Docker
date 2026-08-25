from __future__ import annotations

from datetime import date
from decimal import Decimal
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

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

from modules.document_intelligence.lockbox_preparation.control_projection import (
    PRIOR_PROJECTED_BALANCED_FLOOR,
    PRIOR_PROJECTED_REVIEW_CEILING,
    PROJECTION_VERSION,
)
from modules.document_intelligence.lockbox_preparation.policy import (
    OpenInvoice,
    RULE_VERSION,
    recommend_allocation,
)
from modules.document_intelligence.lockbox_preparation.repository import (
    SERVICE_VERSION,
)
from modules.document_intelligence.pnc_lockbox_parser import (
    EXTRACTION_VERSION,
    _ocr_visual_row_text,
)
from modules.document_intelligence.remittance_understanding import (
    extract_remittance_evidence,
)


def main() -> None:
    sparse_data = {
        "text": [
            "430000101",
            "06/06/26",
            "412.34",
            "430000202",
            "06/20/26",
            "587.66",
        ],
        "left": [10, 140, 280, 10, 140, 280],
        "top": [100, 100, 101, 130, 130, 131],
        "width": [80, 70, 60, 80, 70, 60],
        "height": [12, 12, 11, 12, 12, 11],
    }
    visual_text = _ocr_visual_row_text(sparse_data)
    assert visual_text.splitlines() == [
        "430000101 06/06/26 412.34",
        "430000202 06/20/26 587.66",
    ]

    evidence = extract_remittance_evidence(
        visual_text,
        12,
        extraction_source="ocr_visual_row",
        ocr_psm=11,
    )
    assert [row.invoice_number for row in evidence.allocations] == [
        "430000101",
        "430000202",
    ]
    assert [row.net_invoice_amount for row in evidence.allocations] == [
        412.34,
        587.66,
    ]
    assert not evidence.rejected_candidates
    assert all(
        row.extraction_source == "ocr_visual_row"
        and row.ocr_psm == 11
        and row.invoice_page == "12;1"
        for row in evidence.allocations
    )

    recommendation = recommend_allocation(
        check_amount=Decimal("1000.00"),
        extracted_invoice_numbers=(
            row.invoice_number for row in evidence.allocations
        ),
        open_invoices=(
            OpenInvoice(
                customer_number="490000",
                invoice_number="430000101",
                open_amount=Decimal("412.34"),
                signed_source_amount=Decimal("412.34"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="Debit",
            ),
            OpenInvoice(
                customer_number="490000",
                invoice_number="430000202",
                open_amount=Decimal("587.66"),
                signed_source_amount=Decimal("587.66"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="Debit",
            ),
        ),
    )
    assert recommendation.status == "recommended"
    assert recommendation.method == "exact_remittance_invoices"
    assert recommendation.suggested_total == Decimal("1000.00")
    assert recommendation.difference == Decimal("0.00")
    assert not recommendation.can_auto_approve

    separated = _ocr_visual_row_text(
        {
            "text": ["430000303", "1000.00"],
            "left": [10, 280],
            "top": [100, 116],
            "width": [80, 60],
            "height": [10, 10],
        }
    )
    separated_evidence = extract_remittance_evidence(
        separated,
        13,
        extraction_source="ocr_visual_row",
        ocr_psm=11,
    )
    assert separated.splitlines() == ["430000303", "1000.00"]
    assert not separated_evidence.allocations

    assert RULE_VERSION == (
        "ADR-001@0.7.0-wave2-increment3x+BR-LOCKBOX-001..041"
    )
    assert SERVICE_VERSION == "lockbox-preparation@0.7.0-wave2-increment3x"
    assert EXTRACTION_VERSION == "pnc-lockbox-parser@0.7.0-wave2-increment3p"
    assert PROJECTION_VERSION.endswith("increment3x")
    assert (PRIOR_PROJECTED_BALANCED_FLOOR, PRIOR_PROJECTED_REVIEW_CEILING) == (
        43,
        35,
    )

    print(
        "Spatial remittance verification passed: split OCR columns became "
        "two governed source rows, current ERP amounts reconciled exactly, "
        "adjacent rows remained separate, and the accepted 43/35 floor is "
        "protected without approval or ERP write authority."
    )


if __name__ == "__main__":
    main()
