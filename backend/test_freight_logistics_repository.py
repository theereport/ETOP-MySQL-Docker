from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from modules.freight_logistics.repository import RouteRepository


class FreightLogisticsRepositoryTest(unittest.TestCase):
    """RouteRepository imports the shared `madden_database` singleton
    directly (not constructor-injected), so these tests patch it at the
    module level rather than passing a fake database in."""

    def test_list_warehouses_queries_wh_dashboard_locations(self) -> None:
        rows = [{"LOCATION_NUMBER": 41, "LOCATION_NAME": "Delphos"}]
        with patch(
            "modules.freight_logistics.repository.madden_database"
        ) as fake_db:
            fake_db.fetch_all.return_value = rows
            repository = RouteRepository()
            result = repository.list_warehouses()

        self.assertEqual(result, rows)
        query = fake_db.fetch_all.call_args[0][0]
        self.assertIn("WH_DASHBOARD_LOCATIONS", query)

    def test_list_routes_for_warehouse_filters_by_exact_warehouse(self) -> None:
        with patch(
            "modules.freight_logistics.repository.madden_database"
        ) as fake_db:
            fake_db.fetch_all.return_value = []
            repository = RouteRepository()
            repository.list_routes_for_warehouse(41, active_only=True)

        query, parameters = fake_db.fetch_all.call_args[0]
        self.assertIn("route.RTEWHSE = %s", query)
        self.assertIn("RTESTATUS", query)
        self.assertEqual(parameters[0], 41)

    def test_list_routes_for_warehouse_can_include_inactive(self) -> None:
        with patch(
            "modules.freight_logistics.repository.madden_database"
        ) as fake_db:
            fake_db.fetch_all.return_value = []
            repository = RouteRepository()
            repository.list_routes_for_warehouse(41, active_only=False)

        query, _parameters = fake_db.fetch_all.call_args[0]
        self.assertNotIn("RTESTATUS) = 'A'", query)

    def test_get_load_lines_for_warehouse_joins_kmroutes_and_filters_dates(
        self,
    ) -> None:
        with patch(
            "modules.freight_logistics.repository.madden_database"
        ) as fake_db:
            fake_db.fetch_all.return_value = []
            repository = RouteRepository()
            repository.get_load_lines_for_warehouse(
                41,
                date_from=date(2026, 9, 1),
                date_to=date(2026, 9, 2),
            )

        query, parameters = fake_db.fetch_all.call_args[0]
        self.assertIn("KMTDTA.KMROUTES", query)
        self.assertIn("route.RTEWHSE = %s", query)
        self.assertEqual(
            parameters,
            (41, date(2026, 9, 1), date(2026, 9, 2), 5000),
        )


if __name__ == "__main__":
    unittest.main()
