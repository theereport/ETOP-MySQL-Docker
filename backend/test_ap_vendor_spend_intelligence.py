from __future__ import annotations

import os
import sys
import types
import unittest
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from unittest.mock import patch


os.environ["MYSQL_HOST"] = "test.invalid"
os.environ["MYSQL_DATABASE"] = "DTA273"
os.environ["MYSQL_USER"] = "read_only_test"
os.environ["MYSQL_PASSWORD"] = "not-used"
os.environ["ETOP_AP_PMGDTEINV_NUMERIC_ENCODING"] = "YYYYMMDD"

# The packaging runtime deliberately lacks FastAPI and mysql-connector. Load the
# pure domain/repository modules without executing the router package initializer
# or opening a database dependency; production imports remain unchanged.
BACKEND_ROOT = Path(__file__).resolve().parent
erp_package = types.ModuleType("modules.erp_evidence")
erp_package.__path__ = [str(BACKEND_ROOT / "modules" / "erp_evidence")]
sys.modules["modules.erp_evidence"] = erp_package
core_package = types.ModuleType("core")
core_package.__path__ = [str(BACKEND_ROOT / "core")]
sys.modules["core"] = core_package
core_database = types.ModuleType("core.database")
core_database.madden_database = object()
sys.modules["core.database"] = core_database

from modules.erp_evidence.ap_spend_parser import parse_ap_spend_question
from modules.erp_evidence.ap_spend_service import APVendorSpendService
from modules.erp_evidence.repository import ERPEvidenceRepository


def confirmed_mapping() -> dict[str, dict[str, dict[str, str]]]:
    pmglds = {}
    for field in [
        "PMGNBVND",
        "PMGNBINV",
        "PMGAMTINV",
        "PMGDTEINV",
        "PMGNBGLDV",
        "PMGNBGL",
        "PMGPR",
        "PMGYR",
    ]:
        data_type = "varchar" if field == "PMGNBINV" else "decimal"
        column_type = (
            "varchar(15)"
            if field == "PMGNBINV"
            else "decimal(18,2)"
            if field == "PMGAMTINV"
            else "decimal(8,0)"
            if field == "PMGDTEINV"
            else "decimal(12,0)"
        )
        pmglds[field] = {
            "data_type": data_type,
            "column_type": column_type,
            "column_comment": "",
        }
    return {
        "PMGLDS": pmglds,
        "PMVEND": {
            "PVNUMVEN": {"data_type": "decimal", "column_type": "decimal", "column_comment": ""},
            "PVNAMVEN": {"data_type": "varchar", "column_type": "varchar(40)", "column_comment": ""},
        },
    }


