from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path


# This focused domain test does not exercise the FastAPI router or a live
# database. Keep it runnable in the packaging environment, where those optional
# runtime dependencies are intentionally absent.
BACKEND_ROOT = Path(__file__).resolve().parent
erp_package = types.ModuleType("modules.erp_evidence")
erp_package.__path__ = [str(BACKEND_ROOT / "modules" / "erp_evidence")]
sys.modules["modules.erp_evidence"] = erp_package
core_package = types.ModuleType("core")
core_package.__path__ = [str(BACKEND_ROOT / "core")]
sys.modules["core"] = core_package
core_database = types.ModuleType("core.database")
core_database.madden_database = object()
sys.modules["core.database"] = core_database
accounts_payable_package = types.ModuleType("modules.accounts_payable")
accounts_payable_package.__path__ = [
    str(BACKEND_ROOT / "modules" / "accounts_payable")
]
sys.modules["modules.accounts_payable"] = accounts_payable_package
accounts_payable_service = types.ModuleType("modules.accounts_payable.service")
accounts_payable_service.accounts_payable_service = object()
sys.modules["modules.accounts_payable.service"] = accounts_payable_service
customer_package = types.ModuleType("modules.customer_360")
customer_package.__path__ = [str(BACKEND_ROOT / "modules" / "customer_360")]
sys.modules["modules.customer_360"] = customer_package
customer_service_module = types.ModuleType("modules.customer_360.service")
customer_service_module.customer_service = object()
sys.modules["modules.customer_360.service"] = customer_service_module

from modules.erp_evidence.repository import ERPEvidenceRepository
from modules.erp_evidence.service import ERPEvidenceService


class FakeAPSource:
    def __init__(self, *, complete_identity: bool = True) -> None:
        self.complete_identity = complete_identity

    def get_invoice(self, ap_invoice_id: str) -> dict[str, object]:
        return {
            "ap_invoice_id": ap_invoice_id,
            "vendor_number": "101" if self.complete_identity else None,
            "vendor_name": "Acme Local",
            "invoice_number": "INV-9" if self.complete_identity else None,
            "invoice_date": "20260801",
            "due_date": "20260831",
            "purchase_order_number": "500",
            "total_amount": 125.50,
            "source_evidence_sha256": "a" * 64,
        }


class FakeCustomerSource:
    def summary(self, customer_number: int) -> dict[str, object]:
        return {
            "customer_name": "Test Customer",
            "credit": {
                "credit_limit": 1_000,
                "raw_on_order": 100,
                "total_exposure": 600,
                "available_credit": 400,
                "terms_code": "2",
                "terms_description": "30/60 Net 10th",
            },
            "activity": {
                "last_payment_amount": 25,
                "last_payment_date": "20260801",
            },
        }


