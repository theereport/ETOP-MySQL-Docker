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
    fastapi.HTTPException = type("HTTPException", (Exception,), {})
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

from modules.document_intelligence.classifiers.rule_based import (  # noqa: E402
    classify_document,
)
from modules.document_intelligence.page_classifier import classify_page  # noqa: E402
from modules.document_intelligence.pnc_lockbox_contract import (  # noqa: E402
    PNC_LOCKBOX_HEADER_RULE_VERSION,
)
from modules.document_intelligence.pnc_lockbox_parser import (  # noqa: E402
    _transaction_from_page,
)


def main() -> None:
    header = (
        "Transaction Information G-9000001 DAL-640045 2026/08/04\n"
        "Reported Amount $ 1,234.56\n"
        "Check Number 012345"
    )
    parsed = _transaction_from_page(header, 7)
    assert parsed is not None
    assert parsed.lockbox == "DAL-640045"
    assert parsed.transaction_id == "G-9000001"
    assert parsed.check_amount == 1234.56
    assert classify_page(header) == "transaction"
    assert classify_document("sample-dallas-lockbox.pdf", f"PNC\n{header}")[
        "document_type"
    ] == "pnc_lockbox"

    pittsburgh = header.replace("DAL-640045", "PGH-640045")
    assert _transaction_from_page(pittsburgh, 7) is not None
    assert classify_page(pittsburgh) == "transaction"
    assert PNC_LOCKBOX_HEADER_RULE_VERSION.endswith("increment3y")

    print(
        "PNC site compatibility passed: Dallas and Pittsburgh headers enter "
        "the same transaction/OCR planning path without changing invoice, "
        "allocation, approval, or ERP-write rules."
    )


if __name__ == "__main__":
    main()