class FakeSpendRepository:
    AP_SPEND_VENDOR_LIMIT = 10
    AP_SPEND_MONTHLY_PERIOD_LIMIT = 12
    AP_SPEND_MONTHLY_LEADER_LIMIT = 10

    def __init__(self, *, mapping=None) -> None:
        self.mapping = confirmed_mapping() if mapping is None else mapping
        self.total_calls: list[dict[str, object]] = []
        self.ranking_calls: list[dict[str, object]] = []

    def inspect_ap_spend_mapping(self):
        return self.mapping

    def get_ap_spend_total(self, **kwargs):
        self.total_calls.append(kwargs)
        return {
            "distribution_row_count": 4,
            "amount_available_row_count": 4,
            "missing_amount_row_count": 0,
            "invoice_identity_count": 3,
            "vendor_count": 2,
            "positive_distribution_amount": "1550.00",
            "negative_distribution_amount": "-50.00",
            "net_signed_amount": "1500.00",
        }

    def get_ap_spend_ranking(self, **kwargs):
        self.ranking_calls.append(kwargs)
        return ([
            {
                "vendor_number": 101,
                "distribution_row_count": 2,
                "amount_available_row_count": 2,
                "missing_amount_row_count": 0,
                "invoice_identity_count": 2,
                "positive_distribution_amount": "1100.00",
                "negative_distribution_amount": "-50.00",
                "net_signed_amount": "1050.00",
            },
            {
                "vendor_number": 202,
                "distribution_row_count": 2,
                "amount_available_row_count": 2,
                "missing_amount_row_count": 0,
                "invoice_identity_count": 1,
                "positive_distribution_amount": "450.00",
                "negative_distribution_amount": "0",
                "net_signed_amount": "450.00",
            },
        ], True)

    def get_ap_vendor_names(self, vendor_numbers: list[int]):
        return {"101": "Alpha Supply", "202": "Beta Supply"}

    def get_ap_spend_evidence(
        self,
        *,
        include_ranking: bool,
        include_vendor_names: bool,
        include_monthly: bool = False,
        **kwargs,
    ):
        total = self.get_ap_spend_total(**kwargs)
        ranking, ranking_complete = (
            self.get_ap_spend_ranking(**kwargs, limit=self.AP_SPEND_VENDOR_LIMIT)
            if include_ranking
            else ([], None)
        )
        monthly_rankings = []
        if include_monthly:
            for month in range(1, 13):
                start = date(int(kwargs["year"]), month, 1)
                end = (
                    date(int(kwargs["year"]) + 1, 1, 1)
                    if month == 12
                    else date(int(kwargs["year"]), month + 1, 1)
                )
                month_ranking, month_complete = self.get_ap_spend_ranking(
                    **kwargs,
                    limit=self.AP_SPEND_VENDOR_LIMIT,
                )
                monthly_rankings.append(
                    {
                        "calendar_year": int(kwargs["year"]),
                        "calendar_month": month,
                        "range_start": start.isoformat(),
                        "range_end_exclusive": end.isoformat(),
                        "ranking": month_ranking,
                        "ranking_complete": month_complete,
                    }
                )
        vendor_rows = list(ranking)
        for monthly in monthly_rankings:
            vendor_rows.extend(monthly["ranking"])
        vendor_numbers = [int(row["vendor_number"]) for row in vendor_rows]
        vendor_names = (
            self.get_ap_vendor_names(vendor_numbers)
            if include_vendor_names and vendor_numbers
            else {}
        )
        return {
            "total": total,
            "ranking": ranking,
            "ranking_complete": ranking_complete,
            "monthly_rankings": monthly_rankings,
            "vendor_names": vendor_names,
            "vendor_identity_queried": bool(vendor_names),
            "snapshot_opened_at": "2026-08-08T14:59:59+00:00",
        }


class TruncatedLeaderTieRepository(FakeSpendRepository):
    def get_ap_spend_ranking(self, **kwargs):
        self.ranking_calls.append(kwargs)
        return (
            [
                {
                    "vendor_number": vendor_number,
                    "distribution_row_count": 1,
                    "amount_available_row_count": 1,
                    "missing_amount_row_count": 0,
                    "invoice_identity_count": 1,
                    "positive_distribution_amount": "100.00",
                    "negative_distribution_amount": "0",
                    "net_signed_amount": "100.00",
                }
                for vendor_number in range(101, 111)
            ],
            False,
        )

    def get_ap_vendor_names(self, vendor_numbers: list[int]):
        return {str(value): f"Vendor {value}" for value in vendor_numbers}


class FirstMonthNoEvidenceRepository(FakeSpendRepository):
    def get_ap_spend_ranking(self, **kwargs):
        if not self.ranking_calls:
            self.ranking_calls.append(kwargs)
            return [], True
        return super().get_ap_spend_ranking(**kwargs)


class MissingAmountRepository(FakeSpendRepository):
    def get_ap_spend_total(self, **kwargs):
        self.total_calls.append(kwargs)
        return {
            "distribution_row_count": 3,
            "amount_available_row_count": 0,
            "missing_amount_row_count": 3,
            "invoice_identity_count": 2,
            "vendor_count": 2,
            "positive_distribution_amount": "0",
            "negative_distribution_amount": "0",
            "net_signed_amount": "0",
        }


class MixedMissingAndNegativeRepository(FakeSpendRepository):
    def get_ap_spend_total(self, **kwargs):
        self.total_calls.append(kwargs)
        return {
            "distribution_row_count": 2,
            "amount_available_row_count": 1,
            "missing_amount_row_count": 1,
            "invoice_identity_count": 2,
            "vendor_count": 2,
            "positive_distribution_amount": "0",
            "negative_distribution_amount": "-5.00",
            "net_signed_amount": "-5.00",
        }

    def get_ap_spend_ranking(self, **kwargs):
        self.ranking_calls.append(kwargs)
        # The production SQL HAVING clause excludes the other vendor whose
        # only PMGAMTINV value is NULL.
        return ([{
            "vendor_number": 202,
            "distribution_row_count": 1,
            "amount_available_row_count": 1,
            "missing_amount_row_count": 0,
            "invoice_identity_count": 1,
            "positive_distribution_amount": "0",
            "negative_distribution_amount": "-5.00",
            "net_signed_amount": "-5.00",
        }], True)


