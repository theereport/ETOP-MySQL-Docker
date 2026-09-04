"""Samsara read/write surface Route Intelligence calls.

SamsaraApiProvider is the real implementation, added 2026-09-04 once a
Samsara API token became available. Endpoints below were confirmed
directly against developers.samsara.com on that date (base URL, auth
header, exact paths, response shapes, pagination) rather than guessed -
see each method's docstring for the endpoint it calls.

UnconfiguredSamsaraProvider remains for any deployment without a token
configured - every method raises a clear error instead of silently
returning empty/fake data. get_samsara_provider() below picks whichever
is appropriate based on whether SAMSARA_API_TOKEN is set, so the rest of
this module (and any future caller) never has to know which one is
active - mirrors the CashApplicationDataProvider /
UnconfiguredCashApplicationDataProvider pattern in
backend/modules/document_intelligence/cash_application/data_provider.py.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Protocol

import requests


class SamsaraProvider(Protocol):
    def list_vehicles(self) -> list[dict[str, Any]]:
        ...

    def list_drivers(self) -> list[dict[str, Any]]:
        ...

    def list_driver_vehicle_assignments(self) -> list[dict[str, Any]]:
        ...

    def list_addresses(self) -> list[dict[str, Any]]:
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

    def list_addresses(self) -> list[dict[str, Any]]:
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


DEFAULT_SAMSARA_BASE_URL = "https://api.samsara.com"
# Batch size for /trips/stream's required `ids` param (confirmed max: 50).
_TRIPS_STREAM_BATCH_SIZE = 50


class SamsaraApiProvider:
    """Real Samsara REST client. Every endpoint here was confirmed against
    developers.samsara.com on 2026-09-04 - see each method for its exact
    source doc. Not all SamsaraProvider methods have a confirmed REST
    endpoint; list_actual_stops() explains why and does not guess one.
    """

    def __init__(
        self,
        *,
        api_token: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        token = api_token or os.getenv("SAMSARA_API_TOKEN")
        if not token:
            raise RuntimeError(
                "SAMSARA_API_TOKEN is not set - cannot construct a real "
                "SamsaraApiProvider. Use get_samsara_provider() instead of "
                "constructing this directly, or set SAMSARA_API_TOKEN."
            )
        self._base_url = (
            base_url or os.getenv("SAMSARA_API_BASE_URL") or DEFAULT_SAMSARA_BASE_URL
        ).rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._session = requests.Session()
        self._session.headers.update(
            {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._session.get(
                f"{self._base_url}{path}",
                params=params,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"Unable to reach Samsara ({path}): connection failed."
            ) from exc
        except requests.Timeout as exc:
            raise RuntimeError(f"Samsara request timed out ({path}).") from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            body = exc.response.text[:500] if exc.response is not None else ""
            raise RuntimeError(
                f"Samsara request failed ({path}): HTTP {status} {body}"
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Samsara request failed ({path}): {exc}") from exc
        return response.json()

    def _paginated_get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Every "list" endpoint here shares the same {data, pagination:
        {endCursor, hasNextPage}} envelope - confirmed for /assets,
        /fleet/drivers, /fleet/driver-vehicle-assignments, /addresses, and
        /trips/stream. /v1/fleet/locations does NOT (see get_live_gps)."""

        results: list[dict[str, Any]] = []
        base_params = dict(params or {})
        cursor: str | None = None
        while True:
            page_params = dict(base_params)
            if cursor:
                page_params["after"] = cursor
            payload = self._get(path, params=page_params)
            results.extend(payload.get("data") or [])
            pagination = payload.get("pagination") or {}
            if not pagination.get("hasNextPage"):
                break
            cursor = pagination.get("endCursor")
            if not cursor:
                break
        return results

    def list_vehicles(self) -> list[dict[str, Any]]:
        """GET /assets?type=vehicle - developers.samsara.com/reference/listassets"""

        return self._paginated_get("/assets", params={"type": "vehicle"})

    def list_drivers(self) -> list[dict[str, Any]]:
        """GET /fleet/drivers - developers.samsara.com/reference/listdrivers"""

        return self._paginated_get("/fleet/drivers")

    def list_driver_vehicle_assignments(self) -> list[dict[str, Any]]:
        """GET /fleet/driver-vehicle-assignments?filterBy=vehicles

        `filterBy` (one of "drivers"/"vehicles") is required but wasn't
        surfaced by developers.samsara.com/docs/driver-vehicle-assignment-
        faqs when this was written - only discovered by a live 400 against
        the real API ("filterBy" is missing...). "vehicles" was chosen
        since Route Intelligence's questions are vehicle-centric (which
        driver is on truck N right now), confirmed live to return
        {startTime, endTime, driver: {id, name}, vehicle: {id, name}}
        rows.
        """

        return self._paginated_get(
            "/fleet/driver-vehicle-assignments", params={"filterBy": "vehicles"}
        )

    def list_addresses(self) -> list[dict[str, Any]]:
        """GET /addresses - developers.samsara.com/reference/listaddresses"""

        return self._paginated_get("/addresses")

    def get_customer_geofence(
        self, customer_number: str
    ) -> dict[str, Any] | None:
        """Filtered client-side by externalIds, since /addresses has no
        confirmed server-side externalId-value filter param. Assumes K&M's
        Samsara addresses are tagged with the ETOP/MaddenCo customer number
        as an externalId value - that tagging convention does not exist
        yet and needs to be established in Samsara before this returns
        anything real. See the module README.
        """

        for address in self.list_addresses():
            external_ids = address.get("externalIds") or {}
            if customer_number in external_ids.values():
                return address
        return None

    def list_historical_routes(
        self, *, date_from: date, date_to: date
    ) -> list[dict[str, Any]]:
        """GET /trips/stream - developers.samsara.com/reference/gettrips

        `ids` (vehicle/asset IDs, max 50 per call) is a required param, so
        this fetches the current vehicle list first and batches trips
        requests across it - callers of the SamsaraProvider interface
        never see that detail.
        """

        vehicle_ids = [
            str(vehicle["id"]) for vehicle in self.list_vehicles() if "id" in vehicle
        ]
        if not vehicle_ids:
            return []
        start_time = f"{date_from.isoformat()}T00:00:00Z"
        end_time = f"{date_to.isoformat()}T00:00:00Z"
        trips: list[dict[str, Any]] = []
        for index in range(0, len(vehicle_ids), _TRIPS_STREAM_BATCH_SIZE):
            batch = vehicle_ids[index : index + _TRIPS_STREAM_BATCH_SIZE]
            trips.extend(
                self._paginated_get(
                    "/trips/stream",
                    params={
                        "startTime": start_time,
                        "endTime": end_time,
                        "ids": ",".join(batch),
                        "completionStatus": "completed",
                    },
                )
            )
        return trips

    def list_actual_stops(self, route_id: str) -> list[dict[str, Any]]:
        raise RuntimeError(
            "Samsara delivers route-stop arrival/departure as webhook "
            "events (RouteStopArrival/RouteStopDeparture, currently "
            "Beta), not a pollable REST list - there is no GET endpoint "
            "to call here. Reading this requires a webhook receiver "
            "(signature verification + event storage), which is separate "
            "infrastructure work, not implemented yet. See the module "
            "README."
        )

    def get_live_gps(self, vehicle_id: str) -> dict[str, Any] | None:
        """GET /v1/fleet/locations - developers.samsara.com/reference/getfleetlocations

        Note the /v1 prefix and "vehicles" response key - this endpoint
        predates the {data, pagination} envelope used everywhere else
        here, so it does not go through _paginated_get.
        """

        payload = self._get("/v1/fleet/locations", params={"vehicleIds": vehicle_id})
        vehicles = payload.get("vehicles") or []
        return vehicles[0] if vehicles else None


def get_samsara_provider() -> SamsaraProvider:
    """The single place that decides which SamsaraProvider is active.

    Every caller in this module should go through this function rather
    than constructing SamsaraApiProvider/UnconfiguredSamsaraProvider
    directly, so Samsara automatically switches on the moment
    SAMSARA_API_TOKEN is configured - no other code change needed.
    """

    if os.getenv("SAMSARA_API_TOKEN"):
        return SamsaraApiProvider()
    return UnconfiguredSamsaraProvider()
