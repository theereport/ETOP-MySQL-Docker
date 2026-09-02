from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine

from modules.vendor_intelligence.notes_repository import VendorNotesRepository


class PoFillRateCacheRepositoryTests(unittest.TestCase):
    """The pre-aggregated fill-rate cache replaces the slow live per-vendor
    TMPOHD/TMPODT join _build_performance_summary() used to run directly on
    the interactive vendor-evidence request path."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp.name) / 'vendor-intelligence.db'}"
        )
        self.addCleanup(self.engine.dispose)
        self.repository = VendorNotesRepository(engine=self.engine)

    def test_never_refreshed_reports_no_rows_and_no_timestamp(self) -> None:
        self.assertIsNone(self.repository.po_fill_rate_cache_refreshed_at())
        self.assertIsNone(self.repository.get_po_fill_rate_cache(1234567))

    def test_replace_then_read_round_trips_per_vendor(self) -> None:
        self.repository.replace_po_fill_rate_cache(
            [
                {
                    "vendor_number": 1234567,
                    "po_count": 12,
                    "quantity_ordered": 200,
                    "quantity_received": 150,
                    "quantity_backorder": 50,
                },
                {
                    "vendor_number": 7654321,
                    "po_count": 3,
                    "quantity_ordered": 40,
                    "quantity_received": 40,
                    "quantity_backorder": 0,
                },
            ],
            window_days=365,
            refreshed_at="2026-06-01T00:00:00+00:00",
        )

        self.assertEqual(
            self.repository.po_fill_rate_cache_refreshed_at(),
            "2026-06-01T00:00:00+00:00",
        )
        first = self.repository.get_po_fill_rate_cache(1234567)
        self.assertEqual(first["po_count"], 12)
        self.assertEqual(first["window_days"], 365)
        second = self.repository.get_po_fill_rate_cache(7654321)
        self.assertEqual(second["quantity_ordered"], 40.0)
        self.assertIsNone(self.repository.get_po_fill_rate_cache(9999999))

    def test_replace_discards_the_prior_snapshot(self) -> None:
        self.repository.replace_po_fill_rate_cache(
            [
                {
                    "vendor_number": 1234567,
                    "po_count": 12,
                    "quantity_ordered": 200,
                    "quantity_received": 150,
                    "quantity_backorder": 50,
                },
            ],
            window_days=365,
            refreshed_at="2026-06-01T00:00:00+00:00",
        )
        self.repository.replace_po_fill_rate_cache(
            [
                {
                    "vendor_number": 7654321,
                    "po_count": 3,
                    "quantity_ordered": 40,
                    "quantity_received": 40,
                    "quantity_backorder": 0,
                },
            ],
            window_days=365,
            refreshed_at="2026-06-02T00:00:00+00:00",
        )

        self.assertIsNone(self.repository.get_po_fill_rate_cache(1234567))
        self.assertIsNotNone(self.repository.get_po_fill_rate_cache(7654321))
        self.assertEqual(
            self.repository.po_fill_rate_cache_refreshed_at(),
            "2026-06-02T00:00:00+00:00",
        )


if __name__ == "__main__":
    unittest.main()
