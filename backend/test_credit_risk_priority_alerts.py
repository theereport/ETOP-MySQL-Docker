from __future__ import annotations

import copy
import sqlite3
import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine

from modules.credit_risk.repository import CreditRiskRepository
from modules.credit_risk.schemas import AssessmentCreate
from modules.credit_risk.service import CreditRiskService


def _synthetic_summary(
    customer_number: int,
    name: str,
    *,
    credit_line: float = 1000.0,
    open_ar: float = 600.0,
    on_order: float = 100.0,
) -> dict:
    return {
        "customer_number": customer_number,
        "customer_name": name,
        "general": {
            "dba_name": f"{name} DBA",
            "address_lines": ["100 Synthetic Test Lane", "Fixture OH 00000"],
            "state_code": 39,
            "zip_code": "00000",
            "phone": "(000) 555-0100",
            "email": "fixture@example.test",
            "route_code": "TEST",
            "store_number": 999,
            "salesman_number": 999,
            "customer_type": "TEST",
            "customer_class": "TEST",
            "active": True,
        },
        "credit": {
            "credit_limit": credit_line,
            "balance": open_ar,
            "raw_on_order": on_order,
            "terms_code": "TEST",
            "terms_description": "Synthetic test terms",
        },
        "aging": {
            "future": 0.0,
            "current": open_ar,
            "days_30": 0.0,
            "days_60": 0.0,
            "days_90": 0.0,
            "days_120": 0.0,
        },
        "activity": {
            "last_payment_amount": 100.0,
            "last_payment_date": "2026-08-01",
        },
    }


class MappingCustomerService:
    def __init__(self, summaries: dict[int, dict]) -> None:
        self.summaries = summaries
        self.failures: set[int] = set()
        self.calls: list[int] = []

    def summary(self, customer_number: int) -> dict | None:
        self.calls.append(customer_number)
        if customer_number in self.failures:
            raise RuntimeError("Synthetic ERP outage")
        summary = self.summaries.get(customer_number)
        return copy.deepcopy(summary) if summary is not None else None


class StepClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        result = self.current
        self.current += timedelta(seconds=1)
        return result


class CreditRiskPriorityAlertsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self._temporary_directory.name)
            / "credit-risk-priority-synthetic-test.db"
        )

        self.engine = create_engine(f"sqlite:///{self.database_path}")
        self.repository = CreditRiskRepository(engine=self.engine)
        self.customer_numbers = {
            "overdue_deteriorated": 990000001,
            "overdue_higher_rating": 990000002,
            "due_source_down": 990000003,
            "scheduled_over_line": 990000004,
            "overdue_tie_break": 990000005,
            "low_assessed": 990000006,
            "unassessed": 999999998,
        }
        self.customer_service = MappingCustomerService(
            {
                self.customer_numbers["overdue_deteriorated"]: (
                    _synthetic_summary(
                        self.customer_numbers["overdue_deteriorated"],
                        "Synthetic Deterioration Customer",
                        credit_line=1000.0,
                        open_ar=950.0,
                        on_order=200.0,
                    )
                ),
                self.customer_numbers["overdue_higher_rating"]: (
                    _synthetic_summary(
                        self.customer_numbers["overdue_higher_rating"],
                        "Synthetic Higher Rating Customer",
                    )
                ),
                self.customer_numbers["due_source_down"]: _synthetic_summary(
                    self.customer_numbers["due_source_down"],
                    "Synthetic Source Down Customer",
                ),
                self.customer_numbers["scheduled_over_line"]: (
                    _synthetic_summary(
                        self.customer_numbers["scheduled_over_line"],
                        "Synthetic Scheduled Customer",
                        credit_line=1000.0,
                        open_ar=1000.0,
                        on_order=50.0,
                    )
                ),
                self.customer_numbers["overdue_tie_break"]: (
                    _synthetic_summary(
                        self.customer_numbers["overdue_tie_break"],
                        "Synthetic Tie Break Customer",
                    )
                ),
                self.customer_numbers["low_assessed"]: _synthetic_summary(
                    self.customer_numbers["low_assessed"],
                    "Synthetic Low Band Customer",
                ),
                self.customer_numbers["unassessed"]: _synthetic_summary(
                    self.customer_numbers["unassessed"],
                    "Synthetic Unassessed Customer",
                ),
            }
        )
        ids = iter(
            f"synthetic-priority-assessment-{index:02d}"
            for index in range(1, 20)
        )
        self.foundation_service = CreditRiskService(
            repository=self.repository,
            customer_summary_service=self.customer_service,
            clock=StepClock(),
            id_factory=lambda: next(ids),
        )
        self._seed_assessments()
        self.customer_service.calls.clear()
        self.customer_service.failures.add(
            self.customer_numbers["due_source_down"]
        )
        self.priority_service = CreditRiskService(
            repository=self.repository,
            customer_summary_service=self.customer_service,
            clock=lambda: datetime(2026, 8, 20, 9, 30, tzinfo=UTC),
        )

    def tearDown(self) -> None:
        self.engine.dispose()
        self._temporary_directory.cleanup()

    def _assess(
        self,
        customer_number: int,
        rating: int,
        review_date: date,
        next_review_date: date,
    ) -> None:
        self.foundation_service.create_assessment(
            customer_number,
            AssessmentCreate(
                manual_rating=rating,
                review_date=review_date,
                next_review_date=next_review_date,
                analyst_identity="Synthetic Credit Professional",
                rationale=(
                    "Synthetic assessment created only for deterministic "
                    "priority and alert verification."
                ),
            ),
        )

    def _seed_assessments(self) -> None:
        customer = self.customer_numbers["overdue_deteriorated"]
        self._assess(customer, 5, date(2026, 6, 1), date(2026, 7, 1))
        self._assess(customer, 6, date(2026, 7, 1), date(2026, 8, 1))
        self._assess(customer, 8, date(2026, 8, 1), date(2026, 8, 10))

        customer = self.customer_numbers["overdue_higher_rating"]
        self._assess(customer, 9, date(2026, 7, 1), date(2026, 8, 10))
        self._assess(customer, 9, date(2026, 8, 1), date(2026, 8, 10))

        self._assess(
            self.customer_numbers["due_source_down"],
            10,
            date(2026, 8, 1),
            date(2026, 8, 20),
        )
        self._assess(
            self.customer_numbers["scheduled_over_line"],
            7,
            date(2026, 8, 1),
            date(2026, 8, 25),
        )
        self._assess(
            self.customer_numbers["overdue_tie_break"],
            9,
            date(2026, 8, 1),
            date(2026, 8, 10),
        )
        self._assess(
            self.customer_numbers["low_assessed"],
            4,
            date(2026, 8, 1),
            date(2026, 9, 1),
        )

    def test_portfolio_includes_only_assessed_customers(self) -> None:
        result = self.priority_service.get_priority_alerts()

        self.assertEqual(result.summary.assessed_customer_count, 6)
        self.assertTrue(result.unassessed_customers_excluded)
        self.assertIn("without a saved manual assessment", result.coverage_statement)
        self.assertNotIn(
            self.customer_numbers["unassessed"],
            [item.customer_number for item in result.items],
        )
        self.assertNotIn(
            self.customer_numbers["unassessed"],
            self.customer_service.calls,
        )

    def test_empty_assessed_portfolio_is_explicit(self) -> None:
        empty_database_path = (
            Path(self._temporary_directory.name)
            / "credit-risk-priority-empty-synthetic-test.db"
        )

        empty_engine = create_engine(f"sqlite:///{empty_database_path}")
        empty_customer_service = MappingCustomerService({})
        service = CreditRiskService(
            repository=CreditRiskRepository(engine=empty_engine),
            customer_summary_service=empty_customer_service,
            clock=lambda: datetime(2026, 8, 20, 9, 30, tzinfo=UTC),
        )

        try:
            result = service.get_priority_alerts()

            self.assertEqual(result.summary.assessed_customer_count, 0)
            self.assertEqual(result.items, [])
            self.assertTrue(result.unassessed_customers_excluded)
            self.assertEqual(empty_customer_service.calls, [])
        finally:
            empty_engine.dispose()

    def test_ordering_is_categorical_stable_and_explainable(self) -> None:
        result = self.priority_service.get_priority_alerts()

        self.assertEqual(
            [item.customer_number for item in result.items],
            [
                self.customer_numbers["overdue_higher_rating"],
                self.customer_numbers["overdue_tie_break"],
                self.customer_numbers["overdue_deteriorated"],
                self.customer_numbers["due_source_down"],
                self.customer_numbers["scheduled_over_line"],
                self.customer_numbers["low_assessed"],
            ],
        )
        self.assertEqual(
            [item.rank for item in result.items],
            [1, 2, 3, 4, 5, 6],
        )
        self.assertEqual(
            result.items[0].priority_category,
            "review_overdue",
        )
        self.assertEqual(
            result.items[3].priority_category,
            "review_due_today",
        )
        self.assertEqual(
            result.items[4].priority_category,
            "scheduled_review",
        )
        self.assertFalse(result.ordering.numeric_risk_score)
        self.assertFalse(result.ordering.automatic_credit_decision)
        self.assertFalse(result.ordering.recommendation)
        self.assertFalse(result.ordering.notification)
        self.assertFalse(result.ordering.erp_write)
        self.assertEqual(len(result.ordering.ordered_conditions), 6)
        self.assertTrue(
            all(item.ordering_reasons for item in result.items)
        )

    def test_alerts_use_exact_assessment_and_live_evidence(self) -> None:
        result = self.priority_service.get_priority_alerts()
        item = next(
            item
            for item in result.items
            if item.customer_number
            == self.customer_numbers["overdue_deteriorated"]
        )

        self.assertEqual(
            item.ordering_evidence.deterioration_state,
            "deteriorated",
        )
        self.assertEqual(item.ordering_evidence.manual_rating_change, 2)
        self.assertEqual(item.previous_assessment.manual_rating, 6)
        self.assertEqual(item.live_exposure.status, "available")
        self.assertEqual(item.live_exposure.amount_over_limit, 150.0)
        self.assertTrue(item.live_exposure.is_over_line)
        alert_codes = {alert.code for alert in item.alerts}
        self.assertEqual(
            alert_codes,
            {
                "review_overdue",
                "manual_rating_deteriorated",
                "draft_band_attention",
                "current_partial_exposure_over_line",
            },
        )
        deterioration = next(
            alert
            for alert in item.alerts
            if alert.code == "manual_rating_deteriorated"
        )
        self.assertEqual(len(deterioration.assessment_ids), 2)
        self.assertEqual(len(deterioration.evidence_sha256), 2)
        self.assertTrue(
            all(len(value) == 64 for value in deterioration.evidence_sha256)
        )

    def test_live_source_failure_retains_assessment_signals(self) -> None:
        result = self.priority_service.get_priority_alerts()
        item = next(
            item
            for item in result.items
            if item.customer_number
            == self.customer_numbers["due_source_down"]
        )

        self.assertEqual(item.latest_assessment.manual_rating, 10)
        self.assertEqual(item.ordering_evidence.review_state, "due_today")
        self.assertEqual(item.ordering_evidence.over_line_state, "unavailable")
        self.assertEqual(item.live_exposure.status, "source_unavailable")
        self.assertIsNone(item.live_exposure.amount_over_limit)
        self.assertEqual(item.customer_name_source, "saved_assessment")
        self.assertEqual(
            {alert.code for alert in item.alerts},
            {"review_due_today", "draft_band_attention", "live_source_degraded"},
        )
        self.assertEqual(result.summary.live_source_degraded_count, 1)
        self.assertEqual(result.summary.overdue_review_count, 3)
        self.assertEqual(result.summary.due_today_review_count, 1)
        self.assertEqual(result.summary.deterioration_count, 1)
        self.assertEqual(result.summary.over_line_count, 2)
        self.assertEqual(result.summary.operational_alert_count, 12)

    def test_broken_promise_and_nsf_are_explicitly_unavailable(self) -> None:
        result = self.priority_service.get_priority_alerts()

        self.assertEqual(
            {capability.code for capability in result.unavailable_capabilities},
            {"broken_promise_alerts", "nsf_alerts"},
        )
        for capability in result.unavailable_capabilities:
            self.assertEqual(
                capability.status,
                "unavailable_source_capability",
            )
            self.assertFalse(capability.emitted_alerts)
            self.assertTrue(capability.explanation)

        emitted_codes = {
            alert.code
            for item in result.items
            for alert in item.alerts
        }
        self.assertNotIn("broken_promise_alerts", emitted_codes)
        self.assertNotIn("nsf_alerts", emitted_codes)

    def test_draft_high_risk_band_attention_uses_saved_band_snapshot(self) -> None:
        result = self.priority_service.get_priority_alerts()

        attention_items = [
            item for item in result.items if item.draft_band_attention
        ]
        self.assertEqual(result.summary.draft_band_attention_count, 5)
        self.assertEqual(len(attention_items), 5)
        self.assertEqual(
            {
                item.latest_assessment.band.meaning
                for item in attention_items
            },
            {
                "High risk",
                "Very high risk",
                "Default likely",
                "Default or legal",
            },
        )
        low_item = next(
            item
            for item in result.items
            if item.customer_number == self.customer_numbers["low_assessed"]
        )
        self.assertFalse(low_item.draft_band_attention)
        self.assertNotIn(
            "draft_band_attention",
            {alert.code for alert in low_item.alerts},
        )

        for item in attention_items:
            alert = next(
                alert
                for alert in item.alerts
                if alert.code == "draft_band_attention"
            )
            self.assertIn("Product Owner draft taxonomy", alert.explanation)
            self.assertIn("not an approved automatic policy", alert.explanation)
            self.assertEqual(
                alert.evidence_sha256,
                [item.latest_assessment.evidence_snapshot_sha256],
            )


if __name__ == "__main__":
    unittest.main()
