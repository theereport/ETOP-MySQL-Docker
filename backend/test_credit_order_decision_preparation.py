from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import create_engine

from modules.credit_risk.repository import CreditRiskRepository
from modules.credit_risk.schemas import AssessmentCreate, OrderRecommendationCreate
from modules.credit_risk.service import CreditRiskService
from test_credit_risk_priority_alerts import MappingCustomerService, _synthetic_summary


class CreditOrderDecisionPreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "order-preparation.db"

        self.engine = create_engine(f"sqlite:///{self.database_path}")
        self.repository = CreditRiskRepository(engine=self.engine)
        self.source = MappingCustomerService(
            {
                920000001: _synthetic_summary(
                    920000001,
                    "Synthetic Order Review Customer",
                    credit_line=1000.0,
                    open_ar=700.0,
                    on_order=100.0,
                )
            }
        )
        self.service = CreditRiskService(
            repository=self.repository,
            customer_summary_service=self.source,
            clock=lambda: datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
            id_factory=lambda: "assessment-order-review",
            order_recommendation_id_factory=(
                lambda: "order-recommendation-one"
            ),
        )
        self.service.create_assessment(
            920000001,
            AssessmentCreate(
                manual_rating=7,
                review_date=date(2026, 8, 20),
                next_review_date=date(2026, 9, 20),
                analyst_identity="Credit Manager",
                rationale="Synthetic evidence for order preparation.",
            ),
        )

    def tearDown(self) -> None:
        self.engine.dispose()
        self.temp.cleanup()

    def test_preparation_uses_partial_evidence_and_withholds_authority(self) -> None:
        result = self.service.get_order_decision_preparation(
            920000001,
            300.0,
            "SYNTH-ORDER-1",
        )

        self.assertEqual(result.evidence.current_partial_exposure, 800.0)
        self.assertEqual(result.evidence.projected_partial_exposure, 1100.0)
        self.assertEqual(
            result.evidence.projected_partial_available_credit,
            -100.0,
        )
        self.assertEqual(
            result.evidence.projected_partial_over_line_amount,
            100.0,
        )
        self.assertTrue(result.professional_review_required)
        self.assertFalse(result.governance.automatic_recommendation)
        self.assertFalse(result.governance.automatic_decision)
        self.assertEqual(result.governance.order_hold_effect, "none")
        self.assertEqual(result.governance.order_release_effect, "none")
        self.assertFalse(result.governance.erp_write)
        gates = {gate.code: gate.status for gate in result.gates}
        self.assertEqual(gates["current_manual_assessment"], "available")
        self.assertEqual(gates["erp_order_identity"], "operator_entered")
        self.assertEqual(gates["approved_order_policy"], "unavailable")

    def test_recommendation_is_append_only_and_has_no_order_effect(self) -> None:
        recommendation = self.service.create_order_recommendation(
            920000001,
            OrderRecommendationCreate(
                contemplated_order_amount=300.0,
                order_reference="SYNTH-ORDER-1",
                disposition="escalate_for_credit_authority",
                analyst_identity="Credit Manager",
                rationale="Escalate the partial-exposure scenario for an authorized decision.",
            ),
        )

        self.assertEqual(recommendation.decision_effect, "none")
        self.assertEqual(recommendation.order_effect, "none")
        self.assertFalse(recommendation.erp_write)
        self.assertEqual(len(recommendation.evidence_snapshot_sha256), 64)
        history = self.service.list_order_recommendations(920000001)
        self.assertEqual(history.count, 1)
        self.assertEqual(
            history.recommendations[0].order_recommendation_id,
            recommendation.order_recommendation_id,
        )

        # Append-only is enforced by convention in the repository layer
        # (it never issues UPDATE/DELETE against these tables), not by a
        # DB trigger - MySQL trigger creation needs a privilege the etop
        # account doesn't have.


if __name__ == "__main__":
    unittest.main()
