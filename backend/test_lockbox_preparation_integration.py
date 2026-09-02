from __future__ import annotations

import sys
import tempfile
import time
import types
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _install_runtime_import_stubs() -> None:
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

            def _route(self, path):
                def decorator(function):
                    self.routes.append(
                        SimpleNamespace(
                            path=self.prefix + path,
                            endpoint=function,
                        )
                    )
                    return function

                return decorator

            def get(self, path, *args, **kwargs):
                return self._route(path)

            def post(self, path, *args, **kwargs):
                return self._route(path)

            def put(self, path, *args, **kwargs):
                return self._route(path)

            def include_router(self, router):
                self.routes.append(SimpleNamespace(router=router))

            def openapi(self):
                paths = {}

                def collect(candidate):
                    nested_router = getattr(candidate, "router", None)
                    if nested_router is not None:
                        for nested in getattr(nested_router, "routes", []):
                            collect(nested)
                        return

                    path = getattr(candidate, "path", "")
                    if path:
                        paths.setdefault(path, {})

                for route in self.routes:
                    collect(route)

                return {"paths": paths}

        class FastAPI(APIRouter):
            pass

        class UploadFile:
            pass

        def parameter(default=None, *args, **kwargs):
            return default

        fastapi.APIRouter = APIRouter
        fastapi.FastAPI = FastAPI
        fastapi.HTTPException = HTTPException
        fastapi.File = parameter
        fastapi.Query = parameter
        fastapi.UploadFile = UploadFile
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")

        class FileResponse:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        responses.FileResponse = FileResponse
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


_install_runtime_import_stubs()

from modules.document_intelligence.lockbox_preparation.active_provider import (
    ExistingReadOnlyPreparationProvider,
)
from modules.document_intelligence.lockbox_preparation.contracts import (
    InvoiceOwnerEvidence,
    OpenInvoice,
    SourceTransaction,
)
from modules.document_intelligence.lockbox_preparation.control_projection import (
    PROMOTION_METHODS,
)
from modules.document_intelligence.integrations.receivables_repository import (
    ReceivablesRepository,
)
from modules.document_intelligence.lockbox_preparation.coordinator import (
    DurableLockboxPreparationCoordinator,
)
from modules.document_intelligence.lockbox_preparation.repository import (
    LockboxPreparationRepository,
)
from modules.document_intelligence.lockbox_preparation.policy import (
    recommend_allocation,
)
from modules.document_intelligence.lockbox_preparation.service import (
    DurableLockboxPreparationService,
)
from modules.document_intelligence.lockbox_preparation.source_loader import (
    SavedLockboxSourceLoader,
    merge_extractions,
    sha256_file,
)
from modules.document_intelligence.pnc_lockbox_parser import EXTRACTION_VERSION

DURABLE_LOCKBOX_ROUTE_PATHS = frozenset(
    {
        (
            "/api/v1/documents/jobs/{source_job_id}"
            "/lockbox/preparation/start"
        ),
        "/api/v1/documents/lockbox/preparation/{job_id}/resume",
        "/api/v1/documents/lockbox/preparation/{job_id}",
        "/api/v1/documents/lockbox/preparation/{job_id}/history",
        (
            "/api/v1/documents/lockbox/preparation/{job_id}"
            "/exception-summary"
        ),
    }
)


class DueDateGroupCombinationPolicyTest(unittest.TestCase):
    @staticmethod
    def _invoice(
        number: int,
        amount: Decimal | str,
        due_date: date,
        *,
        credit: bool = False,
        customer_number: str = "350063",
    ) -> OpenInvoice:
        return OpenInvoice(
            customer_number=customer_number,
            invoice_number=str(number),
            open_amount=abs(Decimal(amount)),
            due_date=due_date,
            invoice_date=date(2026, 6, 22),
            raw_transaction_type="C" if credit else "D",
            signed_source_amount=(
                -abs(Decimal(amount)) if credit else abs(Decimal(amount))
            ),
            aging_bucket=(
                "PAST DUE 31-60"
                if due_date == date(2026, 7, 10)
                else "PAST DUE 1-30"
                if due_date == date(2026, 8, 10)
                else "CURRENT"
            ),
            source_reference="TMAROP",
            open_item_key=f"{customer_number}|{number}",
        )

    def test_overinclusive_remittance_uses_unique_exact_due_date_combination(
        self,
    ) -> None:
        number = 350000000

        july = [
            self._invoice(number + 1, "312.00", date(2026, 7, 10)),
            self._invoice(number + 2, "300.00", date(2026, 7, 10)),
        ]
        number += 2

        august = [
            self._invoice(number + index, "300.00", date(2026, 8, 10))
            for index in range(1, 15)
        ]
        number += 14
        august.extend(
            (
                self._invoice(number + 1, "632.00", date(2026, 8, 10)),
                self._invoice(
                    number + 2,
                    "348.00",
                    date(2026, 8, 10),
                    credit=True,
                ),
            )
        )
        number += 2

        september_candidate = [
            self._invoice(number + index, "300.00", date(2026, 9, 10))
            for index in range(1, 10)
        ]
        number += 9
        september_candidate.append(
            self._invoice(number + 1, "1593.76", date(2026, 9, 10))
        )
        number += 1

        september_remaining = [
            self._invoice(number + index, "250.00", date(2026, 9, 10))
            for index in range(1, 19)
        ]
        number += 18
        september_remaining.append(
            self._invoice(number + 1, "754.96", date(2026, 9, 10))
        )

        selected_due_date_items = [*july, *august]
        remittance_items = [
            *selected_due_date_items,
            *september_candidate,
        ]
        all_open_items = [
            *remittance_items,
            *september_remaining,
        ]
        remittance_rows = [
            {
                "invoice_number": invoice.invoice_number,
                "net_invoice_amount": (
                    -invoice.open_amount
                    if invoice.raw_transaction_type == "C"
                    else invoice.open_amount
                ),
            }
            for invoice in remittance_items
        ]

        recommendation = recommend_allocation(
            check_amount="5096.00",
            extracted_invoice_numbers=(
                invoice.invoice_number for invoice in remittance_items
            ),
            open_invoices=all_open_items,
            remittance_allocations=remittance_rows,
            remittance_evidence_complete=True,
        )

        self.assertEqual(recommendation.status, "recommended")
        self.assertEqual(
            recommendation.method,
            "unique_exact_due_date_group_combination",
        )
        self.assertEqual(len(recommendation.allocations), 18)
        self.assertEqual(recommendation.suggested_total, Decimal("5096.00"))
        self.assertEqual(recommendation.difference, Decimal("0.00"))
        self.assertEqual(
            {allocation.due_date for allocation in recommendation.allocations},
            {date(2026, 7, 10), date(2026, 8, 10)},
        )
        self.assertIn(
            "unique_exact_due_date_group_combination",
            PROMOTION_METHODS,
        )

    def test_overinclusive_remittance_uses_one_complete_matching_bucket(
        self,
    ) -> None:
        august = self._invoice(
            640095565,
            "2228.00",
            date(2026, 8, 10),
            customer_number="640516",
        )
        september_remit = self._invoice(
            640096189,
            "573.92",
            date(2026, 9, 10),
            customer_number="640516",
        )
        september_other = self._invoice(
            640097243,
            "426.00",
            date(2026, 9, 10),
            customer_number="640516",
        )

        recommendation = recommend_allocation(
            check_amount="2228.00",
            extracted_invoice_numbers=(
                august.invoice_number,
                september_remit.invoice_number,
            ),
            open_invoices=(august, september_remit, september_other),
            remittance_allocations=(
                {
                    "invoice_number": august.invoice_number,
                    "net_invoice_amount": august.open_amount,
                },
                {
                    "invoice_number": september_remit.invoice_number,
                    "net_invoice_amount": september_remit.open_amount,
                },
            ),
            remittance_evidence_complete=True,
        )

        self.assertEqual(recommendation.status, "recommended")
        self.assertEqual(
            recommendation.method,
            "unique_exact_due_date_group_combination",
        )
        self.assertEqual(len(recommendation.allocations), 1)
        self.assertEqual(
            recommendation.allocations[0].invoice_number,
            "640095565",
        )
        self.assertEqual(recommendation.suggested_total, Decimal("2228.00"))
        self.assertEqual(recommendation.difference, Decimal("0.00"))
        self.assertEqual(
            {allocation.due_date for allocation in recommendation.allocations},
            {date(2026, 8, 10)},
        )

    def test_ambiguous_due_date_group_combinations_remain_review(self) -> None:
        open_items = [
            self._invoice(350000101, "100.00", date(2026, 7, 10)),
            self._invoice(350000102, "100.00", date(2026, 8, 10)),
            self._invoice(350000103, "200.00", date(2026, 9, 10)),
        ]

        recommendation = recommend_allocation(
            check_amount="200.00",
            extracted_invoice_numbers=(
                invoice.invoice_number for invoice in open_items
            ),
            open_invoices=open_items,
            remittance_allocations=(
                {
                    "invoice_number": invoice.invoice_number,
                    "net_invoice_amount": invoice.open_amount,
                }
                for invoice in open_items
            ),
            remittance_evidence_complete=True,
        )

        self.assertEqual(recommendation.status, "review_required")
        self.assertEqual(recommendation.method, "partial_exact_remittance")
        self.assertNotEqual(recommendation.difference, Decimal("0.00"))