class CapturingDatabase:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, parameters=()):
        self.calls.append(("one", sql, tuple(parameters)))
        return None

    def fetch_all(self, sql: str, parameters=()):
        self.calls.append(("all", sql, tuple(parameters)))
        return []

    @contextmanager
    def read_consistent_snapshot(self):
        self.calls.append(("snapshot", "BEGIN READ ONLY CONSISTENT SNAPSHOT", ()))
        self.snapshot_opened_at = "2026-08-08T14:59:59+00:00"
        yield self


class APSpendParserTests(unittest.TestCase):
    def test_total_division_plain_year_uses_calendar_invoice_date(self) -> None:
        parsed = parse_ap_spend_question(
            "In division 3, what was total vendor spend for 2026 as a whole?",
            today=date(2026, 8, 8),
        )
        self.assertEqual(parsed.intent, "total_spend")
        self.assertEqual(parsed.division, "3")
        self.assertEqual(parsed.time_basis, "calendar_invoice_date")
        self.assertEqual(parsed.range_start, "2026-01-01")
        self.assertEqual(parsed.range_end_exclusive, "2027-01-01")
        self.assertEqual(parsed.missing_slots, [])

    def test_account_dash_division_and_this_month_are_deterministic(self) -> None:
        parsed = parse_ap_spend_question(
            "For account 5050-3, which vendor had the highest spend this month?",
            today=date(2026, 8, 8),
        )
        self.assertEqual(parsed.intent, "top_vendor")
        self.assertEqual(parsed.account, "5050")
        self.assertEqual(parsed.division, "3")
        self.assertEqual(parsed.time_basis, "calendar_invoice_date")
        self.assertEqual(parsed.range_start, "2026-08-01")
        self.assertEqual(parsed.range_end_exclusive, "2026-09-01")
        self.assertTrue(any("account 5050" in note for note in parsed.interpretation_notes))

    def test_highest_vendor_each_month_is_a_bounded_calendar_series(self) -> None:
        parsed = parse_ap_spend_question(
            "Which vendor had the highest spend each month for account 5050-3 in 2025?",
            today=date(2026, 8, 8),
        )
        self.assertEqual(parsed.intent, "top_vendor_by_month")
        self.assertEqual(parsed.account, "5050")
        self.assertEqual(parsed.division, "3")
        self.assertEqual(parsed.time_basis, "calendar_invoice_date")
        self.assertEqual(parsed.range_start, "2025-01-01")
        self.assertEqual(parsed.range_end_exclusive, "2026-01-01")
        self.assertEqual(parsed.missing_slots, [])

    def test_monthly_total_is_not_silently_reinterpreted_as_a_yearly_total(self) -> None:
        parsed = parse_ap_spend_question(
            "What was total vendor spend by month in division 3 for 2025?",
            today=date(2026, 8, 8),
        )
        self.assertEqual(parsed.intent, "total_spend")
        self.assertIn("unsupported_monthly_measure", parsed.unavailable_slots)

    def test_explicit_accounting_period_uses_raw_period_fields(self) -> None:
        parsed = parse_ap_spend_question(
            "Which vendor had the highest spend for account 5050-3 in ERP accounting year 2026 period 8?",
            today=date(2026, 8, 8),
        )
        self.assertEqual(parsed.time_basis, "erp_accounting_period")
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.accounting_period, 8)
        self.assertIsNone(parsed.range_start)

    def test_fiscal_year_is_explicitly_unavailable(self) -> None:
        parsed = parse_ap_spend_question(
            "What was total vendor spend in division 3 for fiscal year 2026?",
            today=date(2026, 8, 8),
        )
        self.assertIn("fiscal_calendar", parsed.unavailable_slots)
        self.assertIsNone(parsed.time_basis)

    def test_two_requested_time_scopes_are_ambiguous(self) -> None:
        parsed = parse_ap_spend_question(
            "For account 5050-3, which vendor was highest this month or this year?",
            today=date(2026, 8, 8),
        )
        self.assertIn("time_scope", parsed.ambiguous_slots)

    def test_sql_text_is_not_an_supported_question(self) -> None:
        parsed = parse_ap_spend_question(
            "SELECT vendor spend in division 3 for 2026",
            today=date(2026, 8, 8),
        )
        self.assertIn("arbitrary_sql", parsed.unavailable_slots)

    def test_multiple_or_unsupported_intents_fail_closed(self) -> None:
        both = parse_ap_spend_question(
            "What were both the total spend and highest vendor in division 3 for 2026?",
            today=date(2026, 8, 8),
        )
        average = parse_ap_spend_question(
            "What was the average vendor spend in division 3 for 2026?",
            today=date(2026, 8, 8),
        )
        self.assertIn("intent", both.ambiguous_slots)
        self.assertIn("unsupported_question_modifier", average.unavailable_slots)

    def test_multiple_combined_accounts_and_conflicting_date_bases_are_ambiguous(self) -> None:
        dimensions = parse_ap_spend_question(
            "Which vendor was highest for account 5050-3 and account 6060-4 in 2026?",
            today=date(2026, 8, 8),
        )
        dates = parse_ap_spend_question(
            "What was vendor spend in division 3 for calendar year 2026 and ERP accounting year 2026?",
            today=date(2026, 8, 8),
        )
        self.assertIn("account", dimensions.ambiguous_slots)
        self.assertIn("division", dimensions.ambiguous_slots)
        self.assertIn("time_basis", dates.ambiguous_slots)

    def test_year_like_account_is_not_reused_as_date(self) -> None:
        parsed = parse_ap_spend_question(
            "Which vendor was highest for account 2026-3?",
            today=date(2026, 8, 8),
        )
        self.assertEqual(parsed.account, "2026")
        self.assertIsNone(parsed.time_basis)
        self.assertIn("time_scope", parsed.missing_slots)


