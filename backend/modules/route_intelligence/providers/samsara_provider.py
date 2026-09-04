"""Samsara read/write surface Route Intelligence will eventually call.

No Samsara API access exists yet (see the module README). This Protocol
lets every other piece of Route Intelligence (forecasting, capacity,
optimization, dispatcher workspaces) be written and tested against a
stable interface today, and swapped to a real implementation with zero
changes to callers once access exists - mirrors the CashApplicationDataProvider
/ UnconfiguredCashApplicationDataProvider pattern in
backend/modules/document_intelligence/cash_application/data_provider.py.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol


class SamsaraProvider(Protocol):
    def list_vehicles(self) -> list[dict[str, Any]]:
        ...

    def list_drivers(self) -> list[dict[str, Any]]:
        ...

    def list_driver_vehicle_assignments(self) -> list[dict[str, Any]]:
        ...

    def get_customer_geofence(
        self, customer_number: str
    ) -> dict[str, Any] | None:
        ...

    def list_historical_routes(
        self, *, date_from: date, date_to: date
    ) -> list[dict[str, Any]]:
        ...

    def list_actual_stops(self, route_id: str) -> list[dict[str, Any]]:
        ...

    def get_live_gps(self, vehicle_id: str) -> dict[str, Any] | None:
        ...


class UnconfiguredSamsaraProvider:
    """Every method raises a clear, specific error instead of the
    interface silently returning empty/fake data - callers should treat a
    RuntimeError here as "Samsara isn't connected yet", not "there's
    nothing to report"."""

    _MESSAGE = (
        "Samsara is not connected yet - no API credentials are configured. "
        "This is expected until the Samsara integration increment begins; "
        "see the route_intelligence module README."
    )

    def list_vehicles(self) -> list[dict[str, Any]]:
        raise RuntimeError(self._MESSAGE)

    def list_drivers(self) -> list[dict[str, Any]]:
        raise RuntimeError(self._MESSAGE)

    def list_driver_vehicle_assignments(self) -> list[dict[str, Any]]:
        raise RuntimeError(self._MESSAGE)

    def get_customer_geofence(
        self, customer_number: str
    ) -> dict[str, Any] | None:
        raise RuntimeError(self._MESSAGE)

    def list_historical_routes(
        self, *, date_from: date, date_to: date
    ) -> list[dict[str, Any]]:
        raise RuntimeError(self._MESSAGE)

    def list_actual_stops(self, route_id: str) -> list[dict[str, Any]]:
        raise RuntimeError(self._MESSAGE)

    def get_live_gps(self, vehicle_id: str) -> dict[str, Any] | None:
        raise RuntimeError(self._MESSAGE)