class FakeRepository:
    OPEN_AR_MAX_LIMIT = 500
    RELATED_ACCOUNT_LIMIT = 250
    AP_HEADER_LIMIT = 25
    AP_DETAIL_LIMIT = 100
    AP_GL_LIMIT = 100
    AP_PO_MATCH_LIMIT = 50
    AP_INPUT_LIMIT = 100
    AP_VENDOR_SEARCH_LIMIT = 25
    AP_INVOICE_SEARCH_LIMIT = 50

    def __init__(self) -> None:
        self.ap_query_count = 0

    def get_credit_customer(self, customer_number: int) -> dict[str, object]:
        return {
            "CUNUMBER": customer_number,
            "CUNAME": "Test Customer",
            "CUNUMENT": 200,
            "CUCRLIMIT": 1_000,
            "CUBALANCE": 500,
            "CUONORDER": 100,
            "CUONORDAR": 0,
        }

    def get_open_ar(self, customer_number: int, *, limit: int):
        return ([{
            "customer_number": customer_number,
            "invoice_number": "9",
            "invoice_count": 1,
            "invoice_date": "20260701",
            "due_date": "20260731",
            "original_amount": 500,
            "open_amount": 500,
            "debit_credit": "D",
            "transaction_type": "I",
            "reference_number": "7",
            "selling_store": "1",
        }], True)

    def get_related_accounts(self, customer_number: int, enterprise_number: str):
        return ([
            {
                "CUNUMBER": customer_number,
                "CUNAME": "Test Customer",
                "CUNUMENT": enterprise_number,
                "CUCRLIMIT": 1_000,
                "CUBALANCE": 500,
                "CUONORDER": 100,
                "CUONORDAR": 0,
            },
            {
                "CUNUMBER": enterprise_number,
                "CUNAME": "Parent",
                "CUNUMENT": enterprise_number,
                "CUCRLIMIT": 2_000,
                "CUBALANCE": 200,
                "CUONORDER": 0,
                "CUONORDAR": 0,
            },
        ], True)

    def get_ap_vendor(self, vendor_number: int):
        self.ap_query_count += 1
        return {
            "vendor_number": vendor_number,
            "vendor_name": "Acme ERP",
            "sort_name": "ACME",
            "vendor_type_code": "A",
            "delete_code": "",
            "terms_code": 30,
            "po_required_code": "Y",
            "no_ap_from_receipt_code": "N",
            "default_gl_division": 1,
            "default_gl_department": 2,
            "default_gl_account": 300,
            "last_paid_date": "20260731",
            "last_paid_amount": "99.50",
        }

    def search_ap_vendors(self, query: str, *, limit: int):
        self.ap_query_count += 1
        if query.lower() in {"101", "acme"}:
            return ([{
                "vendor_number": 101,
                "vendor_name": "Acme ERP",
                "sort_name": "ACME",
            }], True)
        return [], True

    def search_ap_posted_invoice_identities(
        self,
        *,
        vendor_numbers: list[int] | None,
        invoice_number: str | None,
        limit: int,
    ):
        self.ap_query_count += 1
        if vendor_numbers is not None and 101 not in vendor_numbers:
            return [], True
        if invoice_number not in {None, "INV-9"}:
            return [], True
        return ([{
            "vendor_number": 101,
            "vendor_name": "Acme ERP",
            "invoice_number": "INV-9",
            "posted_header_row_count": 1,
            "latest_invoice_date": "20260801",
            "latest_due_date": "20260831",
        }], True)

    def get_ap_posted_headers(self, vendor_number: int, invoice_number: str):
        self.ap_query_count += 1
        return ([{
            "vendor_number": vendor_number,
            "invoice_number": invoice_number,
            "payment_number": 1,
            "invoice_amount": "125.50",
            "discount_amount": "0",
            "invoice_description": "Tires",
            "invoice_date": "20260801",
            "due_date": "20260831",
            "created_date": "20260802",
            "changed_date": "20260803",
            "check_number": 0,
            "check_date": 0,
            "hold_flag": "N",
            "selection_code": "",
            "discount_taken_code": "",
            "gl_reference": 7,
            "check_gl_reference": 0,
            "void_gl_reference": 0,
            "void_check_gl_reference": 0,
            "accounting_period": 8,
            "accounting_year": 2026,
        }], True)

    def get_ap_posted_details(self, vendor_number: int, invoice_number: str):
        self.ap_query_count += 1
        return ([{
            "sequence_number": 1,
            "line_description": "Line",
            "line_amount": "125.50",
            "quantity": "2",
            "gl_division": 1,
            "gl_department": 2,
            "gl_account": 300,
            "po_receiver_reference": 555,
            "customer_number": 0,
            "job_number": 0,
        }], True)

    def _empty(self, vendor_number: int, invoice_number: str):
        self.ap_query_count += 1
        return [], True

    get_ap_gl_distributions = _empty
    get_po_receiving_match = _empty
    get_ap_input_headers = _empty
    get_ap_input_details = _empty
    get_ap_input_payment_splits = _empty


class CapturingDatabase:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_all(self, sql: str, parameters=()):
        self.calls.append((sql, tuple(parameters)))
        return list(self.rows)


