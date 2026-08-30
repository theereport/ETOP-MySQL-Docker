from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from modules.accounts_payable.erp_ledger_repository import (
    AccountsPayableErpLedgerRepository,
    parse_madden_date,
)
from modules.accounts_payable.repository import AccountsPayableRepository
from modules.accounts_payable.service import AccountsPayableService


def _ledger_row(
    *,
    vendor: str,
    invoice: str,
    due: str,
    invoice_date: str = "20260801",
    amount: float,
    discount: float = 0.0,
    on_hold: str = "",
) -> dict:
    return {
        "PMHNBVND": vendor,
        "PMHNBINV": invoice,
        "PMHDTEINV": invoice_date,
        "PMHDTEDUE": due,
        "PMHAMTINV": amount,
        "PMHAMTDIS": discount,
        "PMHFLGHLD": on_hold,
    }


class ParseMaddenDateTest(unittest.TestCase):
    def test_parses_valid_yyyymmdd(self) -> None:
        self.assertEqual(parse_madden_date("20260830"), date(2026, 8, 30))

    def test_none_for_zero_date(self) -> None:
        self.assertIsNone(parse_madden_date("00000000"))

    def test_none_for_malformed_or_missing(self) -> None:
        self.assertIsNone(parse_madden_date(None))
        self.assertIsNone(parse_madden_date(""))
        self.assertIsNone(parse_madden_date("not-a-date"))


class AccountsPayableErpLedgerRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_path = Path(self.temp.name) / "ap-erp-ledger.db"
        self.repository = AccountsPayableErpLedgerRepository(
            self._connection_factory
        )

    def _connection_factory(self) -> sqlite3.Connection:
        return sqlite3.connect(
            self.database_path, timeout=30, check_same_thread=False
        )

    def test_replace_open_ledger_skips_rows_without_usable_identity(self) -> None:
        count = self.repository.replace_open_ledger(
            [
                _ledger_row(vendor="0", invoice="BAD", due="20260830", amount=1),
                _ledger_row(vendor="12345", invoice="", due="20260830", amount=1),
                _ledger_row(vendor="12345", invoice="INV001", due="20260830", amount=100),
            ]
        )

        self.assertEqual(count, 1)

    def test_open_ledger_summary_before_refresh_reports_no_data(self) -> None:
        summary = self.repository.open_ledger_summary(date(2026, 8, 30))

        self.assertIsNone(summary["refreshed_at"])
        self.assertEqual(summary["total_count"], 0)

    def test_open_ledger_summary_buckets_by_due_date_and_hold_status(self) -> None:
        self.repository.replace_open_ledger(
            [
                _ledger_row(
                    vendor="12345", invoice="INV001", due="20260830", amount=100
                ),  # due today
                _ledger_row(
                    vendor="12345", invoice="INV002", due="20260825",
                    amount=50, discount=5, on_hold="Y",
                ),  # past due but on hold
                _ledger_row(
                    vendor="12345", invoice="INV003", due="20260820", amount=200
                ),  # genuinely past due
                _ledger_row(
                    vendor="12345", invoice="INV004", due="20260902", amount=30
                ),  # due within 7 days
                _ledger_row(
                    vendor="12345", invoice="INV005", due="00000000", amount=20
                ),  # unparseable due date
            ]
        )

        summary = self.repository.open_ledger_summary(date(2026, 8, 30))

        self.assertIsNotNone(summary["refreshed_at"])
        self.assertEqual(summary["total_count"], 5)
        self.assertAlmostEqual(summary["total_balance"], 395.0)
        self.assertEqual(summary["on_hold_count"], 1)
        self.assertAlmostEqual(summary["on_hold_amount"], 45.0)
        self.assertEqual(summary["due_today_count"], 1)
        self.assertAlmostEqual(summary["due_today_amount"], 100.0)
        self.assertEqual(summary["past_due_count"], 1)
        self.assertAlmostEqual(summary["past_due_amount"], 200.0)
        self.assertAlmostEqual(summary["due_within_7_days_amount"], 130.0)

    def test_replace_open_ledger_aggregates_multiple_payment_split_rows(
        self,
    ) -> None:
        # PMHD's real key is (vendor, invoice, payment_number) - an invoice
        # can have multiple payment-split rows. This must not collide on
        # the (vendor, invoice) cache key; it must aggregate instead.
        count = self.repository.replace_open_ledger(
            [
                _ledger_row(
                    vendor="12345", invoice="INV001", due="20260905",
                    amount=60, discount=1, on_hold="",
                ),
                _ledger_row(
                    vendor="12345", invoice="INV001", due="20260830",
                    amount=40, discount=0, on_hold="Y",
                ),
            ]
        )

        self.assertEqual(count, 1)
        summary = self.repository.open_ledger_summary(date(2026, 8, 30))
        self.assertEqual(summary["total_count"], 1)
        self.assertAlmostEqual(summary["total_balance"], 99.0)  # (60-1)+(40-0)
        self.assertEqual(summary["on_hold_count"], 1)  # any split on hold

    def test_replace_open_ledger_is_wholesale_not_additive(self) -> None:
        self.repository.replace_open_ledger(
            [_ledger_row(vendor="1", invoice="A", due="20260830", amount=10)]
        )
        self.repository.replace_open_ledger(
            [_ledger_row(vendor="1", invoice="B", due="20260830", amount=20)]
        )

        summary = self.repository.open_ledger_summary(date(2026, 8, 30))

        self.assertEqual(summary["total_count"], 1)
        self.assertAlmostEqual(summary["total_balance"], 20.0)

    def test_replace_vendor_terms_cache_skips_invalid_vendor_numbers(self) -> None:
        count = self.repository.replace_vendor_terms_cache(
            [
                {"PVNUMVEN": "0", "PVCODTREM": "001"},
                {"PVNUMVEN": "12345", "PVCODTREM": "004"},
            ]
        )

        self.assertEqual(count, 1)


class AccountsPayableTermsReferenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_path = Path(self.temp.name) / "ap-terms.db"
        self.repository = AccountsPayableErpLedgerRepository(
            self._connection_factory
        )

    def _connection_factory(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _flat_days_terms(
        self, terms_code: str = "11", *, num_days: int = 10, discount_percent: float = 20
    ) -> None:
        self.repository.upsert_vendor_terms_reference(
            terms_code=terms_code,
            discount_percent=discount_percent,
            num_periods=None,
            num_months=None,
            num_days=num_days,
            second_period=None,
            third_period=None,
            next_period=None,
            day_of_month=None,
            cutoff_day=None,
            description="2% 10 days",
        )

    def _proximo_terms(self, terms_code: str = "4") -> None:
        # Mirrors real terms code 4: "FORD 2% Discount 15th" - discount_percent
        # > 0 but no flat num_days, relies on day_of_month/cutoff_day instead.
        self.repository.upsert_vendor_terms_reference(
            terms_code=terms_code,
            discount_percent=20,
            num_periods=3,
            num_months=1,
            num_days=None,
            second_period=None,
            third_period=None,
            next_period=None,
            day_of_month=15,
            cutoff_day=25,
            description="FORD 2% Discount 15th",
        )

    def test_upsert_is_insert_then_update(self) -> None:
        self._flat_days_terms(discount_percent=20)
        self._flat_days_terms(discount_percent=25)  # same code, new value

        items = self.repository.list_vendor_terms_reference()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["discount_percent"], 25)

    def test_discount_eligibility_unavailable_without_reference_data(self) -> None:
        summary = self.repository.discount_eligibility_summary(date(2026, 8, 30))

        self.assertFalse(summary["has_reference_data"])

    def test_flat_days_invoice_inside_window_is_eligible(self) -> None:
        self._flat_days_terms(num_days=10, discount_percent=20)
        self.repository.replace_open_ledger(
            [
                _ledger_row(
                    vendor="12345", invoice="INV001", due="20260910",
                    invoice_date="20260825", amount=100,
                )
            ]
        )
        self.repository.replace_vendor_terms_cache(
            [{"PVNUMVEN": "12345", "PVCODTREM": "11"}]
        )

        summary = self.repository.discount_eligibility_summary(date(2026, 8, 30))

        self.assertEqual(summary["eligible_count"], 1)
        self.assertAlmostEqual(summary["eligible_amount"], 20.0)  # 100 * 20%
        self.assertEqual(summary["excluded_codes"], [])

    def test_flat_days_invoice_past_window_is_not_eligible(self) -> None:
        self._flat_days_terms(num_days=10, discount_percent=20)
        self.repository.replace_open_ledger(
            [
                _ledger_row(
                    vendor="12345", invoice="INV001", due="20260910",
                    invoice_date="20260801", amount=100,  # window closed 8/11
                )
            ]
        )
        self.repository.replace_vendor_terms_cache(
            [{"PVNUMVEN": "12345", "PVCODTREM": "11"}]
        )

        summary = self.repository.discount_eligibility_summary(date(2026, 8, 30))

        self.assertEqual(summary["eligible_count"], 0)
        self.assertAlmostEqual(summary["eligible_amount"], 0.0)

    def test_on_hold_invoice_is_never_eligible(self) -> None:
        self._flat_days_terms(num_days=30, discount_percent=20)
        self.repository.replace_open_ledger(
            [
                _ledger_row(
                    vendor="12345", invoice="INV001", due="20260910",
                    invoice_date="20260825", amount=100, on_hold="Y",
                )
            ]
        )
        self.repository.replace_vendor_terms_cache(
            [{"PVNUMVEN": "12345", "PVCODTREM": "11"}]
        )

        summary = self.repository.discount_eligibility_summary(date(2026, 8, 30))

        self.assertEqual(summary["eligible_count"], 0)

    def test_proximo_terms_code_is_excluded_not_zeroed(self) -> None:
        self._proximo_terms(terms_code="4")
        self.repository.replace_open_ledger(
            [
                _ledger_row(
                    vendor="12345", invoice="INV001", due="20260910",
                    invoice_date="20260825", amount=100,
                )
            ]
        )
        self.repository.replace_vendor_terms_cache(
            [{"PVNUMVEN": "12345", "PVCODTREM": "4"}]
        )

        summary = self.repository.discount_eligibility_summary(date(2026, 8, 30))

        self.assertEqual(summary["eligible_count"], 0)
        self.assertEqual(summary["eligible_amount"], 0)
        self.assertEqual(len(summary["excluded_codes"]), 1)
        self.assertEqual(summary["excluded_codes"][0]["terms_code"], "4")

    def test_non_discount_terms_code_is_ignored_not_excluded(self) -> None:
        self.repository.upsert_vendor_terms_reference(
            terms_code="1",
            discount_percent=0,
            num_periods=0,
            num_months=0,
            num_days=10,
            second_period=None,
            third_period=None,
            next_period=None,
            day_of_month=None,
            cutoff_day=None,
            description="DUE IN 10 DAYS",
        )
        self.repository.replace_open_ledger(
            [
                _ledger_row(
                    vendor="12345", invoice="INV001", due="20260910",
                    invoice_date="20260825", amount=100,
                )
            ]
        )
        self.repository.replace_vendor_terms_cache(
            [{"PVNUMVEN": "12345", "PVCODTREM": "1"}]
        )

        summary = self.repository.discount_eligibility_summary(date(2026, 8, 30))

        self.assertEqual(summary["eligible_count"], 0)
        self.assertEqual(summary["excluded_codes"], [])


class AccountsPayableServiceErpLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_path = Path(self.temp.name) / "ap-service.db"

        def connection_factory() -> sqlite3.Connection:
            return sqlite3.connect(
                self.database_path, timeout=30, check_same_thread=False
            )

        self.ap_repository = AccountsPayableRepository(connection_factory)
        self.erp_ledger_repository = AccountsPayableErpLedgerRepository(
            connection_factory
        )
        self.job_events: list[tuple] = []
        self.ledger_rows: list[dict] = []
        self.terms_rows: list[dict] = []
        self.division_rows: list[dict] = []
        self.division_scan_calls: list[tuple] = []
        self.service = AccountsPayableService(
            repository=self.ap_repository,
            clock=lambda: datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
            id_factory=lambda: "sync-erp-ledger",
            warehouse_action_id_factory=lambda: "warehouse-action-1",
            erp_ledger_repository=self.erp_ledger_repository,
            open_ledger_scan=lambda: self.ledger_rows,
            vendor_terms_scan=lambda: self.terms_rows,
            gl_division_scan=self._gl_division_scan,
            on_ledger_job_started=lambda job_id: self.job_events.append(
                ("started", job_id)
            ),
            on_ledger_job_complete=lambda job_id, result, error: (
                self.job_events.append(("complete", job_id, result, error))
            ),
        )

    def _gl_division_scan(
        self, vendor_numbers: list[str], years: list[int]
    ) -> list[dict]:
        self.division_scan_calls.append((vendor_numbers, years))
        return self.division_rows

    def test_overview_shows_unavailable_ledger_metrics_before_any_refresh(
        self,
    ) -> None:
        overview = self.service.overview()

        self.assertEqual(overview.metrics.current_ap_balance.status, "unavailable")
        self.assertEqual(overview.metrics.past_due_count.status, "unavailable")

    def test_synchronous_refresh_populates_real_metrics(self) -> None:
        self.ledger_rows = [
            _ledger_row(vendor="12345", invoice="INV001", due="20260830", amount=100)
        ]

        result = self.service.refresh_erp_ledger(background=False)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.job_events[0], ("started", result["job_id"]))
        self.assertEqual(self.job_events[1][0], "complete")
        self.assertIsNone(self.job_events[1][3])  # no error

        overview = self.service.overview()
        self.assertEqual(overview.metrics.current_ap_balance.status, "available")
        self.assertEqual(overview.metrics.current_ap_balance.value, 100.0)
        self.assertEqual(
            overview.metrics.current_ap_balance.source,
            "accounts_payable.erp_open_ledger_cache",
        )

    def test_background_refresh_reports_completion_via_job_hooks(self) -> None:
        self.ledger_rows = [
            _ledger_row(vendor="12345", invoice="INV001", due="20260830", amount=50)
        ]

        result = self.service.refresh_erp_ledger(background=True)
        self.service._erp_ledger_executor.shutdown(wait=True)

        self.assertEqual(result["status"], "queued")
        self.assertEqual(self.job_events[0], ("started", result["job_id"]))
        self.assertEqual(self.job_events[1][0], "complete")
        self.assertIsNone(self.job_events[1][3])

    def test_scan_failure_is_reported_not_raised_in_background(self) -> None:
        def failing_scan() -> list[dict]:
            raise RuntimeError("MaddenCo connection refused")

        self.service._open_ledger_scan = failing_scan

        result = self.service.refresh_erp_ledger(background=True)
        self.service._erp_ledger_executor.shutdown(wait=True)

        self.assertEqual(result["status"], "queued")
        complete_event = self.job_events[1]
        self.assertEqual(complete_event[0], "complete")
        self.assertIsNone(complete_event[2])  # no result
        self.assertIsInstance(complete_event[3], RuntimeError)

    def test_scan_failure_raises_when_run_synchronously(self) -> None:
        def failing_scan() -> list[dict]:
            raise RuntimeError("MaddenCo connection refused")

        self.service._open_ledger_scan = failing_scan

        with self.assertRaises(RuntimeError):
            self.service.refresh_erp_ledger(background=False)

    def test_discounts_available_metric_unavailable_before_refresh(self) -> None:
        metric = self.service.overview().metrics.discounts_available

        self.assertEqual(metric.status, "unavailable")
        self.assertIsNone(metric.value)

    def test_discounts_available_metric_unavailable_without_terms_reference(
        self,
    ) -> None:
        self.ledger_rows = [
            _ledger_row(vendor="12345", invoice="INV001", due="20260910", amount=100)
        ]
        self.service.refresh_erp_ledger(background=False)

        metric = self.service.overview().metrics.discounts_available

        self.assertEqual(metric.status, "unavailable")
        self.assertIn("terms reference", metric.explanation)

    def test_discounts_available_metric_reports_real_eligible_amount(self) -> None:
        self.ledger_rows = [
            _ledger_row(
                vendor="12345", invoice="INV001", due="20260910",
                invoice_date="20260825", amount=100,
            )
        ]
        self.terms_rows = [{"PVNUMVEN": "12345", "PVCODTREM": "11"}]
        self.service.refresh_erp_ledger(background=False)
        self.erp_ledger_repository.upsert_vendor_terms_reference(
            terms_code="11",
            discount_percent=20,
            num_periods=None,
            num_months=None,
            num_days=10,
            second_period=None,
            third_period=None,
            next_period=None,
            day_of_month=None,
            cutoff_day=None,
            description="2% 10 days",
        )

        metric = self.service.overview().metrics.discounts_available

        self.assertEqual(metric.status, "available")
        self.assertEqual(metric.value, 20.0)


class AccountsPayableWarehouseApprovalRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_path = Path(self.temp.name) / "ap-warehouse.db"
        self.repository = AccountsPayableErpLedgerRepository(
            self._connection_factory
        )
        # The warehouse queue's linkage LEFT JOIN reads accounts_payable's
        # own ap_invoices table, which only exists once that repository has
        # initialized it too - both are always initialized together at
        # startup in data/database.py.
        AccountsPayableRepository(self._connection_factory).initialize()

    def _connection_factory(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path, timeout=30, check_same_thread=False
        )
        connection.row_factory = sqlite3.Row
        return connection

    def _seed_open_invoices(self, rows: list[dict]) -> None:
        self.repository.replace_open_ledger(
            [
                _ledger_row(
                    vendor=row["vendor"],
                    invoice=row["invoice"],
                    due=row.get("due", "20260910"),
                    amount=row.get("amount", 100),
                )
                for row in rows
            ]
        )
        gl_fields = {
            (row["vendor"], row["invoice"]): (
                row["division"], row.get("account"), row.get("department"),
            )
            for row in rows
            if row.get("division") is not None
        }
        if gl_fields:
            self.repository.update_open_ledger_gl_fields(gl_fields)

    def _record_action(
        self,
        *,
        action_id: str,
        vendor: str = "6245",
        invoice: str = "INV001",
        to_status: str,
        actor: str = "jdoe",
        created_at: str = "2026-08-30T00:00:00+00:00",
    ) -> dict:
        return self.repository.record_warehouse_approval_action(
            action_id=action_id,
            vendor_number=vendor,
            invoice_number=invoice,
            to_status=to_status,
            actor_identity=actor,
            actor_identity_source="operator_supplied",
            notes="",
            created_at=created_at,
        )

    def test_actions_table_rejects_update(self) -> None:
        self._seed_open_invoices([{"vendor": "6245", "invoice": "INV001"}])
        self._record_action(action_id="a1", to_status="approved_by_warehouse")

        connection = self._connection_factory()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE ap_warehouse_approval_actions "
                    "SET notes = 'x' WHERE action_id = 'a1';"
                )
        finally:
            connection.close()

    def test_actions_table_rejects_delete(self) -> None:
        self._seed_open_invoices([{"vendor": "6245", "invoice": "INV001"}])
        self._record_action(action_id="a1", to_status="approved_by_warehouse")

        connection = self._connection_factory()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM ap_warehouse_approval_actions "
                    "WHERE action_id = 'a1';"
                )
        finally:
            connection.close()

    def test_status_defaults_to_needs_approval_with_no_actions(self) -> None:
        self._seed_open_invoices([{"vendor": "6245", "invoice": "INV001"}])

        result = self.repository.warehouse_approval_queue(None)

        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["status"], "needs_approval")
        self.assertIsNone(result["items"][0]["last_actor_identity"])
        self.assertIsNone(result["items"][0]["vendor_name"])

    def test_queue_includes_the_cached_vendor_name(self) -> None:
        self._seed_open_invoices([{"vendor": "6245", "invoice": "INV001"}])
        self.repository.replace_vendor_terms_cache(
            [{"PVNUMVEN": "6245", "PVCODTREM": "11", "PVNAMVEN": "JINKS MOBILE REPAIR"}]
        )

        result = self.repository.warehouse_approval_queue(None)

        self.assertEqual(result["items"][0]["vendor_name"], "JINKS MOBILE REPAIR")

    def test_status_derives_from_the_latest_action(self) -> None:
        self._seed_open_invoices([{"vendor": "6245", "invoice": "INV001"}])
        self._record_action(
            action_id="a1",
            to_status="approved_by_warehouse",
            actor="jdoe",
            created_at="2026-08-30T00:00:00+00:00",
        )
        self._record_action(
            action_id="a2",
            to_status="approved_and_entered_by_ap",
            actor="asmith",
            created_at="2026-08-30T01:00:00+00:00",
        )

        result = self.repository.warehouse_approval_queue(None)

        self.assertEqual(
            result["items"][0]["status"], "approved_and_entered_by_ap"
        )
        self.assertEqual(result["items"][0]["last_actor_identity"], "asmith")

    def test_from_status_reflects_the_prior_derived_status(self) -> None:
        self._seed_open_invoices([{"vendor": "6245", "invoice": "INV001"}])

        first = self._record_action(
            action_id="a1", to_status="approved_by_warehouse"
        )
        self.assertEqual(first["from_status"], "needs_approval")

        second = self._record_action(
            action_id="a2",
            to_status="approved_and_entered_by_ap",
            created_at="2026-08-30T01:00:00+00:00",
        )
        self.assertEqual(second["from_status"], "approved_by_warehouse")

    def test_division_filter_scopes_the_queue(self) -> None:
        self._seed_open_invoices(
            [
                {"vendor": "1", "invoice": "A", "division": "59"},
                {"vendor": "2", "invoice": "B", "division": "12"},
            ]
        )

        result = self.repository.warehouse_approval_queue("59")

        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["vendor_number"], "1")
        self.assertEqual(
            sorted(result["available_divisions"]), ["12", "59"]
        )

    def test_update_open_ledger_gl_fields_never_inserts_new_rows(self) -> None:
        # An invoice must already be cached as open (unpaid) for its GL
        # detail to matter here - this must not create a phantom row.
        updated = self.repository.update_open_ledger_gl_fields(
            {("9999", "GHOST"): ("59", "5050", "0")}
        )

        self.assertEqual(updated, 0)
        result = self.repository.warehouse_approval_queue(None)
        self.assertEqual(result["items"], [])


class AccountsPayableWarehouseApprovalLinkageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_path = Path(self.temp.name) / "ap-warehouse-linkage.db"
        self.erp_repository = AccountsPayableErpLedgerRepository(
            self._connection_factory
        )
        self.ap_repository = AccountsPayableRepository(self._connection_factory)
        self.ap_repository.initialize()

    def _connection_factory(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path, timeout=30, check_same_thread=False
        )
        connection.row_factory = sqlite3.Row
        return connection

    def _insert_ap_invoice(
        self, ap_invoice_id: str, vendor_number: str, invoice_number: str
    ) -> None:
        connection = self._connection_factory()
        try:
            connection.execute(
                """
                INSERT INTO ap_invoices (
                    ap_invoice_id, source_key, document_job_id,
                    document_result_id, source_file_name, document_type,
                    document_status, classification_evidence_json,
                    vendor_number, vendor_name, normalized_vendor_identity,
                    invoice_number, normalized_invoice_number,
                    field_evidence_json, exceptions_json, warnings_json,
                    base_review_required, ocr_review_required,
                    source_as_of, source_evidence_sha256, imported_at,
                    last_synced_at
                ) VALUES (
                    ?, ?, 'job-1', 'result-1', 'file.pdf', 'vendor_invoice',
                    'evidence_available', '{}', ?, 'Vendor Name', ?,
                    ?, ?, '{}', '[]', '[]', 0, 0,
                    '2026-08-30T00:00:00+00:00', ?,
                    '2026-08-30T00:00:00+00:00', '2026-08-30T00:00:00+00:00'
                );
                """,
                (
                    ap_invoice_id,
                    ap_invoice_id,
                    vendor_number,
                    f"number:{vendor_number}",
                    invoice_number,
                    invoice_number.upper(),
                    "0" * 64,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def test_open_invoice_links_to_a_matching_ap_invoice(self) -> None:
        self.erp_repository.replace_open_ledger(
            [_ledger_row(vendor="6245", invoice="INV001", due="20260910", amount=100)]
        )
        self._insert_ap_invoice("ap-invoice-abc123", "6245", "INV001")

        result = self.erp_repository.warehouse_approval_queue(None)

        self.assertEqual(
            result["items"][0]["linked_ap_invoice_id"], "ap-invoice-abc123"
        )

    def test_open_invoice_without_a_match_has_no_link(self) -> None:
        self.erp_repository.replace_open_ledger(
            [_ledger_row(vendor="6245", invoice="INV002", due="20260910", amount=100)]
        )

        result = self.erp_repository.warehouse_approval_queue(None)

        self.assertIsNone(result["items"][0]["linked_ap_invoice_id"])


class AccountsPayableServiceWarehouseApprovalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_path = Path(self.temp.name) / "ap-warehouse-service.db"

        def connection_factory() -> sqlite3.Connection:
            return sqlite3.connect(
                self.database_path, timeout=30, check_same_thread=False
            )

        self.ap_repository = AccountsPayableRepository(connection_factory)
        self.ap_repository.initialize()
        self.erp_ledger_repository = AccountsPayableErpLedgerRepository(
            connection_factory
        )
        self.ledger_rows: list[dict] = []
        self.terms_rows: list[dict] = []
        self.division_rows: list[dict] = []
        self.division_scan_calls: list[tuple] = []
        self.service = AccountsPayableService(
            repository=self.ap_repository,
            clock=lambda: datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
            erp_ledger_repository=self.erp_ledger_repository,
            open_ledger_scan=lambda: self.ledger_rows,
            vendor_terms_scan=lambda: self.terms_rows,
            gl_division_scan=self._gl_division_scan,
            on_ledger_job_started=lambda job_id: None,
            on_ledger_job_complete=lambda job_id, result, error: None,
            warehouse_action_id_factory=lambda: "warehouse-action-1",
        )

    def _gl_division_scan(
        self, vendor_numbers: list[str], years: list[int]
    ) -> list[dict]:
        self.division_scan_calls.append((vendor_numbers, years))
        return self.division_rows

    def test_refresh_scopes_the_division_scan_to_open_vendors_and_years(
        self,
    ) -> None:
        self.ledger_rows = [
            _ledger_row(
                vendor="6245", invoice="INV001", due="20260910",
                invoice_date="20260501", amount=100,
            )
        ]

        self.service.refresh_erp_ledger(background=False)

        self.assertEqual(len(self.division_scan_calls), 1)
        vendor_numbers, years = self.division_scan_calls[0]
        self.assertEqual(vendor_numbers, ["6245"])
        self.assertEqual(years, [2026])

    def test_refresh_picks_the_largest_amount_line_and_excludes_paid_invoices(
        self,
    ) -> None:
        self.ledger_rows = [
            _ledger_row(
                vendor="6245", invoice="INV001", due="20260910",
                invoice_date="20260501", amount=100,
            )
        ]
        self.division_rows = [
            {"PMGNBVND": "6245", "PMGNBINV": "INV001", "PMGNBGLDV": "12", "PMGNBGLDP": "1", "PMGNBGL": "1000", "PMGAMTINV": 10},
            # PMGNBGLDP arrives as a NOT NULL decimal column - Decimal(0)
            # is a real department code, not a missing one, and is falsy
            # in Python (unlike the string "0"), so this exercises that
            # distinction directly.
            {"PMGNBVND": "6245", "PMGNBINV": "INV001", "PMGNBGLDV": "59", "PMGNBGLDP": Decimal("0"), "PMGNBGL": "5050", "PMGAMTINV": 90},
            # Same vendor's other GL activity in the scoped year, for an
            # already-paid invoice - must never receive GL detail here.
            {"PMGNBVND": "6245", "PMGNBINV": "INV999", "PMGNBGLDV": "99", "PMGNBGLDP": "0", "PMGNBGL": "9999", "PMGAMTINV": 999},
        ]

        result = self.service.refresh_erp_ledger(background=False)

        self.assertEqual(result["divisions_populated"], 1)
        queue = self.service.warehouse_approval_queue(None)
        self.assertEqual(queue.needs_approval[0].gl_division, "59")
        self.assertEqual(queue.needs_approval[0].gl_account, "5050")
        self.assertEqual(queue.needs_approval[0].gl_department, "0")
        self.assertEqual(queue.available_divisions, ["59"])

    def test_queue_defaults_new_invoices_to_needs_approval(self) -> None:
        self.ledger_rows = [
            _ledger_row(vendor="6245", invoice="INV001", due="20260910", amount=100)
        ]
        self.service.refresh_erp_ledger(background=False)

        queue = self.service.warehouse_approval_queue(None)

        self.assertEqual(len(queue.needs_approval), 1)
        self.assertEqual(queue.needs_approval[0].vendor_number, "6245")
        self.assertEqual(queue.needs_approval[0].status, "needs_approval")
        self.assertEqual(queue.approved_by_warehouse, [])
        self.assertEqual(queue.approved_and_entered_by_ap, [])

    def test_queue_items_carry_the_cached_vendor_name(self) -> None:
        self.ledger_rows = [
            _ledger_row(vendor="6245", invoice="INV001", due="20260910", amount=100)
        ]
        self.terms_rows = [
            {"PVNUMVEN": "6245", "PVCODTREM": "11", "PVNAMVEN": "JINKS MOBILE REPAIR"}
        ]
        self.service.refresh_erp_ledger(background=False)

        queue = self.service.warehouse_approval_queue(None)

        self.assertEqual(queue.needs_approval[0].vendor_name, "JINKS MOBILE REPAIR")

    def test_recording_an_action_moves_the_bucket(self) -> None:
        self.ledger_rows = [
            _ledger_row(vendor="6245", invoice="INV001", due="20260910", amount=100)
        ]
        self.service.refresh_erp_ledger(background=False)

        record = self.service.record_warehouse_approval_action(
            vendor_number="6245",
            invoice_number="INV001",
            to_status="approved_by_warehouse",
            actor_identity="jdoe",
            notes="looks fine",
        )

        self.assertEqual(record.from_status, "needs_approval")
        self.assertEqual(record.to_status, "approved_by_warehouse")
        self.assertEqual(record.actor_identity_source, "operator_supplied")
        queue = self.service.warehouse_approval_queue(None)
        self.assertEqual(queue.needs_approval, [])
        self.assertEqual(len(queue.approved_by_warehouse), 1)

    def test_invoice_leaves_the_queue_once_no_longer_open(self) -> None:
        self.ledger_rows = [
            _ledger_row(vendor="6245", invoice="INV001", due="20260910", amount=100)
        ]
        self.service.refresh_erp_ledger(background=False)
        self.service.record_warehouse_approval_action(
            vendor_number="6245",
            invoice_number="INV001",
            to_status="approved_by_warehouse",
            actor_identity="jdoe",
            notes="",
        )

        # MaddenCo now shows the invoice paid - it drops out of the next
        # open-ledger scan, same as the dashboard's own cache.
        self.ledger_rows = []
        self.service.refresh_erp_ledger(background=False)

        queue = self.service.warehouse_approval_queue(None)
        self.assertEqual(queue.needs_approval, [])
        self.assertEqual(queue.approved_by_warehouse, [])
        self.assertEqual(queue.approved_and_entered_by_ap, [])


if __name__ == "__main__":
    unittest.main()
