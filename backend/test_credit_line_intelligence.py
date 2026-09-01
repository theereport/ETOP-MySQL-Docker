from __future__ import annotations

import copy
import sqlite3
import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine

from modules.credit_risk.repository import CreditRiskRepository
from modules.credit_risk.schemas import CreditLineProposalCreate
from modules.credit_risk.service import CreditRiskService


def _summary() -> dict:
    return {
        "customer_number": 900000010,
        "customer_name": "Synthetic Line Intelligence Customer",
        "general": {
            "dba_name": "",
            "address_lines": ["10 Evidence Way"],
            "state_code": 39,
            "zip_code": "45402",
            "phone": "(937) 555-0110",
            "email": "credit-line@example.test",
            "route_code": "D1",
            "store_number": 1,
            "salesman_number": 10,
            "customer_type": "DLR",
            "customer_class": "A",
            "active": True,
        },
        "credit": {
            "credit_limit": 250000.0,
            "balance": 175000.0,
            "raw_on_order": 25000.0,
            "total_exposure": 200000.0,
            "available_credit": 50000.0,
            "amount_over_limit": 0.0,
            "utilization_percent": 80.0,
            "high_balance": 230000.0,
            "monthly_high_balance": 215000.0,
            "average_daily_balance": 182500.0,
            "terms_code": "1",
            "terms_description": "Due on the 10th",
        },
        "aging": {
            "future": 0.0,
            "current": 150000.0,
            "days_30": 25000.0,
            "days_60": 0.0,
            "days_90": 0.0,
            "days_120": 0.0,
            "past_due": 25000.0,
            "total_aging": 175000.0,
        },
        "sales": {
            "month_to_date": 180000.0,
            "year_to_date": 1500000.0,
            "last_year": 2200000.0,
            "annualized_sales": 2400000.0,
            "expected_credit_line": 400000.0,
        },
        "activity": {
            "last_payment_amount": 85000.0,
            "last_payment_date": "2026-08-01",
        },
    }


class FakeCustomerService:
    def __init__(self) -> None:
        self.value = _summary()
        self.error: Exception | None = None

    def summary(self, customer_number: int) -> dict:
        del customer_number
        if self.error is not None:
            raise self.error
        return copy.deepcopy(self.value)


class StepClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 6, 18, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        result = self.value
        self.value += timedelta(seconds=1)
        return result


class CreditLineIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        database_path = Path(self.temp.name) / "credit-line.db"

        self.database_path = database_path
        self.engine = create_engine(f"sqlite:///{database_path}")
        self.repository = CreditRiskRepository(engine=self.engine)
        self.source = FakeCustomerService()
        proposal_ids = iter(("proposal-one", "proposal-two"))
        self.service = CreditRiskService(
            repository=self.repository,
            customer_summary_service=self.source,
            clock=StepClock(),
            proposal_id_factory=lambda: next(proposal_ids),
        )

    def tearDown(self) -> None:
        self.engine.dispose()
        self.temp.cleanup()

    def test_reference_reproduces_existing_formula_without_becoming_policy(
        self,
    ) -> None:
        result = self.service.get_credit_line_intelligence(900000010)

        self.assertEqual(result.sales.annualized_sales.value, 2400000.0)
        self.assertEqual(result.analytical_reference.amount, 400000.0)
        self.assertEqual(result.analytical_reference.status, "available")
        self.assertFalse(result.analytical_reference.automatic_recommendation)
        self.assertEqual(
            result.analytical_reference.policy_status,
            "existing_unapproved_analytical_reference",
        )
        self.assertEqual(result.capacity.partial_exposure.value, 200000.0)
        self.assertEqual(result.capacity.high_balance.value, 230000.0)
        self.assertFalse(result.governance.reference_is_recommendation)
        self.assertFalse(result.governance.erp_write)
        self.assertEqual(len(result.gaps), 5)

    def test_missing_sales_is_unavailable_not_zero(self) -> None:
        self.source.value.pop("sales")

        result = self.service.get_credit_line_intelligence(900000010)

        self.assertIsNone(result.sales.annualized_sales.value)
        self.assertEqual(result.sales.annualized_sales.status, "unavailable")
        self.assertIsNone(result.analytical_reference.amount)
        self.assertEqual(result.analytical_reference.status, "unavailable")

    def test_conflicting_reference_is_withheld(self) -> None:
        self.source.value["sales"]["expected_credit_line"] = 999999.0

        result = self.service.get_credit_line_intelligence(900000010)

        self.assertIsNone(result.analytical_reference.amount)
        self.assertEqual(result.analytical_reference.status, "invalid")
        self.assertIn("did not reproduce", result.analytical_reference.explanation)

    def test_professional_proposals_are_append_only_and_non_authorizing(
        self,
    ) -> None:
        first = self.service.create_credit_line_proposal(
            900000010,
            CreditLineProposalCreate(
                proposed_credit_line=350000.0,
                review_date=date(2026, 8, 6),
                analyst_identity="Credit Manager",
                rationale="Support current growth while retaining review.",
            ),
        )
        second = self.service.create_credit_line_proposal(
            900000010,
            CreditLineProposalCreate(
                proposed_credit_line=375000.0,
                review_date=date(2026, 8, 7),
                analyst_identity="Credit Manager",
                rationale="Updated professional proposal after review.",
            ),
        )

        history = self.service.list_credit_line_proposals(900000010)
        self.assertEqual(history.count, 2)
        self.assertEqual(
            [item.proposal_id for item in history.proposals],
            [second.proposal_id, first.proposal_id],
        )
        self.assertEqual(first.analytical_reference_line, 400000.0)
        self.assertEqual(first.approval_status, "not_submitted_to_governed_approval")
        self.assertEqual(first.decision_effect, "none")
        self.assertFalse(first.erp_write)
        self.assertEqual(len(first.evidence_snapshot_sha256), 64)

        # Append-only is enforced by convention in the repository layer
        # (it never issues UPDATE/DELETE against these tables), not by a
        # DB trigger - MySQL trigger creation needs a privilege the etop
        # account doesn't have.

    def test_proposal_history_survives_live_source_failure(self) -> None:
        self.service.create_credit_line_proposal(
            900000010,
            CreditLineProposalCreate(
                proposed_credit_line=300000.0,
                review_date=date(2026, 8, 6),
                analyst_identity="Credit Manager",
                rationale="Local proposal evidence.",
            ),
        )
        self.source.error = RuntimeError("ERP unavailable")

        history = self.service.list_credit_line_proposals(900000010)
        self.assertEqual(history.count, 1)
        self.assertEqual(history.proposals[0].proposed_credit_line, 300000.0)


if __name__ == "__main__":
    unittest.main()
