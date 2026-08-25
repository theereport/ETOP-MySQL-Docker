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
        self.assertEqual(self.repository.ap_query_count, 7)

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


if __name__ == "__main__":
    unittest.main()
