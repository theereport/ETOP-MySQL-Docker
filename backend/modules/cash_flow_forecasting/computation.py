from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Literal


HORIZON_WEEKS = 14
OTHER_PATTERN_LOOKBACK_WEEKS = 26
PRIOR_YEAR_OFFSET_DAYS = 364  # 52 weeks - keeps Monday-start alignment


# -- description classification (validated live against 6 months of --
# -- real GMAD JE postings to the tracked cash accounts) --------------

_RECEIPT_MARKERS = (
    "CASH RECEIPTS",
    "ACH RECEIPTS",
    "MOBILE RECEIPTS",
    "LBOX RECEIPTS",
    "MAIL RECEIPTS",
    "CC RECEIPTS",
    "CC/WEBPAY RECEIPTS",
    "WEBPAY RECEIPTS",
    "ECOMM RECEIPTS",
)
_SWEEP_MARKERS = ("SWEEP FROM", "SWEEP TO", "FUNDS TRANSFER FROM")
_LOC_MARKERS = ("ON LOC", "LINE OF CREDIT FEE")

JeClassification = Literal["receipt", "sweep", "loc", "other"]


def classify_je_description(description: str) -> JeClassification:
    upper = (description or "").upper()
    if any(marker in upper for marker in _RECEIPT_MARKERS):
        return "receipt"
    if any(marker in upper for marker in _SWEEP_MARKERS):
        return "sweep"
    if any(marker in upper for marker in _LOC_MARKERS):
        return "loc"
    return "other"


_LEADING_DATE_RE = re.compile(r"^[\d./\-]+\s*")
_EMBEDDED_DATE_RE = re.compile(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}")


def normalize_description_family(description: str) -> str:
    text = (description or "").strip().upper()
    text = _LEADING_DATE_RE.sub("", text)
    text = _EMBEDDED_DATE_RE.sub("<DATE>", text)
    return text.strip()


def signed_cash_amount(amount: float, debit_or_credit: str) -> float:
    """Sign a GMAD amount for a cash/bank asset account: DB increases
    cash (inflow), CR decreases cash (outflow)."""

    return amount if (debit_or_credit or "").strip().upper() == "DB" else -amount


def parse_madden_date(value: object) -> date | None:
    text = str(value or "").strip()
    if len(text) != 8 or text == "00000000":
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


# -- week grid ----------------------------------------------------------


def week_bounds(
    as_of: date, horizon_weeks: int = HORIZON_WEEKS
) -> list[tuple[int, date, date]]:
    """14 Monday-Sunday weeks starting with the week containing as_of."""

    monday = as_of - timedelta(days=as_of.weekday())
    return [
        (index + 1, monday + timedelta(weeks=index), monday + timedelta(weeks=index, days=6))
        for index in range(horizon_weeks)
    ]


def shift_weeks_one_year_back(
    weeks: list[tuple[int, date, date]],
) -> list[tuple[int, date, date]]:
    offset = timedelta(days=PRIOR_YEAR_OFFSET_DAYS)
    return [
        (index, start - offset, end - offset) for index, start, end in weeks
    ]


def _week_for_date(
    target: date, weeks: list[tuple[int, date, date]]
) -> int | None:
    for index, start, end in weeks:
        if start <= target <= end:
            return index
    return None


# -- AR / AP due-date bucketing (the v1 due-date baseline) --------------


def bucket_ar_by_due_week(
    rows: list[dict[str, Any]], weeks: list[tuple[int, date, date]]
) -> dict[int, float]:
    totals = {index: 0.0 for index, _, _ in weeks}
    for row in rows:
        due = parse_madden_date(row.get("TARODTEDUE"))
        if due is None:
            continue
        index = _week_for_date(due, weeks)
        if index is None:
            continue
        amount = row.get("TAROAMTOPN")
        if amount is None:
            amount = row.get("TAROAMTORG")
        totals[index] += float(amount or 0)
    return totals


