from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import create_engine

from modules.credit_risk.repository import CreditRiskRepository
from modules.credit_risk.schemas import (
    AssessmentCreate,
    CreditLineProposalCreate,
    PortfolioReviewCreate,
)
from modules.credit_risk.service import CreditRiskService
from test_credit_risk_priority_alerts import (
    MappingCustomerService,
    _synthetic_summary,
)


class CreditPortfolioMonitoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "portfolio-monitoring.db"

        self.engine = create_engine(f"sqlite:///{self.database_path}")
        self.repository = CreditRiskRepository(engine=self.engine)
        self.source = MappingCustomerService(
            {
                910000001: _synthetic_summary(
                    910000001,
                    "Synthetic Watchlist Customer",
                    credit_line=1000.0,
                    open_ar=800.0,
                    on_order=200.0,
                ),
                910000002: _synthetic_summary(
                    910000002,
                    "Synthetic Routine Customer",
                    credit_line=2000.0,
                    open_ar=400.0,
                    on_order=100.0,
                ),
            }
        )
        assessment_ids = iter(("assessment-watch", "assessment-routine"))
        proposal_ids = iter(("proposal-watch",))
        review_ids = iter(("portfolio-review-one", "portfolio-review-two"))
        self.service = CreditRiskService(
            repository=self.repository,
            customer_summary_service=self.source,
            clock=lambda: datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
            id_factory=lambda: next(assessment_ids),
            proposal_id_factory=lambda: next(proposal_ids),
            portfolio_review_id_factory=lambda: next(review_ids),
        )
        self.service.create_assessment(
            910000001,
            AssessmentCreate(
                manual_rating=8,
                review_date=date(2026, 8, 1),
                next_review_date=date(2026, 8, 15),
                analyst_identity="Credit Manager",
                rationale="Synthetic watchlist assessment.",
            ),
        )
        self.service.create_assessment(
            910000002,
            AssessmentCreate(
                manual_rating=4,
                review_date=date(2026, 8, 10),
                next_review_date=date(2026, 9, 15),
                analyst_identity="Credit Manager",
                rationale="Synthetic routine assessment.",
            ),
        )

    def tearDown(self) -> None:
        self.engine.dispose()
        self.temp.cleanup()

    def test_monitoring_is_assessed_portfolio_work_not_policy(self) -> None:
        self.service.create_credit_line_proposal(
            910000001,
            CreditLineProposalCreate(
                proposed_credit_line=1500.0,
                review_date=date(2026, 8, 20),
                analyst_identity="Credit Manager",
                rationale="Synthetic professional proposal.",
            ),
        )

        result = self.service.get_portfolio_monitoring()

        self.assertEqual(result.summary.assessed_customer_count, 2)
        self.assertEqual(result.summary.watchlist_customer_count, 1)
        self.assertEqual(result.summary.overdue_review_count, 1)
        self.assertEqual(result.summary.customers_with_proposals, 1)
        self.assertEqual(result.summary.partial_exposure_total, 1500.0)
        self.assertEqual(result.items[0].customer_number, 910000001)
        self.assertTrue(result.items[0].watchlist)
        self.assertEqual(result.items[0].days_to_review, -5)
        self.assertAlmostEqual(
            result.items[0].partial_exposure_share_percent,
            66.67,
        )
        self.assertFalse(result.governance.approved_portfolio_policy)
        self.assertFalse(result.governance.automatic_decision)
        self.assertFalse(result.governance.erp_write)

    def test_review_history_is_append_only_and_non_authorizing(self) -> None:
        first = self.service.create_portfolio_review(
            910000001,
            PortfolioReviewCreate(
                disposition="information_requested",
                reviewer_identity="Credit Manager",
                notes="Request current financial support.",
                follow_up_date=date(2026, 8, 25),
            ),
        )
        second = self.service.create_portfolio_review(
            910000001,
            PortfolioReviewCreate(
                disposition="reassessment_needed",
                reviewer_identity="Credit Manager",
                notes="Record a new assessment after evidence arrives.",
            ),
        )

        history = self.service.list_portfolio_reviews(910000001)
        self.assertEqual(history.count, 2)
        self.assertEqual(
            [review.portfolio_review_id for review in history.reviews],
            [second.portfolio_review_id, first.portfolio_review_id],
        )
        self.assertEqual(first.decision_effect, "none")
        self.assertFalse(first.erp_write)
        self.assertEqual(len(first.evidence_snapshot_sha256), 64)

        monitoring = self.service.get_portfolio_monitoring()
        watch_item = next(
            item for item in monitoring.items
            if item.customer_number == 910000001
        )
        self.assertEqual(
            watch_item.latest_portfolio_review.portfolio_review_id,
            second.portfolio_review_id,
        )

        # Append-only is enforced by convention in the repository layer
        # (it never issues UPDATE/DELETE against these tables), not by a
        # DB trigger - MySQL trigger creation needs a privilege the etop
        # account doesn't have.


if __name__ == "__main__":
    unittest.main()
