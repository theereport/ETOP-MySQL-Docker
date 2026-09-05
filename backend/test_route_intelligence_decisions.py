from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine

from data.mysql import _reset_engine_override, _set_engine_override
from modules.route_intelligence import repository as route_repository
from modules.route_intelligence import service as route_service


class FakeFreightLogisticsService:
    def __init__(self, *, warehouses, daily_totals_by_warehouse=None):
        self._warehouses = warehouses
        self._daily_totals_by_warehouse = daily_totals_by_warehouse or {}

    def list_warehouses(self):
        return SimpleNamespace(
            warehouses=[
                SimpleNamespace(warehouse_number=number, warehouse_location_name=name)
                for number, name in self._warehouses
            ]
        )

    def get_daily_load_totals_for_warehouse(self, warehouse_number, *, date_from, date_to):
        return SimpleNamespace(
            totals=self._daily_totals_by_warehouse.get(warehouse_number, [])
        )


class RouteIntelligenceDecisionsTest(unittest.TestCase):
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

    def _successful_run_id(self) -> int:
        """Builds one real successful optimization run via the RI-4
        pipeline (a small fixture with one customer/one vehicle) so
        RI-5's decision workflow has a genuine "success" run to act on."""

        route_service.save_warehouse_location(
            41, {"latitude": 40.7440, "longitude": -84.9401}
        )
        route_service.save_customer_profile(
            "1", {"latitude": 40.75, "longitude": -84.93}
        )
        vehicle = route_service.create_vehicle(
            {"unit_number": "T-41", "home_warehouse_number": 41}
        )
        route_service.add_vehicle_capacity(vehicle.vehicle_id, {"max_stops": 2})

        freight_service = FakeFreightLogisticsService(warehouses=[(41, "Dallas")])
        customer_row = {
            "CUNUMBER": "1", "CUNAME": "Customer 1", "CUROUTECD": "12", "CUSTORENUM": 41,
        }
        with self._patch_customers([customer_row]):
            run = route_service.compute_route_optimization(
                41, date(2026, 9, 10), freight_service=freight_service,
            )
        self.assertEqual(run.status, "success")  # pragma: no cover - sanity
        return run.run_id

    # --- happy path ---------------------------------------------------

    def test_decide_approved_baseline_round_trips(self) -> None:
        run_id = self._successful_run_id()

        record = route_service.decide_optimization_run(
            run_id, decision="approved_baseline", decided_by="Jamie",
            reason="Looks good, matches current coverage.",
        )
        self.assertEqual(record.decision, "approved_baseline")
        self.assertEqual(record.decided_by, "Jamie")
        self.assertIsNone(record.modification_notes)

        history = route_service.list_plan_decisions(run_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].decision_id, record.decision_id)

    def test_multiple_decisions_accumulate_as_history(self) -> None:
        run_id = self._successful_run_id()

        route_service.decide_optimization_run(
            run_id, decision="rejected", decided_by="Jamie", reason="Too conservative.",
        )
        route_service.decide_optimization_run(
            run_id, decision="approved_with_backup", decided_by="Sam",
            reason="Overruled - backup driver makes sense today.",
        )

        history = route_service.list_plan_decisions(run_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].decision, "rejected")
        self.assertEqual(history[1].decision, "approved_with_backup")

    def test_modified_decision_carries_notes(self) -> None:
        run_id = self._successful_run_id()

        record = route_service.decide_optimization_run(
            run_id, decision="modified", decided_by="Jamie",
            reason="Needs a manual tweak before use.",
            modification_notes="Move customer 1 to the afternoon route instead.",
        )
        self.assertEqual(record.decision, "modified")
        self.assertEqual(
            record.modification_notes, "Move customer 1 to the afternoon route instead."
        )

    # --- guards ----------------------------------------------------------

    def test_cannot_decide_on_an_insufficient_data_run(self) -> None:
        # No warehouse location/customers/vehicles set up - this run will
        # honestly come back insufficient_data, per RI-4.
        with self._patch_customers([]):
            run = route_service.compute_route_optimization(99, date(2026, 9, 10))
        self.assertEqual(run.status, "insufficient_data")  # pragma: no cover

        with self.assertRaises(HTTPException) as ctx:
            route_service.decide_optimization_run(
                run.run_id, decision="approved_baseline", decided_by="Jamie",
                reason="Attempting to approve anyway.",
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("insufficient_data", ctx.exception.detail)

    def test_cannot_decide_on_a_nonexistent_run(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            route_service.decide_optimization_run(
                999999, decision="approved_baseline", decided_by="Jamie", reason="x",
            )
        self.assertEqual(ctx.exception.status_code, 404)

    # --- repository round-trip ----------------------------------------------

    def test_repository_save_and_list_round_trip(self) -> None:
        run = route_repository.save_optimization_run({
            "run_at": "2026-09-10T00:00:00Z", "warehouse_number": 41,
            "target_date": "2026-09-10", "status": "success", "message": "ok",
        })
        route_repository.save_plan_decision({
            "run_id": run["run_id"], "decision": "approved_baseline",
            "decided_by": "Jamie", "reason": "Looks fine.",
            "modification_notes": None, "decided_at": "2026-09-10T08:00:00Z",
        })
        route_repository.save_plan_decision({
            "run_id": run["run_id"], "decision": "rejected",
            "decided_by": "Sam", "reason": "Changed my mind.",
            "modification_notes": None, "decided_at": "2026-09-10T09:00:00Z",
        })

        rows = route_repository.list_plan_decisions_for_run(run["run_id"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["decision"], "approved_baseline")
        self.assertEqual(rows[1]["decision"], "rejected")


if __name__ == "__main__":
    unittest.main()