class ERPEvidenceRepositorySearchTests(unittest.TestCase):
    def test_confirmed_ap_readiness_maps_ptdt_explicitly(self) -> None:
        database = CapturingDatabase(
            rows=[
                {"table_name": "PTDT", "column_name": "PTHNBVND"},
                {"table_name": "PTDT", "column_name": "PTHNBINV"},
                {"table_name": "PTDT", "column_name": "PTDNBPORV"},
            ]
        )
        repository = ERPEvidenceRepository(database=database)
        candidates, _column_count, complete = repository.inspect_confirmed_ap_mapping()
        self.assertTrue(complete)
        self.assertEqual(
            set(candidates),
            {
                "vendor_master",
                "posted_invoice_history",
                "po_receiver_reference",
                "gl_distribution",
                "input_invoice",
                "input_invoice_detail",
                "input_payment_split",
            },
        )
        self.assertIn("input_invoice_detail", candidates)
        ptdt = candidates["input_invoice_detail"][0]
        self.assertEqual(ptdt["table_name"], "PTDT")
        self.assertEqual(ptdt["missing_fields"], [])
        self.assertFalse(ptdt["source_rows_read"])

    def test_vendor_name_search_is_parameterized_and_bounded(self) -> None:
        database = CapturingDatabase()
        repository = ERPEvidenceRepository(database=database)
        rows, complete = repository.search_ap_vendors("Acme", limit=500)
        self.assertEqual(rows, [])
        self.assertTrue(complete)
        sql, parameters = database.calls[0]
        self.assertIn("LOCATE(%s, UPPER(TRIM(PVNAMVEN)))", sql)
        self.assertIn("LIMIT 26", sql)
        self.assertEqual(parameters, ("ACME", "ACME", -1, "ACME"))
        self.assertNotIn("Acme", sql)

    def test_invoice_search_uses_only_controlled_predicates(self) -> None:
        database = CapturingDatabase()
        repository = ERPEvidenceRepository(database=database)
        rows, complete = repository.search_ap_posted_invoice_identities(
            vendor_numbers=[101, 202],
            invoice_number="INV-9",
            limit=500,
        )
        self.assertEqual(rows, [])
        self.assertTrue(complete)
        sql, parameters = database.calls[0]
        self.assertIn("H.PMHNBVND IN (%s, %s)", sql)
        self.assertIn("TRIM(H.PMHNBINV) = %s", sql)
        self.assertIn("LIMIT 51", sql)
        self.assertEqual(parameters, (101, 202, "INV-9"))
        self.assertNotIn("INV-9", sql)

    def test_invoice_search_rejects_unbounded_request(self) -> None:
        repository = ERPEvidenceRepository(database=CapturingDatabase())
        with self.assertRaisesRegex(ValueError, "required"):
            repository.search_ap_posted_invoice_identities(
                vendor_numbers=None,
                invoice_number=None,
                limit=50,
            )


class ERPEvidenceGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeRepository()
        self.service = ERPEvidenceService(
            repository=self.repository,
            customer_source=FakeCustomerSource(),
            ap_source=FakeAPSource(),
            clock=lambda: "2026-08-07T12:00:00+00:00",
        )

    def test_credit_contract_is_bounded_read_only_evidence(self) -> None:
        response = self.service.credit_customer(100, open_item_limit=200)
        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(response.open_ar.reconciliation_difference, 0)
        self.assertEqual(
            response.related_accounts.relationship_basis,
            "TMCUST.CUNUMENT",
        )
        self.assertEqual(response.related_accounts.partial_group_exposure, 800)
        self.assertFalse(response.governance.erp_write)
        self.assertEqual(response.governance.decision_effect, "none")
        self.assertEqual(len(response.evidence_sha256), 64)

    def test_ap_contract_excludes_sensitive_vendor_fields(self) -> None:
        response = self.service.ap_invoice("ap-invoice-" + "1" * 24)
        self.assertEqual(response.vendor_master.vendor_name, "Acme ERP")
        self.assertEqual(
            response.lookup_identity.lookup_origin,
            "local_imported_invoice",
        )
        self.assertEqual(response.posted_headers[0].invoice_amount, 125.50)
        self.assertEqual(
            response.posted_details[0].po_receiver_reference,
            "555",
        )
        self.assertFalse(response.governance.erp_write)
        self.assertEqual(response.governance.execution_effect, "none")
        self.assertEqual(len(response.evidence_sha256), 64)
        vendor_fields = set(response.vendor_master.model_dump())
        self.assertTrue(
            vendor_fields.isdisjoint({"PVACCBNK", "PVROUBNK", "PVIDFED"})
        )
        self.assertEqual(self.repository.ap_query_count, 8)

    def test_direct_erp_search_does_not_require_local_invoice(self) -> None:
        search = self.service.search_ap_invoices(
            vendor_query="Acme",
            invoice_number="INV-9",
            limit=50,
        )
        self.assertEqual(len(search.vendor_candidates), 1)
        self.assertEqual(len(search.invoice_candidates), 1)
        self.assertEqual(
            search.vendor_candidates[0].match_basis,
            ["vendor_name_contains"],
        )
        self.assertFalse(search.governance.automatic_selection)
        self.assertFalse(search.governance.erp_write)
        self.assertEqual(len(search.evidence_sha256), 64)

        response = self.service.ap_invoice_by_erp_identity(
            vendor_number=101,
            invoice_number="INV-9",
        )
        self.assertEqual(response.lookup_identity.lookup_origin, "direct_erp_search")
        self.assertIsNone(response.local_invoice)
        self.assertEqual(response.vendor_master.vendor_name, "Acme ERP")
        self.assertEqual(response.posted_headers[0].invoice_number, "INV-9")

    def test_exact_invoice_search_preserves_ambiguous_vendor_candidates(self) -> None:
        search = self.service.search_ap_invoices(
            vendor_query=None,
            invoice_number="INV-9",
            limit=50,
        )
        self.assertEqual(search.vendor_candidates, [])
        self.assertEqual(search.invoice_candidates[0].vendor_number, "101")
        self.assertFalse(search.governance.automatic_selection)

    def test_direct_search_requires_at_least_one_identity_clue(self) -> None:
        with self.assertRaisesRegex(ValueError, "Enter a vendor"):
            self.service.search_ap_invoices(
                vendor_query=None,
                invoice_number=None,
                limit=50,
            )

    def test_incomplete_ap_identity_never_triggers_broad_erp_query(self) -> None:
        repository = FakeRepository()
        service = ERPEvidenceService(
            repository=repository,
            customer_source=FakeCustomerSource(),
            ap_source=FakeAPSource(complete_identity=False),
            clock=lambda: "2026-08-07T12:00:00+00:00",
        )
        response = service.ap_invoice("ap-invoice-" + "2" * 24)
        self.assertEqual(repository.ap_query_count, 0)
        self.assertEqual(response.source_references, [])
        self.assertEqual(response.posted_headers, [])
        self.assertFalse(response.governance.erp_write)


class FakeRepositoryWithGLAccountMaster(FakeRepository):
    def get_ap_gl_distributions(self, vendor_number: int, invoice_number: str):
        self.ap_query_count += 1
        return ([{
            "sequence_number": "1",
            "payment_number": 1,
            "invoice_amount": 390.23,
            "quantity": 0,
            "description": None,
            "invoice_date": "20260827",
            "gl_division": 59,
            "gl_department": None,
            "gl_account": 5050,
            "accounting_period": 8,
            "accounting_year": 2026,
            "program_code": "E",
        }], True)

    def get_gl_account_descriptions(self, division_and_account):
        self.gl_account_lookup_calls = getattr(self, "gl_account_lookup_calls", 0) + 1
        self.gl_account_lookup_args = division_and_account
        return {("59", "5050"): "TRUCK EXPENSE - REPAIRS"}


