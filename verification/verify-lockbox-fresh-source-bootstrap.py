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
    FRESH_SOURCE_PROJECTION_VERSION,
    apply_fresh_source_projection,
)


def transaction(ordinal: int, *, balanced: bool, duplicate: bool = False) -> dict:
    transaction_id = f"SYNTHETIC-{ordinal:03d}"
    matching_evidence = {
        "contact_candidate_complete": True,
        "phone_candidate_complete": True,
        "address_candidate_complete": True,
        "exact_phone_postal_match_count": 2 if duplicate else 1,
        "exact_phone_match_count": 2 if duplicate else 1,
        "exact_address_postal_match_count": 0,
        "payer_account_directive_verified": False,
        "payer_account_directive_conflict": False,
        "failed_selection_gates": (
            ["duplicate_exact_phone_zip"] if duplicate else []
        ),
    }
    return {
        "job_id": "synthetic-candidate-job",
        "transaction_id": transaction_id,
        "ordinal": ordinal,
        "state": "prepared_balanced" if balanced else "prepared_exception",
        "source": {
            "transaction_id": transaction_id,
            "original_source": {"transaction_id": transaction_id},
            "projection_evidence": {
                "removed_allocation_count": 0,
                "allocation_conflict_count": 0,
                "customer_conflict_count": 0,
                "boundary_rule": EXPECTED_BOUNDARY_RULE,
                "boundary_closed": True,
                "remittance_evidence_complete": False,
                "review_edits_used_as_extraction": False,
            },
        },
        "result": {
            "customer_resolution": {
                "status": "resolved" if balanced else "ambiguous",
                "customer_number": "SYNTHETIC-CUSTOMER" if balanced else "",
                "selection_basis": "exact_phone_and_zip" if balanced else "",
                "selected_confidence": 0.97 if balanced else 0,
                "matching_evidence": matching_evidence if balanced else {},
            },
            "customer_snapshot": {
                "fields": {
                    "customer_number": (
                        "SYNTHETIC-CUSTOMER" if balanced else ""
                    )
                }
            },
            "recommendation": {
                "status": "recommended" if balanced else "review_required",
                "method": "exact_total_open_balance" if balanced else "no_exact_match",
                "difference": "0.00" if balanced else "1.00",
                "allocations": (
                    [{"business_type": "Debit", "apply_amount": "25.00"}]
                    if balanced
                    else []
                ),
                "can_auto_approve": False,
            },
            "can_auto_approve": False,
            "erp_write_performed": False,
        },
    }


def snapshot() -> dict:
    transactions = [
        transaction(
            ordinal,
            balanced=ordinal in {1, 2},
            duplicate=ordinal == 2,
        )
        for ordinal in range(1, 188)
    ]
    return {
        "job_id": "synthetic-candidate-job",
        "source_job_id": "synthetic-new-source-job",
        "source_file_hash": "f" * 64,
        "state": "complete",
        "complete": True,
        "counts_final": True,
        "expected_count": 187,
        "terminal_count": 187,
        "balanced_count": 2,
        "exception_count": 185,
        "preserved_count": 0,
        "transactions": transactions,
    }


def classified_batch_snapshot() -> dict:
    transactions = []
    for ordinal in range(1, 188):
        balanced = ordinal <= 76
        duplicate = 67 <= ordinal <= 76
        item = transaction(
            ordinal,
            balanced=balanced,
            duplicate=duplicate,
        )
        if not balanced:
            item["result"]["customer_resolution"]["status"] = "not_found"
            item["result"]["exception_analysis"] = {
                "classifier_version": "synthetic-classifier",
                "primary_reason": {
                    "code": "customer_not_found",
                    "category": "customer",
                },
                "contributing_reasons": [],
                "reason_codes": ["customer_not_found"],
                "stage": "customer_resolution",
                "retry_eligible": False,
            }
            item["error"] = {
                "type": "PreparationPolicyError",
                "message": "Synthetic professional-review exception.",
                "stage": "customer_resolution",
                "retry_eligible": False,
            }
        transactions.append(item)
    return {
        "job_id": "synthetic-classified-candidate-job",
        "source_job_id": "synthetic-classified-source-job",
        "source_file_hash": "e" * 64,
        "state": "complete",
        "complete": True,
        "counts_final": True,
        "expected_count": 187,
        "terminal_count": 187,
        "balanced_count": 76,
        "exception_count": 111,
        "preserved_count": 0,
        "transactions": transactions,
    }


def main() -> None:
    projected = apply_fresh_source_projection(snapshot())
    assert projected["expected_count"] == 187
    assert projected["terminal_count"] == 187
    assert projected["balanced_count"] == 1
    assert projected["exception_count"] == 186
    assert projected["admitted_promotion_count"] == 1
    assert projected["blocked_promotion_count"] == 1
    assert projected["projection_mode"] == "fresh_source_initial"
    assert projected["control_job_id"] == ""
    assert projected["control_projection_version"] == FRESH_SOURCE_PROJECTION_VERSION
    assert all(projected["projection_release_gates"].values())
    assert not projected["can_auto_approve"]
    assert not projected["erp_write_performed"]

    incomplete = snapshot()
    incomplete["transactions"].pop()
    try:
        apply_fresh_source_projection(incomplete)
    except RuntimeError as error:
        assert "complete, reconciled" in str(error)
    else:
        raise AssertionError("Incomplete fresh-source coverage did not fail closed.")

    classified = apply_fresh_source_projection(
        classified_batch_snapshot()
    )
    assert classified["balanced_count"] == 66
    assert classified["exception_count"] == 121
    assert classified["admitted_promotion_count"] == 66
    assert classified["blocked_promotion_count"] == 10
    reasons = {
        row["code"]: row["count"]
        for row in classified["exception_reason_summary"][
            "by_primary_reason"
        ]
    }
    assert reasons == {
        "customer_not_found": 111,
        "projection_evidence_gate_blocked": 10,
    }
    assert "preparation_failure" not in reasons
    preserved = classified["transactions"][76]
    assert preserved["state"] == "prepared_exception"
    assert preserved["error"]["stage"] == "customer_resolution"
    assert (
        preserved["result"]["exception_analysis"]["primary_reason"][
            "code"
        ]
        == "customer_not_found"
    )
    assert (
        preserved["result"]["control_projection"]["outcome"]
        == "review_preserved"
    )
    assert not classified["can_auto_approve"]
    assert not classified["erp_write_performed"]

    print(
        "Increment 3T fresh-source classification verification passed: a "
        "complete synthetic "
        "187-transaction source receives its own review-floor projection; "
        "existing professional-review classifications remain distinct from "
        "ten blocked balanced candidates, duplicate ownership remains review, "
        "incomplete coverage fails closed, and neither approval nor ERP write "
        "authority is granted."
    )


if __name__ == "__main__":
    main()
