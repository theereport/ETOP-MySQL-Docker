from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine

from data.mysql import _reset_engine_override, _set_engine_override
from modules.route_intelligence import repository as route_repository
from modules.route_intelligence import service as route_service


class RouteIntelligenceOptimizerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmpdir.name) / 'route.db'}"
        )
        _set_engine_override(self.engine)
        self.addCleanup(_reset_engine_override)
        self.addCleanup(self.engine.dispose)

    def _patch_customers(self, rows: list[dict]):
        return patch.object(
            route_repository, "madden_database", SimpleNamespace(
                fetch_all=lambda *_args, **_kwargs: rows,
            ),
        )

    def _customer_row(self, number: str, store_number: int) -> dict:
        return {
            "CUNUMBER": number, "CUNAME": f"Customer {number}",
            "CUROUTECD": "12", "CUSTORENUM": store_number,
        }

    def _vehicle_with_capacity(self, *, warehouse_number, max_stops=None):
        vehicle = route_service.create_vehicle(
            {"unit_number": f"T-{warehouse_number}", "home_warehouse_number": warehouse_number}
        )
        route_service.add_vehicle_capacity(
            vehicle.vehicle_id, {"max_stops": max_stops} if max_stops else {},
        )
        return vehicle

    # --- readiness -----------------------------------------------------

    def test_readiness_reports_real_counts(self) -> None:
        route_service.save_customer_profile("1", {"latitude": 40.7, "longitude": -84.9})
        route_service.save_customer_profile("2", {})  # no coordinates
        self._vehicle_with_capacity(warehouse_number=41)
        route_service.create_vehicle({"unit_number": "no-cap", "home_warehouse_number": 41})

        with self._patch_customers([
            self._customer_row("1", 41), self._customer_row("2", 41),
        ]):
            readiness = route_service.compute_optimization_readiness(41)

        self.assertFalse(readiness.has_location)
        self.assertEqual(readiness.customer_count, 2)
        self.assertEqual(readiness.customers_with_location_count, 1)
        self.assertEqual(readiness.vehicle_count, 2)
        self.assertEqual(readiness.vehicles_with_capacity_count, 1)

    # --- insufficient-data gates -----------------------------------------

    def test_insufficient_data_when_warehouse_has_no_location(self) -> None:
        with self._patch_customers([self._customer_row("1", 41)]):
            run = route_service.compute_route_optimization(41, date(2026, 9, 10))

        self.assertEqual(run.status, "insufficient_data")
        self.assertIn("no saved location", run.message)

    def test_insufficient_data_when_no_customer_has_coordinates(self) -> None:
        route_service.save_warehouse_location(41, {"latitude": 40.74, "longitude": -84.94})
        route_service.save_customer_profile("1", {})  # no coordinates

        with self._patch_customers([self._customer_row("1", 41)]):
            run = route_service.compute_route_optimization(41, date(2026, 9, 10))

        self.assertEqual(run.status, "insufficient_data")
        self.assertIn("coordinates", run.message)

    def test_insufficient_data_when_no_vehicle_has_capacity(self) -> None:
        route_service.save_warehouse_location(41, {"latitude": 40.74, "longitude": -84.94})
        route_service.save_customer_profile("1", {"latitude": 40.75, "longitude": -84.93})
        route_service.create_vehicle({"unit_number": "no-cap", "home_warehouse_number": 41})

        with self._patch_customers([self._customer_row("1", 41)]):
            run = route_service.compute_route_optimization(41, date(2026, 9, 10))

        self.assertEqual(run.status, "insufficient_data")
        self.assertIn("capacity", run.message)

    # --- successful two-scenario run ---------------------------------------

    def test_successful_run_produces_baseline_and_backup_scenarios(self) -> None:
        route_service.save_warehouse_location(41, {"latitude": 40.7440, "longitude": -84.9401})
        customers = [
            ("1", 40.75, -84.93), ("2", 40.76, -84.92), ("3", 40.77, -84.91),
        ]
        for number, lat, lon in customers:
            route_service.save_customer_profile(number, {"latitude": lat, "longitude": lon})
        self._vehicle_with_capacity(warehouse_number=41, max_stops=2)
        self._vehicle_with_capacity(warehouse_number=41, max_stops=2)

        with self._patch_customers([self._customer_row(n, 41) for n, _, _ in customers]):
            run = route_service.compute_route_optimization(41, date(2026, 9, 10))

        self.assertEqual(run.status, "success")
        self.assertEqual(run.customer_count, 3)
        self.assertEqual(run.customers_with_location_count, 3)
        self.assertEqual(run.vehicles_with_capacity_count, 2)

        scenarios = {plan.scenario for plan in run.plans}
        self.assertEqual(scenarios, {"baseline", "with_backup"})

        baseline_stops = {
            stop for plan in run.plans if plan.scenario == "baseline"
            for stop in plan.stop_sequence
        }
        self.assertEqual(baseline_stops, {"1", "2", "3"})

        with_backup_slots = [p for p in run.plans if p.scenario == "with_backup"]
        self.assertEqual(
            {p.vehicle_slot for p in with_backup_slots} & {3}, {3},
            "with_backup scenario should include a 3rd (hypothetical) vehicle slot",
        )
        for plan in run.plans:
            if plan.stop_count > 0:
                self.assertIsNotNone(plan.total_distance_miles)
                self.assertGreaterEqual(plan.total_distance_miles, 0.0)

        # Reading the run back later must reproduce the same plans.
        reread = route_service.get_optimization_run(run.run_id)
        self.assertEqual(len(reread.plans), len(run.plans))

    def test_unassigned_stops_reported_when_capacity_is_too_small(self) -> None:
        route_service.save_warehouse_location(41, {"latitude": 40.7440, "longitude": -84.9401})
        customers = [
            ("1", 40.75, -84.93), ("2", 40.76, -84.92), ("3", 40.77, -84.91),
        ]
        for number, lat, lon in customers:
            route_service.save_customer_profile(number, {"latitude": lat, "longitude": lon})
        self._vehicle_with_capacity(warehouse_number=41, max_stops=1)

        with self._patch_customers([self._customer_row(n, 41) for n, _, _ in customers]):
            run = route_service.compute_route_optimization(41, date(2026, 9, 10))

        self.assertEqual(run.status, "success")
        self.assertIn("Unassigned stops", run.message)

    # --- repository CRUD --------------------------------------------------

    def test_warehouse_location_save_and_get_round_trip(self) -> None:
        route_repository.save_warehouse_location(
            41, {"latitude": 40.74, "longitude": -84.94, "updated_by": "tester"}
        )
        row = route_repository.get_warehouse_location(41)
        self.assertEqual(row["latitude"], 40.74)
        self.assertEqual(row["longitude"], -84.94)

        # Saving again updates in place, not a second row.
        route_repository.save_warehouse_location(41, {"latitude": 41.0, "longitude": -85.0})
        self.assertEqual(len(route_repository.list_warehouse_locations()), 1)

    def test_optimization_run_and_plan_round_trip(self) -> None:
        run = route_repository.save_optimization_run({
            "run_at": "2026-09-10T00:00:00Z", "warehouse_number": 41,
            "target_date": "2026-09-10", "status": "running", "message": "in progress",
        })
        route_repository.save_optimization_plan({
            "run_id": run["run_id"], "scenario": "baseline", "vehicle_slot": 1,
            "assigned_vehicle_id": None, "stop_sequence_json": '["1","2"]',
            "stop_count": 2, "total_distance_miles": 12.5, "total_time_minutes": 18.0,
        })
        updated = route_repository.update_optimization_run(
            run["run_id"], {"status": "success", "message": "done"},
        )
        self.assertEqual(updated["status"], "success")

        plans = route_repository.list_optimization_plans_for_run(run["run_id"])
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["stop_count"], 2)


if __name__ == "__main__":
    unittest.main()
