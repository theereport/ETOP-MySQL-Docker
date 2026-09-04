from __future__ import annotations

import unittest

from fastapi import HTTPException

from modules.route_intelligence import service as route_service
from modules.route_intelligence.providers.samsara_provider import (
    UnconfiguredSamsaraProvider,
)


class FakeSamsaraProvider:
    def list_vehicles(self):
        return [{"id": "1", "name": "Truck 1"}]

    def get_customer_geofence(self, customer_number):
        return {"id": "a1", "name": f"Geofence for {customer_number}"}


class SamsaraServiceWrapperTest(unittest.TestCase):
    def test_list_samsara_vehicles_returns_provider_data(self) -> None:
        vehicles = route_service.list_samsara_vehicles(samsara=FakeSamsaraProvider())
        self.assertEqual(vehicles, [{"id": "1", "name": "Truck 1"}])

    def test_get_samsara_customer_geofence_passes_through_the_customer_number(
        self,
    ) -> None:
        geofence = route_service.get_samsara_customer_geofence(
            "640194", samsara=FakeSamsaraProvider()
        )
        self.assertEqual(geofence["name"], "Geofence for 640194")

    def test_unconfigured_provider_becomes_a_clear_http_502(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            route_service.list_samsara_vehicles(
                samsara=UnconfiguredSamsaraProvider()
            )
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("Samsara is not connected", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
