from __future__ import annotations

import os
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import requests

from modules.route_intelligence.providers.samsara_provider import (
    SamsaraApiProvider,
    UnconfiguredSamsaraProvider,
    get_samsara_provider,
)


def _fake_response(json_payload, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_payload
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
    else:
        response.raise_for_status.return_value = None
    return response


class SamsaraApiProviderConstructionTest(unittest.TestCase):
    def test_requires_a_token(self) -> None:
        # The real environment may legitimately have SAMSARA_API_TOKEN set
        # (this repo's own .env does) - isolate it explicitly rather than
        # assuming a clean environment.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SAMSARA_API_TOKEN", None)
            with self.assertRaisesRegex(RuntimeError, "SAMSARA_API_TOKEN"):
                SamsaraApiProvider(api_token="")

    def test_accepts_an_explicit_token(self) -> None:
        provider = SamsaraApiProvider(api_token="test-token")
        self.assertEqual(
            provider._session.headers["Authorization"], "Bearer test-token"
        )

    def test_defaults_to_the_us_base_url(self) -> None:
        provider = SamsaraApiProvider(api_token="test-token")
        self.assertEqual(provider._base_url, "https://api.samsara.com")

    def test_accepts_an_explicit_base_url(self) -> None:
        provider = SamsaraApiProvider(
            api_token="test-token", base_url="https://api.eu.samsara.com/"
        )
        self.assertEqual(provider._base_url, "https://api.eu.samsara.com")


class SamsaraApiProviderRequestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = SamsaraApiProvider(api_token="test-token")
        self.provider._session.get = MagicMock()

    def test_list_vehicles_filters_by_type_and_paginates(self) -> None:
        self.provider._session.get.side_effect = [
            _fake_response({
                "data": [{"id": "1", "name": "Truck 1"}],
                "pagination": {"endCursor": "cursor-1", "hasNextPage": True},
            }),
            _fake_response({
                "data": [{"id": "2", "name": "Truck 2"}],
                "pagination": {"endCursor": None, "hasNextPage": False},
            }),
        ]

        vehicles = self.provider.list_vehicles()

        self.assertEqual([v["id"] for v in vehicles], ["1", "2"])
        first_call = self.provider._session.get.call_args_list[0]
        self.assertEqual(first_call.kwargs["params"]["type"], "vehicle")
        second_call = self.provider._session.get.call_args_list[1]
        self.assertEqual(second_call.kwargs["params"]["after"], "cursor-1")

    def test_list_drivers_hits_fleet_drivers(self) -> None:
        self.provider._session.get.return_value = _fake_response({
            "data": [{"id": "d1", "name": "Sam Rivera"}],
            "pagination": {"hasNextPage": False},
        })

        drivers = self.provider.list_drivers()

        self.assertEqual(drivers[0]["name"], "Sam Rivera")
        called_url = self.provider._session.get.call_args.args[0]
        self.assertIn("/fleet/drivers", called_url)

    def test_list_driver_vehicle_assignments_filters_by_vehicles(self) -> None:
        self.provider._session.get.return_value = _fake_response({
            "data": [{"driver": {"id": "d1"}, "vehicle": {"id": "v1"}}],
            "pagination": {"hasNextPage": False},
        })

        assignments = self.provider.list_driver_vehicle_assignments()

        self.assertEqual(assignments[0]["vehicle"]["id"], "v1")
        called_params = self.provider._session.get.call_args.kwargs["params"]
        self.assertEqual(called_params["filterBy"], "vehicles")

    def test_get_customer_geofence_filters_by_external_id(self) -> None:
        self.provider._session.get.return_value = _fake_response({
            "data": [
                {"id": "a1", "name": "Wrong Customer", "externalIds": {"erp": "999"}},
                {"id": "a2", "name": "Right Customer", "externalIds": {"erp": "640194"}},
            ],
            "pagination": {"hasNextPage": False},
        })

        geofence = self.provider.get_customer_geofence("640194")

        self.assertEqual(geofence["id"], "a2")

    def test_get_customer_geofence_returns_none_when_not_found(self) -> None:
        self.provider._session.get.return_value = _fake_response({
            "data": [], "pagination": {"hasNextPage": False},
        })

        self.assertIsNone(self.provider.get_customer_geofence("640194"))

    def test_get_live_gps_uses_v1_endpoint_and_vehicles_key(self) -> None:
        self.provider._session.get.return_value = _fake_response({
            "vehicles": [{"id": 1, "latitude": 40.84, "longitude": -84.30}],
        })

        location = self.provider.get_live_gps("1")

        self.assertEqual(location["latitude"], 40.84)
        called_url = self.provider._session.get.call_args.args[0]
        self.assertIn("/v1/fleet/locations", called_url)

    def test_get_live_gps_returns_none_when_empty(self) -> None:
        self.provider._session.get.return_value = _fake_response({"vehicles": []})
        self.assertIsNone(self.provider.get_live_gps("1"))

    def test_list_historical_routes_batches_vehicle_ids(self) -> None:
        many_vehicles = [{"id": str(i)} for i in range(60)]
        responses = [
            _fake_response({  # list_vehicles page
                "data": many_vehicles, "pagination": {"hasNextPage": False},
            }),
            _fake_response({  # first /trips/stream batch (50 ids)
                "data": [{"id": "trip-1"}], "pagination": {"hasNextPage": False},
            }),
            _fake_response({  # second /trips/stream batch (10 ids)
                "data": [{"id": "trip-2"}], "pagination": {"hasNextPage": False},
            }),
        ]
        self.provider._session.get.side_effect = responses

        trips = self.provider.list_historical_routes(
            date_from=date(2026, 9, 1), date_to=date(2026, 9, 2),
        )

        self.assertEqual([t["id"] for t in trips], ["trip-1", "trip-2"])
        trip_calls = self.provider._session.get.call_args_list[1:]
        self.assertEqual(len(trip_calls), 2)
        self.assertEqual(len(trip_calls[0].kwargs["params"]["ids"].split(",")), 50)
        self.assertEqual(len(trip_calls[1].kwargs["params"]["ids"].split(",")), 10)

    def test_list_historical_routes_returns_empty_with_no_vehicles(self) -> None:
        self.provider._session.get.return_value = _fake_response({
            "data": [], "pagination": {"hasNextPage": False},
        })
        trips = self.provider.list_historical_routes(
            date_from=date(2026, 9, 1), date_to=date(2026, 9, 2),
        )
        self.assertEqual(trips, [])

    def test_list_actual_stops_raises_a_clear_webhook_explanation(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "webhook events"):
            self.provider.list_actual_stops("route-1")

    def test_connection_error_is_wrapped(self) -> None:
        self.provider._session.get.side_effect = requests.ConnectionError("boom")
        with self.assertRaisesRegex(RuntimeError, "connection failed"):
            self.provider.list_vehicles()

    def test_timeout_is_wrapped(self) -> None:
        self.provider._session.get.side_effect = requests.Timeout("boom")
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            self.provider.list_vehicles()

    def test_http_error_is_wrapped_with_status_and_body(self) -> None:
        self.provider._session.get.return_value = _fake_response(
            {"message": "unauthorized"}, status_code=401
        )
        self.provider._session.get.return_value.text = '{"message": "unauthorized"}'
        with self.assertRaisesRegex(RuntimeError, "401"):
            self.provider.list_vehicles()


class GetSamsaraProviderTest(unittest.TestCase):
    def test_returns_real_provider_when_token_set(self) -> None:
        import os
        old = os.environ.get("SAMSARA_API_TOKEN")
        os.environ["SAMSARA_API_TOKEN"] = "test-token"
        try:
            self.assertIsInstance(get_samsara_provider(), SamsaraApiProvider)
        finally:
            if old is None:
                os.environ.pop("SAMSARA_API_TOKEN", None)
            else:
                os.environ["SAMSARA_API_TOKEN"] = old

    def test_returns_unconfigured_provider_when_no_token(self) -> None:
        import os
        old = os.environ.pop("SAMSARA_API_TOKEN", None)
        try:
            self.assertIsInstance(get_samsara_provider(), UnconfiguredSamsaraProvider)
        finally:
            if old is not None:
                os.environ["SAMSARA_API_TOKEN"] = old


if __name__ == "__main__":
    unittest.main()
