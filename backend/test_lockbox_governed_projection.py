from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import types
import unittest
from copy import deepcopy
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _install_runtime_stubs() -> None:
    try:
        __import__("fastapi")
    except ModuleNotFoundError:
        pass
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

            def _route(self, path, method):
                def decorator(function):
                    self.routes.append(
                        SimpleNamespace(
                            path=self.prefix + path,
                            endpoint=function,
                            methods={method},
                        )
                    )
                    return function
                return decorator

            def get(self, path, *args, **kwargs):
                return self._route(path, "GET")

            def post(self, path, *args, **kwargs):
                return self._route(path, "POST")

            def put(self, path, *args, **kwargs):
                return self._route(path, "PUT")

            def include_router(self, router):
                self.routes.append(SimpleNamespace(router=router))

            def openapi(self):
                paths = {}

                def collect(candidate):
                    nested = getattr(candidate, "router", None)
                    if nested is not None:
                        for item in nested.routes:
                            collect(item)
                        return
                    path = getattr(candidate, "path", "")
                    if path:
                        paths.setdefault(path, {})

                for route in self.routes:
                    collect(route)
                return {"paths": paths}

        def parameter(default=None, *args, **kwargs):
            return default

        fastapi.APIRouter = APIRouter
        fastapi.FastAPI = APIRouter
        fastapi.HTTPException = HTTPException
        fastapi.File = parameter
        fastapi.Query = parameter
        fastapi.UploadFile = type("UploadFile", (), {})
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")
        responses.FileResponse = type("FileResponse", (), {})
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


_install_runtime_stubs()

from modules.document_intelligence.lockbox_preparation.service import (
    DurableLockboxPreparationService,
)
from modules.document_intelligence.lockbox_preparation.control_projection import (
    _customer_evidence_is_deterministic,
)
from modules.document_intelligence.lockbox_preparation.contracts import (
    StartPreparationRequest,
)
from modules.document_intelligence.lockbox_preparation.policy import RULE_VERSION
from modules.document_intelligence.lockbox_preparation.repository import (
    SERVICE_VERSION,
    LockboxPreparationRepository,
)
from modules.document_intelligence.lockbox_review import database
from data.mysql import (
    _reset_engine_override,
    _set_engine_override,
    lockbox_reviews_table,
    metadata as shared_metadata,
)
from modules.document_intelligence.lockbox_review.schemas import (
    AppendCustomerNoteRequest,
    LockboxReviewResponse,
    SaveTransactionReviewRequest,
)
from modules.document_intelligence.lockbox_review import service as review_service
from modules.document_intelligence.lockbox_service import (
    _recalculate_transaction,
)
from modules.document_intelligence.lockbox_schemas import (
    LockboxProcessingResponse,
)
from modules.document_intelligence.manifest import manifest


def _routes(router):
    try:
        from fastapi.routing import iter_route_contexts
    except (ImportError, ModuleNotFoundError):
        pass
    else:
        yield from iter_route_contexts(router.routes)
        return

    for route in router.routes:
        effective_route_contexts = getattr(
            route,
            "effective_route_contexts",
            None,
        )
        if callable(effective_route_contexts):
            yield from effective_route_contexts()
            continue

        nested = getattr(route, "router", None)
        if nested is None:
            nested = getattr(route, "original_router", None)
        if nested is not None:
            yield from _routes(nested)
        elif hasattr(route, "path"):
            yield route


class GovernedRouteContractTest(unittest.TestCase):
    def test_route_enumerator_supports_included_routers(self):
        from fastapi import APIRouter

        child = APIRouter(prefix="/route-iterator")

        @child.get("/probe")
        def route_iterator_probe():
            return {"status": "ok"}

        parent = APIRouter()
        parent.include_router(child)
        matches = [
            route
            for route in _routes(parent)
            if getattr(route, "path", None) == "/route-iterator/probe"
            and "GET" in getattr(route, "methods", {"GET"})
        ]
        self.assertEqual(len(matches), 1)

    def test_review_routes_have_one_runtime_owner(self):
        routes = list(_routes(manifest.router))
        targets = {
            ("GET", "/api/v1/documents/jobs/{job_id}/lockbox/review"),
            (
                "PUT",
                "/api/v1/documents/jobs/{job_id}/lockbox/review/"
                "{transaction_id}",
            ),
            (
                "GET",
                "/api/v1/documents/jobs/{job_id}/lockbox/review/"
                "{transaction_id}/customer-notes",
            ),
            (
                "POST",
                "/api/v1/documents/jobs/{job_id}/lockbox/review/"
                "{transaction_id}/customer-notes",
            ),
        }
        for method, path in targets:
            matches = [
                route
                for route in routes
                if route.path == path
                and method in getattr(route, "methods", {method})
            ]
            self.assertEqual(len(matches), 1, (method, path, matches))

    def test_current_governed_projection_route_is_published(self):
        paths = {route.path for route in _routes(manifest.router)}
        self.assertIn(
            "/api/v1/documents/jobs/{source_job_id}/lockbox/"
            "preparation/current",
            paths,
        )