class FakeReceivablesRepository:
    def __init__(self, invoices=None):
        self.invoices = list(invoices or [])
        self.calls = []

    def get_open_invoices(self, customer_number, aging_as_of_date):
        self.calls.append((customer_number, aging_as_of_date))
        return list(self.invoices)

    def get_current_invoice_owners(self, invoice_numbers):
        requested = set(invoice_numbers)
        owners = {invoice: set() for invoice in invoice_numbers}
        for invoice in self.invoices:
            invoice_number = str(
                getattr(invoice, "invoice_number", "") or ""
            )
            customer_number = str(
                getattr(invoice, "customer_number", "") or ""
            )
            if invoice_number in requested and customer_number:
                owners[invoice_number].add(customer_number)
        return owners


def customer_record(
    number: str = "520459",
    enterprise_number: str = "",
) -> dict:
    return {
        "customer_number": number,
        "customer_name": "Example Tire",
        "phone": "4195551212",
        "address_line_1": "100 Main Street",
        "address_line_2": "",
        "city": "Minster",
        "state": "OH",
        "postal_code": "45865",
        "enterprise_number": enterprise_number,
    }


class ActiveProviderIntegrationTest(unittest.TestCase):
    def provider(
        self,
        *,
        owners,
        records,
        invoices=None,
        address_complete=True,
        confirmed_mappings=None,
    ):
        confirmed_mappings = confirmed_mappings or {}
        return ExistingReadOnlyPreparationProvider(
            FakeReceivablesRepository(invoices),
            payer_mapping_lookup=(
                lambda routing, last4: confirmed_mappings.get(
                    (routing, last4), []
                )
            ),
            invoice_owner_loader=lambda values: (owners, []),
            customer_columns_loader=lambda: {
                "customer_number": "CUNUMBER",
                "customer_name": "CUNAME",
                "phone": "CUPHONE",
                "address_line_1": "CUADDRESS",
                "address_line_2": "CUADDRESS2",
                "city": "CUCITY",
                "state": "CUSTATE",
                "postal_code": "CUZIP",
                "enterprise_number": "CUNUMENT",
            },
            customer_record_loader=lambda columns, request, numbers: [
                row
                for row in records
                if not numbers or row["customer_number"] in numbers
            ],
            customer_group_record_loader=(
                lambda columns, customer_number, enterprise_number: [
                    row
                    for row in records
                    if row["customer_number"] in {
                        customer_number,
                        enterprise_number,
                    }
                    or row.get("enterprise_number") == enterprise_number
                ]
            ),
            exact_phone_loader=(
                lambda columns, phone: (list(records), True)
            ),
            exact_address_loader=(
                lambda columns, address, postal: (
                    list(records),
                    address_complete,
                )
            ),
        )

    def test_all_invoice_evidence_resolves_one_customer(self):
        provider = self.provider(
            owners={
                "431063896": {"520459"},
                "431063897": {"520459"},
            },
            records=[customer_record()],
        )
        evidence = provider.resolve_invoice_owners(
            ["431063896", "431063897"]
        )
        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-1",
                ordinal=1,
                check_amount=Decimal("100.00"),
                extracted_invoice_numbers=(
                    "431063896",
                    "431063897",
                ),
            ),
            evidence,
        )
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.customer_number, "520459")
        self.assertEqual(
            resolution.customer_snapshot["customer_name"],
            "Example Tire",
        )

    def test_verified_payer_supplied_customer_number_resolves(self):
        provider = self.provider(
            owners={},
            records=[customer_record("700001")],
        )

        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-ACCOUNT-1",
                ordinal=1,
                check_amount=Decimal("125.00"),
                original_source={
                    "printed_customer_number": "700001",
                    "printed_customer_number_evidence": (
                        "Apply payment to account 700001"
                    ),
                },
            ),
            {},
        )

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.customer_number, "700001")
        self.assertEqual(
            resolution.confidence_basis,
            "payer_supplied_customer_number",
        )
        self.assertEqual(resolution.selected_confidence, 1.0)
        self.assertTrue(
            resolution.matching_evidence[
                "payer_account_directive_verified"
            ]
        )

    def test_invoice_owner_remains_ahead_of_conflicting_payer_account(self):
        provider = self.provider(
            owners={"431700001": {"700002"}},
            records=[customer_record("700001"), customer_record("700002")],
        )
        evidence = provider.resolve_invoice_owners(["431700001"])

        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-ACCOUNT-2",
                ordinal=1,
                check_amount=Decimal("125.00"),
                extracted_invoice_numbers=("431700001",),
                original_source={"printed_customer_number": "700001"},
            ),
            evidence,
        )

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.customer_number, "700002")
        self.assertEqual(
            resolution.confidence_basis,
            "unique_remittance_invoice_owner",
        )

    def test_verified_km_statement_customer_number_resolves_after_check_fallback(
        self,
    ):
        provider = self.provider(
            owners={},
            records=[customer_record("640516")],
        )

        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-STATEMENT-1",
                ordinal=1,
                check_amount=Decimal("125.00"),
                original_source={
                    "statement_customer_number": "640516",
                    "statement_customer_number_evidence": (
                        "JV AUTO TECH - 640516"
                    ),
                },
            ),
            {},
        )

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.customer_number, "640516")
        self.assertEqual(
            resolution.confidence_basis,
            "km_statement_customer_number",
        )
        self.assertTrue(
            resolution.matching_evidence[
                "km_statement_customer_verified"
            ]
        )

    def test_check_customer_number_remains_ahead_of_statement_number(self):
        provider = self.provider(
            owners={},
            records=[customer_record("650426"), customer_record("640516")],
        )

        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-STATEMENT-2",
                ordinal=1,
                check_amount=Decimal("125.00"),
                original_source={
                    "printed_customer_number": "650426",
                    "statement_customer_number": "640516",
                },
            ),
            {},
        )

        self.assertEqual(resolution.customer_number, "650426")
        self.assertEqual(
            resolution.confidence_basis,
            "payer_supplied_customer_number",
        )

    def test_verified_check_for_customer_number_resolves_last(self):
        provider = self.provider(
            owners={},
            records=[customer_record("331002")],
        )

        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-FOR-1",
                ordinal=1,
                check_amount=Decimal("125.00"),
                original_source={
                    "for_customer_number": "331002",
                    "for_customer_number_evidence": "For 331002",
                },
            ),
            {},
        )

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.customer_number, "331002")
        self.assertEqual(
            resolution.confidence_basis,
            "check_for_customer_number",
        )
        self.assertEqual(resolution.selected_confidence, 1.0)
        self.assertTrue(
            resolution.matching_evidence["check_for_customer_verified"]
        )

    def test_verified_seven_digit_check_for_customer_number_resolves(self):
        # MaddenCo customer numbers (TMCUST.CUNUMBER) are decimal(7,0) — a
        # real customer number can be seven digits, not only six.
        provider = self.provider(
            owners={},
            records=[customer_record("1000045")],
        )

        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-FOR-7",
                ordinal=1,
                check_amount=Decimal("125.00"),
                original_source={
                    "for_customer_number": "1000045",
                    "for_customer_number_evidence": "For 1000045",
                },
            ),
            {},
        )

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.customer_number, "1000045")
        self.assertEqual(
            resolution.confidence_basis,
            "check_for_customer_number",
        )
        self.assertEqual(resolution.selected_confidence, 1.0)
        self.assertTrue(
            resolution.matching_evidence["check_for_customer_verified"]
        )

    def test_verified_check_phone_number_resolves_after_for_line(self):
        provider = self.provider(
            owners={},
            records=[customer_record("640194")],
        )

        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-PHONE-1",
                ordinal=1,
                check_amount=Decimal("11660.98"),
                original_source={
                    "customer_phone": "(419) 555-1212",
                },
            ),
            {},
        )

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.customer_number, "640194")
        self.assertEqual(
            resolution.confidence_basis,
            "check_phone_number_match",
        )
        self.assertEqual(resolution.selected_confidence, 1.0)
        self.assertTrue(
            resolution.matching_evidence["check_phone_number_verified"]
        )

    def test_check_for_customer_number_remains_ahead_of_phone_number(self):
        provider = self.provider(
            owners={},
            records=[customer_record("331002")],
        )

        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-PHONE-2",
                ordinal=1,
                check_amount=Decimal("125.00"),
                original_source={
                    "for_customer_number": "331002",
                    "customer_phone": "4195551212",
                },
            ),
            {},
        )

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.customer_number, "331002")
        self.assertEqual(
            resolution.confidence_basis,
            "check_for_customer_number",
        )

    def test_check_phone_number_conflict_with_invoice_owner_is_not_selected(self):
        provider = self.provider(
            owners={"431000001": {"111111"}},
            records=[customer_record("999999")],
        )
        evidence = provider.resolve_invoice_owners(["431000001"])

        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-PHONE-3",
                ordinal=1,
                check_amount=Decimal("125.00"),
                extracted_invoice_numbers=(
                    "431000001",
                    "431000002",
                ),
                original_source={"customer_phone": "4195551212"},
            ),
            evidence,
        )

        self.assertNotEqual(
            resolution.confidence_basis,
            "check_phone_number_match",
        )
        self.assertTrue(
            resolution.matching_evidence["check_phone_number_conflict"]
        )

    def test_learned_payer_bank_account_mapping_resolves(self):
        provider = self.provider(
            owners={},
            records=[customer_record("640194")],
            confirmed_mappings={("076401251", "1234"): ["640194"]},
        )

        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-LEARNED-1",
                ordinal=1,
                check_amount=Decimal("125.00"),
                original_source={
                    "aba_routing": "076401251",
                    "account_number": "998877661234",
                },
            ),
            {},
        )

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.customer_number, "640194")
        self.assertEqual(
            resolution.confidence_basis,
            "learned_payer_bank_account_mapping",
        )
        self.assertEqual(resolution.selected_confidence, 1.0)
        self.assertTrue(
            resolution.matching_evidence[
                "learned_payer_bank_account_verified"
            ]
        )

    def test_check_for_customer_number_remains_ahead_of_learned_mapping(self):
        provider = self.provider(
            owners={},
            records=[customer_record("331002")],
            confirmed_mappings={("076401251", "1234"): ["999999"]},
        )

        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-LEARNED-2",
                ordinal=1,
                check_amount=Decimal("125.00"),
                original_source={
                    "for_customer_number": "331002",
                    "aba_routing": "076401251",
                    "account_number": "1234",
                },
            ),
            {},
        )

        self.assertEqual(resolution.customer_number, "331002")
        self.assertEqual(
            resolution.confidence_basis,
            "check_for_customer_number",
        )

    def test_learned_mapping_conflict_with_invoice_owner_is_not_selected(self):
        provider = self.provider(
            owners={"431000001": {"111111"}},
            records=[customer_record("999999")],
            confirmed_mappings={("076401251", "1234"): ["999999"]},
        )
        evidence = provider.resolve_invoice_owners(["431000001"])

        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-LEARNED-3",
                ordinal=1,
                check_amount=Decimal("125.00"),
                extracted_invoice_numbers=(
                    "431000001",
                    "431000002",
                ),
                original_source={
                    "aba_routing": "076401251",
                    "account_number": "1234",
                },
            ),
            evidence,
        )

        self.assertNotEqual(
            resolution.confidence_basis,
            "learned_payer_bank_account_mapping",
        )
        self.assertTrue(
            resolution.matching_evidence[
                "learned_payer_bank_account_conflict"
            ]
        )

    def test_learned_mapping_with_multiple_distinct_customers_is_not_used(self):
        provider = self.provider(
            owners={},
            records=[customer_record("640194")],
            confirmed_mappings={
                ("076401251", "1234"): ["640194", "700001"],
            },
        )

        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-LEARNED-4",
                ordinal=1,
                check_amount=Decimal("125.00"),
                original_source={
                    "aba_routing": "076401251",
                    "account_number": "1234",
                },
            ),
            {},
        )

        self.assertNotEqual(
            resolution.confidence_basis,
            "learned_payer_bank_account_mapping",
        )

    def test_statement_customer_number_remains_ahead_of_for_line(self):
        provider = self.provider(
            owners={},
            records=[customer_record("640516"), customer_record("331002")],
        )

        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-FOR-2",
                ordinal=1,
                check_amount=Decimal("125.00"),
                original_source={
                    "statement_customer_number": "640516",
                    "for_customer_number": "331002",
                },
            ),
            {},
        )

        self.assertEqual(resolution.customer_number, "640516")
        self.assertEqual(
            resolution.confidence_basis,
            "km_statement_customer_number",
        )

    def test_invoice_owner_remains_ahead_of_conflicting_for_line(self):
        provider = self.provider(
            owners={"431700001": {"700002"}},
            records=[customer_record("331002"), customer_record("700002")],
        )
        evidence = provider.resolve_invoice_owners(["431700001"])

        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-FOR-3",
                ordinal=1,
                check_amount=Decimal("125.00"),
                extracted_invoice_numbers=("431700001",),
                original_source={"for_customer_number": "331002"},
            ),
            evidence,
        )

        self.assertEqual(resolution.customer_number, "700002")
        self.assertEqual(
            resolution.confidence_basis,
            "unique_remittance_invoice_owner",
        )

    def test_ambiguous_invoice_owners_are_not_auto_selected(self):
        provider = self.provider(
            owners={"431063896": {"520459", "520460"}},
            records=[customer_record("520459"), customer_record("520460")],
        )
        evidence = provider.resolve_invoice_owners(["431063896"])
        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-2",
                ordinal=1,
                check_amount=Decimal("100.00"),
                extracted_invoice_numbers=("431063896",),
            ),
            evidence,
        )
        self.assertEqual(resolution.status, "ambiguous")
        self.assertEqual(set(resolution.candidates), {"520459", "520460"})

    def test_phone_zip_anchor_is_preserved_during_invoice_conflict(self):
        other = customer_record("520460")
        other["phone"] = "4195559999"
        provider = self.provider(
            owners={"431063896": {"520459", "520460"}},
            records=[customer_record("520459", "700000"), other],
        )
        evidence = provider.resolve_invoice_owners(["431063896"])
        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-2A",
                ordinal=1,
                check_amount=Decimal("100.00"),
                extracted_invoice_numbers=("431063896",),
                original_source={
                    "customer_phone": "(419) 555-1212",
                    "customer_postal_code": "45865-1234",
                },
            ),
            evidence,
        )

        self.assertEqual(resolution.status, "ambiguous")
        self.assertEqual(
            resolution.customer_snapshot["customer_number"],
            "520459",
        )
        self.assertIn("first five ZIP digits", resolution.matched_on[0])

    def test_contact_fallback_reuses_established_match_ranking(self):
        # Two records share one phone number, so the earlier
        # check_phone_number_match tier's "exactly one exact-phone
        # candidate" precondition is not met and this falls through to
        # the deeper address+zip-corroborated ranking path.
        second_record = dict(customer_record("520460"))
        second_record["address_line_1"] = "200 Other Ave"
        second_record["postal_code"] = "45866"
        provider = self.provider(
            owners={},
            records=[customer_record(), second_record],
        )
        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-3",
                ordinal=1,
                check_amount=Decimal("100.00"),
                original_source={
                    "customer_phone": "419-555-1212",
                    "customer_address_line_1": "100 Main St",
                    "customer_postal_code": "45865",
                    "customer_name": "Example Tire",
                },
            ),
            {},
        )
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.customer_number, "520459")
        self.assertEqual(resolution.selected_confidence, 1.0)
        self.assertEqual(
            resolution.confidence_basis,
            "unique_phone_zip_with_address_confirmation",
        )
        self.assertEqual(
            resolution.matching_evidence["candidate_snapshot_version"],
            "lockbox-candidate-evidence@1.0.0",
        )
        self.assertTrue(
            resolution.matching_evidence["candidate_query_complete"]
        )
        self.assertEqual(
            resolution.matching_evidence["ranked_candidates"][0][
                "customer_number"
            ],
            "520459",
        )
        self.assertIn(
            "Phone number matches",
            " ".join(
                resolution.matching_evidence["ranked_candidates"][0][
                    "matched_on"
                ]
            ),
        )

    def test_unique_exact_phone_resolves_without_zip(self):
        # A unique exact-phone match now resolves through the earlier
        # check_phone_number_match tier (same precedence tier as the check
        # FOR line), unconditionally at full confidence - it no longer
        # depends on name/address corroboration via the deeper generic
        # customer-match-service ranking path.
        provider = self.provider(
            owners={},
            records=[customer_record()],
        )
        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-3A",
                ordinal=1,
                check_amount=Decimal("950.04"),
                original_source={
                    "customer_phone": "(419) 555-1212",
                    "customer_name": "Example Tire",
                },
            ),
            {},
        )

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.customer_number, "520459")
        self.assertEqual(
            resolution.selection_basis,
            "check_phone_number_match",
        )
        self.assertEqual(resolution.selected_confidence, 1.0)
        self.assertEqual(
            resolution.confidence_basis,
            "check_phone_number_match",
        )
        self.assertTrue(
            resolution.matching_evidence["check_phone_number_verified"]
        )

    def test_unique_exact_phone_without_other_contact_is_deterministic(self):
        provider = self.provider(
            owners={},
            records=[customer_record()],
        )
        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-3B",
                ordinal=1,
                check_amount=Decimal("950.04"),
                original_source={
                    "customer_phone": "4195551212",
                },
            ),
            {},
        )

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.customer_number, "520459")
        self.assertEqual(resolution.selected_confidence, 1.0)
        self.assertEqual(
            resolution.confidence_basis,
            "check_phone_number_match",
        )

    def test_complete_unique_exact_address_and_zip_reaches_provider(self):
        provider = self.provider(
            owners={},
            records=[customer_record()],
        )
        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-3C",
                ordinal=1,
                check_amount=Decimal("950.04"),
                original_source={
                    "customer_address_line_1": "100 Main St.",
                    "customer_postal_code": "45865-1234",
                },
            ),
            {},
        )

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.customer_number, "520459")
        self.assertEqual(
            resolution.selection_basis,
            "exact_address_and_zip",
        )
        self.assertEqual(
            resolution.confidence_basis,
            "unique_exact_address_and_zip",
        )
        self.assertTrue(
            resolution.matching_evidence["address_candidate_complete"]
        )

    def test_nonzero_cunument_loads_every_linked_customer(self):
        provider = self.provider(
            owners={},
            records=[
                customer_record("700000", "0"),
                customer_record("520459", "700000"),
                customer_record("520460", "700000"),
                customer_record("999999", "800000"),
            ],
        )

        customer = provider.load_customer("520459")
        group = provider.load_customer_group(customer)

        self.assertEqual(group.enterprise_number, "700000")
        self.assertEqual(
            [account.customer_number for account in group.accounts],
            ["520459", "520460", "700000"],
        )
        self.assertTrue(group.source_reference.startswith("ERP TMCUST"))

    def test_negative_debit_maps_raw_and_signed_erp_evidence(self):
        invoice = SimpleNamespace(
            customer_number="520459",
            invoice_number="431063896",
            open_amount=Decimal("916.00"),
            due_date=date(2026, 7, 10),
            invoice_date=date(2026, 6, 10),
            transaction_type="Debit",
            debit_credit="D",
            original_amount=Decimal("-916.00"),
            aging_bucket="CURRENT",
        )
        provider = self.provider(
            owners={},
            records=[customer_record()],
            invoices=[invoice],
        )
        snapshot = provider.load_open_ar("520459", date(2026, 7, 10))
        row = snapshot.invoices[0]
        self.assertEqual(row.raw_transaction_type, "Debit")
        self.assertEqual(row.open_amount, Decimal("916.00"))
        self.assertEqual(row.signed_source_amount, Decimal("-916.00"))

    def test_sc_open_item_preserves_positive_effect_and_unique_row_key(self):
        invoice = SimpleNamespace(
            customer_number="430547",
            invoice_number="8",
            invoice_count=8,
            open_amount=Decimal("14.18"),
            due_date=date(2026, 7, 10),
            invoice_date=date(2026, 6, 30),
            transaction_type="SC",
            debit_credit="D",
            original_amount=Decimal("14.18"),
            aging_bucket="CURRENT",
        )
        provider = self.provider(
            owners={},
            records=[customer_record("430547")],
            invoices=[invoice],
        )

        snapshot = provider.load_open_ar("430547", date(2026, 7, 10))
        row = snapshot.invoices[0]

        self.assertEqual(row.raw_transaction_type, "SC")
        self.assertEqual(row.signed_source_amount, Decimal("14.18"))
        self.assertEqual(row.invoice_count, 8)
        self.assertEqual(row.open_item_key, "430547|SC|8|8")

    def test_provider_surface_contains_no_erp_write_or_approval(self):
        public = {
            name
            for name in dir(ExistingReadOnlyPreparationProvider)
            if not name.startswith("_")
        }
        self.assertFalse(
            public
            & {
                "approve",
                "apply",
                "post",
                "write",
                "update_invoice",
                "save_customer",
            }
        )

    def test_more_than_100_invoices_and_oversized_ocr_fields_are_safe(
        self,
    ) -> None:
        invoices = tuple(f"43{ordinal:06d}" for ordinal in range(125))
        provider = self.provider(
            owners={},
            records=[customer_record()],
        )
        resolution = provider.resolve_customer(
            SourceTransaction(
                transaction_id="G-125",
                ordinal=1,
                check_amount=Decimal("125.00"),
                extracted_invoice_numbers=invoices,
                original_source={
                    "customer_phone": "9" * 500,
                    "customer_name": "X" * 500,
                },
            ),
            {
                invoice: InvoiceOwnerEvidence(
                    invoice_number=invoice,
                    customer_numbers=(),
                )
                for invoice in invoices
            },
        )

        self.assertNotEqual(resolution.status, "unavailable")
        self.assertEqual(
            resolution.matching_evidence["valid_invoice_count"],
            125,
        )
        rejected = resolution.matching_evidence["rejected_input_fields"]
        self.assertTrue(any(item.startswith("phone:") for item in rejected))
        self.assertTrue(
            any(item.startswith("customer_name:") for item in rejected)
        )


