from __future__ import annotations

import unittest
from datetime import date
from unittest import mock

from modules.cash_flow_forecasting import computation as calc
from modules.cash_flow_forecasting.bank_balance_source import BankBalanceRow
from modules.cash_flow_forecasting.service import CashFlowForecastingService


class FakeRepository:
    def __init__(self) -> None:
        self.open_ar_rows: list[dict] = []
        self.any_status_ar_rows: list[dict] = []
        self.je_rows: list[dict] = []
        self.ap_rows: list[dict] = []

    def get_open_ar_invoices_due_between(self, start_date, end_date):
        return self.open_ar_rows

    def get_ar_invoices_due_between_any_status(
        self, start_date, end_date, *, invoiced_on_or_before
    ):
        return self.any_status_ar_rows

    def get_cash_account_je_activity(self, start_date, end_date):
        return [
            row
            for row in self.je_rows
            if start_date <= calc.parse_madden_date(row["GADTPST"]) <= end_date
        ]

    def get_cash_account_ap_activity(self, start_date, end_date):
        return [
            row
            for row in self.ap_rows
            if start_date <= calc.parse_madden_date(row["GADTPST"]) <= end_date
        ]


class FakeNotesRepository:
    def __init__(self) -> None:
        self.ap_cache: dict[tuple[str, str], dict] = {}
        self.snapshots: list[dict] = []
        self.actuals: list[dict] = []

    def ap_cache_refreshed_at(self):
        return "2026-08-25T00:00:00+00:00" if self.ap_cache else None

    def get_ap_due_date_cache(self, week_start, week_end):
        return self.ap_cache.get((week_start, week_end))

    def replace_ap_due_date_cache(self, buckets, *, refreshed_at):
        self.ap_cache = {
            (bucket["week_start"], bucket["week_end"]): bucket for bucket in buckets
        }

    def create_snapshot(self, *, snapshot, weeks):
        self.snapshots.append({"snapshot": snapshot, "weeks": weeks})

    def list_snapshots(self, limit=50):
        return []

    def record_actual(self, record):
        self.actuals.append(record)

    def latest_actual_for_week(self, week_start, week_end):
        matches = [
            a for a in self.actuals if a["week_start"] == week_start and a["week_end"] == week_end
        ]
        return matches[-1] if matches else None

    def list_actuals(self, limit=200):
        return []


def je_row(posted: str, amount: float, dbcr: str, description: str) -> dict:
    return {"GADTPST": posted, "GAAMT": amount, "GACDDBCR": dbcr, "GADSR": description}


class WeekBoundsTests(unittest.TestCase):
    def test_week_bounds_start_on_monday_and_cover_fourteen_weeks(self):
        weeks = calc.week_bounds(date(2026, 8, 25))  # a Tuesday

        self.assertEqual(len(weeks), 14)
        self.assertEqual(weeks[0], (1, date(2026, 8, 24), date(2026, 8, 30)))
        self.assertEqual(weeks[1][1], date(2026, 8, 31))
        self.assertEqual(weeks[-1][0], 14)

    def test_shift_weeks_one_year_back_preserves_monday_alignment(self):
        weeks = calc.week_bounds(date(2026, 8, 25))
        prior = calc.shift_weeks_one_year_back(weeks)

        for (_, start, _), (_, prior_start, _) in zip(weeks, prior):
            self.assertEqual(prior_start.weekday(), 0)
            self.assertEqual(start.weekday(), 0)
            self.assertEqual((start - prior_start).days, 364)


