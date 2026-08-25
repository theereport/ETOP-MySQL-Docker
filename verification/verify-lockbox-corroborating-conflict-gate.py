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


def exact_phone_postal_evidence(*, complete: bool = True) -> dict:
    return {
        "valid_invoice_count": 0,
        "invoice_owner_conflict": False,
        "partial_invoice_owner_evidence": False,
        "contact_candidate_complete": complete,
        "phone_candidate_complete": True,
        "address_candidate_complete": True,
        "exact_phone_postal_match_count": 1,
        "exact_phone_match_count": 1,
        "exact_address_postal_match_count": 0,
        "payer_account_directive_verified": False,
        "payer_account_directive_conflict": False,
        "failed_selection_gates": (
            [] if complete else ["contact_candidate_set_incomplete"]
        ),
    }


def candidate(
    *,
    basis: str = "exact_phone_and_zip",
    confidence: float = 0.97,
    matching_evidence: dict | None = None,
    conflict_count: int = 0,
    conflict_fields: tuple[str, ...] = (),
) -> dict:
    return {
        "state": "prepared_balanced",
        "source": {
            "projection_evidence": source_evidence(
                conflict_count=conflict_count,
                conflict_fields=conflict_fields,
            ),
            "original_source": {},
        },
        "result": {
            "customer_resolution": {
                "status": "resolved",
                "customer_number": "700001",
                "selection_basis": basis,
                "confidence_basis": basis,
                "selected_confidence": confidence,
                "matching_evidence": (
                    matching_evidence or exact_phone_postal_evidence()
                ),
            },
            "customer_snapshot": {
                "fields": {"customer_number": "700001"}
            },
            "recommendation": {
                "status": "recommended",
                "method": "exact_aging_bucket_match",
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


def verify_reported_gate_shape() -> None:
    reported_shape = candidate(
        conflict_count=2,
        conflict_fields=("customer_name", "customer_city"),
    )
    admitted, blockers = promotion_assessment(control(), reported_shape)
    assert admitted, blockers


def verify_identity_boundaries() -> None:
    incomplete = candidate(
        matching_evidence=exact_phone_postal_evidence(complete=False),
        conflict_count=2,
        conflict_fields=("customer_name", "customer_city"),
    )
    admitted, blockers = promotion_assessment(control(), incomplete)
    assert not admitted
    assert "customer_evidence_not_deterministic" in blockers
    assert "customer_evidence_conflict" in blockers

    duplicate_evidence = exact_phone_postal_evidence()
    duplicate_evidence["exact_phone_postal_match_count"] = 2
    duplicate_evidence["failed_selection_gates"] = [
        "duplicate_exact_phone_zip"
    ]
    duplicate = candidate(
        matching_evidence=duplicate_evidence,
        conflict_count=2,
        conflict_fields=("customer_name", "customer_city"),
    )
    admitted, blockers = promotion_assessment(control(), duplicate)
    assert not admitted
    assert "customer_evidence_not_deterministic" in blockers

    address = candidate(
        basis="unique_exact_address_and_zip",
        confidence=1.0,
        matching_evidence={
            "address_candidate_complete": True,
            "exact_address_postal_match_count": 1,
            "failed_selection_gates": [],
        },
        conflict_count=2,
        conflict_fields=("customer_name", "customer_city"),
    )
    admitted, blockers = promotion_assessment(control(), address)
    assert not admitted
    assert "customer_evidence_conflict" in blockers

    contact_conflict = candidate(
        conflict_count=3,
        conflict_fields=(
            "customer_name",
            "customer_city",
            "customer_phone",
        ),
    )
    admitted, blockers = promotion_assessment(control(), contact_conflict)
    assert not admitted
    assert "customer_evidence_conflict" in blockers

    count_mismatch = candidate(
        conflict_count=3,
        conflict_fields=("customer_name", "customer_city"),
    )
    admitted, blockers = promotion_assessment(control(), count_mismatch)
    assert not admitted
    assert "customer_evidence_conflict" in blockers


def verify_allocation_and_authority_boundaries() -> None:
    unresolved = candidate(
        conflict_count=2,
        conflict_fields=("customer_name", "customer_city"),
    )
    unresolved["result"]["recommendation"]["difference"] = "0.02"
    admitted, blockers = promotion_assessment(control(), unresolved)
    assert not admitted
    assert "allocation_not_reconciled" in blockers

    unresolved = candidate(
        conflict_count=2,
        conflict_fields=("customer_name", "customer_city"),
    )
    unresolved["result"]["recommendation"]["allocations"] = []
    admitted, blockers = promotion_assessment(control(), unresolved)
    assert not admitted
    assert "allocation_rows_missing" in blockers

    unresolved = candidate(
        conflict_count=2,
        conflict_fields=("customer_name", "customer_city"),
    )
    unresolved["result"]["can_auto_approve"] = True
    admitted, blockers = promotion_assessment(control(), unresolved)
    assert not admitted
    assert "automatic_approval_reported" in blockers

    unresolved = candidate(
        conflict_count=2,
        conflict_fields=("customer_name", "customer_city"),
    )
    unresolved["result"]["erp_write_performed"] = True
    admitted, blockers = promotion_assessment(control(), unresolved)
    assert not admitted
    assert "erp_write_reported" in blockers


def main() -> None:
    verify_reported_gate_shape()
    verify_identity_boundaries()
    verify_allocation_and_authority_boundaries()
    assert PROJECTION_VERSION.endswith("increment3x")
    print(
        "Increment 3R corroborating-conflict verification passed: a complete "
        "unique phone/postal owner is not defeated by name/city-only "
        "projection conflicts, while incomplete or duplicate ownership, "
        "address-basis city conflicts, contact conflicts, allocation gaps, "
        "approval, and ERP writes remain blocked."
    )


if __name__ == "__main__":
    main()