class ReceivablesRepositoryCurrentOwnerTest(unittest.TestCase):
    def test_current_owner_lookup_is_chunked_complete_and_read_only(
        self,
    ) -> None:
        class FakeDatabase:
            def __init__(self):
                self.calls = []

            def fetch_all(self, query, parameters):
                self.calls.append((query, tuple(parameters)))
                return [
                    {
                        "invoice_number": invoice,
                        "customer_number": "520459",
                    }
                    for invoice in parameters
                ]

        database = FakeDatabase()
        repository = ReceivablesRepository(database)
        invoices = tuple(f"43{ordinal:06d}" for ordinal in range(205))

        owners = repository.get_current_invoice_owners(invoices)

        self.assertEqual(
            [len(call[1]) for call in database.calls],
            [100, 100, 5],
        )
        self.assertEqual(set(owners), set(invoices))
        self.assertTrue(
            all(value == {"520459"} for value in owners.values())
        )
        for query, _ in database.calls:
            normalized = " ".join(query.upper().split())
            self.assertTrue(normalized.startswith("SELECT"))
            self.assertNotIn(" UPDATE ", f" {normalized} ")
            self.assertNotIn(" INSERT ", f" {normalized} ")
            self.assertNotIn(" DELETE ", f" {normalized} ")

    def test_current_owner_lookup_fails_closed_at_row_limit(self) -> None:
        class TruncatedDatabase:
            def fetch_all(self, query, parameters):
                invoice = parameters[0]
                return [
                    {
                        "invoice_number": invoice,
                        "customer_number": str(ordinal),
                    }
                    for ordinal in range(1001)
                ]

        repository = ReceivablesRepository(TruncatedDatabase())

        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            repository.get_current_invoice_owners(("43000001",))


