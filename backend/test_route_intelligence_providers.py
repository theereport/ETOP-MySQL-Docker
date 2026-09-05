from __future__ import annotations

import unittest
from datetime import date

from modules.route_intelligence.providers.forecast_provider import (
    HistoricalDemandPoint,
    SimpleDayOfWeekForecastProvider,
    _percentile,
)
from modules.route_intelligence.providers.routing_solver_provider import (
    OrToolsRoutingSolverProvider,
    SolverStop,
    SolverVehicle,
    UnconfiguredRoutingSolverProvider,
    get_routing_solver_provider,
)
from modules.route_intelligence.providers.samsara_provider import (
    UnconfiguredSamsaraProvider,
)
from modules.route_intelligence.providers.travel_matrix_provider import (
    HaversineTravelMatrixProvider,
)
from modules.route_intelligence.providers.weather_provider import (
    UnconfiguredWeatherProvider,
)


class UnconfiguredSamsaraProviderTest(unittest.TestCase):
    def test_every_method_raises_a_clear_error(self) -> None:
        provider = UnconfiguredSamsaraProvider()
        with self.assertRaisesRegex(RuntimeError, "Samsara is not connected"):
            provider.list_vehicles()
        with self.assertRaisesRegex(RuntimeError, "Samsara is not connected"):
            provider.list_drivers()
        with self.assertRaisesRegex(RuntimeError, "Samsara is not connected"):
            provider.get_customer_geofence("640194")
        with self.assertRaisesRegex(RuntimeError, "Samsara is not connected"):
            provider.list_historical_routes(
                date_from=date(2026, 9, 1), date_to=date(2026, 9, 2)
            )


class UnconfiguredRoutingSolverProviderTest(unittest.TestCase):
    def test_solve_raises_a_clear_error(self) -> None:
        provider = UnconfiguredRoutingSolverProvider()
        with self.assertRaisesRegex(RuntimeError, "No route optimization"):
            provider.solve(
                depot=(0.0, 0.0), stops=[], vehicles=[],
                travel_matrix=HaversineTravelMatrixProvider(),
            )


class OrToolsRoutingSolverProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = OrToolsRoutingSolverProvider()
        self.travel_matrix = HaversineTravelMatrixProvider()
        # A depot plus 4 stops spread out in a rough line so a sane
        # solver visits them in a sensible order, not scrambled.
        self.depot = (40.7440, -84.9401)
        self.stops = [
            SolverStop(stop_id="A", latitude=40.75, longitude=-84.93),
            SolverStop(stop_id="B", latitude=40.76, longitude=-84.92),
            SolverStop(stop_id="C", latitude=40.77, longitude=-84.91),
            SolverStop(stop_id="D", latitude=40.78, longitude=-84.90),
        ]

    def test_all_stops_assigned_when_capacity_is_sufficient(self) -> None:
        vehicles = [SolverVehicle(vehicle_slot=1, max_stops=4)]
        plan = self.provider.solve(
            depot=self.depot, stops=self.stops, vehicles=vehicles,
            travel_matrix=self.travel_matrix,
        )
        self.assertEqual(plan.unassigned_stop_ids, [])
        assigned = {stop_id for route in plan.routes for stop_id in route.stop_ids}
        self.assertEqual(assigned, {"A", "B", "C", "D"})

    def test_respects_per_vehicle_stop_capacity(self) -> None:
        vehicles = [
            SolverVehicle(vehicle_slot=1, max_stops=2),
            SolverVehicle(vehicle_slot=2, max_stops=2),
        ]
        plan = self.provider.solve(
            depot=self.depot, stops=self.stops, vehicles=vehicles,
            travel_matrix=self.travel_matrix,
        )
        for route in plan.routes:
            self.assertLessEqual(len(route.stop_ids), 2)
        assigned = {stop_id for route in plan.routes for stop_id in route.stop_ids}
        self.assertEqual(assigned | set(plan.unassigned_stop_ids), {"A", "B", "C", "D"})

    def test_drops_stops_that_do_not_fit_instead_of_failing(self) -> None:
        # Total capacity (1) is less than the number of stops (4) - the
        # solver must drop the excess as unassigned, not raise or return
        # an empty/broken plan.
        vehicles = [SolverVehicle(vehicle_slot=1, max_stops=1)]
        plan = self.provider.solve(
            depot=self.depot, stops=self.stops, vehicles=vehicles,
            travel_matrix=self.travel_matrix,
        )
        assigned_count = sum(len(route.stop_ids) for route in plan.routes)
        self.assertEqual(assigned_count, 1)
        self.assertEqual(len(plan.unassigned_stop_ids), 3)

    def test_no_stops_returns_an_empty_plan(self) -> None:
        plan = self.provider.solve(
            depot=self.depot, stops=[],
            vehicles=[SolverVehicle(vehicle_slot=1, max_stops=4)],
            travel_matrix=self.travel_matrix,
        )
        self.assertEqual(plan.routes, [])
        self.assertEqual(plan.unassigned_stop_ids, [])

    def test_no_vehicles_leaves_every_stop_unassigned(self) -> None:
        plan = self.provider.solve(
            depot=self.depot, stops=self.stops, vehicles=[],
            travel_matrix=self.travel_matrix,
        )
        self.assertEqual(plan.routes, [])
        self.assertEqual(set(plan.unassigned_stop_ids), {"A", "B", "C", "D"})