class ERPEvidenceGLAccountDescriptionTests(unittest.TestCase):
    def test_gl_distribution_carries_chart_of_accounts_description(self) -> None:
        repository = FakeRepositoryWithGLAccountMaster()
        service = ERPEvidenceService(
            repository=repository,
            customer_source=FakeCustomerSource(),
            ap_source=FakeAPSource(),
            clock=lambda: "2026-08-07T12:00:00+00:00",
        )

        response = service.ap_invoice("ap-invoice-" + "1" * 24)

        self.assertEqual(len(response.gl_distributions), 1)
        line = response.gl_distributions[0]
        self.assertEqual(line.gl_division, "59")
        self.assertEqual(line.gl_account, "5050")
        self.assertIsNone(line.description)
        self.assertEqual(line.gl_account_description, "TRUCK EXPENSE - REPAIRS")
        self.assertEqual(repository.gl_account_lookup_args, [(59, 5050)])

    def test_missing_account_master_row_leaves_description_none_not_fabricated(
        self,
    ) -> None:
        class RepositoryWithNoMatch(FakeRepositoryWithGLAccountMaster):
            def get_gl_account_descriptions(self, division_and_account):
                return {}

        repository = RepositoryWithNoMatch()
        service = ERPEvidenceService(
            repository=repository,
            customer_source=FakeCustomerSource(),
            ap_source=FakeAPSource(),
            clock=lambda: "2026-08-07T12:00:00+00:00",
        )

        response = service.ap_invoice("ap-invoice-" + "1" * 24)

        self.assertIsNone(response.gl_distributions[0].gl_account_description)

    def test_missing_lookup_method_degrades_gracefully(self) -> None:
        # A repository double that doesn't implement the new method at all
        # (e.g. an older/unrelated fake) must not break GL distribution
        # evidence - the description is simply unavailable.
        class RepositoryWithoutLookup(FakeRepository):
            def get_ap_gl_distributions(self, vendor_number: int, invoice_number: str):
                self.ap_query_count += 1
                return ([{
                    "sequence_number": "1",
                    "payment_number": 1,
                    "invoice_amount": 100.0,
                    "quantity": 1,
                    "description": None,
                    "invoice_date": "20260827",
                    "gl_division": 59,
                    "gl_department": None,
                    "gl_account": 9999,
                    "accounting_period": 8,
                    "accounting_year": 2026,
                    "program_code": "E",
                }], True)

        repository = RepositoryWithoutLookup()
        service = ERPEvidenceService(
            repository=repository,
            customer_source=FakeCustomerSource(),
            ap_source=FakeAPSource(),
            clock=lambda: "2026-08-07T12:00:00+00:00",
        )

        response = service.ap_invoice("ap-invoice-" + "1" * 24)

        self.assertIsNone(response.gl_distributions[0].gl_account_description)


class ERPEvidencePoReceivingMatchTests(unittest.TestCase):
    def test_no_po_reference_is_not_applicable_not_an_error(self) -> None:
        # FakeRepository's default get_po_receiving_match returns no rows,
        # matching the real query's behavior when every invoice line has
        # PMDNBPORV = 0 (the overwhelming majority of AP activity).
        repository = FakeRepository()
        service = ERPEvidenceService(
            repository=repository,
            customer_source=FakeCustomerSource(),
            ap_source=FakeAPSource(),
            clock=lambda: "2026-08-07T12:00:00+00:00",
        )

        response = service.ap_invoice("ap-invoice-" + "1" * 24)

        self.assertEqual(response.po_receiving_match, [])
        self.assertEqual(
            response.po_receiving_match_collection.status, "not_applicable"
        )
        self.assertTrue(response.po_receiving_match_collection.complete)
        three_way_match = next(
            item for item in response.coverage if item.key == "three_way_match"
        )
        self.assertEqual(three_way_match.status, "not_applicable")

    def test_po_referenced_line_computes_quantity_variance(self) -> None:
        class RepositoryWithPoMatch(FakeRepository):
            def get_po_receiving_match(
                self, vendor_number: int, invoice_number: str
            ):
                self.ap_query_count += 1
                return ([{
                    "sequence_number": 1,
                    "po_receiver_reference": 774859,
                    "product_number": "C174007001",
                    "po_number": 770000528,
                    "quantity_received_this_receipt": "6",
                    "receipt_date": "20260810",
                    "po_complete_flag": "Y",
                    "po_date": "20260801",
                    "quantity_ordered": "6",
                    "quantity_received_total": "6",
                    "quantity_backorder": "0",
                    "quantity_invoiced": "5",
                    "line_amount": "624.45",
                }], True)

        repository = RepositoryWithPoMatch()
        service = ERPEvidenceService(
            repository=repository,
            customer_source=FakeCustomerSource(),
            ap_source=FakeAPSource(),
            clock=lambda: "2026-08-07T12:00:00+00:00",
        )

        response = service.ap_invoice("ap-invoice-" + "1" * 24)

        self.assertEqual(len(response.po_receiving_match), 1)
        match = response.po_receiving_match[0]
        self.assertEqual(match.po_number, "770000528")
        self.assertEqual(match.quantity_ordered, 6)
        self.assertEqual(match.quantity_invoiced, 5)
        # 6 received on this receipt vs. 5 invoiced - a real, disclosed variance.
        self.assertEqual(match.quantity_variance, 1)
        self.assertEqual(
            response.po_receiving_match_collection.status, "available"
        )


