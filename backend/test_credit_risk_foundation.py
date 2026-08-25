from __future__ import annotations

import copy
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from modules.credit_risk.repository import (
    AssessmentEvidenceIntegrityError,
    BAND_SET_VERSION,
    CreditRiskRepository,
)
from modules.credit_risk.schemas import AssessmentCreate
from modules.credit_risk.service import (
    CreditRiskCustomerNotFound,
    CreditRiskService,
    CreditRiskSourceIntegrityError,
    CreditRiskSourceUnavailable,
)


def _customer_summary() -> dict:
    return {
        "customer_number": 900000001,
        "customer_name": "Synthetic Credit Test Customer",
        "general": {
            "dba_name": "Synthetic Credit Fixture",
            "address_lines": [
                "100 Test Fixture Lane",
                "Example OH 00000",
            ],
            "state_code": 39,
            "zip_code": "45402",
            "phone": "(937) 555-0100",
            "email": "credit@example.test",
            "route_code": "D1",
            "store_number": 1,
            "salesman_number": 45,
            "customer_type": "DLR",
            "customer_class": "A",
            "active": True,
        },
        "credit": {
            "credit_limit": 1200.0,
            "balance": 1000.0,
            "raw_on_order": 300.0,
            "total_exposure": 1300.0,
            "available_credit": -100.0,
            "amount_over_limit": 100.0,
            "utilization_percent": 108.33,
            "terms_code": "1",
            "terms_description": "Due on the 10th",
        },
        "aging": {
            "future": 50.0,
            "current": 700.0,
            "days_30": 200.0,
            "days_60": 100.0,
            "days_90": -25.0,
            "days_120": 0.0,
            "past_due": 275.0,
            # Customer 360 currently double-counts past due in this field.
            # The Credit Risk service must not consume it.
            "total_aging": 987654321.25,
        },
        "activity": {
            "last_payment_amount": 750.0,
            "last_payment_date": "2026-08-01",
        },
    }


class FakeCustomerService:
    def __init__(self, summary: dict | None) -> None:
        self.summary_value = summary
        self.error: Exception | None = None

    def summary(self, customer_number: int) -> dict | None:
        del customer_number
        if self.error is not None:
            raise self.error
        return copy.deepcopy(self.summary_value)


class StepClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 6, 16, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        result = self.current
        self.current += timedelta(seconds=1)
        return result


class CreditRiskFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self._temporary_directory.name) / "credit-risk-test.db"
        )

        def connection_factory() -> sqlite3.Connection:
            return sqlite3.connect(
                self.database_path,
                timeout=5,
                check_same_thread=False,
            )

        self.repository = CreditRiskRepository(connection_factory)
        self.customer_service = FakeCustomerService(_customer_summary())
        self.clock = StepClock()
        self.ids = iter(("assessment-one", "assessment-two"))
        self.service = CreditRiskService(
            repository=self.repository,
            customer_summary_service=self.customer_service,
            clock=self.clock,
            id_factory=lambda: next(self.ids),
        )

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def test_initialization_and_band_seed_are_idempotent(self) -> None:
        self.repository.initialize()
        with closing(sqlite3.connect(self.database_path)) as connection:
            seeded_at = connection.execute(
                "SELECT seeded_at FROM credit_risk_band_sets"
            ).fetchone()[0]

        self.repository.initialize()
        configuration = self.service.list_bands()

        self.assertEqual(configuration.band_set.version, BAND_SET_VERSION)
        self.assertEqual(
            configuration.band_set.status,
            "product_owner_supplied_draft",
        )
        self.assertFalse(configuration.band_set.automated_policy)
        self.assertEqual(len(configuration.bands), 8)

        covered_ratings: list[int] = []
        for band in configuration.bands:
            covered_ratings.extend(
                range(band.rating_min, band.rating_max + 1)
            )
        self.assertEqual(covered_ratings, list(range(1, 11)))

        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM credit_risk_band_sets"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM credit_risk_bands"
                ).fetchone()[0],
                8,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT seeded_at FROM credit_risk_band_sets"
                ).fetchone()[0],
                seeded_at,
            )

    def test_customer_not_found_and_source_unavailable_are_distinct(self) -> None:
        self.customer_service.summary_value = None
        with self.assertRaises(CreditRiskCustomerNotFound):
            self.service.get_customer_risk(900000002)

        self.customer_service.error = RuntimeError("ERP timed out")
        with self.assertRaises(CreditRiskSourceUnavailable) as context:
            self.service.get_customer_risk(900000001)

        self.assertIn("read-only ERP facts", str(context.exception))
        self.assertIsInstance(context.exception.__cause__, RuntimeError)

    def test_cross_customer_source_evidence_fails_closed(self) -> None:
        self.customer_service.summary_value["customer_number"] = 900000002

        with self.assertRaises(CreditRiskSourceIntegrityError) as context:
            self.service.get_customer_risk(900000001)

        self.assertIn("requested customer 900000001", str(context.exception))
        history = self.service.list_assessments(900000001)
        self.assertEqual(history.count, 0)

    def test_partial_exposure_and_signed_aging_are_explicit(self) -> None:
        result = self.service.get_customer_risk(900000001)

        self.assertEqual(result.credit.open_ar, 1000.0)
        self.assertEqual(result.credit.erp_on_order_aggregate, 300.0)
        self.assertEqual(result.exposure.partial_exposure, 1300.0)
        self.assertEqual(result.exposure.partial_available_credit, -100.0)
        self.assertEqual(result.exposure.known_component_subtotal, 1000.0)
        self.assertIsNone(result.exposure.full_exposure)
        self.assertEqual(result.exposure.completeness, "partial")
        self.assertEqual(len(result.exposure.missing_required_components), 5)

        on_order = next(
            component
            for component in result.exposure.components
            if component.key == "erp_on_order_aggregate"
        )
        self.assertEqual(on_order.status, "available_unclassified")
        self.assertTrue(on_order.included_in_partial_calculation)
        self.assertFalse(on_order.required_for_full_exposure)

        self.assertEqual(result.aging.days_90, -25.0)
        self.assertEqual(result.aging.past_due, 275.0)
        self.assertEqual(result.aging.bucket_total, 1025.0)
        self.assertEqual(
            result.aging.open_ar_reconciliation_difference,
            -25.0,
        )
        self.assertNotEqual(result.aging.bucket_total, 987654321.25)

        self.assertEqual(result.payment.last_payment_amount, 750.0)
        self.assertEqual(result.payment.last_payment_status, "available")
        self.assertIsNone(result.payment.average_days_to_pay.value)
        self.assertEqual(
            result.payment.average_days_to_pay.status,
            "unavailable",
        )

    def test_negative_on_order_is_preserved_but_not_subtracted(self) -> None:
        self.customer_service.summary_value["credit"]["raw_on_order"] = -75.0
        result = self.service.get_customer_risk(900000001)

        self.assertEqual(result.credit.erp_on_order_aggregate, -75.0)
        self.assertEqual(result.exposure.partial_exposure, 1000.0)
        on_order = next(
            component
            for component in result.exposure.components
            if component.key == "erp_on_order_aggregate"
        )
        self.assertEqual(on_order.value, -75.0)
        self.assertEqual(on_order.calculation_value, 0.0)

    def test_required_numeric_source_facts_fail_closed(self) -> None:
        for section in ("general", "credit", "aging", "activity"):
            with self.subTest(section=section):
                self.customer_service.summary_value = _customer_summary()
                self.customer_service.summary_value[section] = None
                with self.assertRaises(CreditRiskSourceIntegrityError):
                    self.service.get_customer_risk(900000001)

        self.customer_service.summary_value = _customer_summary()
        self.customer_service.summary_value["customer_name"] = ""
        with self.assertRaises(CreditRiskSourceIntegrityError):
            self.service.get_customer_risk(900000001)

        cases = (
            ("credit", "balance", "missing"),
            ("credit", "credit_limit", None),
            ("credit", "raw_on_order", "not-a-number"),
            ("aging", "future", float("nan")),
            ("aging", "days_30", float("inf")),
            ("aging", "days_120", True),
        )

        for section, key, value in cases:
            with self.subTest(section=section, key=key, value=value):
                self.customer_service.summary_value = _customer_summary()
                source_section = self.customer_service.summary_value[section]
                if value == "missing":
                    source_section.pop(key)
                else:
                    source_section[key] = value

                with self.assertRaises(CreditRiskSourceIntegrityError):
                    self.service.get_customer_risk(900000001)

    def test_last_payment_evidence_states_are_honest(self) -> None:
        cases = (
            (
                {"last_payment_amount": 0.0, "last_payment_date": "2026-08-01"},
                "available",
                0.0,
                "2026-08-01",
            ),
            (
                {"last_payment_date": "2026-08-01"},
                "partial",
                None,
                "2026-08-01",
            ),
            (
                {"last_payment_amount": 125.0},
                "partial",
                125.0,
                None,
            ),
            (
                {"last_payment_amount": 125.0, "last_payment_date": "NOT-A-DATE"},
                "degraded",
                125.0,
                "NOT-A-DATE",
            ),
            (
                {"last_payment_amount": "invalid", "last_payment_date": "2026-08-01"},
                "degraded",
                None,
                "2026-08-01",
            ),
            ({}, "no_record_in_current_contract", None, None),
        )

        for activity, status, amount, payment_date in cases:
            with self.subTest(activity=activity):
                self.customer_service.summary_value = _customer_summary()
                self.customer_service.summary_value["activity"] = activity
                result = self.service.get_customer_risk(900000001)
                self.assertEqual(result.payment.last_payment_status, status)
                self.assertEqual(result.payment.last_payment_amount, amount)
                self.assertEqual(result.payment.last_payment_date, payment_date)
                self.assertTrue(result.payment.last_payment_explanation)

    def test_payment_history_gaps_are_not_fabricated(self) -> None:
        self.customer_service.summary_value["activity"] = {}
        result = self.service.get_customer_risk(900000001)

        self.assertIsNone(result.payment.last_payment_amount)
        self.assertIsNone(result.payment.last_payment_date)
        self.assertEqual(
            result.payment.last_payment_status,
            "no_record_in_current_contract",
        )
        for field_name in (
            "average_days_to_pay",
            "weighted_average_days_to_pay",
            "days_beyond_terms",
            "on_time_percentage",
            "late_payment_frequency",
            "largest_historical_delinquency",
        ):
            metric = getattr(result.payment, field_name)
            self.assertIsNone(metric.value)
            self.assertEqual(metric.status, "unavailable")
            self.assertIsNone(metric.source)

    def test_assessment_request_validation(self) -> None:
        valid = {
            "manual_rating": 6,
            "review_date": "2026-08-06",
            "next_review_date": "2026-09-06",
            "analyst_identity": "  Josh Corbit  ",
            "rationale": "  Exposure requires professional monitoring.  ",
        }
        parsed = AssessmentCreate(**valid)
        self.assertEqual(parsed.analyst_identity, "Josh Corbit")
        self.assertEqual(
            parsed.rationale,
            "Exposure requires professional monitoring.",
        )

        invalid_cases = (
            {**valid, "manual_rating": 0},
            {**valid, "manual_rating": 11},
            {**valid, "manual_rating": True},
            {**valid, "manual_rating": 6.0},
            {**valid, "manual_rating": 6.5},
            {**valid, "manual_rating": "6"},
            {**valid, "manual_rating": "rating 6"},
            {**valid, "analyst_identity": "   "},
            {**valid, "rationale": "\t"},
            {**valid, "evidence_snapshot": {"injected": True}},
            {**valid, "actor_authority_status": "verified"},
            {**valid, "band_set_version": "client-version"},
            {**valid, "created_at": "2020-01-01T00:00:00Z"},
            {
                **valid,
                "review_date": "2026-09-06",
                "next_review_date": "2026-08-06",
            },
        )
        for invalid in invalid_cases:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValidationError):
                    AssessmentCreate(**invalid)

    def test_assessments_are_append_only_and_reconstruct_exact_snapshots(
        self,
    ) -> None:
        first = self.service.create_assessment(
            900000001,
            AssessmentCreate(
                manual_rating=6,
                review_date=date(2026, 8, 6),
                next_review_date=date(2026, 9, 6),
                analyst_identity="Josh Corbit",
                rationale="Elevated exposure requires analyst review.",
            ),
        )

        self.customer_service.summary_value["credit"]["balance"] = 1200.0
        self.customer_service.summary_value["aging"]["days_60"] = 300.0
        second = self.service.create_assessment(
            900000001,
            AssessmentCreate(
                manual_rating=7,
                review_date=date(2026, 8, 7),
                next_review_date=date(2026, 8, 21),
                analyst_identity="Credit Manager",
                rationale="Exposure and signed aging evidence deteriorated.",
            ),
        )

        history = self.service.list_assessments(900000001)
        self.assertEqual(history.count, 2)
        self.assertEqual(
            [item.assessment_id for item in history.assessments],
            ["assessment-two", "assessment-one"],
        )
        self.assertEqual(
            first.evidence_snapshot["credit"]["open_ar"],
            1000.0,
        )
        self.assertEqual(
            second.evidence_snapshot["credit"]["open_ar"],
            1200.0,
        )
        self.assertEqual(first.band_set_version, BAND_SET_VERSION)
        self.assertEqual(first.band.meaning, "Elevated risk")
        self.assertEqual(second.band.meaning, "High risk")
        self.assertEqual(
            first.evidence_snapshot["risk_band_configuration"][
                "band_set"
            ]["version"],
            BAND_SET_VERSION,
        )
        self.assertEqual(
            len(
                first.evidence_snapshot["risk_band_configuration"][
                    "bands"
                ]
            ),
            8,
        )
        self.assertEqual(first.actor_identity_source, "operator_supplied")
        self.assertEqual(
            first.actor_authority_status,
            "not_independently_verified",
        )
        self.assertEqual(first.decision_effect, "none")
        self.assertEqual(len(first.evidence_snapshot_sha256), 64)
        self.assertEqual(
            first.evidence_snapshot_sha256,
            history.assessments[1].evidence_snapshot_sha256,
        )

        reopened = self.service.get_customer_risk(900000001)
        self.assertIsNotNone(reopened.latest_assessment)
        self.assertEqual(
            reopened.latest_assessment.assessment_id,
            "assessment-two",
        )

        for statement in (
            "UPDATE credit_risk_assessments SET rationale = 'changed'",
            "DELETE FROM credit_risk_assessments",
        ):
            connection = sqlite3.connect(self.database_path)
            try:
                with self.assertRaises(sqlite3.IntegrityError) as context:
                    connection.execute(statement)
                    connection.commit()
                self.assertIn("append-only", str(context.exception))
            finally:
                connection.rollback()
                connection.close()

        unchanged = self.service.list_assessments(900000001)
        self.assertEqual(unchanged.count, 2)
        self.assertEqual(
            unchanged.assessments[1].rationale,
            "Elevated exposure requires analyst review.",
        )

    def test_evidence_hash_detects_storage_tampering(self) -> None:
        created = self.service.create_assessment(
            900000001,
            AssessmentCreate(
                manual_rating=5,
                review_date=date(2026, 8, 6),
                next_review_date=date(2026, 9, 6),
                analyst_identity="Credit Analyst",
                rationale="Manual baseline assessment recorded.",
            ),
        )
        self.assertEqual(len(created.evidence_snapshot_sha256), 64)

        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                "DROP TRIGGER credit_risk_assessments_no_update"
            )
            connection.execute(
                """
                UPDATE credit_risk_assessments
                SET evidence_snapshot_json = '{"tampered":true}'
                WHERE assessment_id = ?
                """,
                (created.assessment_id,),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(AssessmentEvidenceIntegrityError):
            self.repository.get_assessment(created.assessment_id)

    def test_history_remains_available_without_live_erp(self) -> None:
        self.service.create_assessment(
            900000001,
            AssessmentCreate(
                manual_rating=5,
                review_date=date(2026, 8, 6),
                next_review_date=date(2026, 9, 6),
                analyst_identity="Credit Analyst",
                rationale="Manual baseline assessment recorded.",
            ),
        )
        self.customer_service.error = RuntimeError("ERP unavailable")

        history = self.service.list_assessments(900000001)
        self.assertEqual(history.count, 1)
        self.assertEqual(history.assessments[0].manual_rating, 5)
        with self.assertRaises(CreditRiskSourceUnavailable):
            self.service.get_customer_risk(900000001)


if __name__ == "__main__":
    unittest.main()