class GetRoutingSolverProviderTest(unittest.TestCase):
    def test_returns_the_real_provider_when_ortools_is_installed(self) -> None:
        self.assertIsInstance(get_routing_solver_provider(), OrToolsRoutingSolverProvider)


class UnconfiguredWeatherProviderTest(unittest.TestCase):
    def test_get_forecast_raises_a_clear_error(self) -> None:
        provider = UnconfiguredWeatherProvider()
        with self.assertRaisesRegex(RuntimeError, "No weather provider"):
            provider.get_forecast(
                location=(40.84, -84.30), target_date=date(2026, 9, 1)
            )


class HaversineTravelMatrixProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = HaversineTravelMatrixProvider()

    def test_distance_between_identical_points_is_zero(self) -> None:
        point = (40.84, -84.30)
        self.assertEqual(self.provider.distance_miles(point, point), 0.0)

    def test_distance_between_known_cities_is_approximately_correct(self) -> None:
        # Columbus, OH to Cincinnati, OH is ~107 straight-line miles - the
        # 1.3x road-distance factor should put this in a sane ~120-160 mile
        # band, not an order of magnitude off.
        columbus = (39.9612, -82.9988)
        cincinnati = (39.1031, -84.5120)
        miles = self.provider.distance_miles(columbus, cincinnati)
        self.assertGreater(miles, 100)
        self.assertLess(miles, 170)

    def test_travel_time_scales_with_distance(self) -> None:
        near = (40.84, -84.30)
        far = (39.1031, -84.5120)
        near_time = self.provider.travel_time_minutes(near, near)
        far_time = self.provider.travel_time_minutes(near, far)
        self.assertEqual(near_time, 0.0)
        self.assertGreater(far_time, 0.0)


class SimpleDayOfWeekForecastProviderTest(unittest.TestCase):
    def test_averages_stops_by_day_of_week(self) -> None:
        provider = SimpleDayOfWeekForecastProvider()
        history = [
            HistoricalDemandPoint(
                day=date(2026, 8, 3),  # Monday
                stop_count=10, total_weight=1000.0, total_quantity=50.0,
            ),
            HistoricalDemandPoint(
                day=date(2026, 8, 10),  # Monday
                stop_count=14, total_weight=1400.0, total_quantity=70.0,
            ),
            HistoricalDemandPoint(
                day=date(2026, 8, 4),  # Tuesday
                stop_count=8, total_weight=800.0, total_quantity=40.0,
            ),
        ]
        result = provider.forecast_day_of_week_baseline(history)

        self.assertEqual(result["Monday"].sample_size, 2)
        self.assertEqual(result["Monday"].expected_stops, 12.0)
        self.assertEqual(result["Tuesday"].sample_size, 1)
        self.assertEqual(result["Tuesday"].expected_stops, 8.0)

    def test_percentiles_are_computed_alongside_the_mean(self) -> None:
        provider = SimpleDayOfWeekForecastProvider()
        history = [
            HistoricalDemandPoint(
                day=date(2026, 8, 3),  # Monday
                stop_count=10, total_weight=1000.0, total_quantity=50.0,
            ),
            HistoricalDemandPoint(
                day=date(2026, 8, 10),  # Monday
                stop_count=14, total_weight=1400.0, total_quantity=70.0,
            ),
        ]
        result = provider.forecast_day_of_week_baseline(history)

        monday = result["Monday"]
        self.assertEqual(monday.p50_weight, 1200.0)
        self.assertEqual(monday.p80_weight, 1320.0)
        self.assertEqual(monday.p90_weight, 1360.0)

    def test_percentile_of_a_single_sample_is_just_that_sample(self) -> None:
        for pct in (50, 80, 90):
            self.assertEqual(_percentile([42.0], pct), 42.0)

    def test_percentile_linear_interpolation(self) -> None:
        values = [10.0, 20.0, 30.0, 40.0]
        self.assertEqual(_percentile(values, 0), 10.0)
        self.assertEqual(_percentile(values, 100), 40.0)
        self.assertEqual(_percentile(values, 50), 25.0)


if __name__ == "__main__":
    unittest.main()
