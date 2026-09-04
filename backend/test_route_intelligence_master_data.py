from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine

from data.mysql import _reset_engine_override, _set_engine_override
from modules.route_intelligence import service as route_service


class CustomerProfileTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmpdir.name) / 'route.db'}"
        )
        _set_engine_override(self.engine)
        self.addCleanup(_reset_engine_override)
        self.addCleanup(self.engine.dispose)

    def test_unset_profile_returns_defaults(self) -> None:
        profile = route_service.get_customer_profile("640194")
        self.assertEqual(profile.customer_number, "640194")
        self.assertIsNone(profile.latitude)
        self.assertEqual(profile.closed_days, [])

    def test_save_and_reload_round_trips(self) -> None:
        route_service.save_customer_profile(
            "640194",
            {
                "latitude": 40.84,
                "longitude": -84.30,
                "closed_days": ["Sunday"],
                "preferred_delivery_days": ["Tuesday", "Thursday"],
                "priority": "high",
                "normal_unloading_minutes": 22.5,
                "updated_by": "jcorbit",
            },
        )
        profile = route_service.get_customer_profile("640194")
        self.assertEqual(profile.latitude, 40.84)
        self.assertEqual(profile.closed_days, ["Sunday"])
        self.assertEqual(
            profile.preferred_delivery_days, ["Tuesday", "Thursday"]
        )
        self.assertEqual(profile.priority, "high")
        self.assertEqual(profile.normal_unloading_minutes, 22.5)
        self.assertEqual(profile.updated_by, "jcorbit")

    def test_list_includes_saved_profiles(self) -> None:
        route_service.save_customer_profile("640194", {})
        route_service.save_customer_profile("999999", {})
        profiles = route_service.list_customer_profiles()
        self.assertEqual(
            sorted(p.customer_number for p in profiles), ["640194", "999999"]
        )

    def test_blank_customer_number_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            route_service.save_customer_profile("  ", {})


class VehicleTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmpdir.name) / 'route.db'}"
        )
        _set_engine_override(self.engine)
        self.addCleanup(_reset_engine_override)
        self.addCleanup(self.engine.dispose)

    def test_create_vehicle_starts_with_no_capacities(self) -> None:
        vehicle = route_service.create_vehicle(
            {"unit_number": "T-101", "vehicle_type": "box_truck"}
        )
        self.assertEqual(vehicle.unit_number, "T-101")
        self.assertEqual(vehicle.capacities, [])

    def test_add_capacity_attaches_to_the_vehicle(self) -> None:
        vehicle = route_service.create_vehicle({"unit_number": "T-101"})
        updated = route_service.add_vehicle_capacity(
            vehicle.vehicle_id,
            {"weight_capacity": 10000.0, "max_stops": 25},
        )
        self.assertEqual(len(updated.capacities), 1)
        self.assertEqual(updated.capacities[0].weight_capacity, 10000.0)
        self.assertEqual(updated.capacities[0].max_stops, 25)

    def test_update_vehicle_changes_fields(self) -> None:
        vehicle = route_service.create_vehicle({"unit_number": "T-101"})
        updated = route_service.update_vehicle(
            vehicle.vehicle_id,
            {"unit_number": "T-101", "active": False},
        )
        self.assertFalse(updated.active)

    def test_update_missing_vehicle_raises(self) -> None:
        with self.assertRaises(Exception):
            route_service.update_vehicle(99999, {"unit_number": "X"})

    def test_add_capacity_to_missing_vehicle_raises(self) -> None:
        with self.assertRaises(Exception):
            route_service.add_vehicle_capacity(99999, {})


class DriverTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmpdir.name) / 'route.db'}"
        )
        _set_engine_override(self.engine)
        self.addCleanup(_reset_engine_override)
        self.addCleanup(self.engine.dispose)

    def test_create_driver_starts_with_no_availability(self) -> None:
        driver = route_service.create_driver({"name": "Sam Rivera"})
        self.assertEqual(driver.availability, [])

    def test_set_availability_is_upserted_per_day(self) -> None:
        driver = route_service.create_driver({"name": "Sam Rivera"})
        route_service.set_driver_availability(
            driver.driver_id,
            {"day_of_week": "Monday", "available": True, "shift_start": "06:00"},
        )
        updated = route_service.set_driver_availability(
            driver.driver_id,
            {"day_of_week": "Monday", "available": False},
        )
        self.assertEqual(len(updated.availability), 1)
        self.assertFalse(updated.availability[0].available)

    def test_set_availability_for_missing_driver_raises(self) -> None:
        with self.assertRaises(Exception):
            route_service.set_driver_availability(
                99999, {"day_of_week": "Monday"}
            )


class BusinessRuleTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmpdir.name) / 'route.db'}"
        )
        _set_engine_override(self.engine)
        self.addCleanup(_reset_engine_override)
        self.addCleanup(self.engine.dispose)

    def test_save_and_reload_round_trips(self) -> None:
        route_service.save_business_rule(
            "capacity_watch_threshold_pct",
            {"rule_value": "80", "description": "P90 saturation watch threshold"},
        )
        rules = route_service.list_business_rules()
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].rule_value, "80")

    def test_save_overwrites_prior_value(self) -> None:
        route_service.save_business_rule(
            "capacity_watch_threshold_pct", {"rule_value": "80"}
        )
        route_service.save_business_rule(
            "capacity_watch_threshold_pct", {"rule_value": "85"}
        )
        rules = route_service.list_business_rules()
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].rule_value, "85")


if __name__ == "__main__":
    unittest.main()
