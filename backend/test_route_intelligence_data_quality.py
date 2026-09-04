from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine

from data.mysql import _reset_engine_override, _set_engine_override
from modules.route_intelligence import repository as route_repository
from modules.route_intelligence import service as route_service


class FakeFreightLogisticsService:
    """Stands in for freight_logistics_service so this test never needs a
    real MaddenCo connection - only the two shapes compute_data_quality_
    report actually reads (warehouses.warehouses[].warehouse_number and
    routes.routes[].route_code) are populated."""

    def __init__(self, *, warehouse_numbers: list[int], route_codes: list[str]):
        self._warehouse_numbers = warehouse_numbers
        self._route_codes = route_codes

    def list_warehouses(self):
        return SimpleNamespace(
            warehouses=[
                SimpleNamespace(warehouse_number=number)
                for number in self._warehouse_numbers
            ]
        )

    def search_routes(self, *, search, active_only, limit):
        return SimpleNamespace(
            routes=[
                SimpleNamespace(route_code=code) for code in self._route_codes
            ]
        )


class DataQualityReportTest(unittest.TestCase):
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

    def test_matched_route_and_store_are_counted(self) -> None:
        rows = [
            {
                "CUNUMBER": 640194, "CUNAME": "Gothenburg Tire",
                "CUROUTECD": "12", "CUSTORENUM": 41,
            },
        ]
        with self._patch_customers(rows):
            report = route_service.compute_data_quality_report(
                freight_service=FakeFreightLogisticsService(
                    warehouse_numbers=[41], route_codes=["12"],
                )
            )

        self.assertEqual(report.customers_checked, 1)
        self.assertEqual(report.matched_route_code_count, 1)
        self.assertEqual(report.matched_store_number_count, 1)
        self.assertEqual(report.route_code_match_rate, 1.0)
        self.assertEqual(report.total_issue_count, 0)

    def test_unmatched_route_code_is_flagged(self) -> None:
        rows = [
            {
                "CUNUMBER": 640194, "CUNAME": "Gothenburg Tire",
                "CUROUTECD": "ZZ", "CUSTORENUM": 41,
            },
        ]
        with self._patch_customers(rows):
            report = route_service.compute_data_quality_report(
                freight_service=FakeFreightLogisticsService(
                    warehouse_numbers=[41], route_codes=["12"],
                )
            )

        self.assertEqual(report.matched_route_code_count, 0)
        self.assertEqual(report.total_issue_count, 1)
        self.assertEqual(
            report.issues[0].category, "customer_route_code_unmatched"
        )
        self.assertIn("640194", report.issues[0].subject)

    def test_unmatched_store_number_is_flagged(self) -> None:
        rows = [
            {
                "CUNUMBER": 640194, "CUNAME": "Gothenburg Tire",
                "CUROUTECD": "12", "CUSTORENUM": 999,
            },
        ]
        with self._patch_customers(rows):
            report = route_service.compute_data_quality_report(
                freight_service=FakeFreightLogisticsService(
                    warehouse_numbers=[41], route_codes=["12"],
                )
            )

        self.assertEqual(report.matched_store_number_count, 0)
        categories = [issue.category for issue in report.issues]
        self.assertIn("customer_store_number_unmatched", categories)

    def test_blank_route_code_is_not_flagged(self) -> None:
        rows = [
            {
                "CUNUMBER": 640194, "CUNAME": "Gothenburg Tire",
                "CUROUTECD": "", "CUSTORENUM": 41,
            },
        ]
        with self._patch_customers(rows):
            report = route_service.compute_data_quality_report(
                freight_service=FakeFreightLogisticsService(
                    warehouse_numbers=[41], route_codes=["12"],
                )
            )

        # A blank route code is a data-entry gap, not a mismatch - it
        # should neither count as matched nor be flagged as unmatched.
        self.assertEqual(report.matched_route_code_count, 0)
        self.assertEqual(report.total_issue_count, 0)

    def test_vehicle_missing_capacity_is_flagged(self) -> None:
        route_service.create_vehicle({"unit_number": "T-101"})
        with self._patch_customers([]):
            report = route_service.compute_data_quality_report(
                freight_service=FakeFreightLogisticsService(
                    warehouse_numbers=[], route_codes=[],
                )
            )

        categories = [issue.category for issue in report.issues]
        self.assertIn("vehicle_missing_capacity", categories)

    def test_driver_missing_availability_is_flagged(self) -> None:
        route_service.create_driver({"name": "Sam Rivera"})
        with self._patch_customers([]):
            report = route_service.compute_data_quality_report(
                freight_service=FakeFreightLogisticsService(
                    warehouse_numbers=[], route_codes=[],
                )
            )

        categories = [issue.category for issue in report.issues]
        self.assertIn("driver_missing_availability", categories)

    def test_customer_profile_missing_coordinates_is_flagged(self) -> None:
        route_service.save_customer_profile("640194", {})
        with self._patch_customers([]):
            report = route_service.compute_data_quality_report(
                freight_service=FakeFreightLogisticsService(
                    warehouse_numbers=[], route_codes=[],
                )
            )

        categories = [issue.category for issue in report.issues]
        self.assertIn("customer_profile_missing_coordinates", categories)


if __name__ == "__main__":
    unittest.main()