class ClassificationTests(unittest.TestCase):
    def test_receipt_summaries_are_classified_as_receipt(self):
        for description in (
            "08.24.2026 CASH RECEIPTS",
            "8.21.26 LBOX RECEIPTS",
            "08.20.2026 CC/WEBPAY RECEIPTS",
        ):
            self.assertEqual(calc.classify_je_description(description), "receipt")

    def test_sweeps_and_transfers_are_excluded(self):
        for description in (
            "SWEEP FROM PNC AR TO PNC AP",
            "FUNDS TRANSFER FROM WF TO PNC AR",
        ):
            self.assertEqual(calc.classify_je_description(description), "sweep")

    def test_loc_activity_is_excluded(self):
        for description in ("DRAW ON LOC 8.20.26", "PAY ON LOC 8.21.26", "TRAVELERS LINE OF CREDIT FEE"):
            self.assertEqual(calc.classify_je_description(description), "loc")

    def test_genuine_other_items_pass_through(self):
        for description in ("PAYROLL ENTRY FOR PERIOD ENDING 8.21.26", "WEX FLEET - FUEL CARDS"):
            self.assertEqual(calc.classify_je_description(description), "other")

    def test_normalize_family_strips_leading_and_embedded_dates(self):
        self.assertEqual(
            calc.normalize_description_family("8.21.26 PAYROLL ENTRY FOR PERIOD ENDING 8.21.26"),
            "PAYROLL ENTRY FOR PERIOD ENDING <DATE>",
        )


class ArDueDateBucketingTests(unittest.TestCase):
    def test_open_ar_buckets_into_the_week_containing_its_due_date(self):
        weeks = calc.week_bounds(date(2026, 8, 25))
        rows = [
            {"TARODTEDUE": "20260826", "TAROAMTOPN": "100.00"},
            {"TARODTEDUE": "20260901", "TAROAMTOPN": "50.00"},
        ]

        totals = calc.bucket_ar_by_due_week(rows, weeks)

        self.assertEqual(totals[1], 100.0)
        self.assertEqual(totals[2], 50.0)

    def test_any_status_bucketing_falls_back_to_original_amount(self):
        weeks = calc.week_bounds(date(2026, 8, 25))
        rows = [{"TARODTEDUE": "20260826", "TAROAMTORG": "250.00"}]

        totals = calc.bucket_ar_by_due_week(rows, weeks)

        self.assertEqual(totals[1], 250.0)


class OtherPatternDetectionTests(unittest.TestCase):
    def test_a_one_off_item_with_only_two_occurrences_is_not_projected(self):
        """Confirmed live: a genuine one-off ~$6.6M wire that happened to
        occur exactly twice was otherwise projected as if it recurred
        every 14 days indefinitely. At least 3 occurrences are required
        before a cadence is trusted."""

        rows = [
            je_row("20260318", -6_600_000.0, "CR", "ZURCHER TIRE WIRE 3.18.26"),
            je_row("20260401", -6_600_000.0, "CR", "ZURCHER TIRE WIRE 4.1.26"),
        ]
        patterns = calc.detect_other_patterns(
            rows, lookback_start=date(2026, 1, 1), before=date(2026, 8, 25)
        )
        family = next(iter(patterns))
        self.assertIsNone(patterns[family].cadence_days)

        weeks = calc.week_bounds(date(2026, 8, 25))
        projected = calc.project_other_bucket(patterns, weeks)
        self.assertEqual(sum(projected.values()), 0.0)

    def test_same_day_lines_are_summed_before_cadence_is_computed(self):
        """A single payroll run can post several GMAD lines the same
        day; treating each line as its own occurrence previously
        produced a spurious ~2-day 'cadence' instead of the real
        biweekly one."""

        rows = [
            je_row("20260306", 80_000.0, "CR", "EMPOWER MATCH 3.6.26"),
            je_row("20260306", 20_000.0, "CR", "EMPOWER MATCH 3.6.26"),
            je_row("20260320", 80_000.0, "CR", "EMPOWER MATCH 3.20.26"),
            je_row("20260320", 20_000.0, "CR", "EMPOWER MATCH 3.20.26"),
            je_row("20260403", 100_000.0, "CR", "EMPOWER MATCH 4.3.26"),
        ]
        patterns = calc.detect_other_patterns(
            rows, lookback_start=date(2026, 1, 1), before=date(2026, 8, 25)
        )
        family = next(iter(patterns))
        self.assertEqual(patterns[family].cadence_days, 14)
        self.assertEqual(patterns[family].average_amount, -100_000.0)
        self.assertEqual(patterns[family].occurrence_count, 3)

    def test_a_genuine_weekly_pattern_is_projected_forward(self):
        rows = [
            je_row(f"202608{day:02d}", 50_000.0, "CR", "PAYROLL ENTRY FOR PERIOD ENDING")
            for day in (7, 14, 21)
        ]
        patterns = calc.detect_other_patterns(
            rows, lookback_start=date(2026, 8, 1), before=date(2026, 8, 25)
        )
        weeks = calc.week_bounds(date(2026, 8, 25))

        projected = calc.project_other_bucket(patterns, weeks)

        self.assertEqual(projected[1], -50_000.0)  # next occurrence: 2026-08-28


