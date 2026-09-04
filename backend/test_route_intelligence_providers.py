from __future__ import annotations

import unittest
from datetime import date

from modules.route_intelligence.providers.forecast_provider import (
    HistoricalDemandPoint,
    SimpleDayOfWeekForecastProvider,
    _percentile,
)
from modules.route_intelligence.providers.routing_solver_provider import (
    UnconfiguredRoutingSolverProvider,
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
            provider.solve(stops=[], vehicles=[], constraints={})


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
