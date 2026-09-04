from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine

from data.mysql import _reset_engine_override, _set_engine_override
from modules.route_intelligence import service as route_service


class FakeSamsaraProvider:
    """Minimal stand-in exercising only what each test needs - matches
    the shapes confirmed live against the real Samsara API this session."""

    def __init__(
        self,
        *,
        vehicles: list[dict[str, Any]] | None = None,
        drivers: list[dict[str, Any]] | None = None,
        addresses: list[dict[str, Any]] | None = None,
        trips: list[dict[str, Any]] | None = None,
    ) -> None:
        self._vehicles = vehicles or []
        self._drivers = drivers or []
        self._addresses = addresses or []
        self._trips = trips or []

    def list_vehicles(self):
        return self._vehicles

    def list_drivers(self):
        return self._drivers

    def list_addresses(self):
        return self._addresses

    def list_historical_routes(self, *, date_from, date_to):
        return self._trips


class ImportSamsaraVehiclesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmpdir.name) / 'route.db'}"
        )
        _set_engine_override(self.engine)
        self.addCleanup(_reset_engine_override)
        self.addCleanup(self.engine.dispose)

    def test_first_import_creates_vehicles(self) -> None:
        provider = FakeSamsaraProvider(
            vehicles=[
                {"id": "v1", "name": "1523 - Columbus", "vin": "ABC123", "type": "Truck"},
                {"id": "v2", "name": "1524 - Delphos", "vin": "DEF456", "type": "Truck"},
            ]
        )
        result = route_service.import_samsara_vehicles(samsara=provider)
        self.assertEqual(result.samsara_count, 2)
        self.assertEqual(result.created_count, 2)
        self.assertEqual(result.updated_count, 0)

        vehicles = route_service.list_vehicles()
        self.assertEqual(len(vehicles), 2)
        by_samsara_id = {v.samsara_vehicle_id: v for v in vehicles}
        self.assertEqual(by_samsara_id["v1"].unit_number, "1523 - Columbus")
        self.assertEqual(by_samsara_id["v1"].vin, "ABC123")

    def test_reimport_updates_rather_than_duplicates(self) -> None:
        provider = FakeSamsaraProvider(
            vehicles=[{"id": "v1", "name": "Old Name", "vin": "ABC123"}]
        )
        route_service.import_samsara_vehicles(samsara=provider)

        renamed_provider = FakeSamsaraProvider(
            vehicles=[{"id": "v1", "name": "New Name", "vin": "ABC123"}]
        )
        result = route_service.import_samsara_vehicles(samsara=renamed_provider)

        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.updated_count, 1)
        vehicles = route_service.list_vehicles()
        self.assertEqual(len(vehicles), 1)
        self.assertEqual(vehicles[0].unit_number, "New Name")

    def test_reimport_preserves_manually_entered_notes(self) -> None:
        route_service.import_samsara_vehicles(
            samsara=FakeSamsaraProvider(vehicles=[{"id": "v1", "name": "Truck 1"}])
        )
        vehicle = route_service.list_vehicles()[0]
        route_service.update_vehicle(
            vehicle.vehicle_id,
            {"unit_number": vehicle.unit_number, "notes": "Needs new tires"},
        )

        route_service.import_samsara_vehicles(
            samsara=FakeSamsaraProvider(vehicles=[{"id": "v1", "name": "Truck 1 Renamed"}])
        )

        reloaded = route_service.list_vehicles()[0]
        self.assertEqual(reloaded.unit_number, "Truck 1 Renamed")
        self.assertEqual(reloaded.notes, "Needs new tires")

    def test_vehicle_missing_id_is_skipped(self) -> None:
        provider = FakeSamsaraProvider(vehicles=[{"name": "No ID"}])
        result = route_service.import_samsara_vehicles(samsara=provider)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(route_service.list_vehicles(), [])


class ImportSamsaraDriversTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmpdir.name) / 'route.db'}"
        )
        _set_engine_override(self.engine)
        self.addCleanup(_reset_engine_override)
        self.addCleanup(self.engine.dispose)

    def test_first_import_creates_drivers(self) -> None:
        provider = FakeSamsaraProvider(
            drivers=[{"id": "d1", "name": "Terry Wiseman"}]
        )
        result = route_service.import_samsara_drivers(samsara=provider)
        self.assertEqual(result.created_count, 1)
        drivers = route_service.list_drivers()
        self.assertEqual(drivers[0].samsara_driver_id, "d1")
        self.assertEqual(drivers[0].name, "Terry Wiseman")

    def test_reimport_updates_rather_than_duplicates(self) -> None:
        provider = FakeSamsaraProvider(drivers=[{"id": "d1", "name": "Old Name"}])
        route_service.import_samsara_drivers(samsara=provider)
        result = route_service.import_samsara_drivers(
            samsara=FakeSamsaraProvider(drivers=[{"id": "d1", "name": "New Name"}])
        )
        self.assertEqual(result.updated_count, 1)
        self.assertEqual(route_service.list_drivers()[0].name, "New Name")


class SearchAndLinkSamsaraAddressTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmpdir.name) / 'route.db'}"
        )
        _set_engine_override(self.engine)
        self.addCleanup(_reset_engine_override)
        self.addCleanup(self.engine.dispose)

    def test_search_filters_by_name(self) -> None:
        provider = FakeSamsaraProvider(
            addresses=[
                {"id": "a1", "name": "Gothenburg Tire", "formattedAddress": "1 Main St"},
                {"id": "a2", "name": "Some Other Place", "formattedAddress": "2 Oak Ave"},
            ]
        )
        results = route_service.search_samsara_addresses("gothenburg", samsara=provider)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "a1")

    def test_blank_query_returns_everything(self) -> None:
        provider = FakeSamsaraProvider(
            addresses=[{"id": "a1", "name": "A"}, {"id": "a2", "name": "B"}]
        )
        results = route_service.search_samsara_addresses("", samsara=provider)
        self.assertEqual(len(results), 2)

    def test_link_round_trips(self) -> None:
        profile = route_service.link_customer_samsara_address("640194", "a1")
        self.assertEqual(profile.samsara_address_id, "a1")
        reloaded = route_service.get_customer_profile("640194")
        self.assertEqual(reloaded.samsara_address_id, "a1")

    def test_unrelated_profile_save_does_not_clobber_the_link(self) -> None:
        route_service.link_customer_samsara_address("640194", "a1")
        route_service.save_customer_profile("640194", {"priority": "high"})
        reloaded = route_service.get_customer_profile("640194")
        self.assertEqual(reloaded.samsara_address_id, "a1")
        self.assertEqual(reloaded.priority, "high")


class SyncSamsaraTripsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmpdir.name) / 'route.db'}"
        )
        _set_engine_override(self.engine)
        self.addCleanup(_reset_engine_override)
        self.addCleanup(self.engine.dispose)

    def _trip(self, trip_id: str, vehicle_id: str, **overrides) -> dict:
        base = {
            "id": trip_id,
            "asset": {"id": vehicle_id},
            "tripStartTime": "2026-09-01T08:00:00Z",
            "tripEndTime": "2026-09-01T09:00:00Z",
            "startLocation": {"latitude": 40.0, "longitude": -84.0},
            "endLocation": {"latitude": 40.1, "longitude": -84.1},
            "finalDistanceMeters": 5000,
            "completionStatus": "completed",
        }
        base.update(overrides)
        return base

    def test_trip_resolves_to_an_imported_vehicle(self) -> None:
        route_service.import_samsara_vehicles(
            samsara=FakeSamsaraProvider(vehicles=[{"id": "v1", "name": "Truck 1"}])
        )
        provider = FakeSamsaraProvider(trips=[self._trip("t1", "v1")])

        runs, sync_state = route_service.sync_samsara_trips(
            date(2026, 9, 1), date(2026, 9, 2), samsara=provider,
        )

        self.assertEqual(len(runs), 1)
        self.assertIsNotNone(runs[0].vehicle_id)
        self.assertIsNone(runs[0].driver_id)  # trips/stream has no driver field
        self.assertEqual(sync_state.last_run_status, "success")
        self.assertEqual(sync_state.last_synced_through, "2026-09-02")

    def test_trip_for_unimported_vehicle_is_stored_unresolved(self) -> None:
        provider = FakeSamsaraProvider(trips=[self._trip("t1", "unknown-vehicle")])
        runs, _sync_state = route_service.sync_samsara_trips(
            date(2026, 9, 1), date(2026, 9, 2), samsara=provider,
        )
        self.assertEqual(len(runs), 1)
        self.assertIsNone(runs[0].vehicle_id)

    def test_resyncing_the_same_trip_upserts_not_duplicates(self) -> None:
        provider = FakeSamsaraProvider(trips=[self._trip("t1", "v1")])
        route_service.sync_samsara_trips(date(2026, 9, 1), date(2026, 9, 2), samsara=provider)
        route_service.sync_samsara_trips(date(2026, 9, 1), date(2026, 9, 2), samsara=provider)
        all_runs = route_service.list_actual_runs()
        self.assertEqual(len(all_runs), 1)

    def test_list_actual_runs_filters_by_date(self) -> None:
        provider = FakeSamsaraProvider(
            trips=[
                self._trip("t1", "v1", tripStartTime="2026-09-01T08:00:00Z"),
                self._trip("t2", "v1", tripStartTime="2026-09-05T08:00:00Z"),
            ]
        )
        route_service.sync_samsara_trips(date(2026, 9, 1), date(2026, 9, 6), samsara=provider)
        filtered = route_service.list_actual_runs(
            date_from="2026-09-05T00:00:00Z", date_to="2026-09-06T00:00:00Z",
        )
        self.assertEqual(len(filtered), 1)


if __name__ == "__main__":
    unittest.main()
