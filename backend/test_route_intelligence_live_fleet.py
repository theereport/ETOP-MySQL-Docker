from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine

from data.mysql import _reset_engine_override, _set_engine_override
from modules.route_intelligence import repository as route_repository
from modules.route_intelligence import service as route_service


class FakeSamsaraProvider:
    """Minimal stand-in for get_live_gps - matches the real shape
    confirmed live this session (onTrip/latitude/longitude/location/
    speed/heading/time in epoch ms)."""

    def __init__(self, *, gps_by_vehicle: dict[str, dict[str, Any] | None] | None = None,
                 raise_for_vehicle: str | None = None):
        self._gps_by_vehicle = gps_by_vehicle or {}
        self._raise_for_vehicle = raise_for_vehicle

    def get_live_gps(self, vehicle_id: str):
        if vehicle_id == self._raise_for_vehicle:
            raise RuntimeError("Samsara request failed")
        return self._gps_by_vehicle.get(vehicle_id)


class LiveFleetStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmpdir.name) / 'route.db'}"
        )
        _set_engine_override(self.engine)
        self.addCleanup(_reset_engine_override)
        self.addCleanup(self.engine.dispose)

    def _vehicle(self, *, unit_number, samsara_vehicle_id=None, warehouse_number=41):
        vehicle = route_service.create_vehicle(
            {"unit_number": unit_number, "home_warehouse_number": warehouse_number}
        )
        if samsara_vehicle_id:
            # samsara_vehicle_id is import-populated, not part of
            # update_vehicle()'s hand-editable payload contract - set it
            # directly via the repository, same as import_samsara_vehicles()
            # would on a real import.
            route_repository.update_vehicle(
                vehicle.vehicle_id, {"samsara_vehicle_id": samsara_vehicle_id}
            )
        return vehicle

    def test_vehicle_currently_on_a_trip_is_reported(self) -> None:
        self._vehicle(unit_number="T-1", samsara_vehicle_id="sv-1")
        samsara = FakeSamsaraProvider(gps_by_vehicle={
            "sv-1": {
                "onTrip": True, "latitude": 40.75, "longitude": -84.93,
                "location": "Delphos, OH", "speed": 55.2, "heading": 180,
                "time": 1737145637022,
            },
        })

        status = route_service.get_live_fleet_status(41, samsara=samsara)

        self.assertEqual(status.vehicle_count, 1)
        self.assertEqual(status.on_trip_count, 1)
        vehicle_status = status.vehicles[0]
        self.assertTrue(vehicle_status.on_trip)
        self.assertEqual(vehicle_status.location_label, "Delphos, OH")
        self.assertIsNotNone(vehicle_status.last_updated_at)
        self.assertIsNone(vehicle_status.unavailable_reason)

    def test_parked_vehicle_is_not_counted_as_on_trip(self) -> None:
        self._vehicle(unit_number="T-1", samsara_vehicle_id="sv-1")
        samsara = FakeSamsaraProvider(gps_by_vehicle={
            "sv-1": {
                "onTrip": False, "latitude": 40.75, "longitude": -84.93,
                "location": "K&M Tire - Delphos", "speed": 0, "heading": 0,
                "time": 1737145637022,
            },
        })

        status = route_service.get_live_fleet_status(41, samsara=samsara)

        self.assertEqual(status.on_trip_count, 0)
        self.assertFalse(status.vehicles[0].on_trip)

    def test_vehicle_with_no_samsara_link_is_reported_unavailable(self) -> None:
        self._vehicle(unit_number="T-1", samsara_vehicle_id=None)

        status = route_service.get_live_fleet_status(41, samsara=FakeSamsaraProvider())

        self.assertEqual(status.vehicle_count, 1)
        self.assertEqual(status.on_trip_count, 0)
        self.assertEqual(
            status.vehicles[0].unavailable_reason, "Not linked to a Samsara vehicle."
        )

    def test_a_failed_live_lookup_does_not_break_the_whole_response(self) -> None:
        self._vehicle(unit_number="T-1", samsara_vehicle_id="sv-1")
        self._vehicle(unit_number="T-2", samsara_vehicle_id="sv-2")
        samsara = FakeSamsaraProvider(
            gps_by_vehicle={"sv-2": {
                "onTrip": True, "latitude": 40.0, "longitude": -84.0,
                "location": "", "speed": 10.0, "heading": 90, "time": None,
            }},
            raise_for_vehicle="sv-1",
        )

        status = route_service.get_live_fleet_status(41, samsara=samsara)

        self.assertEqual(status.vehicle_count, 2)
        self.assertEqual(status.on_trip_count, 1)
        by_unit = {v.unit_number: v for v in status.vehicles}
        self.assertIsNotNone(by_unit["T-1"].unavailable_reason)
        self.assertIsNone(by_unit["T-2"].unavailable_reason)
        self.assertTrue(by_unit["T-2"].on_trip)

    def test_no_live_location_on_file_is_reported_unavailable(self) -> None:
        self._vehicle(unit_number="T-1", samsara_vehicle_id="sv-1")
        samsara = FakeSamsaraProvider(gps_by_vehicle={"sv-1": None})

        status = route_service.get_live_fleet_status(41, samsara=samsara)

        self.assertEqual(
            status.vehicles[0].unavailable_reason,
            "No live location on file for this vehicle.",
        )

    def test_only_vehicles_at_the_requested_warehouse_are_included(self) -> None:
        self._vehicle(unit_number="T-1", samsara_vehicle_id="sv-1", warehouse_number=41)
        self._vehicle(unit_number="T-2", samsara_vehicle_id="sv-2", warehouse_number=84)

        status = route_service.get_live_fleet_status(41, samsara=FakeSamsaraProvider())

        self.assertEqual(status.vehicle_count, 1)
        self.assertEqual(status.vehicles[0].unit_number, "T-1")


if __name__ == "__main__":
    unittest.main()
