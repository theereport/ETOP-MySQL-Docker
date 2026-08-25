from __future__ import annotations

import copy
import sqlite3
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path

from modules.accounts_payable.repository import AccountsPayableRepository
from modules.accounts_payable.schemas import APExceptionActionCreate
from modules.accounts_payable.service import (
    APControlConflict,
    APInvoiceNotFound,
    AccountsPayableService,
)
from test_accounts_payable_foundation import _complete_fields, _evidence


class MutableSource:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def list_vendor_invoice_evidence(self) -> list[dict]:
        return copy.deepcopy(self.items)


class AccountsPayableExceptionOperationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "ap-exception-operations.db"

        def connection_factory() -> sqlite3.Connection:
            return sqlite3.connect(
                self.database_path,
                timeout=30,
                check_same_thread=False,
            )

        self.repository = AccountsPayableRepository(connection_factory)
        self.source = MutableSource()
        self.action_ids = iter(("exception-action-one", "exception-action-two"))
        self.service = AccountsPayableService(
            repository=self.repository,
            source=self.source,
            clock=lambda: datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
            id_factory=lambda: "exception-operations-sync",
            exception_action_id_factory=lambda: next(self.action_ids),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _sync_review_evidence(self) -> None:
        fields = _complete_fields(
            vendor_name="SYNTH-EXCEPTION-VENDOR",
            vendor_number="SYNTH-EX-001",
            invoice_number="SYNTH-EX-INV-001",
            total="450.00",
        )
        fields.pop("due_date")
        self.source.items = [_evidence("exception-operations-one", fields=fields)]
        self.service.sync()

    def test_queue_uses_existing_reasons_and_no_hidden_score(self) -> None:
        self._sync_review_evidence()

        result = self.service.exception_operations(date(2026, 8, 20))

        self.assertEqual(result.summary.queue_count, 1)
        self.assertEqual(result.summary.unworked_count, 1)
        self.assertEqual(result.summary.known_amount_count, 1)
        self.assertEqual(result.summary.extracted_amount, 450.0)
        self.assertEqual(result.items[0].queue_rank, 1)
        self.assertEqual(result.items[0].work_state, "unworked")
        self.assertTrue(result.items[0].reasons)
        self.assertFalse(result.governance.approved_sla)
        self.assertFalse(result.governance.authenticated_assignment)
        self.assertFalse(result.governance.automatic_resolution)
        self.assertFalse(result.governance.erp_write)

    def test_actions_are_append_only_and_source_change_reopens_work(self) -> None:
        self._sync_review_evidence()
        invoice_id = self.service.exception_operations().items[0].ap_invoice_id

        action = self.service.create_exception_action(
            invoice_id,
            APExceptionActionCreate(
                disposition="information_requested",
                owner_identity="AP Lead",
                actor_identity="AP Reviewer",
                notes="Request the missing due-date evidence.",
                follow_up_date=date(2026, 8, 19),
            ),
        )
        queue = self.service.exception_operations(date(2026, 8, 20))
        self.assertEqual(queue.items[0].work_state, "follow_up_overdue")
        self.assertEqual(action.approval_effect, "none")
        self.assertEqual(action.payment_effect, "none")
        self.assertFalse(action.erp_write)

        changed_fields = _complete_fields(
            vendor_name="SYNTH-EXCEPTION-VENDOR",
            vendor_number="SYNTH-EX-001",
            invoice_number="SYNTH-EX-INV-001",
            total="475.00",
        )
        changed_fields.pop("due_date")
        self.source.items = [_evidence("exception-operations-one", fields=changed_fields)]
        self.service.sync()
        changed_queue = self.service.exception_operations(date(2026, 8, 20))
        self.assertEqual(changed_queue.items[0].work_state, "source_changed")

        history = self.service.list_exception_actions(invoice_id)
        self.assertEqual(history.count, 1)
        self.assertEqual(len(action.evidence_snapshot_sha256), 64)
        self.assertNotIn("latest_action", action.evidence_snapshot)

        next_action = self.service.create_exception_action(
            invoice_id,
            APExceptionActionCreate(
                disposition="document_correction_needed",
                owner_identity="AP Lead",
                actor_identity="AP Reviewer",
                notes="Preserve the prior action by reference without nesting it.",
            ),
        )
        self.assertEqual(
            next_action.evidence_snapshot["prior_action"]["action_id"],
            action.action_id,
        )
        self.assertNotIn("latest_action", next_action.evidence_snapshot)

        for statement in (
            "UPDATE ap_exception_actions SET notes = 'changed'",
            "DELETE FROM ap_exception_actions",
        ):
            connection = sqlite3.connect(self.database_path)
            try:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(statement)
                    connection.commit()
            finally:
                connection.rollback()
                connection.close()

    def test_actions_require_a_current_exception_queue_item(self) -> None:
        self.source.items = [
            _evidence(
                "exception-operations-clean",
                fields=_complete_fields(
                    vendor_name="SYNTH-CLEAN-VENDOR",
                    vendor_number="SYNTH-CLEAN-001",
                    invoice_number="SYNTH-CLEAN-INV-001",
                    total="125.00",
                ),
            )
        ]
        self.service.sync()
        clean_invoice_id = self.repository.list_all_invoices()[0][
            "ap_invoice_id"
        ]
        payload = APExceptionActionCreate(
            disposition="investigating",
            owner_identity="AP Lead",
            actor_identity="AP Reviewer",
            notes="This should not be admitted without current review evidence.",
        )

        with self.assertRaises(APControlConflict):
            self.service.create_exception_action(clean_invoice_id, payload)
        with self.assertRaises(APInvoiceNotFound):
            self.service.create_exception_action(
                "ap-invoice-000000000000000000000000",
                payload,
            )

        self.assertEqual(
            self.service.exception_operations().summary.queue_count,
            0,
        )
        self.assertEqual(self.repository.list_exception_actions(clean_invoice_id), [])


if __name__ == "__main__":
    unittest.main()