class GovernedProjectionContractTest(unittest.TestCase):
    def test_verified_for_line_customer_is_deterministic_only_without_conflict(
        self,
    ):
        result = {
            "customer_resolution": {
                "status": "resolved",
                "customer_number": "331002",
                "selection_basis": "check_for_customer_number",
                "selected_confidence": 1.0,
                "matching_evidence": {
                    "selected_basis": "check_for_customer_number",
                    "check_for_customer_verified": True,
                    "check_for_customer_conflict": False,
                    "invoice_owner_conflict": False,
                    "partial_invoice_owner_evidence": False,
                    "failed_selection_gates": [],
                },
            }
        }

        self.assertTrue(_customer_evidence_is_deterministic(result))
        result["customer_resolution"]["matching_evidence"][
            "check_for_customer_conflict"
        ] = True
        self.assertFalse(_customer_evidence_is_deterministic(result))

    @staticmethod
    def service():
        return DurableLockboxPreparationService(
            coordinator=SimpleNamespace(repository=SimpleNamespace()),
            control_projection_required=False,
        )

    def test_count_reconciliation_and_safety_flags(self):
        snapshot = {
            "complete": True,
            "counts_final": True,
            "expected_count": 78,
            "terminal_count": 78,
            "balanced_count": 30,
            "exception_count": 48,
            "preserved_count": 0,
            "exception_reason_summary": {
                "total_exception_count": 48,
            },
        }
        projected = self.service()._governed_projection(
            snapshot,
            current_for_rule=True,
        )
        self.assertTrue(projected["reconciled"])
        self.assertTrue(projected["counts_final"])
        self.assertTrue(projected["recommendation_not_decision"])
        self.assertFalse(projected["can_auto_approve"])
        self.assertFalse(projected["erp_write_performed"])

    def test_held_status_survives_legacy_result_recalculation(self):
        transaction = {
            "status": "held",
            "check_amount": 100.0,
            "allocations": [
                {"invoice_number": "", "net_invoice_amount": 25.0}
            ],
        }

        _recalculate_transaction(transaction)

        self.assertEqual(transaction["status"], "held")
        self.assertEqual(transaction["allocation_total"], 25.0)
        self.assertEqual(transaction["difference"], 75.0)

    def test_held_status_is_a_preexisting_human_disposition(self):
        request = DurableLockboxPreparationService.request_from_source(
            source_job_id="job-held",
            source_file_hash="hash-held",
            source={
                "source_file_name": "held.pdf",
                "transaction_date": "2026-08-12",
                "transactions": [
                    {
                        "transaction_id": "T-HELD",
                        "status": "held",
                        "check_amount": 100.0,
                        "reviewer": "reviewer-test",
                        "notes": "Waiting for evidence.",
                        "allocations": [
                            {
                                "invoice_number": "",
                                "net_invoice_amount": 25.0,
                            }
                        ],
                    }
                ],
            },
        )

        disposition = request.transactions[0].preexisting_human_disposition
        self.assertIsNotNone(disposition)
        self.assertEqual(disposition["status"], "held")
        self.assertEqual(disposition["reviewer"], "reviewer-test")
        self.assertEqual(disposition["allocations"][0]["invoice_number"], "")

    def test_mismatched_reason_total_withholds_final_counts(self):
        snapshot = {
            "complete": True,
            "counts_final": True,
            "expected_count": 78,
            "terminal_count": 78,
            "balanced_count": 30,
            "exception_count": 48,
            "preserved_count": 0,
            "exception_reason_summary": {
                "total_exception_count": 47,
            },
        }
        projected = self.service()._governed_projection(
            snapshot,
            current_for_rule=True,
        )
        self.assertFalse(projected["reconciled"])
        self.assertFalse(projected["counts_final"])

    def test_current_projection_lookup_creates_no_generation(self):
        self.assertIn("increment4a", RULE_VERSION)
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "preparation.db"
            engine = create_engine(f"sqlite:///{database_path}")
            repository = LockboxPreparationRepository(engine=engine)
            registered = repository.register(
                StartPreparationRequest(
                    source_job_id="source-test",
                    source_file_hash="hash-test",
                    transactions=(),
                )
            )
            before = (
                registered["job_id"],
                registered["preparation_generation"],
                registered["updated_at"],
                len(repository.list_events(registered["job_id"])),
            )
            first = repository.get_current_job("source-test", "hash-test")
            second = repository.get_current_job("source-test", "hash-test")
            after = (
                second["job_id"],
                second["preparation_generation"],
                second["updated_at"],
                len(repository.list_events(second["job_id"])),
            )
            self.assertEqual(first["job_id"], registered["job_id"])
            self.assertEqual(after, before)
            with closing(sqlite3.connect(database_path)) as connection:
                count = connection.execute(
                    "SELECT COUNT(*) FROM lockbox_preparation_jobs"
                ).fetchone()[0]
            self.assertEqual(count, 1)
            engine.dispose()

    def test_new_source_can_register_before_any_historical_control(self):
        class SourceLoader:
            @staticmethod
            def identity(source_job_id):
                return {
                    "source_job_id": source_job_id,
                    "source_file_hash": "f" * 64,
                }

            @staticmethod
            def __call__(source_job_id):
                return {
                    "source_job_id": source_job_id,
                    "source_file_hash": "f" * 64,
                    "source_file_name": "synthetic-new-source.pdf",
                    "extraction_version": "synthetic-extraction",
                    "transactions": [
                        {
                            "transaction_id": "SYNTHETIC-1",
                            "check_amount": "25.00",
                            "allocations": [],
                        }
                    ],
                }

        class Repository:
            rule_version = RULE_VERSION
            service_version = SERVICE_VERSION

            @staticmethod
            def get_job_for_rule(*_args, **_kwargs):
                raise AssertionError(
                    "A new source must register before control lookup."
                )

        class Coordinator:
            repository = Repository()

            @staticmethod
            def start(_request, *, background=True):
                return {
                    "job_id": "fresh-job",
                    "source_job_id": "fresh-source",
                    "source_file_hash": "f" * 64,
                    "state": "running",
                    "complete": False,
                    "counts_final": False,
                    "expected_count": 1,
                    "terminal_count": 0,
                    "balanced_count": 0,
                    "exception_count": 0,
                    "preserved_count": 0,
                    "rule_version": RULE_VERSION,
                    "service_version": SERVICE_VERSION,
                    "exception_reason_summary": {
                        "total_exception_count": 0,
                    },
                    "transactions": [],
                }

        service = DurableLockboxPreparationService(
            Coordinator(),
            SourceLoader(),
            control_projection_required=True,
        )

        started = service.start_source_job(
            "fresh-source",
            "f" * 64,
            background=True,
        )

        self.assertEqual(started["state"], "running")
        self.assertEqual(started["expected_count"], 1)
        self.assertFalse(started["complete"])

    def test_complete_new_source_uses_fresh_projection_not_78_item_control(
        self,
    ):
        class Repository:
            rule_version = RULE_VERSION
            service_version = SERVICE_VERSION

            @staticmethod
            def get_job_for_rule(*_args, **_kwargs):
                raise KeyError("No exact historical control for this source.")

        service = DurableLockboxPreparationService(
            SimpleNamespace(repository=Repository()),
            control_projection_required=True,
        )
        snapshot = {
            "job_id": "fresh-job",
            "source_job_id": "fresh-source",
            "source_file_hash": "f" * 64,
            "state": "complete",
            "complete": True,
            "counts_final": True,
            "expected_count": 1,
            "terminal_count": 1,
            "balanced_count": 1,
            "exception_count": 0,
            "preserved_count": 0,
            "rule_version": RULE_VERSION,
            "service_version": SERVICE_VERSION,
            "exception_reason_summary": {"total_exception_count": 0},
            "transactions": [
                {
                    "job_id": "fresh-job",
                    "transaction_id": "SYNTHETIC-1",
                    "ordinal": 1,
                    "state": "prepared_balanced",
                    "source": {
                        "original_source": {
                            "transaction_id": "SYNTHETIC-1",
                        },
                        "projection_evidence": {
                            "removed_allocation_count": 0,
                            "allocation_conflict_count": 0,
                            "customer_conflict_count": 0,
                            "boundary_rule": "next_transaction_information",
                            "boundary_closed": True,
                            "remittance_evidence_complete": True,
                            "review_edits_used_as_extraction": False,
                        },
                    },
                    "result": {
                        "customer_resolution": {
                            "status": "resolved",
                            "customer_number": "SYNTHETIC-CUSTOMER",
                            "selection_basis": (
                                "unique_current_open_invoice_owner"
                            ),
                            "selected_confidence": 1.0,
                            "matching_evidence": {
                                "valid_invoice_count": 1,
                                "selected_basis": (
                                    "current_open_invoice_owner"
                                ),
                                "current_open_status": "resolved",
                                "failed_selection_gates": [],
                                "invoice_owner_conflict": False,
                                "partial_invoice_owner_evidence": False,
                                "payer_account_directive_conflict": False,
                            },
                        },
                        "customer_conflict_assessment": {
                            "status": "resolved",
                            "customer_number": "SYNTHETIC-CUSTOMER",
                            "candidate_customer_numbers": [
                                "SYNTHETIC-CUSTOMER"
                            ],
                            "remittance_invoice_numbers": ["12345678"],
                            "broad_invoice_owners": {"12345678": []},
                            "current_open_invoice_owners": {
                                "12345678": ["SYNTHETIC-CUSTOMER"],
                            },
                            "missing_current_open_invoices": [],
                            "unavailable_customer_numbers": [],
                            "current_open_ar_sources": {},
                            "current_open_invoice_sources": {
                                "12345678": {
                                    "source_reference": (
                                        "ERP TMAROP current open invoice "
                                        "ownership"
                                    ),
                                    "as_of_time": (
                                        "2026-08-05T01:00:00+00:00"
                                    ),
                                }
                            },
                            "rule_version": (
                                "lockbox-current-open-ar-customer-"
                                "resolution@1.1.0"
                            ),
                            "requires_human_review": True,
                            "can_auto_approve": False,
                            "erp_write_performed": False,
                        },
                        "recommendation": {
                            "status": "recommended",
                            "method": "exact_remittance_invoices",
                            "difference": "0.00",
                            "allocations": [
                                {
                                    "business_type": "Debit",
                                    "apply_amount": "25.00",
                                }
                            ],
                            "can_auto_approve": False,
                        },
                        "can_auto_approve": False,
                        "erp_write_performed": False,
                    },
                    "error": {},
                }
            ],
        }

        projected = service._governed_projection(
            snapshot,
            current_for_rule=True,
        )

        self.assertEqual(projected["projection_mode"], "fresh_source_initial")
        self.assertEqual(projected["expected_count"], 1)
        self.assertEqual(projected["balanced_count"], 1)
        self.assertEqual(projected["exception_count"], 0)
        self.assertTrue(projected["reconciled"])
        self.assertFalse(projected["can_auto_approve"])
        self.assertFalse(projected["erp_write_performed"])


