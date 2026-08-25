from __future__ import annotations

import sys
import types
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


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

if "core.database" not in sys.modules:
    core_database = types.ModuleType("core.database")
    core_database.madden_database = SimpleNamespace(
        fetch_all=lambda *_args, **_kwargs: [],
        fetch_one=lambda *_args, **_kwargs: None,
    )
    sys.modules["core.database"] = core_database

from modules.document_intelligence.lockbox_review import service  # noqa: E402

customer_360_package = types.ModuleType("modules.customer_360")
customer_360_package.__path__ = [
    str(BACKEND_ROOT / "modules" / "customer_360")
]
sys.modules["modules.customer_360"] = customer_360_package

from modules.customer_360 import repository as repository_module  # noqa: E402
from modules.customer_360.repository import CustomerRepository  # noqa: E402


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


def expect_blocked(function, status_code: int) -> None:
    try:
        function()
    except Exception as error:
        assert getattr(error, "status_code", None) == status_code
    else:
        raise AssertionError("Unsafe review evidence was admitted.")


def verify_current_review_validation() -> None:
    first = allocation("7", 11.25, 7)
    second = allocation("8", 14.18, 8)
    current = {
        "customer_number": "customer-test",
        "invoices": [
            {
                "customer_number": "customer-test",
                "invoice_number": "7",
                "raw_transaction_type": "SC",
                "open_item_key": first["open_item_key"],
            },
            {
                "customer_number": "customer-test",
                "invoice_number": "8",
                "raw_transaction_type": "SC",
                "open_item_key": second["open_item_key"],
            },
        ],
    }
    service.configure_governed_preparation_loader(
        lambda _job_id: {
            "transactions": [
                {
                    "transaction_id": "T-CURRENT-SC",
                    "result": {
                        "open_ar": {"invoices": []},
                        "recommendation": {"allocations": []},
                    },
                }
            ]
        }
    )
    service.configure_current_open_ar_loader(
        lambda customer_number, _as_of: current
        if customer_number == "customer-test"
        else {"customer_number": customer_number, "invoices": []}
    )

    service._validate_allocation_identifiers(
        "job-test",
        "T-CURRENT-SC",
        [first, second],
        customer_number="customer-test",
        as_of_date=date(2026, 8, 5),
    )

    expect_blocked(
        lambda: service._validate_allocation_identifiers(
            "job-test",
            "T-CURRENT-SC",
            [first, first],
            customer_number="customer-test",
        ),
        400,
    )
    service.configure_current_open_ar_loader(
        lambda _customer_number, _as_of: {
            "customer_number": "customer-test",
            "invoices": [],
        }
    )
    expect_blocked(
        lambda: service._validate_allocation_identifiers(
            "job-test",
            "T-CURRENT-SC",
            [second],
            customer_number="customer-test",
        ),
        400,
    )

    def unavailable(_customer_number, _as_of):
        raise RuntimeError("synthetic read-only ERP outage")

    service.configure_current_open_ar_loader(unavailable)
    expect_blocked(
        lambda: service._validate_allocation_identifiers(
            "job-test",
            "T-CURRENT-SC",
            [second],
            customer_number="customer-test",
        ),
        503,
    )


def verify_open_invoice_customer_search() -> None:
    captured: dict[str, object] = {}

    def fetch_all(sql, parameters):
        captured["sql"] = sql
        captured["parameters"] = list(parameters)
        return []

    with patch.object(
        repository_module.madden_database,
        "fetch_all",
        fetch_all,
    ):
        CustomerRepository().search_customers(
            search="812-345-678",
            active_only=False,
        )

    sql = str(captured["sql"])
    parameters = list(captured["parameters"])
    assert "FROM TMAROP AS OPEN_AR" in sql
    assert "OPEN_AR.TAROAMTOPN <> 0" in sql
    assert "CUCITY" not in sql.upper()
    assert sql.count("%s") == len(parameters)
    assert parameters.count("812345678") == 4
    for forbidden in ("UPDATE ", "INSERT ", "DELETE "):
        assert forbidden not in sql.upper()

    workspace = (
        ROOT
        / "src"
        / "modules"
        / "document-intelligence"
        / "components"
        / "LockboxReviewWorkspace.tsx"
    ).read_text(encoding="utf-8")
    assert "Open invoice, customer number" in workspace


def main() -> None:
    verify_current_review_validation()
    verify_open_invoice_customer_search()
    print(
        "Current-review and invoice-search verification passed: distinct "
        "current SC items validate for a reviewer-selected customer, unsafe "
        "or unavailable evidence remains blocked, and exact open invoices "
        "can locate customer candidates through schema-compatible read-only "
        "ERP search."
    )


if __name__ == "__main__":
    main()
