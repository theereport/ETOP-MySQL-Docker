from __future__ import annotations

import copy
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from modules.accounts_payable.repository import AccountsPayableRepository
from modules.accounts_payable.schemas import (
    APControlCaseCreate,
    APControlReviewCreate,
)
from modules.accounts_payable.service import (
    APControlConflict,
    AccountsPayableService,
)

from test_accounts_payable_foundation import _complete_fields, _evidence


class MutableSource:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def list_vendor_invoice_evidence(self) -> list[dict]:
        return copy.deepcopy(self.items)


class StepClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 6, 19, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        result = self.value
        self.value += timedelta(seconds=1)
        return result


class AccountsPayableControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "ap-controls.db"

        def connection_factory() -> sqlite3.Connection:
            return sqlite3.connect(
                self.database_path,
                timeout=30,
                check_same_thread=False,
            )

        self.repository = AccountsPayableRepository(connection_factory)
        self.source = MutableSource()
        case_ids = iter(("control-case-one", "control-case-two"))
        review_ids = iter(("control-review-one", "control-review-two"))
        self.service = AccountsPayableService(
            repository=self.repository,
            source=self.source,
            clock=StepClock(),
            id_factory=lambda: "sync-controls",
            control_case_id_factory=lambda: next(case_ids),
            control_review_id_factory=lambda: next(review_ids),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _sync_complete_invoice(self, *, total: str = "100.00") -> str:
        self.source.items = [
            _evidence(
                "synthetic-control-job",
                fields=_complete_fields(total=total),
            )
        ]
        self.service.sync()
        listing = self.service.list_invoices(
            query=None,
            status=None,
            exception=None,
            duplicate=None,
            exception_code=None,
            limit=50,
            offset=0,
            sort_by="received_at",
            sort_order="desc",
        )
        return listing.items[0].ap_invoice_id

    def test_approval_case_records_readiness_without_approval_effect(self) -> None:
        invoice_id = self._sync_complete_invoice()
        created = self.service.create_control_case(
            invoice_id,
            APControlCaseCreate(
                intended_action="approval_review",
                requested_by="AP Specialist",
                assigned_reviewer="Accounting Manager",
                notes="Prepare document evidence for governed approval.",
            ),
        )

        self.assertTrue(created.document_evidence_ready)
        self.assertTrue(created.evidence_current)
        self.assertEqual(created.control_status, "control_review_pending")
        self.assertFalse(created.can_enter_governed_approval)
        self.assertFalse(created.can_authorize_payment)
        self.assertEqual(created.approval_authority_status, "unavailable")
        self.assertIn(
            "unavailable",
            {gate.status for gate in created.evidence_gates},
        )

        reviewed = self.service.create_control_review(
            created.control_case_id,
            APControlReviewCreate(
                reviewer_identity="Accounting Manager",
                disposition="evidence_ready",
                notes="Available document evidence is complete for the next governed step.",
            ),
        )
        self.assertEqual(reviewed.control_status, "evidence_ready")
        self.assertEqual(len(reviewed.reviews), 1)
        self.assertEqual(reviewed.reviews[0].approval_effect, "none")
        self.assertEqual(reviewed.reviews[0].payment_effect, "none")

    def test_self_review_blocks_evidence_ready_disposition(self) -> None:
        invoice_id = self._sync_complete_invoice()
        created = self.service.create_control_case(
            invoice_id,
            APControlCaseCreate(
                intended_action="approval_review",
                requested_by="Same Person",
                assigned_reviewer="Same Person",
                notes="Control should remain blocked.",
            ),
        )
        self.assertFalse(created.document_evidence_ready)
        self.assertIn(
            "blocked",
            {check.status for check in created.segregation_checks},
        )
        with self.assertRaises(APControlConflict):
            self.service.create_control_review(
                created.control_case_id,
                APControlReviewCreate(
                    reviewer_identity="Same Person",
                    disposition="evidence_ready",
                    notes="Attempted readiness disposition.",
                ),
            )

    def test_payment_case_requires_separate_preparer_but_never_authorizes(
        self,
    ) -> None:
        invoice_id = self._sync_complete_invoice()
        created = self.service.create_control_case(
            invoice_id,
            APControlCaseCreate(
                intended_action="payment_preparation",
                requested_by="AP Specialist",
                assigned_reviewer="Accounting Manager",
                payment_preparer="Treasury Specialist",
                notes="Prepare a control packet; do not create a payment batch.",
            ),
        )
        self.assertTrue(created.document_evidence_ready)
        self.assertEqual(created.payment_authorization_status, "unavailable")
        self.assertFalse(created.can_authorize_payment)
        payment_gate = next(
            gate
            for gate in created.evidence_gates
            if gate.code == "payment_execution"
        )
        self.assertEqual(payment_gate.status, "unavailable")

    def test_changed_invoice_revision_invalidates_prior_ready_case(self) -> None:
        invoice_id = self._sync_complete_invoice(total="100.00")
        created = self.service.create_control_case(
            invoice_id,
            APControlCaseCreate(
                intended_action="approval_review",
                requested_by="AP Specialist",
                assigned_reviewer="Accounting Manager",
                notes="Bind the current evidence revision.",
            ),
        )
        self.service.create_control_review(
            created.control_case_id,
            APControlReviewCreate(
                reviewer_identity="Accounting Manager",
                disposition="evidence_ready",
                notes="Ready against the original source revision.",
            ),
        )

        self.source.items = [
            _evidence(
                "synthetic-control-job",
                fields=_complete_fields(total="125.00"),
                result_updated_at="2026-08-07T12:01:00+00:00",
            )
        ]
        self.service.sync()
        reopened = self.service.get_control_case(created.control_case_id)

        self.assertFalse(reopened.evidence_current)
        self.assertFalse(reopened.document_evidence_ready)
        self.assertEqual(reopened.control_status, "not_ready")
        current_gate = next(
            gate
            for gate in reopened.evidence_gates
            if gate.code == "source_evidence_current"
        )
        self.assertEqual(current_gate.status, "blocked")

    def test_control_records_are_append_only(self) -> None:
        invoice_id = self._sync_complete_invoice()
        created = self.service.create_control_case(
            invoice_id,
            APControlCaseCreate(
                intended_action="approval_review",
                requested_by="AP Specialist",
                assigned_reviewer="Accounting Manager",
                notes="Append-only test case.",
            ),
        )
        self.service.create_control_review(
            created.control_case_id,
            APControlReviewCreate(
                reviewer_identity="Accounting Manager",
                disposition="needs_information",
                notes="Additional support is required.",
            ),
        )

        for statement in (
            "UPDATE ap_control_cases SET notes = 'changed'",
            "DELETE FROM ap_control_cases",
            "UPDATE ap_control_reviews SET notes = 'changed'",
            "DELETE FROM ap_control_reviews",
        ):
            connection = sqlite3.connect(self.database_path)
            try:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(statement)
                    connection.commit()
            finally:
                connection.rollback()
                connection.close()

        listing = self.service.list_control_cases(
            intended_action="approval_review",
            limit=50,
            offset=0,
        )
        self.assertEqual(listing.total, 1)
        self.assertEqual(listing.items[0].control_status, "needs_information")


if __name__ == "__main__":
    unittest.main()
