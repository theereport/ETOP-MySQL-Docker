from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.ar_collections import router as ar_collections_router
from modules.ar_collections.service import (
    ARCollectionsSourceIntegrityError,
    ARCollectionsSourceUnavailable,
    ar_collections_service,
)


class ARCollectionsRouterErrorMappingTests(unittest.TestCase):
    """ARCollectionsSourceUnavailable/ARCollectionsSourceIntegrityError were
    raised by the service but never caught by this router - they used to
    propagate as unhandled exceptions (a raw 500), unlike the identical
    exception-naming pattern in credit_risk's and accounts_payable's own
    routers, which already map them to 503/502."""

    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(ar_collections_router.router)
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_source_unavailable_becomes_a_clean_503(self) -> None:
        with patch.object(
            ar_collections_service,
            "get_customer_collections",
            side_effect=ARCollectionsSourceUnavailable(
                "Customer 360 could not retrieve the read-only ERP facts."
            ),
        ):
            response = self.client.get("/api/v1/ar-collections/customers/12345")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"]["code"],
            "ar_collections_source_unavailable",
        )

    def test_source_integrity_error_becomes_a_clean_502(self) -> None:
        with patch.object(
            ar_collections_service,
            "get_customer_collections",
            side_effect=ARCollectionsSourceIntegrityError(
                "Customer 360 returned an invalid customer summary envelope."
            ),
        ):
            response = self.client.get("/api/v1/ar-collections/customers/12345")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"]["code"],
            "ar_collections_source_integrity_error",
        )

    def test_source_unavailable_on_note_creation_becomes_a_clean_503(self) -> None:
        with patch.object(
            ar_collections_service,
            "create_note",
            side_effect=ARCollectionsSourceUnavailable(
                "Customer 360 could not retrieve the read-only ERP facts."
            ),
        ):
            response = self.client.post(
                "/api/v1/ar-collections/customers/12345/notes",
                json={"author_identity": "tester", "note": "Follow up."},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"]["code"],
            "ar_collections_source_unavailable",
        )


if __name__ == "__main__":
    unittest.main()
