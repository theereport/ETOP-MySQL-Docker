from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine

from data.mysql import _reset_engine_override, _set_engine_override
from modules.route_intelligence import repository as route_repository
from modules.route_intelligence import service as route_service

WEEKDAYS = [
    "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
]


class FakeFreightLogisticsService:
    def __init__(self, *, warehouses):
        self._warehouses = warehouses

    def list_warehouses(self):
        return SimpleNamespace(
            warehouses=[
                SimpleNamespace(warehouse_number=number, warehouse_location_name=name)
                for number, name in self._warehouses
            ]
        )


class RouteIntelligenceNetworkReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmpdir.name) / 'route.db'}"
        )
        _set_engine_override(self.engine)
        self.addCleanup(_reset_engine_override)
        self.addCleanup(self.engine.dispose)
        self.freight_service = FakeFreightLogisticsService(warehouses=[(41, "Dallas")])

    def _seed_week(
        self, warehouse_number, *, weight_capacity, p50_by_day, p90_by_day,
        status_by_day, sample_size=8,
    ):
        for day in WEEKDAYS:
            route_repository.upsert_capacity_assessment(warehouse_number, day, {
                "forecast_run_id": None,
                "sample_size": sample_size,
                "expected_weight": p50_by_day.get(day, 0.0),
                "expected_quantity": 0.0,
                "expected_stops": 0.0,
                "p50_weight": p50_by_day.get(day, 0.0),
                "p80_weight": p50_by_day.get(day, 0.0),
                "p90_weight": p90_by_day.get(day, p50_by_day.get(day, 0.0)),
                "weight_capacity": weight_capacity,
                "p90_utilization_pct": None,
                "status": status_by_day.get(day, "healthy"),
                "structural_review": False,
                "computed_at": "2026-09-05T00:00:00Z",
            })

    def test_warehouse_below_every_threshold_produces_no_candidate(self) -> None:
        self._seed_week(
            41, weight_capacity=1000.0,
            p50_by_day={d: 100.0 for d in WEEKDAYS},
            p90_by_day={d: 150.0 for d in WEEKDAYS},
            status_by_day={d: "healthy" for d in WEEKDAYS},
        )

        review = route_service.compute_network_review(freight_service=self.freight_service)

        self.assertEqual(review.status, "success")
        self.assertEqual(review.candidate_count, 0)
        self.assertEqual(review.candidates, [])

    def test_three_or_more_days_over_median_threshold_triggers_a_candidate(self) -> None:
        # Default median threshold is 85% - 3 days at 90% utilization
        # (p50=900 / capacity=1000) should trigger.
        p50 = {d: 200.0 for d in WEEKDAYS}
        for day in WEEKDAYS[:3]:
            p50[day] = 900.0
        self._seed_week(
            41, weight_capacity=1000.0, p50_by_day=p50,
            p90_by_day={d: v for d, v in p50.items()},
            status_by_day={d: "healthy" for d in WEEKDAYS},
        )

        review = route_service.compute_network_review(freight_service=self.freight_service)

        self.assertEqual(review.candidate_count, 1)
        candidate = review.candidates[0]
        self.assertEqual(candidate.warehouse_number, 41)
        self.assertIn("median_utilization_over_threshold", candidate.trigger_reasons)
        self.assertGreaterEqual(candidate.days_over_median_threshold, 3)

    def test_two_or_more_split_recommended_days_triggers_a_candidate(self) -> None:
        status_by_day = {d: "healthy" for d in WEEKDAYS}
        status_by_day["Monday"] = "split_recommended"
        status_by_day["Tuesday"] = "split_recommended"
        self._seed_week(
            41, weight_capacity=1000.0,
            p50_by_day={d: 100.0 for d in WEEKDAYS},
            p90_by_day={d: 100.0 for d in WEEKDAYS},
            status_by_day=status_by_day,
        )

        review = route_service.compute_network_review(freight_service=self.freight_service)

        self.assertEqual(review.candidate_count, 1)
        candidate = review.candidates[0]
        self.assertIn("p90_over_threshold_at_least_twice", candidate.trigger_reasons)
        self.assertIn("forecast_shows_recurring_overload", candidate.trigger_reasons)
        self.assertEqual(candidate.days_over_p90_threshold, 2)

    def test_unavailable_fields_are_always_reported(self) -> None:
        status_by_day = {d: "healthy" for d in WEEKDAYS}
        status_by_day["Monday"] = "split_recommended"
        status_by_day["Tuesday"] = "split_recommended"
        self._seed_week(
            41, weight_capacity=1000.0,
            p50_by_day={d: 100.0 for d in WEEKDAYS},
            p90_by_day={d: 100.0 for d in WEEKDAYS},
            status_by_day=status_by_day,
        )

        review = route_service.compute_network_review(freight_service=self.freight_service)

        candidate = review.candidates[0]
        for field in (
            "proposed_customers", "territory", "expected_miles_hours",
            "expected_cost", "service_level_impact",
        ):
            self.assertIn(field, candidate.unavailable_fields)

    def test_confidence_reflects_the_minimum_sample_size(self) -> None:
        status_by_day = {d: "healthy" for d in WEEKDAYS}
        status_by_day["Monday"] = "split_recommended"
        status_by_day["Tuesday"] = "split_recommended"
        self._seed_week(
            41, weight_capacity=1000.0,
            p50_by_day={d: 100.0 for d in WEEKDAYS},
            p90_by_day={d: 100.0 for d in WEEKDAYS},
            status_by_day=status_by_day, sample_size=2,
        )

        review = route_service.compute_network_review(freight_service=self.freight_service)

        self.assertEqual(review.candidates[0].confidence, "low")

    def test_configured_threshold_overrides_the_default(self) -> None:
        route_service.save_business_rule(
            "network_review_min_days_over_median", {"rule_value": "1"}
        )
        p50 = {d: 200.0 for d in WEEKDAYS}
        p50["Monday"] = 900.0  # only 1 day over 85% utilization
        self._seed_week(
            41, weight_capacity=1000.0, p50_by_day=p50,
            p90_by_day=p50, status_by_day={d: "healthy" for d in WEEKDAYS},
        )

        review = route_service.compute_network_review(freight_service=self.freight_service)

        # Below the hardcoded default (3 days) but above the configured
        # override (1 day) - should trigger with the configured threshold.
        self.assertEqual(review.candidate_count, 1)

    def test_get_network_review_reproduces_the_same_candidates(self) -> None:
        status_by_day = {d: "healthy" for d in WEEKDAYS}
        status_by_day["Monday"] = "split_recommended"
        status_by_day["Tuesday"] = "split_recommended"
        self._seed_week(
            41, weight_capacity=1000.0,
            p50_by_day={d: 100.0 for d in WEEKDAYS},
            p90_by_day={d: 100.0 for d in WEEKDAYS},
            status_by_day=status_by_day,
        )

        review = route_service.compute_network_review(freight_service=self.freight_service)
        reread = route_service.get_network_review(
            review.run_id, freight_service=self.freight_service,
        )

        self.assertEqual(len(reread.candidates), len(review.candidates))
        self.assertEqual(reread.status, "success")


if __name__ == "__main__":
    unittest.main()