def bucket_ap_cache_rows_by_week(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Bucket a raw PMHD scan into Monday-Sunday weeks, for the AP
    due-date cache. `rows` come from a full, unfiltered PMHD read."""

    weekly: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    for row in rows:
        due = parse_madden_date(row.get("PMHDTEDUE"))
        if due is None:
            continue
        monday = due - timedelta(days=due.weekday())
        sunday = monday + timedelta(days=6)
        key = (monday.isoformat(), sunday.isoformat())
        amount = float(row.get("PMHAMTINV") or 0) - float(row.get("PMHAMTDIS") or 0)
        on_hold = str(row.get("PMHFLGHLD") or "").strip().upper() == "Y"
        weekly[key][1 if on_hold else 0] += amount
    return [
        {
            "week_start": start,
            "week_end": end,
            "open_amount": values[0],
            "open_on_hold_amount": values[1],
        }
        for (start, end), values in weekly.items()
    ]


# -- GMAD-derived actuals (receipts / AP check-writing / other) --------


def actual_ar_and_other_from_je_rows(
    je_rows: list[dict[str, Any]], weeks: list[tuple[int, date, date]]
) -> tuple[dict[int, float], dict[int, float]]:
    """Split GACDSYS='JE' cash-account postings into actual AR (receipt
    summaries) and actual other (everything left after excluding
    receipts, inter-account sweeps, and Line of Credit activity)."""

    ar_totals = {index: 0.0 for index, _, _ in weeks}
    other_totals = {index: 0.0 for index, _, _ in weeks}
    for row in je_rows:
        posted = parse_madden_date(row.get("GADTPST"))
        if posted is None:
            continue
        index = _week_for_date(posted, weeks)
        if index is None:
            continue
        classification = classify_je_description(row.get("GADSR", ""))
        if classification not in ("receipt", "other"):
            continue
        amount = signed_cash_amount(
            float(row.get("GAAMT") or 0), row.get("GACDDBCR", "")
        )
        if classification == "receipt":
            ar_totals[index] += amount
        else:
            other_totals[index] += amount
    return ar_totals, other_totals


def actual_ap_from_ap_rows(
    ap_rows: list[dict[str, Any]], weeks: list[tuple[int, date, date]]
) -> dict[int, float]:
    """Actual AP cash-out (positive = paid out) from GACDSYS='AP'
    postings to the cash accounts."""

    totals = {index: 0.0 for index, _, _ in weeks}
    for row in ap_rows:
        posted = parse_madden_date(row.get("GADTPST"))
        if posted is None:
            continue
        index = _week_for_date(posted, weeks)
        if index is None:
            continue
        amount = signed_cash_amount(
            float(row.get("GAAMT") or 0), row.get("GACDDBCR", "")
        )
        totals[index] += -amount
    return totals


# -- "other" bucket: recurring-pattern detection and projection --------


class OtherFamilyPattern:
    __slots__ = ("cadence_days", "average_amount", "last_date", "occurrence_count")

    def __init__(
        self,
        cadence_days: int | None,
        average_amount: float,
        last_date: date | None,
        occurrence_count: int,
    ) -> None:
        self.cadence_days = cadence_days
        self.average_amount = average_amount
        self.last_date = last_date
        self.occurrence_count = occurrence_count


MIN_OCCURRENCES_TO_PROJECT = 3
MIN_CADENCE_DAYS = 5


def detect_other_patterns(
    je_rows: list[dict[str, Any]],
    *,
    lookback_start: date,
    before: date,
) -> dict[str, OtherFamilyPattern]:
    """Detect recurring non-AR/AP cash-account items in [lookback_start,
    before). `before` is exclusive so a backtest never uses data that
    would not yet have existed at the historical as-of date being
    simulated.

    Same-day rows for a family are summed into one daily total first -
    a single payroll run, for example, can post several GMAD lines on
    the same day, and treating each line as its own "occurrence" would
    both undercount the real per-event amount and corrupt the gap
    calculation with spurious zero/near-zero gaps.

    At least 3 distinct days are required before a cadence is trusted
    (2 occurrences means exactly one gap, with no way to tell a real
    recurrence from a coincidence - confirmed live: a single one-off
    ~$6.6M wire that happened to occur twice was otherwise projected
    as if it recurred every 14 days indefinitely). The cadence itself
    is the median day-to-day gap, not the most common single gap value,
    which is more robust when real-world gaps vary by a few days
    (holidays, weekends) - and a median gap under 5 days is treated as
    noise (irregular/clustered postings), not a trustworthy cadence.
    """

    daily_totals: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    for row in je_rows:
        description = row.get("GADSR", "")
        if classify_je_description(description) != "other":
            continue
        posted = parse_madden_date(row.get("GADTPST"))
        if posted is None or not (lookback_start <= posted < before):
            continue
        family = normalize_description_family(description)
        amount = signed_cash_amount(
            float(row.get("GAAMT") or 0), row.get("GACDDBCR", "")
        )
        daily_totals[family][posted] += amount

    patterns: dict[str, OtherFamilyPattern] = {}
    for family, totals_by_day in daily_totals.items():
        dates = sorted(totals_by_day.keys())
        amounts = [totals_by_day[d] for d in dates]

        cadence_days: int | None = None
        if len(dates) >= MIN_OCCURRENCES_TO_PROJECT:
            gaps = sorted(
                (dates[i] - dates[i - 1]).days for i in range(1, len(dates))
            )
            median_gap = gaps[len(gaps) // 2]
            if median_gap >= MIN_CADENCE_DAYS:
                cadence_days = median_gap

        patterns[family] = OtherFamilyPattern(
            cadence_days=cadence_days,
            average_amount=sum(amounts) / len(amounts) if amounts else 0.0,
            last_date=dates[-1] if dates else None,
            occurrence_count=len(dates),
        )
    return patterns


def project_other_bucket(
    patterns: dict[str, OtherFamilyPattern],
    weeks: list[tuple[int, date, date]],
    *,
    max_projected_occurrences: int = 500,
) -> dict[int, float]:
    totals = {index: 0.0 for index, _, _ in weeks}
    if not weeks:
        return totals
    horizon_end = weeks[-1][2]
    for pattern in patterns.values():
        if (
            pattern.cadence_days is None
            or pattern.last_date is None
            or pattern.occurrence_count < 2
        ):
            continue
        next_date = pattern.last_date + timedelta(days=pattern.cadence_days)
        projected_count = 0
        while next_date <= horizon_end and projected_count < max_projected_occurrences:
            index = _week_for_date(next_date, weeks)
            if index is not None:
                totals[index] += pattern.average_amount
            next_date += timedelta(days=pattern.cadence_days)
            projected_count += 1
    return totals
