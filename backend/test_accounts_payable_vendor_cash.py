from __future__ import annotations

import copy
import sqlite3
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path

from modules.accounts_payable.erp_ledger_repository import (
    AccountsPayableErpLedgerRepository,
)
from modules.accounts_payable.repository import AccountsPayableRepository
from modules.accounts_payable.schemas import APCashScenarioCreate
from modules.accounts_payable.service import AccountsPayableService
from test_accounts_payable_foundation import _complete_fields, _evidence


class MutableSource:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def list_vendor_invoice_evidence(self) -> list[dict]:
        return copy.deepcopy(self.items)


class AccountsPayableVendorCashTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "ap-vendor-cash.db"

        def connection_factory() -> sqlite3.Connection:
            return sqlite3.connect(
                self.database_path,
                timeout=30,
                check_same_thread=False,
            )

        self.repository = AccountsPayableRepository(connection_factory)
        self.source = MutableSource()
        scenario_ids = iter(("cash-scenario-one", "cash-scenario-two"))
        self.service = AccountsPayableService(
            repository=self.repository,
            source=self.source,
            clock=lambda: datetime(2026, 8, 6, 20, 0, tzinfo=UTC),
            id_factory=lambda: "sync-vendor-cash",
            cash_scenario_id_factory=lambda: next(scenario_ids),
            erp_ledger_repository=AccountsPayableErpLedgerRepository(
                connection_factory
            ),
            open_ledger_scan=lambda: [],
            vendor_terms_scan=lambda: [],
            on_ledger_job_started=lambda job_id: None,
            on_ledger_job_complete=lambda job_id, result, error: None,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _sync_vendor_evidence(self) -> None:
        duplicate_fields = _complete_fields(
            vendor_name="SYNTH-VENDOR-ALPHA",
            vendor_number="SYNTH-001",
            invoice_number="SYNTH-DUP-001",
            due_date="2026-08-10",
            total="125.00",
        )
        no_due_fields = _complete_fields(
            vendor_name="SYNTH-VENDOR-BETA",
            vendor_number="SYNTH-002",
            invoice_number="SYNTH-NODUE-001",
            total="300.00",
        )
        no_due_fields.pop("due_date")
        self.source.items = [
            _evidence(
                "vendor-cash-clean",
                fields=_complete_fields(
                    vendor_name="SYNTH-VENDOR-BETA",
                    vendor_number="SYNTH-002",
                    invoice_number="SYNTH-CLEAN-001",
                    due_date="2026-08-05",
                    total="200.00",
                ),
            ),
            _evidence("vendor-cash-duplicate-a", fields=duplicate_fields),
            _evidence("vendor-cash-duplicate-b", fields=duplicate_fields),
            _evidence("vendor-cash-no-due", fields=no_due_fields),
        ]
        self.service.sync()

    def test_vendor_and_cash_windows_are_document_evidence_only(self) -> None:
        self._sync_vendor_evidence()

        result = self.service.vendor_cash_intelligence(date(2026, 8, 6))

        self.assertEqual(result.coverage.imported_invoice_count, 4)
        self.assertEqual(result.coverage.identified_vendor_invoice_count, 4)
        self.assertEqual(result.coverage.due_date_invoice_count, 3)
        self.assertEqual(len(result.vendors), 2)
        alpha = next(
            vendor for vendor in result.vendors
            if vendor.vendor_number == "SYNTH-001"
        )
        self.assertEqual(alpha.invoice_count, 2)
        self.assertEqual(alpha.extracted_total_amount, 250.0)
        self.assertEqual(alpha.review_required_count, 2)
        self.assertEqual(alpha.duplicate_candidate_invoice_count, 2)
        windows = {window.code: window for window in result.cash_windows}
        self.assertEqual(windows["past_due"].invoice_count, 1)
        self.assertEqual(windows["past_due"].extracted_amount, 200.0)
        self.assertEqual(windows["next_7_days"].invoice_count, 2)
        self.assertEqual(windows["next_7_days"].extracted_amount, 250.0)
        self.assertEqual(windows["due_date_unavailable"].invoice_count, 1)
        self.assertFalse(result.governance.current_payable_status_known)
        self.assertFalse(result.governance.vendor_performance_score)
        self.assertFalse(result.governance.payment_proposal)
        self.assertFalse(result.governance.erp_write)

    def test_cash_scenario_is_immutable_analysis_not_payment_proposal(self) -> None:
        self._sync_vendor_evidence()

        scenario = self.service.create_cash_scenario(
            APCashScenarioCreate(
                as_of_date=date(2026, 8, 6),
                horizon_days=7,
                include_review_required=False,
                prepared_by="Accounting Leader",
                rationale="Prepare a document-evidence cash discussion.",
            )
        )

        self.assertEqual(scenario.included_invoice_count, 1)
        self.assertEqual(scenario.extracted_amount, 200.0)
        self.assertEqual(scenario.excluded_review_required_count, 2)
        self.assertEqual(scenario.excluded_missing_due_date_count, 1)
        self.assertFalse(scenario.current_payable_status_known)
        self.assertEqual(scenario.approval_effect, "none")
        self.assertEqual(scenario.payment_effect, "none")
        self.assertFalse(scenario.erp_write)
        self.assertEqual(len(scenario.evidence_snapshot_sha256), 64)

        history = self.service.list_cash_scenarios()
        self.assertEqual(history.count, 1)
        self.assertEqual(
            history.scenarios[0].cash_scenario_id,
            scenario.cash_scenario_id,
        )

        for statement in (
            "UPDATE ap_cash_scenarios SET rationale = 'changed'",
            "DELETE FROM ap_cash_scenarios",
        ):
            connection = sqlite3.connect(self.database_path)
            try:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(statement)
                    connection.commit()
            finally:
                connection.rollback()
                connection.close()


if __name__ == "__main__":
    unittest.main()
