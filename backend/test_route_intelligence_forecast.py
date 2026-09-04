from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine

from data.mysql import _reset_engine_override, _set_engine_override
from modules.route_intelligence import repository as route_repository
from modules.route_intelligence import service as route_service


class FakeFreightLogisticsService:
    """Stands in for freight_logistics_service - only the shapes
    compute_capacity_forecast actually reads are populated:
    warehouses.warehouses[] and
    get_daily_load_totals_for_warehouse(...).totals[] with
    .load_date/.route_count/.total_weight/.total_quantity (the server-
    side-aggregated-by-day call, NOT the raw-line
    get_load_lines_for_warehouse - see route_intelligence/service.py's
    _build_historical_demand_points docstring for why)."""

    def __init__(
        self,
        *,
        warehouses: list[tuple[int, str]],
        daily_totals_by_warehouse: dict[int, list[SimpleNamespace]] | None = None,
        raise_for_warehouse: int | None = None,
    ):
        self._warehouses = warehouses
        self._daily_totals_by_warehouse = daily_totals_by_warehouse or {}
        self._raise_for_warehouse = raise_for_warehouse

    def list_warehouses(self):
        return SimpleNamespace(
            warehouses=[
                SimpleNamespace(warehouse_number=number, warehouse_location_name=name)
                for number, name in self._warehouses
            ]
        )

    def get_daily_load_totals_for_warehouse(self, warehouse_number, *, date_from, date_to):
        if warehouse_number == self._raise_for_warehouse:
            raise RuntimeError("MaddenCo connection failed")
        return SimpleNamespace(
            totals=self._daily_totals_by_warehouse.get(warehouse_number, [])
        )


def _daily_total(
    *, weight: float, quantity: float, route_count: int = 1, load_date: str
) -> SimpleNamespace:
    return SimpleNamespace(
        load_date=load_date, route_count=route_count,
        total_weight=weight, total_quantity=quantity,
    )


class RouteIntelligenceForecastTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmpdir.name) / 'route.db'}"
        )
        _set_engine_override(self.engine)
        self.addCleanup(_reset_engine_override)
        self.addCleanup(self.engine.dispose)

    def _vehicle_with_capacity(self, *, warehouse_number, weight_capacity):
        vehicle = route_service.create_vehicle(
            {"unit_number": "T-101", "home_warehouse_number": warehouse_number}
        )
        route_service.add_vehicle_capacity(
            vehicle.vehicle_id, {"weight_capacity": weight_capacity}
        )
        return vehicle

    # --- happy path ---------------------------------------------------

    def test_compute_and_list_capacity_forecast(self) -> None:
        self._vehicle_with_capacity(warehouse_number=41, weight_capacity=1000.0)
        freight_service = FakeFreightLogisticsService(
            warehouses=[(41, "Dallas")],
            daily_totals_by_warehouse={
                41: [
                    # Two Mondays, weights 400 and 600 -> mean 500,
                    # p50=500, p90 interpolated toward 600.
                    _daily_total(weight=400.0, quantity=10.0, load_date="2026-08-03"),
                    _daily_total(weight=600.0, quantity=12.0, load_date="2026-08-10"),
                ]
            },
        )

        run = route_service.compute_capacity_forecast(
            weeks_back=8, warehouse_number=41, freight_service=freight_service,
        )
        self.assertEqual(run.status, "success")
        self.assertEqual(run.warehouse_count, 1)

        assessments = route_service.list_capacity_forecasts(freight_service=freight_service)
        monday = next(a for a in assessments if a.day_of_week == "Monday")
        self.assertEqual(monday.warehouse_number, 41)
        self.assertEqual(monday.sample_size, 2)
        self.assertEqual(monday.expected_weight, 500.0)
        self.assertEqual(monday.weight_capacity, 1000.0)
        self.assertIsNotNone(monday.p90_utilization_pct)

    def test_forecast_run_status_reflects_the_latest_run(self) -> None:
        self.assertEqual(route_service.get_forecast_run_status().status, "")

        freight_service = FakeFreightLogisticsService(warehouses=[(41, "Dallas")])
        route_service.compute_capacity_forecast(
            weeks_back=4, warehouse_number=41, freight_service=freight_service,
        )

        status = route_service.get_forecast_run_status()
        self.assertEqual(status.status, "success")
        self.assertEqual(status.weeks_of_history, 4)

    # --- status classification -----------------------------------------

    def _assessment_for(self, freight_service, warehouse_number=41):
        route_service.compute_capacity_forecast(
            weeks_back=8, warehouse_number=warehouse_number, freight_service=freight_service,
        )
        assessments = route_service.list_capacity_forecasts(freight_service=freight_service)
        return next(a for a in assessments if a.day_of_week == "Monday")

    def test_status_is_healthy_below_watch_threshold(self) -> None:
        self._vehicle_with_capacity(warehouse_number=41, weight_capacity=1000.0)
        freight_service = FakeFreightLogisticsService(
            warehouses=[(41, "Dallas")],
            daily_totals_by_warehouse={
                41: [_daily_total(weight=500.0, quantity=1.0, load_date="2026-08-03")]
            },
        )
        self.assertEqual(self._assessment_for(freight_service).status, "healthy")

    def test_status_is_watch_between_80_and_90_pct(self) -> None:
        self._vehicle_with_capacity(warehouse_number=41, weight_capacity=1000.0)
        freight_service = FakeFreightLogisticsService(
            warehouses=[(41, "Dallas")],
            daily_totals_by_warehouse={
                41: [_daily_total(weight=850.0, quantity=1.0, load_date="2026-08-03")]
            },
        )
        self.assertEqual(self._assessment_for(freight_service).status, "watch")

    def test_status_is_backup_likely_between_90_and_100_pct(self) -> None:
        self._vehicle_with_capacity(warehouse_number=41, weight_capacity=1000.0)
        freight_service = FakeFreightLogisticsService(
            warehouses=[(41, "Dallas")],
            daily_totals_by_warehouse={
                41: [_daily_total(weight=950.0, quantity=1.0, load_date="2026-08-03")]
            },
        )
        self.assertEqual(self._assessment_for(freight_service).status, "backup_likely")

    def test_status_is_split_recommended_at_or_above_100_pct(self) -> None:
        self._vehicle_with_capacity(warehouse_number=41, weight_capacity=1000.0)
        freight_service = FakeFreightLogisticsService(
            warehouses=[(41, "Dallas")],
            daily_totals_by_warehouse={
                41: [_daily_total(weight=1200.0, quantity=1.0, load_date="2026-08-03")]
            },
        )
        self.assertEqual(self._assessment_for(freight_service).status, "split_recommended")

    def test_status_is_unknown_with_no_capacity_data(self) -> None:
        # No vehicle at all at this warehouse - capacity is 0, so a
        # utilization percentage can't be computed. Must not divide by
        # zero and must not default to "healthy".
        freight_service = FakeFreightLogisticsService(
            warehouses=[(41, "Dallas")],
            daily_totals_by_warehouse={
                41: [_daily_total(weight=500.0, quantity=1.0, load_date="2026-08-03")]
            },
        )
        assessment = self._assessment_for(freight_service)
        self.assertIsNone(assessment.p90_utilization_pct)
        self.assertEqual(assessment.status, "unknown")

    def test_configured_threshold_overrides_the_default(self) -> None:
        route_service.save_business_rule(
            "forecast_watch_threshold_pct", {"rule_value": "30"}
        )
        self._vehicle_with_capacity(warehouse_number=41, weight_capacity=1000.0)
        freight_service = FakeFreightLogisticsService(
            warehouses=[(41, "Dallas")],
            daily_totals_by_warehouse={
                41: [_daily_total(weight=400.0, quantity=1.0, load_date="2026-08-03")]
            },
        )
        # 40% utilization is below the 80% hardcoded default ("healthy")
        # but above the configured 30% threshold ("watch").
        self.assertEqual(self._assessment_for(freight_service).status, "watch")

    # --- structural review -----------------------------------------------

    def test_structural_review_flags_recurring_historical_overload(self) -> None:
        self._vehicle_with_capacity(warehouse_number=41, weight_capacity=1000.0)
        freight_service = FakeFreightLogisticsService(
            warehouses=[(41, "Dallas")],
            daily_totals_by_warehouse={
                41: [
                    # Three historical Mondays already over the current
                    # 1000 capacity - a real recurring pattern, not a guess.
                    _daily_total(weight=1100.0, quantity=1.0, load_date="2026-08-03"),
                    _daily_total(weight=1200.0, quantity=1.0, load_date="2026-08-10"),
                    _daily_total(weight=1300.0, quantity=1.0, load_date="2026-08-17"),
                ]
            },
        )
        self.assertTrue(self._assessment_for(freight_service).structural_review)

    def test_structural_review_is_false_below_the_occurrence_threshold(self) -> None:
        self._vehicle_with_capacity(warehouse_number=41, weight_capacity=1000.0)
        freight_service = FakeFreightLogisticsService(
            warehouses=[(41, "Dallas")],
            daily_totals_by_warehouse={
                41: [
                    # Only one historical Monday over capacity - below the
                    # default min-occurrences-of-2 threshold.
                    _daily_total(weight=1100.0, quantity=1.0, load_date="2026-08-03"),
                    _daily_total(weight=500.0, quantity=1.0, load_date="2026-08-10"),
                ]
            },
        )
        self.assertFalse(self._assessment_for(freight_service).structural_review)

    # --- failure handling --------------------------------------------------

    def test_a_maddenco_failure_marks_the_run_failed_and_raises(self) -> None:
        freight_service = FakeFreightLogisticsService(
            warehouses=[(41, "Dallas")], raise_for_warehouse=41,
        )
        with self.assertRaises(Exception):
            route_service.compute_capacity_forecast(
                weeks_back=8, warehouse_number=41, freight_service=freight_service,
            )
        status = route_service.get_forecast_run_status()
        self.assertEqual(status.status, "failed")

    # --- repository upsert behavior ----------------------------------------

    def test_upsert_capacity_assessment_overwrites_not_duplicates(self) -> None:
        route_repository.upsert_capacity_assessment(
            41, "Monday", {
                "forecast_run_id": None, "sample_size": 1,
                "expected_weight": 100.0, "expected_quantity": 1.0,
                "expected_stops": 1.0, "p50_weight": 100.0, "p80_weight": 100.0,
                "p90_weight": 100.0, "weight_capacity": 0.0,
                "p90_utilization_pct": None, "status": "unknown",
                "structural_review": False, "computed_at": "2026-01-01T00:00:00",
            },
        )
        route_repository.upsert_capacity_assessment(
            41, "Monday", {
                "forecast_run_id": None, "sample_size": 2,
                "expected_weight": 200.0, "expected_quantity": 2.0,
                "expected_stops": 2.0, "p50_weight": 200.0, "p80_weight": 200.0,
                "p90_weight": 200.0, "weight_capacity": 0.0,
                "p90_utilization_pct": None, "status": "unknown",
                "structural_review": False, "computed_at": "2026-01-02T00:00:00",
            },
        )
        rows = route_repository.list_capacity_assessments()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sample_size"], 2)


if __name__ == "__main__":
    unittest.main()
