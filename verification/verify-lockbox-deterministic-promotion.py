from __future__ import annotations

import importlib.util
import sys
import types
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
        def __init__(self, *args, prefix="", **kwargs):
            self.prefix = prefix
            self.routes = []

        def _register(self, method, path, *args, **kwargs):
            def decorator(function):
                self.routes.append(
                    SimpleNamespace(
                        path=f"{self.prefix}{path}",
                        methods={method.upper()},
                        endpoint=function,
                    )
                )
                return function

            return decorator

        def get(self, path, *args, **kwargs):
            return self._register("get", path, *args, **kwargs)

        def post(self, path, *args, **kwargs):
            return self._register("post", path, *args, **kwargs)

        def put(self, path, *args, **kwargs):
            return self._register("put", path, *args, **kwargs)

        def include_router(self, router, *, prefix="", **kwargs):
            for route in router.routes:
                self.routes.append(
                    SimpleNamespace(
                        path=f"{self.prefix}{prefix}{route.path}",
                        methods=set(getattr(route, "methods", set())),
                        endpoint=getattr(route, "endpoint", None),
                    )
                )

    class FastAPI(APIRouter):
        def openapi(self):
            paths = {}
            for route in self.routes:
                methods = paths.setdefault(route.path, {})
                for method in route.methods:
                    methods[method.lower()] = {}
            return {"paths": paths}

    class HTTPException(RuntimeError):
        def __init__(self, status_code, detail=None, *args, **kwargs):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    fastapi.APIRouter = APIRouter
    fastapi.FastAPI = FastAPI
    fastapi.HTTPException = HTTPException
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
    EXPECTED_BOUNDARY_RULE,
    PROJECTION_VERSION,
    promotion_assessment,
)


def source_evidence(
    *,
    conflict_count: int = 0,
    conflict_fields: tuple[str, ...] = (),
) -> dict:
    return {
        "removed_allocation_count": 0,
        "allocation_conflict_count": 0,
        "customer_conflict_count": conflict_count,
        "customer_conflict_fields": list(conflict_fields),
        "boundary_rule": EXPECTED_BOUNDARY_RULE,
        "boundary_closed": True,
        "remittance_evidence_complete": False,
        "review_edits_used_as_extraction": False,
    }


def candidate(
    *,
    basis: str,
    confidence: float,
    matching_evidence: dict,
    conflict_count: int = 0,
    conflict_fields: tuple[str, ...] = (),
) -> dict:
    return {
        "state": "prepared_balanced",
        "source": {
            "projection_evidence": source_evidence(
                conflict_count=conflict_count,
                conflict_fields=conflict_fields,
            )
        },
        "result": {
            "customer_resolution": {
                "status": "resolved",
                "customer_number": "700001",
                "selection_basis": basis,
                "confidence_basis": basis,
                "selected_confidence": confidence,
                "matching_evidence": matching_evidence,
            },
            "recommendation": {
                "status": "recommended",
                "method": "oldest_open_items_exact_match",
                "difference": "0.00",
                "allocations": [
                    {
                        "invoice_number": "431700001",
                        "business_type": "Debit",
                        "apply_amount": "173.25",
                    }
                ],
                "can_auto_approve": False,
            },
            "can_auto_approve": False,
            "erp_write_performed": False,
        },
    }


def control() -> dict:
    return {
        "state": "prepared_exception",
        "source": {"projection_evidence": source_evidence()},
        "result": {
            "customer_resolution": {"status": "not_found"},
            "recommendation": {
                "status": "review_required",
                "method": "no_exact_match",
                "difference": "173.25",
                "allocations": [],
            },
        },
    }


