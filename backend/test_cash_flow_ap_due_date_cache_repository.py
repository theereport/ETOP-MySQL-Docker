from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, event

from modules.cash_flow_forecasting.notes_repository import (
    CashFlowForecastingNotesRepository,
)


class ApDueDateCacheRangeLookupTests(unittest.TestCase):
    """_ap_for_weeks() used to call get_ap_due_date_cache() once per week
    of the forecast horizon (14 weeks = 15 queries including the
    refreshed-at check). get_ap_due_date_cache_for_range() replaces the
    per-week loop with one query covering the whole horizon."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp.name) / 'cash-flow.db'}"
        )
        self.addCleanup(self.engine.dispose)
        self.repository = CashFlowForecastingNotesRepository(engine=self.engine)
        self.repository.replace_ap_due_date_cache(
            [
                {
                    "week_start": "2026-08-24",
                    "week_end": "2026-08-30",
                    "open_amount": 1000.0,
                    "open_on_hold_amount": 50.0,
                },
                {
                    "week_start": "2026-08-31",
                    "week_end": "2026-09-06",
                    "open_amount": 2000.0,
                    "open_on_hold_amount": 0.0,
                },
                {
                    "week_start": "2026-12-01",
                    "week_end": "2026-12-07",
                    "open_amount": 9999.0,
                    "open_on_hold_amount": 0.0,
                },
            ],
            refreshed_at="2026-08-25T00:00:00+00:00",
        )

    def test_range_lookup_returns_only_weeks_within_range(self) -> None:
        result = self.repository.get_ap_due_date_cache_for_range(
            "2026-08-24", "2026-09-06"
        )
        self.assertEqual(
            set(result.keys()),
            {("2026-08-24", "2026-08-30"), ("2026-08-31", "2026-09-06")},
        )
        self.assertEqual(
            result[("2026-08-24", "2026-08-30")]["open_amount"], 1000.0
        )
        self.assertEqual(
            result[("2026-08-31", "2026-09-06")]["open_on_hold_amount"], 0.0
        )

    def test_query_count_does_not_scale_with_number_of_weeks_requested(
        self,
    ) -> None:
        def _query_count(week_start: str, week_end: str) -> int:
            statements: list[str] = []

            def _record(conn, cursor, statement, parameters, context, executemany):
                statements.append(statement)

            event.listen(self.engine, "before_cursor_execute", _record)
            try:
                self.repository.get_ap_due_date_cache_for_range(
                    week_start, week_end
                )
            finally:
                event.remove(self.engine, "before_cursor_execute", _record)
            return len([
                s for s in statements if s.strip().upper().startswith("SELECT")
            ])

        one_week = _query_count("2026-08-24", "2026-08-30")
        fourteen_weeks = _query_count("2026-08-24", "2026-12-07")
        self.assertEqual(one_week, 1)
        self.assertEqual(one_week, fourteen_weeks)


if __name__ == "__main__":
    unittest.main()