class APVendorSpendServiceTests(unittest.TestCase):
    def make_service(self, repository: FakeSpendRepository) -> APVendorSpendService:
        return APVendorSpendService(
            repository=repository,
            clock=lambda: "2026-08-08T15:00:00+00:00",
            today_provider=lambda: date(2026, 8, 8),
        )

    def test_total_answer_discloses_positive_negative_and_net(self) -> None:
        repository = FakeSpendRepository()
        result = self.make_service(repository).answer(
            "What was total vendor spend in division 3 for calendar year 2026?"
        )
        self.assertEqual(result.status, "answered")
        self.assertEqual(result.total.net_signed_amount, 1500.0)
        self.assertEqual(result.total.positive_distribution_amount, 1550.0)
        self.assertEqual(result.total.negative_distribution_amount, -50.0)
        self.assertIn("net signed posted AP GL-distribution", result.answer_text)
        self.assertEqual(repository.total_calls[0]["division"], 3)
        self.assertEqual(repository.total_calls[0]["range_start"], 20260101)
        self.assertFalse(result.governance.erp_write)
        self.assertEqual(result.governance.execution_effect, "none")
        self.assertEqual(
            result.evidence_consistency,
            "single_read_only_consistent_snapshot",
        )

    def test_highest_vendor_uses_account_5050_division_3_and_bounded_ranking(self) -> None:
        repository = FakeSpendRepository()
        result = self.make_service(repository).answer(
            "For account 5050-3, which vendor had the highest spend this month?"
        )
        self.assertEqual(result.status, "answered")
        self.assertEqual(result.leaders[0].vendor_name, "Alpha Supply")
        self.assertEqual(result.leaders[0].net_signed_amount, 1050.0)
        self.assertEqual(repository.ranking_calls[0]["division"], 3)
        self.assertEqual(repository.ranking_calls[0]["account"], 5050)
        self.assertEqual(repository.ranking_calls[0]["limit"], 10)
        self.assertTrue(result.leader_set_complete)

    def test_highest_vendor_each_month_returns_twelve_ordered_periods(self) -> None:
        repository = FakeSpendRepository()
        result = self.make_service(repository).answer(
            "Which vendor had the highest spend each month for account 5050-3 in calendar year 2025?"
        )
        self.assertEqual(result.status, "answered")
        self.assertEqual(result.parsed.intent, "top_vendor_by_month")
        self.assertEqual(len(result.monthly_periods), 12)
        self.assertEqual(
            [period.calendar_month for period in result.monthly_periods],
            list(range(1, 13)),
        )
        self.assertTrue(
            all(period.leaders[0].vendor_name == "Alpha Supply" for period in result.monthly_periods)
        )
        self.assertTrue(all(period.leader_set_complete for period in result.monthly_periods))
        self.assertEqual(result.monthly_period_limit, 12)
        self.assertEqual(result.monthly_leader_limit, 10)
        self.assertEqual(result.ranking, [])
        self.assertIn("12 ordered calendar months", result.answer_text)
        self.assertEqual(
            result.evidence_consistency,
            "single_read_only_consistent_snapshot",
        )
        self.assertEqual(
            [source.source_object for source in result.source_references],
            ["PMGLDS", "PMVEND"],
        )

    def test_monthly_series_preserves_an_explicit_no_evidence_month(self) -> None:
        repository = FirstMonthNoEvidenceRepository()
        result = self.make_service(repository).answer(
            "Which vendor had the highest spend each month for account 5050-3 in calendar year 2025?"
        )
        january = result.monthly_periods[0]
        february = result.monthly_periods[1]
        self.assertEqual(january.status, "no_evidence")
        self.assertEqual(january.leaders, [])
        self.assertTrue(january.leader_set_complete)
        self.assertIn("did not create a zero leader", january.explanation)
        self.assertEqual(february.status, "available")

    def test_truncated_rank_one_tie_is_qualified_as_a_lower_bound(self) -> None:
        repository = TruncatedLeaderTieRepository()
        result = self.make_service(repository).answer(
            "For account 5050-3, which vendor had the highest spend this month?"
        )
        self.assertEqual(result.status, "answered")
        self.assertFalse(result.ranking_complete)
        self.assertFalse(result.leader_set_complete)
        self.assertEqual(len(result.leaders), 10)
        self.assertIn("at least 10", result.answer_text)
        self.assertIn("does not assert an exact tie count", result.answer_text)
        self.assertTrue(
            any("lower bound" in warning for warning in result.warnings)
        )

    def test_unqueried_vendor_master_is_not_claimed_as_a_source(self) -> None:
        mapping = confirmed_mapping()
        mapping["PMVEND"] = {}
        repository = FakeSpendRepository(mapping=mapping)
        result = self.make_service(repository).answer(
            "For account 5050-3, which vendor had the highest spend this month?"
        )
        self.assertEqual(result.status, "answered")
        self.assertEqual(
            [source.source_object for source in result.source_references],
            ["PMGLDS"],
        )
        self.assertTrue(all(vendor.vendor_name is None for vendor in result.ranking))
        ranking_coverage = next(
            item for item in result.coverage if item.key == "vendor_ranking"
        )
        self.assertEqual(ranking_coverage.source, "MaddenCo PMGLDS")

    def test_all_missing_amounts_do_not_become_zero_spend_or_a_leader(self) -> None:
        repository = MissingAmountRepository()
        result = self.make_service(repository).answer(
            "For account 5050-3, which vendor had the highest spend this month?"
        )
        self.assertEqual(result.status, "no_evidence")
        self.assertEqual(result.leaders, [])
        self.assertIn("did not assert a zero spend", result.answer_text)
        amount_coverage = next(
            item
            for item in result.coverage
            if item.key == "signed_posted_ap_gl_distribution"
        )
        self.assertEqual(amount_coverage.status, "unavailable")
        self.assertFalse(amount_coverage.complete)

    def test_null_only_vendor_cannot_outrank_real_negative_amount(self) -> None:
        repository = MixedMissingAndNegativeRepository()
        result = self.make_service(repository).answer(
            "For account 5050-3, which vendor had the highest spend this month?"
        )
        self.assertEqual(result.status, "answered")
        self.assertEqual(result.leaders[0].vendor_number, "202")
        self.assertEqual(result.leaders[0].net_signed_amount, -5.0)
        self.assertNotIn("$0.00", result.answer_text.split("highest", 1)[-1].split(".", 1)[0])

    def test_ambiguous_question_executes_no_financial_query(self) -> None:
        repository = FakeSpendRepository()
        result = self.make_service(repository).answer(
            "For account 5050-3, which vendor was highest this month or this year?"
        )
        self.assertEqual(result.status, "needs_clarification")
        self.assertEqual(repository.total_calls, [])
        self.assertEqual(repository.ranking_calls, [])
        self.assertEqual(result.source_references, [])

    def test_new_unsupported_and_ambiguous_forms_execute_no_financial_query(self) -> None:
        questions = [
            "What were both the total spend and highest vendor in division 3 for 2026?",
            "What was the average vendor spend in division 3 for 2026?",
            "Which vendor was highest for account 5050-3 and account 6060-4 in 2026?",
            "Which vendor was highest for account 2026-3?",
            "What was vendor spend in division 3 for calendar year 2026 and ERP accounting year 2026?",
            "What was vendor spend in division 3 for January 2026 and ERP accounting period 8?",
        ]
        for question in questions:
            with self.subTest(question=question):
                repository = FakeSpendRepository()
                result = self.make_service(repository).answer(question)
                self.assertIn(result.status, {"needs_clarification", "unavailable"})
                self.assertEqual(repository.total_calls, [])
                self.assertEqual(repository.ranking_calls, [])
                self.assertEqual(result.evidence_consistency, "no_financial_query")

    def test_missing_calendar_date_field_fails_closed(self) -> None:
        mapping = confirmed_mapping()
        del mapping["PMGLDS"]["PMGDTEINV"]
        repository = FakeSpendRepository(mapping=mapping)
        result = self.make_service(repository).answer(
            "What was total vendor spend in division 3 for calendar year 2026?"
        )
        self.assertEqual(result.status, "unavailable")
        self.assertEqual(repository.total_calls, [])
        self.assertTrue(any("PMGDTEINV" in warning for warning in result.warnings))

    def test_unconfigured_numeric_invoice_date_encoding_fails_closed(self) -> None:
        repository = FakeSpendRepository()
        with patch.dict(
            os.environ,
            {"ETOP_AP_PMGDTEINV_NUMERIC_ENCODING": ""},
        ):
            result = self.make_service(repository).answer(
                "What was total vendor spend in division 3 for calendar year 2026?"
            )
        self.assertEqual(result.status, "unavailable")
        self.assertEqual(repository.total_calls, [])
        self.assertTrue(
            any(
                "ETOP_AP_PMGDTEINV_NUMERIC_ENCODING" in warning
                for warning in result.warnings
            )
        )

    def test_native_date_needs_no_numeric_encoding(self) -> None:
        mapping = confirmed_mapping()
        mapping["PMGLDS"]["PMGDTEINV"] = {
            "data_type": "date",
            "column_type": "date",
            "column_comment": "",
        }
        repository = FakeSpendRepository(mapping=mapping)
        with patch.dict(
            os.environ,
            {"ETOP_AP_PMGDTEINV_NUMERIC_ENCODING": ""},
        ):
            result = self.make_service(repository).answer(
                "What was total vendor spend in division 3 for calendar year 2026?"
            )
        self.assertEqual(result.status, "answered")
        self.assertEqual(repository.total_calls[0]["range_start"], "2026-01-01")
        self.assertEqual(
            repository.total_calls[0]["calendar_date_encoding"],
            "NATIVE_DATE",
        )

    def test_varchar_amount_mapping_fails_closed(self) -> None:
        mapping = confirmed_mapping()
        mapping["PMGLDS"]["PMGAMTINV"] = {
            "data_type": "varchar",
            "column_type": "varchar(20)",
            "column_comment": "",
        }
        repository = FakeSpendRepository(mapping=mapping)
        result = self.make_service(repository).answer(
            "What was total vendor spend in division 3 for ERP accounting year 2026?"
        )
        self.assertEqual(result.status, "unavailable")
        self.assertEqual(repository.total_calls, [])
        self.assertTrue(
            any("PMGAMTINV" in warning for warning in result.warnings)
        )

    def test_varchar_invoice_identity_mapping_answers_without_coercion(self) -> None:
        mapping = confirmed_mapping()
        self.assertEqual(
            mapping["PMGLDS"]["PMGNBINV"]["column_type"],
            "varchar(15)",
        )
        repository = FakeSpendRepository(mapping=mapping)
        result = self.make_service(repository).answer(
            "What was total vendor spend in division 3 for ERP accounting year 2026?"
        )
        self.assertEqual(result.status, "answered")
        self.assertEqual(len(repository.total_calls), 1)
        self.assertEqual(repository.ranking_calls, [])

    def test_numeric_invoice_identity_mapping_remains_supported(self) -> None:
        mapping = confirmed_mapping()
        mapping["PMGLDS"]["PMGNBINV"] = {
            "data_type": "decimal",
            "column_type": "decimal(12,0)",
            "column_comment": "",
        }
        repository = FakeSpendRepository(mapping=mapping)
        result = self.make_service(repository).answer(
            "What was total vendor spend in division 3 for ERP accounting year 2026?"
        )
        self.assertEqual(result.status, "answered")
        self.assertEqual(len(repository.total_calls), 1)
        self.assertEqual(repository.ranking_calls, [])

    def test_unsupported_invoice_identity_types_execute_no_financial_query(self) -> None:
        for data_type, column_type in [
            ("blob", "blob"),
            ("text", "text"),
            ("binary", "binary(15)"),
        ]:
            with self.subTest(column_type=column_type):
                mapping = confirmed_mapping()
                mapping["PMGLDS"]["PMGNBINV"] = {
                    "data_type": data_type,
                    "column_type": column_type,
                    "column_comment": "",
                }
                repository = FakeSpendRepository(mapping=mapping)
                result = self.make_service(repository).answer(
                    "What was total vendor spend in division 3 for ERP accounting year 2026?"
                )
                self.assertEqual(result.status, "unavailable")
                self.assertEqual(repository.total_calls, [])
                self.assertEqual(repository.ranking_calls, [])
                self.assertTrue(
                    any("PMGNBINV" in warning for warning in result.warnings)
                )

    def test_other_core_fields_retain_exact_numeric_gate(self) -> None:
        for field in ["PMGNBVND", "PMGAMTINV", "PMGNBGLDV", "PMGNBGL"]:
            with self.subTest(field=field):
                mapping = confirmed_mapping()
                mapping["PMGLDS"][field] = {
                    "data_type": "varchar",
                    "column_type": "varchar(15)",
                    "column_comment": "",
                }
                repository = FakeSpendRepository(mapping=mapping)
                result = self.make_service(repository).answer(
                    "What was total vendor spend in division 3 for ERP accounting year 2026?"
                )
                self.assertEqual(result.status, "unavailable")
                self.assertEqual(repository.total_calls, [])
                self.assertEqual(repository.ranking_calls, [])
                self.assertTrue(
                    any(field in warning for warning in result.warnings)
                )

    def test_approximate_and_undersized_numeric_dates_fail_closed(self) -> None:
        for data_type, column_type in [
            ("float", "float"),
            ("smallint", "smallint unsigned"),
            ("decimal", "decimal(8,2)"),
        ]:
            with self.subTest(column_type=column_type):
                mapping = confirmed_mapping()
                mapping["PMGLDS"]["PMGDTEINV"] = {
                    "data_type": data_type,
                    "column_type": column_type,
                    "column_comment": "",
                }
                repository = FakeSpendRepository(mapping=mapping)
                result = self.make_service(repository).answer(
                    "What was total vendor spend in division 3 for calendar year 2026?"
                )
                self.assertEqual(result.status, "unavailable")
                self.assertEqual(repository.total_calls, [])
                self.assertTrue(any("PMGDTEINV" in warning for warning in result.warnings))


