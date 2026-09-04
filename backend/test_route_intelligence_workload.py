from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine

from data.mysql import _reset_engine_override, _set_engine_override
from modules.route_intelligence import repository as route_repository
from modules.route_intelligence import service as route_service


class FakeFreightLogisticsService:
    """Stands in for freight_logistics_service - only the two shapes
    compute_workload_summary actually reads (warehouses.warehouses[] and
    get_load_lines_for_warehouse(...).lines[].weight/.quantity/.route) are
    populated. Date filtering is real freight_logistics' job, already
    covered by its own tests - this fake just returns whatever's
    registered for a warehouse number."""

    def __init__(
        self,
        *,
        warehouses: list[tuple[int, str]],
        load_lines_by_warehouse: dict[int, list[SimpleNamespace]] | None = None,
    ):
        self._warehouses = warehouses
        self._load_lines_by_warehouse = load_lines_by_warehouse or {}

    def list_warehouses(self):
        return SimpleNamespace(
            warehouses=[
                SimpleNamespace(warehouse_number=number, warehouse_location_name=name)
                for number, name in self._warehouses
            ]
        )

    def get_load_lines_for_warehouse(self, warehouse_number, *, date_from, date_to):
        return SimpleNamespace(
            lines=self._load_lines_by_warehouse.get(warehouse_number, [])
        )


def _load_line(*, weight: float | None, quantity: float | None, route: str) -> SimpleNamespace:
    return SimpleNamespace(weight=weight, quantity=quantity, route=route)


class RouteIntelligenceWorkloadTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmpdir.name) / 'route.db'}"
        )
        _set_engine_override(self.engine)
        self.addCleanup(_reset_engine_override)
        self.addCleanup(self.engine.dispose)

    # --- get_current_vehicle_capacity ------------------------------------

    def test_current_capacity_picks_the_latest_effective_date(self) -> None:
        vehicle = route_service.create_vehicle({"unit_number": "T-101"})
        route_service.add_vehicle_capacity(
            vehicle.vehicle_id,
            {"weight_capacity": 1000.0, "effective_date": "2026-01-01"},
        )
        route_service.add_vehicle_capacity(
            vehicle.vehicle_id,
            {"weight_capacity": 2000.0, "effective_date": "2026-06-01"},
        )

        current = route_repository.get_current_vehicle_capacity(vehicle.vehicle_id)

        self.assertIsNotNone(current)
        self.assertEqual(current["weight_capacity"], 2000.0)

    def test_current_capacity_is_none_when_vehicle_has_no_capacity_rows(self) -> None:
        vehicle = route_service.create_vehicle({"unit_number": "T-101"})

        self.assertIsNone(
            route_repository.get_current_vehicle_capacity(vehicle.vehicle_id)
        )

    # --- compute_workload_summary -----------------------------------------

    def test_workload_summary_computes_utilization_and_ok_status(self) -> None:
        vehicle = route_service.create_vehicle(
            {"unit_number": "T-101", "home_warehouse_number": 41}
        )
        route_service.add_vehicle_capacity(
            vehicle.vehicle_id, {"weight_capacity": 1000.0}
        )
        freight_service = FakeFreightLogisticsService(
            warehouses=[(41, "Dallas")],
            load_lines_by_warehouse={
                41: [_load_line(weight=400.0, quantity=10.0, route="R1")]
            },
        )

        summary = route_service.compute_workload_summary(
            date(2026, 9, 1), date(2026, 9, 2), freight_service=freight_service,
        )

        self.assertEqual(len(summary.warehouses), 1)
        warehouse = summary.warehouses[0]
        self.assertEqual(warehouse.warehouse_number, 41)
        self.assertEqual(warehouse.vehicle_count, 1)
        self.assertEqual(warehouse.total_weight_capacity, 1000.0)
        self.assertEqual(warehouse.total_weight_demand, 400.0)
        self.assertEqual(warehouse.route_count_with_activity, 1)
        self.assertEqual(warehouse.weight_utilization_pct, 40.0)
        self.assertEqual(warehouse.status, "ok")

    def test_workload_summary_flags_warning_at_default_threshold(self) -> None:
        vehicle = route_service.create_vehicle(
            {"unit_number": "T-101", "home_warehouse_number": 41}
        )
        route_service.add_vehicle_capacity(
            vehicle.vehicle_id, {"weight_capacity": 1000.0}
        )
        freight_service = FakeFreightLogisticsService(
            warehouses=[(41, "Dallas")],
            load_lines_by_warehouse={
                41: [_load_line(weight=850.0, quantity=10.0, route="R1")]
            },
        )

        summary = route_service.compute_workload_summary(
            date(2026, 9, 1), date(2026, 9, 2), freight_service=freight_service,
        )

        self.assertEqual(summary.warehouses[0].status, "warning")

    def test_workload_summary_flags_critical_at_default_threshold(self) -> None:
        vehicle = route_service.create_vehicle(
            {"unit_number": "T-101", "home_warehouse_number": 41}
        )
        route_service.add_vehicle_capacity(
            vehicle.vehicle_id, {"weight_capacity": 1000.0}
        )
        freight_service = FakeFreightLogisticsService(
            warehouses=[(41, "Dallas")],
            load_lines_by_warehouse={
                41: [_load_line(weight=1200.0, quantity=10.0, route="R1")]
            },
        )

        summary = route_service.compute_workload_summary(
            date(2026, 9, 1), date(2026, 9, 2), freight_service=freight_service,
        )

        self.assertEqual(summary.warehouses[0].status, "critical")

    def test_workload_summary_status_is_unknown_with_no_capacity_data(self) -> None:
        # No vehicles at all home-based at this warehouse - capacity is 0,
        # so a utilization percentage can't be computed. Must not raise a
        # divide-by-zero and must not be silently reported as "ok".
        freight_service = FakeFreightLogisticsService(
            warehouses=[(41, "Dallas")],
            load_lines_by_warehouse={
                41: [_load_line(weight=400.0, quantity=10.0, route="R1")]
            },
        )

        summary = route_service.compute_workload_summary(
            date(2026, 9, 1), date(2026, 9, 2), freight_service=freight_service,
        )

        warehouse = summary.warehouses[0]
        self.assertEqual(warehouse.vehicle_count, 0)
        self.assertIsNone(warehouse.weight_utilization_pct)
        self.assertEqual(warehouse.status, "unknown")

    def test_workload_summary_ignores_inactive_vehicles(self) -> None:
        vehicle = route_service.create_vehicle(
            {"unit_number": "T-101", "home_warehouse_number": 41, "active": False}
        )
        route_service.add_vehicle_capacity(
            vehicle.vehicle_id, {"weight_capacity": 1000.0}
        )
        freight_service = FakeFreightLogisticsService(warehouses=[(41, "Dallas")])

        summary = route_service.compute_workload_summary(
            date(2026, 9, 1), date(2026, 9, 2), freight_service=freight_service,
        )

        self.assertEqual(summary.warehouses[0].vehicle_count, 0)
        self.assertEqual(summary.warehouses[0].total_weight_capacity, 0.0)

    def test_workload_summary_honors_a_configured_threshold(self) -> None:
        route_service.save_business_rule(
            "workload_warning_threshold_pct", {"rule_value": "30"}
        )
        vehicle = route_service.create_vehicle(
            {"unit_number": "T-101", "home_warehouse_number": 41}
        )
        route_service.add_vehicle_capacity(
            vehicle.vehicle_id, {"weight_capacity": 1000.0}
        )
        freight_service = FakeFreightLogisticsService(
            warehouses=[(41, "Dallas")],
            load_lines_by_warehouse={
                41: [_load_line(weight=400.0, quantity=10.0, route="R1")]
            },
        )

        summary = route_service.compute_workload_summary(
            date(2026, 9, 1), date(2026, 9, 2), freight_service=freight_service,
        )

        # 40% utilization is below the 80% hardcoded default (would be
        # "ok") but above the 30% configured threshold ("warning").
        self.assertEqual(summary.warehouses[0].status, "warning")

    def test_workload_summary_includes_a_warehouse_freight_logistics_does_not_list(
        self,
    ) -> None:
        # freight_logistics's own warehouse master can be missing real
        # warehouse numbers (confirmed live: WH_DASHBOARD_LOCATIONS only
        # covers 17 of 51 real K&M warehouses) - a vehicle home-based at
        # an unlisted warehouse number must still show up in the report,
        # not be silently dropped because it's absent from
        # list_warehouses().
        vehicle = route_service.create_vehicle(
            {"unit_number": "T-101", "home_warehouse_number": 999}
        )
        route_service.add_vehicle_capacity(
            vehicle.vehicle_id, {"weight_capacity": 1000.0}
        )
        freight_service = FakeFreightLogisticsService(warehouses=[(41, "Dallas")])

        summary = route_service.compute_workload_summary(
            date(2026, 9, 1), date(2026, 9, 2), freight_service=freight_service,
        )

        warehouse_numbers = {w.warehouse_number for w in summary.warehouses}
        self.assertIn(999, warehouse_numbers)
        unlisted = next(w for w in summary.warehouses if w.warehouse_number == 999)
        self.assertEqual(unlisted.warehouse_location_name, "")
        self.assertEqual(unlisted.vehicle_count, 1)
        self.assertEqual(unlisted.total_weight_capacity, 1000.0)

    # --- compute_vehicle_performance ---------------------------------------

    def test_vehicle_performance_aggregates_distance_and_run_count(self) -> None:
        vehicle = route_service.create_vehicle({"unit_number": "T-101"})
        route_repository.upsert_actual_run(
            "trip-1",
            {
                "vehicle_id": vehicle.vehicle_id, "driver_id": None,
                "start_time": "2026-09-01T08:00:00Z", "end_time": None,
                "start_latitude": None, "start_longitude": None,
                "end_latitude": None, "end_longitude": None,
                "distance_meters": 1000.0, "completion_status": "completed",
                "ingested_at": "2026-09-01T09:00:00Z",
            },
        )
        route_repository.upsert_actual_run(
            "trip-2",
            {
                "vehicle_id": vehicle.vehicle_id, "driver_id": None,
                "start_time": "2026-09-01T14:00:00Z", "end_time": None,
                "start_latitude": None, "start_longitude": None,
                "end_latitude": None, "end_longitude": None,
                "distance_meters": 2000.0, "completion_status": "completed",
                "ingested_at": "2026-09-01T15:00:00Z",
            },
        )

        report = route_service.compute_vehicle_performance(
            date(2026, 9, 1), date(2026, 9, 2)
        )

        self.assertEqual(len(report.vehicles), 1)
        performance = report.vehicles[0]
        self.assertEqual(performance.unit_number, "T-101")
        self.assertEqual(performance.run_count, 2)
        self.assertEqual(performance.total_distance_meters, 3000.0)
        self.assertEqual(performance.average_distance_meters, 1500.0)

    def test_vehicle_performance_excludes_runs_outside_the_date_range(self) -> None:
        vehicle = route_service.create_vehicle({"unit_number": "T-101"})
        route_repository.upsert_actual_run(
            "trip-1",
            {
                "vehicle_id": vehicle.vehicle_id, "driver_id": None,
                "start_time": "2026-09-10T08:00:00Z", "end_time": None,
                "start_latitude": None, "start_longitude": None,
                "end_latitude": None, "end_longitude": None,
                "distance_meters": 1000.0, "completion_status": "completed",
                "ingested_at": "2026-09-10T09:00:00Z",
            },
        )

        report = route_service.compute_vehicle_performance(
            date(2026, 9, 1), date(2026, 9, 2)
        )

        self.assertEqual(report.vehicles, [])

    def test_vehicle_performance_excludes_trips_with_no_resolved_vehicle(self) -> None:
        route_repository.upsert_actual_run(
            "trip-1",
            {
                "vehicle_id": None, "driver_id": None,
                "start_time": "2026-09-01T08:00:00Z", "end_time": None,
                "start_latitude": None, "start_longitude": None,
                "end_latitude": None, "end_longitude": None,
                "distance_meters": 1000.0, "completion_status": "completed",
                "ingested_at": "2026-09-01T09:00:00Z",
            },
        )

        report = route_service.compute_vehicle_performance(
            date(2026, 9, 1), date(2026, 9, 2)
        )

        self.assertEqual(report.vehicles, [])


if __name__ == "__main__":
    unittest.main()
