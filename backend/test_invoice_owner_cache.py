from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.document_intelligence.integrations.invoice_owner_cache import (
    InvoiceOwnerCacheRepository,
)
from modules.document_intelligence.integrations.receivables_repository import (
    ReceivablesRepository,
)


class InvoiceOwnerCacheRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.cache = InvoiceOwnerCacheRepository(
            Path(self._tmpdir.name) / "invoice_owner_cache.db"
        )

    def test_never_refreshed_returns_none(self) -> None:
        self.assertIsNone(self.cache.get_owners(["43000001"]))
        self.assertIsNone(self.cache.refreshed_at())

    def test_replace_all_then_get_owners_round_trips(self) -> None:
        invoices_cached = self.cache.replace_all(
            [
                {"invoice_number": "43000001", "customer_number": "520459"},
                {"invoice_number": "43000002", "customer_number": "520459"},
            ]
        )

        self.assertEqual(invoices_cached, 2)
        self.assertIsNotNone(self.cache.refreshed_at())

        owners = self.cache.get_owners(["43000001", "43000002", "43000003"])

        self.assertEqual(owners["43000001"], {"520459"})
        self.assertEqual(owners["43000002"], {"520459"})
        self.assertEqual(owners["43000003"], set())

    def test_multiple_owners_for_one_invoice_are_merged(self) -> None:
        self.cache.replace_all(
            [
                {"invoice_number": "43000001", "customer_number": "520459"},
                {"invoice_number": "43000001", "customer_number": "610233"},
            ]
        )

        owners = self.cache.get_owners(["43000001"])

        self.assertEqual(owners["43000001"], {"520459", "610233"})

    def test_replace_all_discards_the_prior_snapshot(self) -> None:
        self.cache.replace_all(
            [{"invoice_number": "43000001", "customer_number": "520459"}]
        )
        self.cache.replace_all(
            [{"invoice_number": "43000002", "customer_number": "610233"}]
        )

        owners = self.cache.get_owners(["43000001", "43000002"])

        self.assertEqual(owners["43000001"], set())
        self.assertEqual(owners["43000002"], {"610233"})

    def test_rows_with_invalid_invoice_or_customer_are_skipped(self) -> None:
        invoices_cached = self.cache.replace_all(
            [
                {"invoice_number": "not-a-number", "customer_number": "520459"},
                {"invoice_number": "43000001", "customer_number": ""},
                {"invoice_number": "43000002", "customer_number": "520459"},
            ]
        )

        self.assertEqual(invoices_cached, 1)
        owners = self.cache.get_owners(["43000002"])
        self.assertEqual(owners["43000002"], {"520459"})


class ReceivablesRepositoryCacheIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.cache = InvoiceOwnerCacheRepository(
            Path(self._tmpdir.name) / "invoice_owner_cache.db"
        )

    class _FailingDatabase:
        def fetch_all(self, query, parameters):
            raise AssertionError(
                "The live database should not be queried when the "
                "invoice-owner cache has already been refreshed."
            )

    def test_cache_hit_bypasses_the_live_database_entirely(self) -> None:
        self.cache.replace_all(
            [{"invoice_number": "43000001", "customer_number": "520459"}]
        )
        repository = ReceivablesRepository(
            self._FailingDatabase(), invoice_owner_cache=self.cache
        )

        owners = repository.get_current_invoice_owners(["43000001"])

        self.assertEqual(owners, {"43000001": {"520459"}})

    def test_cache_never_refreshed_falls_back_to_the_live_database(self) -> None:
        class FakeDatabase:
            def fetch_all(self, query, parameters):
                return [
                    {"invoice_number": "43000001", "customer_number": "520459"}
                ]

        repository = ReceivablesRepository(
            FakeDatabase(), invoice_owner_cache=self.cache
        )

        owners = repository.get_current_invoice_owners(["43000001"])

        self.assertEqual(owners, {"43000001": {"520459"}})


if __name__ == "__main__":
    unittest.main()