class SourceLoaderIntegrationTest(unittest.TestCase):
    def test_preserved_ten_digit_rows_are_not_recovered(self):
        rejected_rows = [
            {
                "raw_invoice_candidates": [str(9999000001 + index)],
                "net_invoice_amount": float(Decimal("500.00") + index),
                "invoice_page": "12;1",
                "reason": "no_governed_invoice_candidate",
                "extraction_source": "embedded_text",
            }
            for index in range(5)
        ]
        source_transaction = {
            "transaction_id": "G-SOURCE-10-DIGIT",
            "transaction_boundary_rule": "next_transaction_information",
            "transaction_boundary_closed": True,
            "remittance_evidence_complete": False,
            "remittance_incomplete_pages": [12],
            "remittance_ocr_errors": [],
            "rejected_remittance_candidates": rejected_rows,
            "allocations": [],
        }

        merged = merge_extractions(
            {"transactions": [source_transaction]},
            {"transactions": [source_transaction]},
        )

        transaction = merged["transactions"][0]
        self.assertEqual(transaction["allocations"], [])
        self.assertFalse(transaction["remittance_evidence_complete"])
        self.assertEqual(
            transaction["rejected_remittance_candidates"],
            rejected_rows,
        )
        evidence = transaction["projection_evidence"]
        self.assertEqual(evidence["source_recovered_allocation_count"], 0)
        self.assertEqual(evidence["source_recovered_rejection_count"], 0)
        self.assertEqual(evidence["unresolved_rejection_count"], 5)
        self.assertEqual(evidence["unresolved_incomplete_pages"], [12])
        self.assertTrue(evidence["baseline_evidence_preserved"])
        self.assertFalse(evidence["review_edits_used_as_extraction"])

    def test_ambiguous_or_placeholder_rejections_are_never_recovered(self):
        source_transaction = {
            "transaction_id": "G-SOURCE-AMBIGUOUS",
            "transaction_boundary_rule": "next_transaction_information",
            "transaction_boundary_closed": True,
            "remittance_evidence_complete": False,
            "remittance_incomplete_pages": [12],
            "rejected_remittance_candidates": [
                {
                    "raw_invoice_candidates": [
                        "9999000001",
                        "9999000002",
                    ],
                    "net_invoice_amount": 500.00,
                    "invoice_page": "12;1",
                    "reason": "no_governed_invoice_candidate",
                },
                {
                    "raw_invoice_candidates": ["9999999999"],
                    "net_invoice_amount": 100.00,
                    "invoice_page": "12;1",
                    "reason": "no_governed_invoice_candidate",
                },
            ],
            "allocations": [],
        }

        merged = merge_extractions(
            {"transactions": [source_transaction]},
            {"transactions": [source_transaction]},
        )

        transaction = merged["transactions"][0]
        self.assertEqual(transaction["allocations"], [])
        self.assertFalse(transaction["remittance_evidence_complete"])
        evidence = transaction["projection_evidence"]
        self.assertEqual(evidence["source_recovered_allocation_count"], 0)
        self.assertEqual(evidence["unresolved_rejection_count"], 2)

    def test_contact_conflict_remains_material_when_zip_disagrees(self):
        saved = {
            "transactions": [
                {
                    "transaction_id": "G-SAFE-1",
                    "customer_name": "ORIGINAL PAYER",
                    "customer_phone": "3125550184",
                    "customer_postal_code": "60601",
                    "allocations": [],
                }
            ]
        }
        candidate = {
            "transactions": [
                {
                    "transaction_id": "G-SAFE-1",
                    "customer_name": "DIFFERENT PAYER",
                    "customer_phone": "3125550184",
                    "customer_address_line_1": "1200 EXAMPLE ROAD",
                    "customer_postal_code": "60602",
                    "customer_identity_confidence": 0.99,
                    "transaction_boundary_rule": (
                        "next_transaction_information"
                    ),
                    "transaction_boundary_closed": True,
                    "allocations": [],
                }
            ]
        }

        merged = merge_extractions(saved, candidate)
        evidence = merged["transactions"][0]["projection_evidence"]

        self.assertEqual(evidence["customer_conflict_count"], 2)
        self.assertEqual(
            evidence["customer_nonmaterial_name_conflict_count"],
            0,
        )

    def test_loader_hashes_saved_pdf_and_preserves_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            pdf_path = Path(temporary) / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.7\ncontrolled-test\n%%EOF")
            original = {
                "job_id": "source-1",
                "source_file_name": "sample.pdf",
                "extraction_version": EXTRACTION_VERSION,
                "transactions": [],
            }
            loader = SavedLockboxSourceLoader(
                job_loader=lambda job_id: {
                    "job_id": job_id,
                    "stored_path": str(pdf_path),
                    "original_file_name": "sample.pdf",
                },
                result_loader=lambda job_id: original,
                review_loader=lambda job_id: original,
                versioned_extraction_dir=Path(temporary) / "extractions",
            )
            loaded = loader("source-1")
            self.assertEqual(
                loaded["source_file_hash"],
                sha256_file(pdf_path),
            )
            self.assertEqual(
                loaded["extraction_version"],
                EXTRACTION_VERSION,
            )
            self.assertNotIn("source_file_hash", original)

    def test_stale_saved_result_is_reparsed_once_and_cached_by_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.7\ncontrolled-test\n%%EOF")
            cache_dir = root / "extractions"
            parser_calls = []
            saved = {
                "job_id": "source-1",
                "extraction_version": "pnc-lockbox-parser@0.6.9",
                "transactions": [
                    {
                        "transaction_id": "G-1",
                        "customer_name": "PAYEE DISTRIBUTION",
                        "customer_phone": "",
                        "customer_postal_code": "",
                        "status": "no_remittance",
                        "allocations": [],
                    }
                ],
            }

            def current_parser(path):
                parser_calls.append(Path(path))
                return {
                    "parser_version": EXTRACTION_VERSION,
                    "extraction_version": EXTRACTION_VERSION,
                    "transactions": [
                        {
                            "transaction_id": "G-1",
                            "customer_name": "EXAMPLE AUTOMOTIVE, INC.",
                            "customer_phone": "(312) 555-0184",
                            "customer_address_line_1": "1200 EXAMPLE ROAD",
                            "customer_city": "SAMPLEVILLE",
                            "customer_state": "IL",
                            "customer_postal_code": "60601",
                            "customer_identity_confidence": 0.99,
                            "status": "no_remittance",
                            "allocations": [],
                        }
                    ],
                }

            job_loader = lambda job_id: {
                "job_id": job_id,
                "stored_path": str(pdf_path),
                "original_file_name": "sample.pdf",
            }
            first_loader = SavedLockboxSourceLoader(
                job_loader=job_loader,
                result_loader=lambda job_id: saved,
                review_loader=lambda job_id: saved,
                parser=current_parser,
                versioned_extraction_dir=cache_dir,
            )
            first = first_loader("source-1")
            self.assertEqual(len(parser_calls), 1)
            self.assertEqual(first["extraction_version"], EXTRACTION_VERSION)
            self.assertEqual(
                first["prior_extraction_version"],
                "pnc-lockbox-parser@0.6.9",
            )
            self.assertEqual(
                first["transactions"][0]["customer_name"],
                "PAYEE DISTRIBUTION",
            )
            self.assertEqual(
                first["transactions"][0]["customer_phone"],
                "(312) 555-0184",
            )
            self.assertEqual(
                first["transactions"][0]["projection_evidence"][
                    "customer_conflict_count"
                ],
                0,
            )
            self.assertEqual(
                first["transactions"][0]["projection_evidence"][
                    "customer_nonmaterial_name_conflict_count"
                ],
                1,
            )

            cached_loader = SavedLockboxSourceLoader(
                job_loader=job_loader,
                result_loader=lambda job_id: saved,
                review_loader=lambda job_id: saved,
                parser=lambda path: self.fail(
                    "A current versioned extraction must be reused."
                ),
                versioned_extraction_dir=cache_dir,
            )
            second = cached_loader("source-1")
            self.assertEqual(second["transactions"], first["transactions"])
            self.assertEqual(len(list(cache_dir.glob("*.json"))), 1)

    def test_current_generation_lookup_reads_identity_without_parsing(self):
        class IdentityOnlyLoader:
            def __init__(self):
                self.identity_calls = 0
                self.parse_calls = 0

            def identity(self, source_job_id):
                self.identity_calls += 1
                return {"source_file_hash": "a" * 64}

            def __call__(self, source_job_id):
                self.parse_calls += 1
                raise AssertionError("GET must not parse the source PDF")

        loader = IdentityOnlyLoader()
        repository = SimpleNamespace(
            get_current_job=lambda source_job_id, source_hash: {
                "complete": True,
                "counts_final": True,
                "expected_count": 0,
                "terminal_count": 0,
                "balanced_count": 0,
                "exception_count": 0,
                "preserved_count": 0,
                "exception_reason_summary": {
                    "total_exception_count": 0,
                },
            }
        )
        service = DurableLockboxPreparationService(
            coordinator=SimpleNamespace(repository=repository),
            source_loader=loader,
            control_projection_required=False,
        )

        result = service.current_source_job("source-1")

        self.assertTrue(result["reconciled"])
        self.assertEqual(loader.identity_calls, 1)
        self.assertEqual(loader.parse_calls, 0)

    def test_nonhuman_review_overlay_never_becomes_extraction_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.7\ncontrolled-test\n%%EOF")
            raw = {
                "extraction_version": EXTRACTION_VERSION,
                "parser_version": EXTRACTION_VERSION,
                "transactions": [
                    {
                        "transaction_id": "G-1",
                        "customer_name": "PARSER PAYER",
                        "status": "review_required",
                        "allocations": [
                            {
                                "invoice_number": "100000001",
                                "net_invoice_amount": 10.00,
                            }
                        ],
                    }
                ],
            }
            editable = {
                **raw,
                "transactions": [
                    {
                        **raw["transactions"][0],
                        "customer_name": "UNSAVED UI VALUE",
                        "allocations": [
                            {
                                "invoice_number": "100000002",
                                "net_invoice_amount": 10.00,
                            }
                        ],
                    }
                ],
            }
            loader = SavedLockboxSourceLoader(
                job_loader=lambda job_id: {
                    "stored_path": str(pdf_path),
                    "original_file_name": "sample.pdf",
                },
                result_loader=lambda job_id: raw,
                review_loader=lambda job_id: editable,
                versioned_extraction_dir=root / "extractions",
            )

            loaded = loader("source-1")

            self.assertEqual(
                loaded["transactions"][0]["customer_name"],
                "PARSER PAYER",
            )
            self.assertEqual(
                loaded["transactions"][0]["allocations"][0][
                    "invoice_number"
                ],
                "100000001",
            )

    def test_reparsed_cba_remit_carries_57_rows_to_balanced_preparation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf_path = root / "cba.pdf"
            pdf_path.write_bytes(b"%PDF-1.7\ncontrolled-test\n%%EOF")
            base_numbers = [
                str(100000100 + index)
                for index in range(55)
            ]
            amounts = (
                [Decimal("34097.25")]
                + [Decimal("10.00")] * 53
                + [Decimal("-6028.24")]
            )
            invoice_amounts = dict(zip(base_numbers, amounts))
            invoice_amounts.update(
                {
                    "100489020": Decimal("316.22"),
                    "400047854": Decimal("348.00"),
                }
            )
            allocations = [
                {
                    "invoice_number": invoice_number,
                    "net_invoice_amount": float(amount),
                    "invoice_page": "48;1",
                }
                for invoice_number, amount in invoice_amounts.items()
            ]
            stale = {
                "extraction_version": "pnc-lockbox-parser@0.6.9",
                "transactions": [],
            }
            parser_result = {
                "parser_version": EXTRACTION_VERSION,
                "extraction_version": EXTRACTION_VERSION,
                "transaction_date": "2026/07/31",
                "transactions": [
                    {
                        "transaction_id": "G-8572002",
                        "check_amount": 29263.23,
                        "date": "2026/07/31",
                        "allocations": allocations,
                        "remittance_evidence_complete": True,
                    }
                ],
            }
            loader = SavedLockboxSourceLoader(
                job_loader=lambda job_id: {
                    "stored_path": str(pdf_path),
                    "original_file_name": "cba.pdf",
                },
                result_loader=lambda job_id: stale,
                review_loader=lambda job_id: stale,
                parser=lambda path: parser_result,
                versioned_extraction_dir=root / "extractions",
            )
            customer = customer_record("404923")
            customer["customer_name"] = "LESLIE TIRE"
            invoices = [
                SimpleNamespace(
                    customer_number="404923",
                    invoice_number=invoice_number,
                    open_amount=amount,
                    due_date=date(2026, 7, 10),
                    invoice_date=date(2026, 6, 10),
                    transaction_type="Debit",
                    debit_credit="D",
                    original_amount=amount,
                    aging_bucket="CURRENT",
                )
                for invoice_number, amount in invoice_amounts.items()
            ]
            provider = ActiveProviderIntegrationTest().provider(
                owners={
                    invoice_number: {"404923"}
                    for invoice_number in invoice_amounts
                },
                records=[customer],
                invoices=invoices,
            )
            preparation_engine = create_engine(f"sqlite:///{root / 'preparation.db'}")
            repository = LockboxPreparationRepository(engine=preparation_engine)
            coordinator = DurableLockboxPreparationCoordinator(
                repository,
                provider,
                read_workers=1,
                recover_on_startup=False,
            )
            service = DurableLockboxPreparationService(
                coordinator,
                source_loader=loader,
                control_projection_required=False,
            )
            try:
                result = service.start_source_job(
                    "source-cba",
                    background=False,
                )
            finally:
                coordinator.shutdown()

            self.assertEqual(result["balanced_count"], 1)
            transaction = result["transactions"][0]
            recommendation = transaction["result"]["recommendation"]
            self.assertEqual(len(recommendation["allocations"]), 57)
            self.assertAlmostEqual(
                sum(abs(float(amount)) for amount in invoice_amounts.values()),
                41319.71,
                places=2,
            )
            self.assertEqual(
                {
                    item["invoice_number"]
                    for item in recommendation["allocations"]
                }
                & {"100489020", "400047854"},
                {"100489020", "400047854"},
            )
            self.assertAlmostEqual(
                sum(
                    float(item["apply_amount"])
                    for item in recommendation["allocations"]
                ),
                29263.23,
                places=2,
            )
            preparation_engine.dispose()

    def test_reparsed_check_payer_resolves_and_balances_without_refresh(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf_path = root / "example-payer.pdf"
            pdf_path.write_bytes(b"%PDF-1.7\ncontrolled-test\n%%EOF")
            stale = {
                "extraction_version": "pnc-lockbox-parser@0.6.9",
                "transactions": [],
            }
            parser_result = {
                "parser_version": EXTRACTION_VERSION,
                "extraction_version": EXTRACTION_VERSION,
                "transaction_date": "2026/01/15",
                "transactions": [
                    {
                        "transaction_id": "G-SYNTH-9002",
                        "check_amount": 250.00,
                        "date": "2026/01/15",
                        "customer_name": "EXAMPLE AUTOMOTIVE, INC.",
                        "customer_phone": "(312) 555-0184",
                        "customer_address_line_1": "1200 EXAMPLE ROAD",
                        "customer_city": "SAMPLEVILLE",
                        "customer_state": "IL",
                        "customer_postal_code": "60601",
                        "allocations": [],
                        "remittance_evidence_complete": False,
                    }
                ],
            }
            loader = SavedLockboxSourceLoader(
                job_loader=lambda job_id: {
                    "stored_path": str(pdf_path),
                    "original_file_name": "example-payer.pdf",
                },
                result_loader=lambda job_id: stale,
                review_loader=lambda job_id: stale,
                parser=lambda path: parser_result,
                versioned_extraction_dir=root / "extractions",
            )
            customer = customer_record("400001")
            customer.update(
                {
                    "customer_name": "EXAMPLE AUTOMOTIVE, INC.",
                    "phone": "3125550184",
                    "address_line_1": "1200 EXAMPLE ROAD",
                    "city": "SAMPLEVILLE",
                    "state": "IL",
                    "postal_code": "60601",
                }
            )
            invoice = SimpleNamespace(
                customer_number="400001",
                invoice_number="100000001",
                open_amount=Decimal("250.00"),
                due_date=date(2026, 1, 10),
                invoice_date=date(2025, 12, 10),
                transaction_type="Debit",
                debit_credit="D",
                original_amount=Decimal("250.00"),
                aging_bucket="CURRENT",
            )
            provider = ActiveProviderIntegrationTest().provider(
                owners={},
                records=[customer],
                invoices=[invoice],
            )
            preparation_engine = create_engine(f"sqlite:///{root / 'preparation.db'}")
            repository = LockboxPreparationRepository(engine=preparation_engine)
            coordinator = DurableLockboxPreparationCoordinator(
                repository,
                provider,
                read_workers=1,
                recover_on_startup=False,
            )
            service = DurableLockboxPreparationService(
                coordinator,
                source_loader=loader,
                control_projection_required=False,
            )
            try:
                result = service.start_source_job(
                    "source-example-payer",
                    background=False,
                )
            finally:
                coordinator.shutdown()

            transaction = result["transactions"][0]
            self.assertEqual(transaction["state"], "prepared_balanced")
            self.assertEqual(
                transaction["result"]["customer_resolution"][
                    "customer_number"
                ],
                "400001",
            )
            self.assertEqual(
                transaction["result"]["customer_resolution"][
                    "selected_confidence"
                ],
                1.0,
            )
            self.assertAlmostEqual(
                float(
                    transaction["result"]["recommendation"][
                        "suggested_total"
                    ]
                ),
                250.00,
                places=2,
            )
            preparation_engine.dispose()

    def test_service_rejects_wrong_client_hash(self):
        coordinator = SimpleNamespace()
        service = DurableLockboxPreparationService(
            coordinator=coordinator,
            source_loader=lambda job_id: {
                "source_file_hash": "a" * 64,
                "transactions": [],
            },
            control_projection_required=False,
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            service.start_source_job("source-1", "b" * 64)

    def test_saved_pnc_date_is_used_for_open_ar_as_of_date(self):
        request = DurableLockboxPreparationService.request_from_source(
            source_job_id="source-1",
            source_file_hash="a" * 64,
            source={
                "transaction_date": "2026/07/10",
                "transactions": [
                    {
                        "transaction_id": "G-1",
                        "check_amount": "100.00",
                        "date": "2026/07/10",
                        "allocations": [],
                    }
                ],
            },
        )
        self.assertEqual(
            request.transactions[0].payment_date,
            date(2026, 7, 10),
        )

    def test_saved_lockbox_source_runs_end_to_end(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.7\ncontrolled-test\n%%EOF")
            source = {
                "job_id": "source-1",
                "source_file_name": "sample.pdf",
                "parser_version": EXTRACTION_VERSION,
                "extraction_version": EXTRACTION_VERSION,
                "transaction_date": "2026/07/10",
                "transactions": [
                    {
                        "transaction_id": "G-1",
                        "check_amount": "100.00",
                        "date": "2026/07/10",
                        "allocations": [
                            {
                                "invoice_number": "431063896",
                                "net_invoice_amount": "100.00",
                            }
                        ],
                    }
                ],
            }
            loader = SavedLockboxSourceLoader(
                job_loader=lambda job_id: {
                    "job_id": job_id,
                    "stored_path": str(pdf_path),
                    "original_file_name": "sample.pdf",
                },
                result_loader=lambda job_id: source,
                review_loader=lambda job_id: source,
                versioned_extraction_dir=root / "extractions",
            )
            invoice = SimpleNamespace(
                customer_number="520459",
                invoice_number="431063896",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 7, 10),
                invoice_date=date(2026, 6, 10),
                transaction_type="Debit",
                debit_credit="D",
                original_amount=Decimal("100.00"),
                aging_bucket="CURRENT",
            )
            provider = ActiveProviderIntegrationTest().provider(
                owners={"431063896": {"520459"}},
                records=[customer_record()],
                invoices=[invoice],
            )
            preparation_engine = create_engine(f"sqlite:///{root / 'preparation.db'}")
            repository = LockboxPreparationRepository(
                engine=preparation_engine
            )
            coordinator = DurableLockboxPreparationCoordinator(
                repository,
                provider,
                recover_on_startup=False,
            )
            service = DurableLockboxPreparationService(
                coordinator,
                loader,
                control_projection_required=False,
            )

            completed = service.start_source_job(
                "source-1",
                background=False,
            )

            self.assertTrue(completed["complete"])
            self.assertEqual(completed["balanced_count"], 1)
            self.assertEqual(
                completed["source_file_hash"],
                sha256_file(pdf_path),
            )
            self.assertEqual(
                provider.receivables_repository.calls,
                [("520459", date(2026, 7, 10))],
            )
            summary = service.exception_summary(completed["job_id"])
            self.assertTrue(summary["counts_final"])
            self.assertEqual(
                summary["exception_reason_summary"][
                    "total_exception_count"
                ],
                0,
            )
            preparation_engine.dispose()


class RuntimeRegistrationTest(unittest.TestCase):
    def test_runtime_routes_publish_through_openapi_contract(self):
        from fastapi import FastAPI
        from modules.document_intelligence.manifest import manifest

        application = FastAPI()
        application.include_router(manifest.router)
        published_paths = set(application.openapi()["paths"])

        self.assertTrue(
            DURABLE_LOCKBOX_ROUTE_PATHS <= published_paths,
            DURABLE_LOCKBOX_ROUTE_PATHS - published_paths,
        )

    def test_document_manifest_registers_durable_routes(self):
        manifest_path = (
            BACKEND_ROOT
            / "modules"
            / "document_intelligence"
            / "manifest.py"
        )
        source = manifest_path.read_text(encoding="utf-8")
        self.assertEqual(
            source.count(
                "module_router.include_router(lockbox_preparation_router)"
            ),
            1,
        )
        self.assertIn(
            "module_router.include_router(lockbox_preparation_router)",
            source,
        )
        router_path = (
            BACKEND_ROOT
            / "modules"
            / "document_intelligence"
            / "lockbox_preparation"
            / "router.py"
        )
        router_source = router_path.read_text(encoding="utf-8")
        self.assertIn(
            '"/jobs/{source_job_id}/lockbox/preparation/start"',
            router_source,
        )
        self.assertIn(
            '"/lockbox/preparation/{job_id}/resume"',
            router_source,
        )
        self.assertIn(
            '"/lockbox/preparation/{job_id}/exception-summary"',
            router_source,
        )
        self.assertNotIn(
            "register_durable_lockbox_routes",
            router_source,
        )

        main_source = (BACKEND_ROOT / "main.py").read_text(
            encoding="utf-8-sig"
        )
        self.assertNotIn(
            "register_durable_lockbox_routes",
            main_source,
        )

    def test_backend_lifecycle_resumes_recovered_jobs(self):
        main_path = BACKEND_ROOT / "main.py"
        source = main_path.read_text(encoding="utf-8-sig")
        self.assertIn(
            "lockbox_preparation_coordinator.resume_recovered()",
            source,
        )

    def test_restart_recovery_runs_with_bound_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            database_path = Path(temporary) / "preparation.db"
            engine = create_engine(f"sqlite:///{database_path}")
            first_repository = LockboxPreparationRepository(engine=engine)
            request_source = {
                "source_file_hash": "c" * 64,
                "source_file_name": "sample.pdf",
                "transactions": [
                    {
                        "transaction_id": "G-1",
                        "check_amount": "100.00",
                        "allocations": [
                            {
                                "invoice_number": "431063896",
                                "net_invoice_amount": "100.00",
                            }
                        ],
                    }
                ],
            }
            first_service = DurableLockboxPreparationService(
                coordinator=SimpleNamespace(),
                source_loader=lambda job_id: request_source,
            )
            request = first_service.request_from_source(
                source_job_id="source-1",
                source_file_hash="c" * 64,
                source=request_source,
            )
            registered = first_repository.register(request)

            invoice = SimpleNamespace(
                customer_number="520459",
                invoice_number="431063896",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 7, 10),
                invoice_date=date(2026, 6, 10),
                transaction_type="Debit",
                debit_credit="D",
                original_amount=Decimal("100.00"),
                aging_bucket="CURRENT",
            )
            provider = ActiveProviderIntegrationTest().provider(
                owners={"431063896": {"520459"}},
                records=[customer_record()],
                invoices=[invoice],
            )
            recovered_repository = LockboxPreparationRepository(engine=engine)
            coordinator = DurableLockboxPreparationCoordinator(
                recovered_repository,
                provider,
            )
            self.assertEqual(
                coordinator.recovered_job_ids,
                (registered["job_id"],),
            )
            coordinator.resume_recovered()
            completed = coordinator.wait(registered["job_id"], timeout=5)
            self.assertTrue(completed["complete"])
            self.assertEqual(completed["balanced_count"], 1)
            result = completed["transactions"][0]["result"]
            self.assertTrue(result["prepared_not_approved"])
            self.assertFalse(result["can_auto_approve"])
            self.assertFalse(result["erp_write_performed"])
            # The completed job's Future must be evicted from the
            # coordinator's in-memory tracking dict once done, not retained
            # for the life of the process - see
            # DurableLockboxPreparationCoordinator._evict_if_still_current.
            # The eviction done-callback runs on the worker thread and isn't
            # guaranteed to have finished by the moment wait() unblocks this
            # thread, so poll briefly rather than asserting immediately.
            deadline = time.monotonic() + 2
            while (
                registered["job_id"] in coordinator._active
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            self.assertNotIn(registered["job_id"], coordinator._active)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