class ReviewContractTest(unittest.TestCase):
    def test_resolved_customer_projects_even_when_allocation_needs_review(self):
        review = {
            "transactions": [
                {
                    "transaction_id": "G-SYNTH-9002",
                    "status": "review_required",
                    "allocations": [],
                    "check_amount": 250.00,
                }
            ],
            "total_check_amount": 250.00,
        }
        preparation = {
            "complete": True,
            "counts_final": True,
            "reconciled": True,
            "current_for_rule": True,
            "recommendation_not_decision": True,
            "can_auto_approve": False,
            "erp_write_performed": False,
            "transactions": [
                {
                    "transaction_id": "G-SYNTH-9002",
                    "state": "prepared_exception",
                    "result": {
                        "customer_snapshot": {
                            "fields": {
                                "customer_number": "400001",
                                "customer_name": "EXAMPLE AUTOMOTIVE, INC.",
                                "phone": "(312) 555-0184",
                                "address_line_1": "1200 EXAMPLE ROAD",
                                "city": "SAMPLEVILLE",
                                "state": "IL",
                                "postal_code": "60601",
                            }
                        }
                    },
                }
            ],
        }

        projected = review_service._project_governed_preparation(
            review,
            preparation,
        )

        transaction = projected["transactions"][0]
        self.assertEqual(transaction["status"], "review_required")
        self.assertEqual(transaction["customer_number"], "400001")
        self.assertEqual(
            transaction["customer_name"],
            "EXAMPLE AUTOMOTIVE, INC.",
        )
        self.assertEqual(transaction["customer_postal_code"], "60601")

    def test_review_request_accepts_all_ui_statuses_and_customer_identity(self):
        for status in (
            "balanced",
            "review_required",
            "no_remittance",
            "corrected",
            "held",
            "approved",
        ):
            request = SaveTransactionReviewRequest(
                allocations=[],
                status=status,
                customer_number="customer-test",
                customer_name="Example Customer",
            )
            self.assertEqual(request.status, status)
            self.assertEqual(request.customer_number, "customer-test")

    def test_customer_note_request_and_service_preserve_origin_evidence(self):
        request = AppendCustomerNoteRequest(
            body="Requested remittance detail.",
            author="Reviewer One",
        )
        review = {
            "transactions": [
                {
                    "transaction_id": "G-100",
                    "customer_number": "400001",
                    "customer_name": "Example Customer",
                    "check_number": "00123",
                }
            ]
        }
        stored = [{"note_id": 1, "body": request.body}]

        with (
            patch.object(
                review_service,
                "get_lockbox_review",
                return_value=review,
            ),
            patch.object(
                review_service,
                "append_customer_note_record",
            ) as append_record,
            patch.object(
                review_service,
                "get_customer_note_records",
                return_value=stored,
            ),
        ):
            result = review_service.append_transaction_customer_note(
                "job-1",
                "G-100",
                request.model_dump(),
            )

        append_record.assert_called_once_with(
            "400001",
            customer_name="Example Customer",
            body="Requested remittance detail.",
            author="Reviewer One",
            source_job_id="job-1",
            source_transaction_id="G-100",
            source_check_number="00123",
        )
        self.assertEqual(result["customer_number"], "400001")
        self.assertEqual(result["notes"], stored)

    def test_customer_note_service_requires_saved_customer_identity(self):
        review = {
            "transactions": [
                {
                    "transaction_id": "G-100",
                    "customer_number": "",
                    "customer_name": "Unknown",
                    "check_number": "00123",
                }
            ]
        }
        with patch.object(
            review_service,
            "get_lockbox_review",
            return_value=review,
        ):
            with self.assertRaises(Exception) as context:
                review_service.get_transaction_customer_notes(
                    "job-1",
                    "G-100",
                )

        self.assertEqual(getattr(context.exception, "status_code", None), 409)

    def test_held_partial_draft_persists_and_survives_governed_projection(self):
        source = {
            "job_id": "job-held",
            "parser_version": "parser-test",
            "extraction_version": "extract-test",
            "source_file_name": "held-source.pdf",
            "lockbox": "test-lockbox",
            "transaction_date": "2026-08-12",
            "transactions": [
                {
                    "transaction_id": "T-HELD",
                    "check_amount": 100.00,
                    "date": "2026-08-12",
                    "status": "review_required",
                    "customer_number": "customer-test",
                    "customer_name": "Example Customer",
                    "allocations": [
                        {
                            "invoice_number": "12345678",
                            "net_invoice_amount": 100.00,
                        }
                    ],
                    "rejected_remittance_candidates": [
                        {"reason": "preserved-source-evidence"}
                    ],
                }
            ],
            "warnings": [],
        }
        preparation = {
            "complete": True,
            "counts_final": True,
            "reconciled": True,
            "current_for_rule": True,
            "recommendation_not_decision": True,
            "can_auto_approve": False,
            "erp_write_performed": False,
            "transactions": [
                {
                    "transaction_id": "T-HELD",
                    "state": "prepared_balanced",
                    "result": {
                        "exception_analysis": {
                            "primary_reason": {
                                "code": "synthetic_reason",
                                "label": "Synthetic reason",
                            }
                        },
                        "recommendation": {
                            "allocations": [
                                {
                                    "invoice_number": "87654321",
                                    "apply_amount": "100.00",
                                }
                            ]
                        },
                    },
                }
            ],
        }
        preparation_before = deepcopy(preparation)

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "lockbox-review.db"
            engine = create_engine(f"sqlite:///{database_path}")
            _set_engine_override(engine)

            def unexpected_current_open_ar(*_args, **_kwargs):
                raise AssertionError(
                    "Holding a partial draft must not query current ERP A/R."
                )

            with (
                patch.object(
                    review_service,
                    "get_lockbox_result",
                    lambda _job_id: deepcopy(source),
                ),
                patch.object(
                    review_service,
                    "_governed_preparation_loader",
                    lambda _job_id: preparation,
                ),
                patch.object(
                    review_service,
                    "_current_open_ar_loader",
                    unexpected_current_open_ar,
                ),
            ):
                payload = SaveTransactionReviewRequest(
                    allocations=[
                        {
                            "invoice_number": "",
                            "net_invoice_amount": 12.34,
                            "raw_invoice_candidates": ["unresolved OCR"],
                        }
                    ],
                    status="held",
                    reviewer="reviewer-test",
                    notes="Needs customer research.",
                    customer_number="customer-test",
                    customer_name="Example Customer",
                ).model_dump()

                saved = review_service.save_transaction_review(
                    "job-held",
                    "T-HELD",
                    payload,
                )
                reopened = review_service.get_lockbox_review("job-held")

            for result in (saved, reopened):
                transaction = result["transactions"][0]
                self.assertEqual(transaction["status"], "held")
                self.assertEqual(transaction["allocations"][0]["invoice_number"], "")
                self.assertEqual(
                    transaction["allocations"][0]["raw_invoice_candidates"],
                    ["unresolved OCR"],
                )
                self.assertEqual(transaction["notes"], "Needs customer research.")
                self.assertEqual(result["held_count"], 1)
                self.assertEqual(result["review_count"], 0)
                self.assertEqual(result["approved_count"], 0)
                self.assertEqual(result["balanced_count"], 0)
                self.assertEqual(
                    transaction["rejected_remittance_candidates"],
                    [{"reason": "preserved-source-evidence"}],
                )

            self.assertEqual(preparation, preparation_before)
            with closing(sqlite3.connect(database_path)) as connection:
                stored_status = connection.execute(
                    "SELECT status FROM lockbox_transaction_reviews "
                    "WHERE job_id = ? AND transaction_id = ?",
                    ("job-held", "T-HELD"),
                ).fetchone()[0]
            self.assertEqual(stored_status, "held")
            _reset_engine_override()
            engine.dispose()

    def test_non_held_save_still_rejects_incomplete_invoice_identifier(self):
        review = {
            "transactions": [
                {
                    "transaction_id": "T-INCOMPLETE",
                    "check_amount": 25.00,
                    "customer_number": "customer-test",
                    "original_allocations": [],
                }
            ]
        }
        with patch.object(
            review_service,
            "get_lockbox_review",
            return_value=review,
        ):
            with self.assertRaises(Exception) as context:
                review_service.save_transaction_review(
                    "job-test",
                    "T-INCOMPLETE",
                    {
                        "allocations": [
                            {
                                "invoice_number": "",
                                "net_invoice_amount": 25.00,
                            }
                        ],
                        "status": "corrected",
                    },
                )

        self.assertEqual(getattr(context.exception, "status_code", None), 400)
        self.assertIn("invoice number", str(context.exception))

    def test_api_models_retain_governed_extraction_and_customer_fields(self):
        transaction = {
            "transaction_id": "T001",
            "customer_name": "Example",
            "customer_number": "customer-test",
            "remittance_pages_examined": [2],
            "rejected_remittance_candidates": [{"reason": "synthetic"}],
        }
        processing = LockboxProcessingResponse(
            job_id="job-test",
            parser_version="parser-test",
            extraction_version="extract-test",
            source_file_name="sample.pdf",
            lockbox="",
            transaction_date="",
            transaction_count=1,
            allocation_count=0,
            total_check_amount=0,
            total_allocation_amount=0,
            total_difference=0,
            balanced_count=0,
            review_count=1,
            transactions=[transaction],
            warnings=[],
        )
        payload = processing.model_dump()
        self.assertEqual(payload["extraction_version"], "extract-test")
        self.assertEqual(
            payload["transactions"][0]["remittance_pages_examined"],
            [2],
        )

        reviewed = LockboxReviewResponse(
            **{
                **payload,
                "approved_count": 0,
                "corrected_count": 0,
                "transactions": [
                    {
                        **payload["transactions"][0],
                        "original_allocations": [],
                        "allocations": [],
                        "allocation_total": 0,
                        "difference": 0,
                        "balanced": False,
                        "status": "review_required",
                        "reviewer": "",
                        "notes": "",
                        "override_reason": "",
                        "reviewed_at": None,
                    }
                ],
            }
        )
        self.assertEqual(
            reviewed.transactions[0].customer_number,
            "customer-test",
        )

    def test_governed_sc_provenance_survives_review_normalization(self):
        normalized = review_service._normalize_allocation(
            {
                "invoice_number": "8",
                "net_invoice_amount": 14.18,
                "invoice_page": "35;1",
                "confidence": 1,
                "raw_invoice_candidates": ["8"],
                "extraction_source": "erp_open_ar",
                "allocation_kind": "service_charge",
                "erp_transaction_type": "SC",
                "open_item_key": "680753|SC|8|8",
                "invoice_count": 8,
            }
        )

        self.assertEqual(normalized["invoice_number"], "8")
        self.assertEqual(normalized["allocation_kind"], "service_charge")
        self.assertEqual(normalized["erp_transaction_type"], "SC")
        self.assertEqual(normalized["open_item_key"], "680753|SC|8|8")
        self.assertEqual(normalized["invoice_count"], 8)

    def test_only_exact_governed_sc_row_may_use_short_identifier(self):
        preparation = {
            "transactions": [
                {
                    "transaction_id": "T-SC",
                    "result": {
                        "recommendation": {
                            "allocations": [
                                {
                                    "invoice_number": "8",
                                    "allocation_kind": "service_charge",
                                    "raw_transaction_type": "SC",
                                    "open_item_key": "680753|SC|8|8",
                                }
                            ]
                        }
                    },
                }
            ]
        }
        allowed = review_service._normalize_allocation(
            {
                "invoice_number": "8",
                "net_invoice_amount": 14.18,
                "allocation_kind": "service_charge",
                "erp_transaction_type": "SC",
                "open_item_key": "680753|SC|8|8",
            }
        )
        forged = {
            **allowed,
            "invoice_number": "9",
        }

        with patch.object(
            review_service,
            "_governed_preparation_loader",
            lambda _job_id: preparation,
        ):
            review_service._validate_allocation_identifiers(
                "job-test",
                "T-SC",
                [allowed],
            )
            with self.assertRaises(Exception) as context:
                review_service._validate_allocation_identifiers(
                    "job-test",
                    "T-SC",
                    [forged],
                )

        self.assertEqual(getattr(context.exception, "status_code", None), 400)

    def test_multiple_distinct_prepared_sc_rows_may_be_reviewed_together(self):
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
                                    "open_item_key": "customer-test|SC|7|7",
                                },
                                {
                                    "customer_number": "customer-test",
                                    "invoice_number": "8",
                                    "open_amount": "14.18",
                                    "raw_transaction_type": "SC",
                                    "invoice_count": 8,
                                    "open_item_key": "customer-test|SC|8|8",
                                },
                            ]
                        },
                        "recommendation": {"allocations": []},
                    },
                }
            ]
        }
        allocations = [
            review_service._normalize_allocation(
                {
                    "invoice_number": invoice_number,
                    "net_invoice_amount": amount,
                    "allocation_kind": "service_charge",
                    "erp_transaction_type": "SC",
                    "open_item_key": open_item_key,
                }
            )
            for invoice_number, amount, open_item_key in (
                ("7", 11.25, "customer-test|SC|7|7"),
                ("8", 14.18, "customer-test|SC|8|8"),
            )
        ]

        with patch.object(
            review_service,
            "_governed_preparation_loader",
            lambda _job_id: preparation,
        ):
            review_service._validate_allocation_identifiers(
                "job-test",
                "T-MULTI-SC",
                allocations,
            )

    def test_manual_customer_sc_rows_use_fresh_current_open_ar(self):
        preparation = {
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
        current_open_ar = {
            "customer_number": "customer-test",
            "invoices": [
                {
                    "customer_number": "customer-test",
                    "invoice_number": "7",
                    "raw_transaction_type": "SC",
                    "invoice_count": 7,
                    "open_item_key": "customer-test|SC|7|7",
                },
                {
                    "customer_number": "customer-test",
                    "invoice_number": "8",
                    "raw_transaction_type": "SC",
                    "invoice_count": 8,
                    "open_item_key": "customer-test|SC|8|8",
                },
            ],
        }
        allocations = [
            review_service._normalize_allocation(
                {
                    "invoice_number": invoice_number,
                    "net_invoice_amount": amount,
                    "allocation_kind": "service_charge",
                    "erp_transaction_type": "SC",
                    "open_item_key": open_item_key,
                }
            )
            for invoice_number, amount, open_item_key in (
                ("7", 11.25, "customer-test|SC|7|7"),
                ("8", 14.18, "customer-test|SC|8|8"),
            )
        ]

        with (
            patch.object(
                review_service,
                "_governed_preparation_loader",
                lambda _job_id: preparation,
            ),
            patch.object(
                review_service,
                "_current_open_ar_loader",
                lambda customer_number, _as_of: current_open_ar
                if customer_number == "customer-test"
                else {},
            ),
        ):
            review_service._validate_allocation_identifiers(
                "job-test",
                "T-CURRENT-SC",
                allocations,
                customer_number="customer-test",
            )

    def test_closed_sc_row_is_blocked_by_fresh_current_open_ar(self):
        allocation = review_service._normalize_allocation(
            {
                "invoice_number": "8",
                "net_invoice_amount": 14.18,
                "allocation_kind": "service_charge",
                "erp_transaction_type": "SC",
                "open_item_key": "customer-test|SC|8|8",
            }
        )
        with patch.object(
            review_service,
            "_current_open_ar_loader",
            lambda _customer_number, _as_of: {
                "customer_number": "customer-test",
                "invoices": [],
            },
        ):
            with self.assertRaises(Exception) as context:
                review_service._validate_allocation_identifiers(
                    "job-test",
                    "T-CLOSED-SC",
                    [allocation],
                    customer_number="customer-test",
                )

        self.assertEqual(getattr(context.exception, "status_code", None), 400)
        self.assertIn("closed, missing", str(context.exception))

    def test_current_open_ar_customer_must_match_review_customer(self):
        allocation = review_service._normalize_allocation(
            {
                "invoice_number": "8",
                "net_invoice_amount": 14.18,
                "allocation_kind": "service_charge",
                "erp_transaction_type": "SC",
                "open_item_key": "customer-test|SC|8|8",
            }
        )
        with patch.object(
            review_service,
            "_current_open_ar_loader",
            lambda _customer_number, _as_of: {
                "customer_number": "other-customer",
                "invoices": [],
            },
        ):
            with self.assertRaises(Exception) as context:
                review_service._validate_allocation_identifiers(
                    "job-test",
                    "T-WRONG-CUSTOMER-SC",
                    [allocation],
                    customer_number="customer-test",
                )

        self.assertEqual(getattr(context.exception, "status_code", None), 409)

    def test_current_open_ar_failure_blocks_sc_save(self):
        allocation = review_service._normalize_allocation(
            {
                "invoice_number": "8",
                "net_invoice_amount": 14.18,
                "allocation_kind": "service_charge",
                "erp_transaction_type": "SC",
                "open_item_key": "customer-test|SC|8|8",
            }
        )

        def unavailable(_customer_number, _as_of):
            raise RuntimeError("synthetic ERP outage")

        with patch.object(
            review_service,
            "_current_open_ar_loader",
            unavailable,
        ):
            with self.assertRaises(Exception) as context:
                review_service._validate_allocation_identifiers(
                    "job-test",
                    "T-ERP-FAILURE-SC",
                    [allocation],
                    customer_number="customer-test",
                )

        self.assertEqual(getattr(context.exception, "status_code", None), 503)

    def test_same_prepared_sc_open_item_cannot_be_used_twice(self):
        preparation = {
            "transactions": [
                {
                    "transaction_id": "T-DUPLICATE-SC",
                    "result": {
                        "open_ar": {
                            "invoices": [
                                {
                                    "customer_number": "customer-test",
                                    "invoice_number": "8",
                                    "open_amount": "14.18",
                                    "raw_transaction_type": "SC",
                                    "invoice_count": 8,
                                    "open_item_key": "customer-test|SC|8|8",
                                }
                            ]
                        },
                        "recommendation": {"allocations": []},
                    },
                }
            ]
        }
        allocation = review_service._normalize_allocation(
            {
                "invoice_number": "8",
                "net_invoice_amount": 14.18,
                "allocation_kind": "service_charge",
                "erp_transaction_type": "SC",
                "open_item_key": "customer-test|SC|8|8",
            }
        )

        with patch.object(
            review_service,
            "_governed_preparation_loader",
            lambda _job_id: preparation,
        ):
            with self.assertRaises(Exception) as context:
                review_service._validate_allocation_identifiers(
                    "job-test",
                    "T-DUPLICATE-SC",
                    [allocation, allocation],
                )

        self.assertEqual(getattr(context.exception, "status_code", None), 400)
        self.assertIn("same open item", str(context.exception))

    def test_sc_row_missing_from_prepared_open_ar_remains_blocked(self):
        preparation = {
            "transactions": [
                {
                    "transaction_id": "T-MISSING-SC",
                    "result": {
                        "open_ar": {"invoices": []},
                        "recommendation": {"allocations": []},
                    },
                }
            ]
        }
        allocation = review_service._normalize_allocation(
            {
                "invoice_number": "9",
                "net_invoice_amount": 12.00,
                "allocation_kind": "service_charge",
                "erp_transaction_type": "SC",
                "open_item_key": "customer-test|SC|9|9",
            }
        )

        with patch.object(
            review_service,
            "_governed_preparation_loader",
            lambda _job_id: preparation,
        ):
            with self.assertRaises(Exception) as context:
                review_service._validate_allocation_identifiers(
                    "job-test",
                    "T-MISSING-SC",
                    [allocation],
                )

        self.assertEqual(getattr(context.exception, "status_code", None), 400)

    def test_legacy_review_migration_is_idempotent_and_preserves_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "review.db"
            engine = create_engine(f"sqlite:///{target}")
            _set_engine_override(engine)
            try:
                with engine.begin() as connection:
                    shared_metadata.create_all(
                        engine, checkfirst=True, tables=[lockbox_reviews_table]
                    )
                    connection.execute(
                        lockbox_reviews_table.insert().values(
                            job_id="job-test",
                            transaction_id="T001",
                            review_json=json.dumps(
                                {
                                    "allocations": [
                                        {
                                            "invoice_number": "12345678",
                                            "net_invoice_amount": 10,
                                            "invoice_page": "2;1",
                                            "confidence": 1,
                                        }
                                    ],
                                    "status": "corrected",
                                    "reviewer": "reviewer-test",
                                    "customer_number": "customer-test",
                                    "customer_name": "Example Customer",
                                }
                            ),
                            created_at="2026-08-01T00:00:00+00:00",
                            updated_at="2026-08-01T00:00:00+00:00",
                        )
                    )
                originals = {
                    "T001": [
                        {
                            "invoice_number": "87654321",
                            "net_invoice_amount": 10,
                            "invoice_page": "2;1",
                            "confidence": 1,
                        }
                    ]
                }
                self.assertEqual(
                    database.migrate_legacy_reviews("job-test", originals),
                    1,
                )
                self.assertEqual(
                    database.migrate_legacy_reviews("job-test", originals),
                    0,
                )
                saved = database.get_reviews("job-test")["T001"]
                self.assertEqual(
                    saved["customer"]["customer_number"],
                    "customer-test",
                )
                self.assertEqual(
                    saved["original_allocations"][0]["invoice_number"],
                    "87654321",
                )
            finally:
                _reset_engine_override()
                engine.dispose()

    def test_reviewed_export_refuses_unresolved_governed_exceptions(self):
        class GovernedHTTPException(Exception):
            def __init__(self, status_code: int, detail: str):
                super().__init__(detail)
                self.status_code = status_code

        final = {
            "complete": True,
            "counts_final": True,
            "reconciled": True,
            "current_for_rule": True,
        }
        review = {"review_count": 1}
        with (
            patch.object(
                review_service,
                "_governed_preparation_loader",
                lambda _job_id: final,
            ),
            patch.object(
                review_service,
                "get_lockbox_review",
                return_value=review,
            ),
            patch.object(
                review_service,
                "HTTPException",
                GovernedHTTPException,
            ),
        ):
            with self.assertRaises(Exception) as context:
                review_service.create_reviewed_export("job-test")
        self.assertEqual(getattr(context.exception, "status_code", None), 409)

    def test_reviewed_export_refuses_held_transaction(self):
        class GovernedHTTPException(Exception):
            def __init__(self, status_code: int, detail: str):
                super().__init__(detail)
                self.status_code = status_code

        final = {
            "complete": True,
            "counts_final": True,
            "reconciled": True,
            "current_for_rule": True,
        }
        review = {"review_count": 0, "held_count": 1}
        with (
            patch.object(
                review_service,
                "_governed_preparation_loader",
                lambda _job_id: final,
            ),
            patch.object(
                review_service,
                "get_lockbox_review",
                return_value=review,
            ),
            patch.object(
                review_service,
                "HTTPException",
                GovernedHTTPException,
            ),
        ):
            with self.assertRaises(Exception) as context:
                review_service.create_reviewed_export("job-test")

        self.assertEqual(getattr(context.exception, "status_code", None), 409)
        self.assertIn("held transaction", str(context.exception))


if __name__ == "__main__":
    unittest.main()
