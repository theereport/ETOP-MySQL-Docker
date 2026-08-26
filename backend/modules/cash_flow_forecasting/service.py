from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from . import computation as calc
from .ap_due_date_cache_source import (
    ApDueDateCacheRefreshFailed,
    scan_all_open_ap_invoices,
)
from .bank_balance_source import (
    BankBalanceFileUnavailable,
    latest_row_on_or_before,
    read_bank_balance_rows,
    row_for_week_end,
)
from .notes_repository import (
    CashFlowForecastingNotesRepository,
    cash_flow_forecasting_notes_repository,
)
from .repository import CashFlowForecastingRepository, cash_flow_forecasting_repository
from .schemas import (
    CashFlowAccuracyHistoryResponse,
    CashFlowAccuracyWeek,
    CashFlowForecastGap,
    CashFlowForecastResponse,
    CashFlowSnapshotHistoryResponse,
    CashFlowSnapshotSummary,
    PriorYearWeekComparison,
    SourceEvidence,
    StartingCashPosition,
    WeeklyProjection,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


_STANDARD_GAPS: list[CashFlowForecastGap] = [
    CashFlowForecastGap(
        code="due_date_baseline_only",
        label="AR/AP projection uses a due-date baseline",
        explanation=(
            "Each open AR item and each open AP payable is projected to "
            "convert to cash in the week containing its due date. "
            "MaddenCo does not reliably retain a per-invoice paid date "
            "(confirmed empirically), so this module does not attempt a "
            "customer- or vendor-specific payment-speed model."
        ),
    ),
    CashFlowForecastGap(
        code="other_bucket_pattern_detection",
        label="Non-AR/AP cash flow is a historical-cadence estimate",
        explanation=(
            "The 'other' category (payroll, retirement, fuel cards, "
            "bank/merchant fees, etc.) is projected from each recurring "
            "item's historical cadence and trailing average amount. It "
            "does not know about future headcount changes, fee-schedule "
            "changes, or one-off items."
        ),
    ),
    CashFlowForecastGap(
        code="variance_is_category_not_narrative",
        label="Variance is reported by category, not by cause",
        explanation=(
            "Prior-year and closed-week variance is broken out by AR/AP/"
            "other dollar amount, not as a narrative root cause (e.g. "
            "'Customer X paid late'). MaddenCo does not reliably retain "
            "a per-invoice paid date, so finer attribution isn't "
            "reliable evidence."
        ),
    ),
    CashFlowForecastGap(
        code="no_automatic_recalibration",
        label="This module does not self-adjust",
        explanation=(
            "Accumulated projected-vs-actual variance is evidence for a "
            "human to review. Nothing in this module feeds that history "
            "back into future projections automatically."
        ),
    ),
    CashFlowForecastGap(
        code="victory_bank_excluded",
        label="Victory Bank (GL account 1014) is not tracked",
        explanation=(
            "GMGM account 1014 (Cash in Bank - Victory Bank) has no "
            "corresponding column in the Consolidated Daily Bank "
            "Balances workbook, so it is excluded from the starting "
            "cash position and from the GL cash-account activity used "
            "here."
        ),
    ),
    CashFlowForecastGap(
        code="ap_hold_timing_unknown",
        label="On-hold payables are shown separately, not zeroed",
        explanation=(
            "Payables flagged on hold (PMHFLGHLD='Y') are reported as "
            "their own figure rather than assumed to pay on schedule, "
            "but this module has no evidence of when (or whether) a "
            "hold will release."
        ),
    ),
    CashFlowForecastGap(
        code="prior_year_ap_projection_unavailable",
        label="Prior-year AP projection is not computable",
        explanation=(
            "PMHD holds only currently-open payables; once an invoice is "
            "paid it moves to PTHD, which retains only a small rolling "
            "window (confirmed live: ~200 rows platform-wide) rather "
            "than a permanent due-date archive. There is no reliable "
            "way to know what was due, a year ago, for an invoice "
            "that's since been paid - so the prior-year comparison shows "
            "actual AP cash-out only, with no projected baseline or "
            "variance for that category."
        ),
    ),
]


class CashFlowForecastingService:
    def __init__(
        self,
        repository: CashFlowForecastingRepository = cash_flow_forecasting_repository,
        notes_repository: CashFlowForecastingNotesRepository = (
            cash_flow_forecasting_notes_repository
        ),
    ) -> None:
        self._repository = repository
        self._notes_repository = notes_repository

    # -- AP due-date cache -----------------------------------------------

    def refresh_ap_due_date_cache(self) -> dict[str, Any]:
        try:
            rows = scan_all_open_ap_invoices()
        except ApDueDateCacheRefreshFailed as exc:
            return {"status": "unavailable_source_capability", "message": str(exc)}
        buckets = calc.bucket_ap_cache_rows_by_week(rows)
        refreshed_at = _now_iso()
        self._notes_repository.replace_ap_due_date_cache(
            buckets, refreshed_at=refreshed_at
        )
        return {
            "status": "ok",
            "weeks_cached": len(buckets),
            "source_rows": len(rows),
            "refreshed_at": refreshed_at,
        }

    def _ap_for_weeks(
        self, weeks: list[tuple[int, date, date]]
    ) -> tuple[dict[int, float], dict[int, float], bool]:
        """Read the AP due-date cache for each week. Returns
        (open_by_week, on_hold_by_week, cache_available)."""

        cache_refreshed_at = self._notes_repository.ap_cache_refreshed_at()
        if cache_refreshed_at is None:
            empty = {index: 0.0 for index, _, _ in weeks}
            return empty, empty, False
        open_totals: dict[int, float] = {}
        hold_totals: dict[int, float] = {}
        for index, start, end in weeks:
            cached = self._notes_repository.get_ap_due_date_cache(
                start.isoformat(), end.isoformat()
            )
            open_totals[index] = cached["open_amount"] if cached else 0.0
            hold_totals[index] = cached["open_on_hold_amount"] if cached else 0.0
        return open_totals, hold_totals, True

    # -- forward 14-week forecast -----------------------------------------

    def get_current_forecast(self, as_of: date | None = None) -> CashFlowForecastResponse:
        as_of = as_of or datetime.now().date()
        weeks = calc.week_bounds(as_of)
        gaps = list(_STANDARD_GAPS)

        starting_position, bank_status = self._starting_position(as_of)

        ar_rows = self._repository.get_open_ar_invoices_due_between(
            weeks[0][1], weeks[-1][2]
        )
        projected_ar = calc.bucket_ar_by_due_week(ar_rows, weeks)

        projected_ap, projected_ap_hold, ap_cache_available = self._ap_for_weeks(weeks)
        if not ap_cache_available:
            gaps.append(
                CashFlowForecastGap(
                    code="ap_cache_not_refreshed",
                    label="AP projection is unavailable",
                    explanation=(
                        "PMHD (open vendor payables) has 5M+ rows with no "
                        "index usable for a due-date filter, so it cannot "
                        "be queried live within the platform's statement "
                        "timeout. The AP due-date cache has never been "
                        "refreshed - call POST "
                        "/api/v1/cash-flow-forecasting/ap-cache/refresh "
                        "(it takes a few minutes) and retry."
                    ),
                )
            )

        lookback_start = as_of - timedelta(weeks=calc.OTHER_PATTERN_LOOKBACK_WEEKS)
        je_rows = self._repository.get_cash_account_je_activity(lookback_start, as_of)
        other_patterns = calc.detect_other_patterns(
            je_rows, lookback_start=lookback_start, before=as_of
        )
        projected_other = calc.project_other_bucket(other_patterns, weeks)

        weekly_projections: list[WeeklyProjection] = []
        running_balance = starting_position.net_available
        for index, start, end in weeks:
            ar = projected_ar.get(index, 0.0)
            ap = projected_ap.get(index, 0.0) if ap_cache_available else None
            ap_hold = projected_ap_hold.get(index, 0.0) if ap_cache_available else None
            other = projected_other.get(index, 0.0)
            net_change = ar - ap + other if ap is not None else None

            ending_balance = None
            if net_change is not None and running_balance is not None:
                running_balance = running_balance + net_change
                ending_balance = running_balance
            elif net_change is None:
                # AP unavailable this call - stop chaining so later weeks
                # don't silently inherit a balance that omitted AP.
                running_balance = None

            weekly_projections.append(
                WeeklyProjection(
                    week_index=index,
                    week_start=start.isoformat(),
                    week_end=end.isoformat(),
                    projected_ar=_round(ar),
                    projected_ap=_round(ap),
                    projected_ap_on_hold=_round(ap_hold),
                    projected_other=_round(other),
                    projected_net_change=_round(net_change),
                    projected_ending_balance=_round(ending_balance),
                )
            )

        prior_year_comparison = self._prior_year_comparison(weeks, as_of)

        return CashFlowForecastResponse(
            generated_at=_now_iso(),
            as_of=as_of.isoformat(),
            source=SourceEvidence(status=bank_status, retrieved_at=_now_iso()),
            starting_position=starting_position,
            weeks=weekly_projections,
            prior_year_comparison=prior_year_comparison,
            gaps=gaps,
        )

    def _starting_position(
        self, as_of: date
    ) -> tuple[StartingCashPosition, str]:
        try:
            rows = read_bank_balance_rows()
        except BankBalanceFileUnavailable as exc:
            return (
                StartingCashPosition(
                    business_day=None,
                    net_available=None,
                    line_of_credit_balance=None,
                    line_of_credit_available=None,
                    line_of_credit_withholding=None,
                    status="unavailable_source_capability",
                    explanation=str(exc),
                ),
                "unavailable_source_capability",
            )
        row = latest_row_on_or_before(as_of, rows)
        if row is None:
            return (
                StartingCashPosition(
                    business_day=None,
                    net_available=None,
                    line_of_credit_balance=None,
                    line_of_credit_available=None,
                    line_of_credit_withholding=None,
                    status="unavailable_source_capability",
                    explanation="No bank balance row exists on or before this date.",
                ),
                "unavailable_source_capability",
            )
        return (
            StartingCashPosition(
                business_day=row.business_day.isoformat(),
                net_available=_round(row.net_available),
                line_of_credit_balance=_round(row.line_of_credit_balance),
                line_of_credit_available=_round(row.line_of_credit_available),
                line_of_credit_withholding=_round(row.line_of_credit_withholding),
            ),
            "available",
        )

    def _prior_year_comparison(
        self, weeks: list[tuple[int, date, date]], as_of: date
    ) -> list[PriorYearWeekComparison]:
        prior_weeks = calc.shift_weeks_one_year_back(weeks)
        prior_start, prior_end = prior_weeks[0][1], prior_weeks[-1][2]

        ar_projected_rows = self._repository.get_ar_invoices_due_between_any_status(
            prior_start, prior_end, invoiced_on_or_before=prior_start
        )
        prior_projected_ar = calc.bucket_ar_by_due_week(ar_projected_rows, prior_weeks)

        other_lookback_start = prior_start - timedelta(
            weeks=calc.OTHER_PATTERN_LOOKBACK_WEEKS
        )
        prior_lookback_rows = self._repository.get_cash_account_je_activity(
            other_lookback_start, prior_start
        )
        prior_patterns = calc.detect_other_patterns(
            prior_lookback_rows, lookback_start=other_lookback_start, before=prior_start
        )
        prior_projected_other = calc.project_other_bucket(prior_patterns, prior_weeks)

        actual_je_rows = self._repository.get_cash_account_je_activity(
            prior_start, prior_end
        )
        actual_ar, actual_other = calc.actual_ar_and_other_from_je_rows(
            actual_je_rows, prior_weeks
        )
        actual_ap_rows = self._repository.get_cash_account_ap_activity(
            prior_start, prior_end
        )
        actual_ap = calc.actual_ap_from_ap_rows(actual_ap_rows, prior_weeks)

        try:
            bank_rows = read_bank_balance_rows()
        except BankBalanceFileUnavailable:
            bank_rows = []

        today = datetime.now().date()
        comparisons: list[PriorYearWeekComparison] = []
        for (index, start, end), (_, prior_start_week, prior_end_week) in zip(
            weeks, prior_weeks
        ):
            p_ar = prior_projected_ar.get(index, 0.0)
            p_other = prior_projected_other.get(index, 0.0)
            a_ar = actual_ar.get(index, 0.0)
            a_ap = actual_ap.get(index, 0.0)
            a_other = actual_other.get(index, 0.0)
            actual_balance_row = row_for_week_end(prior_end_week, bank_rows) if bank_rows else None
            a_ending = _round(actual_balance_row.net_available) if actual_balance_row else None

            current_year_closed = end < today
            current_actual_ar = current_actual_ap = current_actual_other = None
            current_actual_ending = None
            current_variance_ar = current_variance_ap = current_variance_other = None
            current_variance_ending = None
            if current_year_closed:
                cy_je_rows = self._repository.get_cash_account_je_activity(start, end)
                cy_ap_rows = self._repository.get_cash_account_ap_activity(start, end)
                cy_ar_totals, cy_other_totals = calc.actual_ar_and_other_from_je_rows(
                    cy_je_rows, [(index, start, end)]
                )
                cy_ap_totals = calc.actual_ap_from_ap_rows(cy_ap_rows, [(index, start, end)])
                current_actual_ar = _round(cy_ar_totals.get(index, 0.0))
                current_actual_ap = _round(cy_ap_totals.get(index, 0.0))
                current_actual_other = _round(cy_other_totals.get(index, 0.0))
                cy_balance_row = row_for_week_end(end, bank_rows) if bank_rows else None
                current_actual_ending = (
                    _round(cy_balance_row.net_available) if cy_balance_row else None
                )

            comparisons.append(
                PriorYearWeekComparison(
                    week_index=index,
                    week_start=start.isoformat(),
                    week_end=end.isoformat(),
                    prior_year_week_start=prior_start_week.isoformat(),
                    prior_year_week_end=prior_end_week.isoformat(),
                    prior_year_projected_ar=_round(p_ar),
                    prior_year_projected_ap=None,
                    prior_year_projected_other=_round(p_other),
                    prior_year_projected_ending_balance=None,
                    prior_year_actual_ar=_round(a_ar),
                    prior_year_actual_ap=_round(a_ap),
                    prior_year_actual_other=_round(a_other),
                    prior_year_actual_ending_balance=a_ending,
                    prior_year_variance_ar=_round(a_ar - p_ar),
                    prior_year_variance_ap=None,
                    prior_year_variance_other=_round(a_other - p_other),
                    prior_year_variance_ending_balance=None,
                    current_year_week_closed=current_year_closed,
                    current_year_actual_ar=current_actual_ar,
                    current_year_actual_ap=current_actual_ap,
                    current_year_actual_other=current_actual_other,
                    current_year_actual_ending_balance=current_actual_ending,
                )
            )
        return comparisons

    # -- snapshots (append-only persistence) ------------------------------

    def create_snapshot(self, as_of: date | None = None) -> str:
        forecast = self.get_current_forecast(as_of)
        snapshot_id = f"CFF-{uuid4().hex}"
        weeks_payload = [
            {
                "week_id": f"CFFW-{uuid4().hex}",
                "week_index": week.week_index,
                "week_start": week.week_start,
                "week_end": week.week_end,
                "projected_ar": week.projected_ar,
                "projected_ap": week.projected_ap,
                "projected_ap_on_hold": week.projected_ap_on_hold,
                "projected_other": week.projected_other,
                "projected_ending_balance": week.projected_ending_balance,
            }
            for week in forecast.weeks
        ]
        self._notes_repository.create_snapshot(
            snapshot={
                "snapshot_id": snapshot_id,
                "as_of": forecast.as_of,
                "generated_at": forecast.generated_at,
                "horizon_weeks": forecast.horizon_weeks,
                "starting_balance_business_day": forecast.starting_position.business_day,
                "starting_balance_amount": forecast.starting_position.net_available,
                "loc_balance": forecast.starting_position.line_of_credit_balance,
                "loc_available": forecast.starting_position.line_of_credit_available,
                "evidence_snapshot": forecast.model_dump(),
            },
            weeks=weeks_payload,
        )
        return snapshot_id

    def list_snapshots(self, limit: int = 50) -> CashFlowSnapshotHistoryResponse:
        rows = self._notes_repository.list_snapshots(limit)
        return CashFlowSnapshotHistoryResponse(
            count=len(rows),
            snapshots=[CashFlowSnapshotSummary(**row) for row in rows],
        )

    # -- accuracy history (closed-week actual-vs-projected) --------------

    def record_closed_weeks(self, as_of: date | None = None) -> dict[str, Any]:
        """Compute and append an actual record for every one of the
        current 14-week horizon's weeks that has already closed and
        does not yet have a recorded actual."""

        as_of = as_of or datetime.now().date()
        weeks = calc.week_bounds(as_of)
        today = datetime.now().date()
        try:
            bank_rows = read_bank_balance_rows()
        except BankBalanceFileUnavailable:
            bank_rows = []

        recorded = 0
        skipped = 0
        for index, start, end in weeks:
            if end >= today:
                continue
            existing = self._notes_repository.latest_actual_for_week(
                start.isoformat(), end.isoformat()
            )
            if existing is not None:
                skipped += 1
                continue

            je_rows = self._repository.get_cash_account_je_activity(start, end)
            ap_rows = self._repository.get_cash_account_ap_activity(start, end)
            ar_totals, other_totals = calc.actual_ar_and_other_from_je_rows(
                je_rows, [(index, start, end)]
            )
            ap_totals = calc.actual_ap_from_ap_rows(ap_rows, [(index, start, end)])
            balance_row = row_for_week_end(end, bank_rows) if bank_rows else None

            self._notes_repository.record_actual(
                {
                    "actual_id": f"CFFA-{uuid4().hex}",
                    "week_start": start.isoformat(),
                    "week_end": end.isoformat(),
                    "actual_ar": ar_totals.get(index, 0.0),
                    "actual_ap": ap_totals.get(index, 0.0),
                    "actual_other": other_totals.get(index, 0.0),
                    "actual_ending_balance": (
                        balance_row.net_available if balance_row else None
                    ),
                    "recorded_at": _now_iso(),
                    "evidence_snapshot": {
                        "week_start": start.isoformat(),
                        "week_end": end.isoformat(),
                        "je_row_count": len(je_rows),
                        "ap_row_count": len(ap_rows),
                    },
                }
            )
            recorded += 1
        return {"recorded": recorded, "already_recorded": skipped}

    def get_accuracy_history(self, limit: int = 200) -> CashFlowAccuracyHistoryResponse:
        rows = self._notes_repository.list_actuals(limit)
        weeks = [
            CashFlowAccuracyWeek(
                week_start=row["week_start"],
                week_end=row["week_end"],
                projected_ar=row.get("projected_ar") or 0.0,
                projected_ap=row.get("projected_ap") or 0.0,
                projected_other=row.get("projected_other") or 0.0,
                projected_ending_balance=row.get("projected_ending_balance"),
                actual_ar=row["actual_ar"],
                actual_ap=row["actual_ap"],
                actual_other=row["actual_other"],
                actual_ending_balance=row.get("actual_ending_balance"),
                variance_ar=row["actual_ar"] - (row.get("projected_ar") or 0.0),
                variance_ap=row["actual_ap"] - (row.get("projected_ap") or 0.0),
                variance_other=row["actual_other"] - (row.get("projected_other") or 0.0),
                variance_ending_balance=(
                    row["actual_ending_balance"] - row["projected_ending_balance"]
                    if row.get("actual_ending_balance") is not None
                    and row.get("projected_ending_balance") is not None
                    else None
                ),
                recorded_at=row["recorded_at"],
            )
            for row in rows
        ]
        return CashFlowAccuracyHistoryResponse(count=len(weeks), weeks=weeks)


cash_flow_forecasting_service = CashFlowForecastingService()
