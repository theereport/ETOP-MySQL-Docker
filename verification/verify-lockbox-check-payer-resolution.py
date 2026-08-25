from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


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

from customer_match_service import CustomerMatchInput, rank_customer_matches
from modules.document_intelligence.lockbox_preparation.control_projection import (
    PRIOR_PROJECTED_BALANCED_FLOOR,
    PRIOR_PROJECTED_REVIEW_CEILING,
    PROJECTION_VERSION,
)
from modules.document_intelligence.lockbox_preparation.policy import RULE_VERSION
from modules.document_intelligence.lockbox_preparation.repository import (
    SERVICE_VERSION,
)
from modules.document_intelligence.lockbox_preparation.source_loader import (
    merge_extractions,
)
from modules.document_intelligence.pnc_lockbox_parser import (
    EXTRACTION_VERSION,
    _extract_transaction_customer_identity,
)
from modules.document_intelligence.vision_models import CustomerIdentity, Region


def verify_bounded_identity_fallback() -> None:
    primary = CustomerIdentity(
        customer_name="PAYEE COMPANY",
        customer_phone="3125550184",
        customer_postal_code="60601",
        confidence=0.96,
        evidence=["phone number", "city/state/ZIP", "business or payer name"],
    )
    payer = CustomerIdentity(
        customer_name="EXAMPLE AUTOMOTIVE, INC.",
        customer_phone="3125550184",
        customer_address_line_1="1200 EXAMPLE ROAD",
        customer_city="EXAMPLE CITY",
        customer_state="IL",
        customer_postal_code="60601",
        confidence=0.99,
        evidence=["phone number", "city/state/ZIP", "street address"],
    )
    regions = [
        ("detected_check_image", Region(0, 50, 100, 100)),
        ("below_label_full_width", Region(0, 20, 100, 100)),
    ]
    with (
        patch(
            "modules.document_intelligence.pnc_lockbox_parser."
            "find_check_regions",
            return_value=regions,
        ),
        patch(
            "modules.document_intelligence.pnc_lockbox_parser."
            "extract_customer_identity",
            side_effect=(primary, payer),
        ),
    ):
        identity, strategy, attempts = _extract_transaction_customer_identity(
            SimpleNamespace(),
            "synthetic transaction page",
        )
    assert identity.customer_phone == "3125550184"
    assert identity.customer_postal_code == "60601"
    assert strategy == "below_label_full_width"
    assert len(attempts) == 2
    assert attempts[0]["exact_phone_present"] is True
    assert attempts[0]["five_digit_zip_present"] is True
    assert attempts[0]["street_present"] is False
    assert attempts[1]["street_present"] is True


def verify_name_only_payee_conflict_is_preserved_but_nonblocking() -> None:
    merged = merge_extractions(
        {
            "transactions": [
                {
                    "transaction_id": "G-SAFE-1",
                    "customer_name": "PAYEE COMPANY",
                    "allocations": [],
                }
            ]
        },
        {
            "transactions": [
                {
                    "transaction_id": "G-SAFE-1",
                    "customer_name": "EXAMPLE AUTOMOTIVE, INC.",
                    "customer_phone": "3125550184",
                    "customer_address_line_1": "1200 EXAMPLE ROAD",
                    "customer_city": "EXAMPLE CITY",
                    "customer_state": "IL",
                    "customer_postal_code": "60601",
                    "customer_identity_confidence": 0.99,
                    "transaction_boundary_rule": (
                        "next_transaction_information"
                    ),
                    "transaction_boundary_closed": True,
                    "allocations": [],
                }
            ]
        },
    )
    transaction = merged["transactions"][0]
    evidence = transaction["projection_evidence"]
    assert transaction["customer_name"] == "PAYEE COMPANY"
    assert transaction["customer_phone"] == "3125550184"
    assert transaction["customer_postal_code"] == "60601"
    assert evidence["customer_conflict_count"] == 0
    assert evidence["customer_nonmaterial_name_conflict_count"] == 1
    assert evidence["baseline_evidence_preserved"] is True


def verify_exact_phone_zip_still_requires_complete_unique_erp_owner() -> None:
    customer = {
        "customer_number": "400001",
        "customer_name": "EXAMPLE AUTOMOTIVE, INC.",
        "phone": "3125550184",
        "address_line_1": "1200 EXAMPLE ROAD",
        "city": "EXAMPLE CITY",
        "state": "IL",
        "postal_code": "60601",
    }
    resolved = rank_customer_matches(
        [customer],
        CustomerMatchInput(
            phone="(312) 555-0184",
            postal_code="60601",
            customer_name="PAYEE COMPANY",
        ),
        contact_candidate_complete=True,
    )
    assert resolved["auto_select"] is True
    assert resolved["selected_basis"] == "exact_phone_and_zip"
    assert resolved["recommended_customer"]["customer_number"] == "400001"

    incomplete = rank_customer_matches(
        [customer],
        CustomerMatchInput(
            phone="3125550184",
            postal_code="60601",
        ),
        contact_candidate_complete=False,
    )
    assert incomplete["auto_select"] is False
    assert "phone_candidate_set_incomplete" in incomplete[
        "failed_selection_gates"
    ]


if __name__ == "__main__":
    assert RULE_VERSION == (
        "ADR-001@0.7.0-wave2-increment4a+BR-LOCKBOX-001..044"
    )
    assert SERVICE_VERSION == "lockbox-preparation@0.7.0-wave2-increment4a"
    assert EXTRACTION_VERSION == "pnc-lockbox-parser@0.7.0-r75.1"
    assert PROJECTION_VERSION.endswith("increment4a")
    assert (
        PRIOR_PROJECTED_BALANCED_FLOOR,
        PRIOR_PROJECTED_REVIEW_CEILING,
    ) == (43, 35)
    verify_bounded_identity_fallback()
    verify_name_only_payee_conflict_is_preserved_but_nonblocking()
    verify_exact_phone_zip_still_requires_complete_unique_erp_owner()
    print(
        "Synthetic check-payer resolution passed: a payee name plus phone and "
        "ZIP without a street did not stop bounded payer recovery, the "
        "original payee assertion remained "
        "preserved, exact unique phone plus ZIP resolved one ERP customer, "
        "and incomplete candidate reads remained ambiguous."
    )