class APSpendRepositoryTests(unittest.TestCase):
    def test_total_sql_has_fixed_projection_bound_filters_and_bound_parameters(self) -> None:
        database = CapturingDatabase()
        repository = ERPEvidenceRepository(database=database)
        repository.get_ap_spend_total(
            division=3,
            account=5050,
            time_basis="calendar_invoice_date",
            year=2026,
            accounting_period=None,
            range_start=20260801,
            range_end_exclusive=20260901,
            calendar_date_encoding="YYYYMMDD",
        )
        method, sql, parameters = database.calls[0]
        self.assertEqual(method, "one")
        self.assertIn("FROM PMGLDS AS G", sql)
        self.assertIn("SUM(CASE WHEN G.PMGAMTINV > 0", sql)
        self.assertIn("SUM(CASE WHEN G.PMGAMTINV < 0", sql)
        self.assertIn("G.PMGNBGLDV = %s", sql)
        self.assertIn("G.PMGNBGL = %s", sql)
        self.assertIn("G.PMGDTEINV >= %s", sql)
        self.assertEqual(parameters, (3, 5050, 20260801, 20260901))
        self.assertNotIn("5050", sql)
        self.assertNotIn("20260801", sql)

    def test_ranking_sql_is_row_capped_and_never_uses_question_text(self) -> None:
        database = CapturingDatabase()
        repository = ERPEvidenceRepository(database=database)
        rows, complete = repository.get_ap_spend_ranking(
            division=3,
            account=None,
            time_basis="erp_accounting_year",
            year=2026,
            accounting_period=None,
            range_start=None,
            range_end_exclusive=None,
            calendar_date_encoding=None,
            limit=999,
        )
        self.assertEqual(rows, [])
        self.assertTrue(complete)
        _, sql, parameters = database.calls[0]
        self.assertIn("GROUP BY G.PMGNBVND", sql)
        self.assertIn("ORDER BY", sql)
        self.assertIn("LIMIT 11", sql)
        self.assertIn("HAVING COUNT(G.PMGAMTINV) > 0", sql)
        self.assertEqual(parameters, (3, 2026))

    def test_mmddyyyy_numeric_date_uses_fixed_safe_conversion(self) -> None:
        database = CapturingDatabase()
        repository = ERPEvidenceRepository(database=database)
        repository.get_ap_spend_total(
            division=3,
            account=None,
            time_basis="calendar_invoice_date",
            year=2026,
            accounting_period=None,
            range_start="2026-01-01",
            range_end_exclusive="2027-01-01",
            calendar_date_encoding="MMDDYYYY",
        )
        _, sql, parameters = database.calls[0]
        self.assertIn("STR_TO_DATE", sql)
        self.assertIn("'%m%d%Y'", sql)
        self.assertEqual(parameters, (3, "2026-01-01", "2027-01-01"))

    def test_mmddyyyy_december_to_january_rollover_keeps_iso_bounds(self) -> None:
        database = CapturingDatabase()
        repository = ERPEvidenceRepository(database=database)
        repository.get_ap_spend_total(
            division=3,
            account=5050,
            time_basis="calendar_invoice_date",
            year=2026,
            accounting_period=None,
            range_start="2026-12-01",
            range_end_exclusive="2027-01-01",
            calendar_date_encoding="MMDDYYYY",
        )
        _, sql, parameters = database.calls[0]
        self.assertEqual(sql.count("STR_TO_DATE"), 2)
        self.assertEqual(
            parameters,
            (3, 5050, "2026-12-01", "2027-01-01"),
        )

    def test_evidence_packet_uses_one_snapshot_for_all_queries(self) -> None:
        database = CapturingDatabase()
        repository = ERPEvidenceRepository(database=database)
        packet = repository.get_ap_spend_evidence(
            division=3,
            account=5050,
            time_basis="erp_accounting_year",
            year=2026,
            accounting_period=None,
            range_start=None,
            range_end_exclusive=None,
            calendar_date_encoding=None,
            include_ranking=True,
            include_vendor_names=True,
        )
        self.assertEqual(packet["ranking"], [])
        self.assertEqual(
            [method for method, _sql, _parameters in database.calls].count("snapshot"),
            1,
        )

    def test_monthly_leaders_use_twelve_fixed_bounded_queries_in_one_snapshot(self) -> None:
        database = CapturingDatabase()
        repository = ERPEvidenceRepository(database=database)
        packet = repository.get_ap_spend_evidence(
            division=3,
            account=5050,
            time_basis="calendar_invoice_date",
            year=2025,
            accounting_period=None,
            range_start=20250101,
            range_end_exclusive=20260101,
            calendar_date_encoding="YYYYMMDD",
            include_ranking=False,
            include_monthly=True,
            include_vendor_names=True,
        )
        self.assertEqual(len(packet["monthly_rankings"]), 12)
        self.assertEqual(
            [period["calendar_month"] for period in packet["monthly_rankings"]],
            list(range(1, 13)),
        )
        self.assertEqual(
            [method for method, _sql, _parameters in database.calls].count("snapshot"),
            1,
        )
        ranking_calls = [
            (sql, parameters)
            for method, sql, parameters in database.calls
            if method == "all" and "GROUP BY G.PMGNBVND" in sql
        ]
        self.assertEqual(len(ranking_calls), 12)
        self.assertTrue(all("LIMIT 11" in sql for sql, _ in ranking_calls))
        self.assertEqual(
            ranking_calls[0][1],
            (3, 5050, 20250101, 20250201),
        )
        self.assertEqual(
            ranking_calls[-1][1],
            (3, 5050, 20251201, 20260101),
        )


if __name__ == "__main__":
    unittest.main()
