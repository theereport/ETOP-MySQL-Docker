from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if "fastapi" not in sys.modules:
    fastapi = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class APIRouter:
        def __init__(self, *args, **kwargs):
            self.prefix = kwargs.get("prefix", "")
            self.routes = []

        def _route(self, path, *args, **kwargs):
            def decorator(function):
                self.routes.append(
                    SimpleNamespace(path=self.prefix + path, endpoint=function)
                )
                return function

            return decorator

        get = _route
        post = _route
        put = _route

        def include_router(self, router):
            self.routes.append(SimpleNamespace(router=router))

    fastapi.APIRouter = APIRouter
    fastapi.FastAPI = APIRouter
    fastapi.HTTPException = HTTPException
    fastapi.File = lambda default=None, *args, **kwargs: default
    fastapi.Query = lambda default=None, *args, **kwargs: default
    fastapi.UploadFile = type("UploadFile", (), {})
    sys.modules["fastapi"] = fastapi

if "fastapi.responses" not in sys.modules:
    responses = types.ModuleType("fastapi.responses")
    responses.FileResponse = SimpleNamespace
    sys.modules["fastapi.responses"] = responses

if "core.database" not in sys.modules:
    core_database = types.ModuleType("core.database")
    core_database.madden_database = SimpleNamespace()
    sys.modules["core.database"] = core_database

if "pytesseract" not in sys.modules:
    pytesseract = types.ModuleType("pytesseract")
    pytesseract.pytesseract = SimpleNamespace(tesseract_cmd="")
    pytesseract.Output = SimpleNamespace(DICT="dict")
    pytesseract.image_to_string = lambda *args, **kwargs: ""
    pytesseract.image_to_data = lambda *args, **kwargs: {
        "text": [],
        "conf": [],
    }
    sys.modules["pytesseract"] = pytesseract

from modules.document_intelligence.lockbox_review import service  # noqa: E402


def allocation(reference: str, amount: float, count: int) -> dict:
    return service._normalize_allocation(
        {
            "invoice_number": reference,
            "net_invoice_amount": amount,
            "allocation_kind": "service_charge",
            "erp_transaction_type": "SC",
            "open_item_key": f"customer-test|SC|{reference}|{count}",
        }
    )


def main() -> None:
    first = allocation("7", 11.25, 7)
    second = allocation("8", 14.18, 8)
    preparation = {
        "transactions": [
            {
                "transaction_id": "T-MULTI-SC",
                "result": {
                    "open_ar": {
                        "invoices": [
                            {
                                "customer_number": "customer-test",
                                "invoice_number": "7",
                                "open_amount": "11.25",
                                "raw_transaction_type": "SC",
                                "invoice_count": 7,
                                "open_item_key": first["open_item_key"],
                            },
                            {
                                "customer_number": "customer-test",
                                "invoice_number": "8",
                                "open_amount": "14.18",
                                "raw_transaction_type": "SC",
                                "invoice_count": 8,
                                "open_item_key": second["open_item_key"],
                            },
                        ]
                    },
                    "recommendation": {"allocations": []},
                },
            }
        ]
    }
    service.configure_governed_preparation_loader(
        lambda _job_id: preparation
    )

    service._validate_allocation_identifiers(
        "job-test",
        "T-MULTI-SC",
        [first, second],
    )

    for rejected in (
        [first, first],
        [
            {
                **second,
                "invoice_number": "9",
                "open_item_key": "customer-test|SC|9|9",
            }
        ],
    ):
        try:
            service._validate_allocation_identifiers(
                "job-test",
                "T-MULTI-SC",
                rejected,
            )
        except Exception as error:
            assert getattr(error, "status_code", None) == 400
            assert "Multiple service charges are allowed" in str(error)
        else:
            raise AssertionError("Unsafe service-charge review row was admitted.")

    print(
        "Multiple-service-charge review validation passed: two distinct "
        "prepared monthly SC items are admitted together, while reuse and "
        "forged short identities remain blocked."
    )


if __name__ == "__main__":
    main()