class ActualsFromGmadTests(unittest.TestCase):
    def test_actual_ap_reports_check_writing_as_a_positive_outflow(self):
        weeks = [calc.week_bounds(date(2026, 8, 25))[0]]
        rows = [je_row("20260824", 500_000.0, "CR", "ACCOUNTS PAYABLE CHECK WRITING")]

        totals = calc.actual_ap_from_ap_rows(rows, weeks)

        self.assertEqual(totals[1], 500_000.0)

    def test_actual_ap_void_check_reduces_the_outflow(self):
        weeks = [calc.week_bounds(date(2026, 8, 25))[0]]
        rows = [
            je_row("20260824", 500_000.0, "CR", "ACCOUNTS PAYABLE CHECK WRITING"),
            je_row("20260824", -1_000.0, "CR", "ACCOUNTS PAYABLE VOID CHECKS"),
        ]

        totals = calc.actual_ap_from_ap_rows(rows, weeks)

        self.assertEqual(totals[1], 499_000.0)

    def test_actual_ar_and_other_split_correctly_and_exclude_sweeps(self):
        weeks = [calc.week_bounds(date(2026, 8, 25))[0]]
        rows = [
            je_row("20260824", 900_000.0, "DB", "08.24.2026 LBOX RECEIPTS"),
            je_row("20260824", 50_000.0, "CR", "WEX FLEET - FUEL CARDS"),
            je_row("20260824", 500_000.0, "CR", "SWEEP FROM PNC AR TO PNC AP"),
        ]

        ar_totals, other_totals = calc.actual_ar_and_other_from_je_rows(rows, weeks)

        self.assertEqual(ar_totals[1], 900_000.0)
        self.assertEqual(other_totals[1], -50_000.0)


_FAKE_BANK_ROW = BankBalanceRow(
    business_day=date(2026, 8, 24),
    net_available=1_000_000.0,
    line_of_credit_withholding=0.0,
    line_of_credit_balance=0.0,
    line_of_credit_available=0.0,
)


class ServiceOrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeRepository()
        self.notes_repository = FakeNotesRepository()
        self.service = CashFlowForecastingService(
            repository=self.repository, notes_repository=self.notes_repository
        )
        patcher = mock.patch(
            "modules.cash_flow_forecasting.service.read_bank_balance_rows",
            return_value=[_FAKE_BANK_ROW],
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ap_unavailable_when_cache_never_refreshed(self):
        forecast = self.service.get_current_forecast(date(2026, 8, 25))

        self.assertTrue(
            any(gap.code == "ap_cache_not_refreshed" for gap in forecast.gaps)
        )
        for week in forecast.weeks:
            self.assertIsNone(week.projected_ap)
            self.assertIsNone(week.projected_ending_balance)

    def test_ap_from_cache_feeds_the_ending_balance_chain(self):
        weeks = calc.week_bounds(date(2026, 8, 25))
        self.notes_repository.ap_cache = {
            (weeks[0][1].isoformat(), weeks[0][2].isoformat()): {
                "week_start": weeks[0][1].isoformat(),
                "week_end": weeks[0][2].isoformat(),
                "open_amount": 40_000.0,
                "open_on_hold_amount": 0.0,
            }
        }
        self.repository.open_ar_rows = [
            {"TARODTEDUE": weeks[0][1].strftime("%Y%m%d"), "TAROAMTOPN": "10000.00"}
        ]

        forecast = self.service.get_current_forecast(date(2026, 8, 25))

        week1 = forecast.weeks[0]
        self.assertEqual(week1.projected_ar, 10000.0)
        self.assertEqual(week1.projected_ap, 40000.0)
        self.assertIsNotNone(week1.projected_ending_balance)
        self.assertEqual(week1.projected_ending_balance, 1_000_000.0 + 10_000.0 - 40_000.0)


if __name__ == "__main__":
    unittest.main()