class ERPEvidenceGLCodingSuggestionsTests(unittest.TestCase):
    def test_known_structural_accounts_excluded_even_below_the_total(self) -> None:
        # Confirmed live against real vendors: control/clearing accounts
        # (1017 cash, 2300 AP control, 1230 AR-vendor clearing) rarely hit
        # exactly 100% of a vendor's invoices even though they are not a
        # real coding choice - an equals-the-total check alone would have
        # let 2300 (9 of 10) through here.
        class RepositoryWithCodingHistory(FakeRepository):
            def get_latest_gl_coding_year(self, vendor_number: int):
                return 2026

            def get_vendor_coded_invoice_count(self, vendor_number: int, *, year: int) -> int:
                return 10

            def get_gl_coding_account_totals(self, vendor_number: int, *, year: int):
                return [
                    {"gl_division": 1, "gl_account": 1017, "invoice_count": 10},
                    {"gl_division": 1, "gl_account": 2300, "invoice_count": 9},
                    {"gl_division": 1, "gl_account": 4055, "invoice_count": 8},
                    {"gl_division": 1, "gl_account": 1230, "invoice_count": 7},
                    {"gl_division": 1, "gl_account": 5050, "invoice_count": 6},
                    {"gl_division": 1, "gl_account": 6000, "invoice_count": 3},
                    {"gl_division": 1, "gl_account": 7000, "invoice_count": 1},
                ]

            def get_gl_coding_department_breakdown(
                self, vendor_number: int, division_and_account
            ):
                return {(str(d), str(a)): "0" for d, a in division_and_account}

            def get_gl_account_descriptions(self, division_and_account):
                return {("1", "5050"): "TRUCK EXPENSE - REPAIRS"}

        repository = RepositoryWithCodingHistory()
        service = ERPEvidenceService(
            repository=repository,
            customer_source=FakeCustomerSource(),
            ap_source=FakeAPSource(),
            clock=lambda: "2026-08-07T12:00:00+00:00",
        )

        response = service.gl_coding_suggestions(102, limit=3)

        self.assertEqual(response.coded_year, 2026)
        self.assertEqual(response.total_coded_invoice_count, 10)
        self.assertEqual(
            sorted(response.excluded_structural_accounts),
            sorted([
                "Division 1 Account 1017",
                "Division 1 Account 2300",
                "Division 1 Account 4055",
                "Division 1 Account 1230",
            ]),
        )
        self.assertEqual(len(response.suggestions), 3)
        first = response.suggestions[0]
        self.assertEqual(first.gl_account, "5050")
        self.assertEqual(first.match_percent, 60.0)
        self.assertEqual(first.gl_account_description, "TRUCK EXPENSE - REPAIRS")
        self.assertEqual(response.suggestions[1].match_percent, 30.0)
        self.assertEqual(response.suggestions[2].match_percent, 10.0)
        self.assertFalse(response.governance.erp_write)

    def test_vendor_with_no_coding_history_returns_empty_shortlist(self) -> None:
        repository = FakeRepository()
        # FakeRepository has no get_latest_gl_coding_year method - the
        # service must degrade to zero/None, not raise.
        service = ERPEvidenceService(
            repository=repository,
            customer_source=FakeCustomerSource(),
            ap_source=FakeAPSource(),
            clock=lambda: "2026-08-07T12:00:00+00:00",
        )

        response = service.gl_coding_suggestions(999, limit=3)

        self.assertIsNone(response.coded_year)
        self.assertEqual(response.total_coded_invoice_count, 0)
        self.assertEqual(response.suggestions, [])
        self.assertEqual(response.excluded_structural_accounts, [])


if __name__ == "__main__":
    unittest.main()