def verify_complete_phone_zip() -> None:
    phone_zip = {
        "contact_candidate_complete": True,
        "phone_candidate_complete": True,
        "exact_phone_postal_match_count": 1,
        "exact_phone_match_count": 1,
        "failed_selection_gates": [],
    }
    admitted, blockers = promotion_assessment(
        control(),
        candidate(
            basis="exact_phone_and_zip",
            confidence=0.97,
            matching_evidence=phone_zip,
        ),
    )
    assert admitted, blockers

    incomplete = dict(phone_zip)
    incomplete["contact_candidate_complete"] = False
    incomplete["failed_selection_gates"] = [
        "contact_candidate_set_incomplete"
    ]
    admitted, blockers = promotion_assessment(
        control(),
        candidate(
            basis="exact_phone_and_zip",
            confidence=0.97,
            matching_evidence=incomplete,
        ),
    )
    assert not admitted
    assert "customer_evidence_not_deterministic" in blockers

    duplicate = dict(phone_zip)
    duplicate["exact_phone_postal_match_count"] = 2
    duplicate["failed_selection_gates"] = ["duplicate_exact_phone_zip"]
    admitted, blockers = promotion_assessment(
        control(),
        candidate(
            basis="exact_phone_and_zip",
            confidence=0.97,
            matching_evidence=duplicate,
        ),
    )
    assert not admitted
    assert "customer_evidence_not_deterministic" in blockers


def verify_name_only_payee_conflict() -> None:
    address_zip = {
        "address_candidate_complete": True,
        "exact_address_postal_match_count": 1,
        "failed_selection_gates": [],
    }
    admitted, blockers = promotion_assessment(
        control(),
        candidate(
            basis="unique_exact_address_and_zip",
            confidence=1.0,
            matching_evidence=address_zip,
            conflict_count=1,
            conflict_fields=("customer_name",),
        ),
    )
    assert admitted, blockers

    admitted, blockers = promotion_assessment(
        control(),
        candidate(
            basis="unique_exact_address_and_zip",
            confidence=1.0,
            matching_evidence=address_zip,
            conflict_count=2,
            conflict_fields=("customer_name", "customer_phone"),
        ),
    )
    assert not admitted
    assert "customer_evidence_conflict" in blockers


def verify_allocation_and_authority_boundaries() -> None:
    address_zip = {
        "address_candidate_complete": True,
        "exact_address_postal_match_count": 1,
        "failed_selection_gates": [],
    }
    unresolved = candidate(
        basis="unique_exact_address_and_zip",
        confidence=1.0,
        matching_evidence=address_zip,
    )
    unresolved["result"]["recommendation"]["difference"] = "0.02"
    admitted, blockers = promotion_assessment(control(), unresolved)
    assert not admitted
    assert "allocation_not_reconciled" in blockers

    unresolved = candidate(
        basis="unique_exact_address_and_zip",
        confidence=1.0,
        matching_evidence=address_zip,
    )
    unresolved["result"]["recommendation"]["allocations"] = []
    admitted, blockers = promotion_assessment(control(), unresolved)
    assert not admitted
    assert "allocation_rows_missing" in blockers

    unresolved = candidate(
        basis="unique_exact_address_and_zip",
        confidence=1.0,
        matching_evidence=address_zip,
    )
    unresolved["result"]["can_auto_approve"] = True
    admitted, blockers = promotion_assessment(control(), unresolved)
    assert not admitted
    assert "automatic_approval_reported" in blockers


def main() -> None:
    verify_complete_phone_zip()
    verify_name_only_payee_conflict()
    verify_allocation_and_authority_boundaries()
    assert PROJECTION_VERSION.endswith(
        (
            "increment3q",
            "increment3r",
            "increment3u",
            "increment3v",
            "increment3w",
            "increment3x",
        )
    )
    print(
        "Retained Increment 3Q deterministic-promotion verification passed: complete "
        "exact phone-plus-ZIP and street-plus-ZIP ownership may promote exact "
        "untouched recommendations, while incomplete, duplicate, conflicting, "
        "unreconciled, empty, and approval-capable candidates remain review."
    )


if __name__ == "__main__":
    main()
