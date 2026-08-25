from __future__ import annotations

import re
from datetime import date

from .ap_spend_schemas import APSpendParsedQuestion


PARSER_VERSION = "ap-vendor-spend-question-parser@1.1.0"

MONTH_NUMBERS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start.isoformat(), end.isoformat()


def _year_bounds(year: int) -> tuple[str, str]:
    return date(year, 1, 1).isoformat(), date(year + 1, 1, 1).isoformat()


def _unique_int_matches(pattern: str, text: str) -> list[int]:
    return sorted({int(value) for value in re.findall(pattern, text)})


def parse_ap_spend_question(
    question: str,
    *,
    today: date | None = None,
) -> APSpendParsedQuestion:
    current_date = today or date.today()
    original = question.strip()
    normalized = re.sub(r"\s+", " ", original.lower()).strip()
    notes: list[str] = []
    missing: list[str] = []
    ambiguous: list[str] = []
    unavailable: list[str] = []

    intent = None
    unsupported_measure = re.search(
        r"\b(average|avg|mean|median|lowest|least|bottom|count|trend|breakdown|"
        r"excluding|exclude|except|compare|comparison)\b",
        normalized,
    )
    unsupported_top_count = re.search(r"\btop\s+\d+\b", normalized)
    if unsupported_measure or unsupported_top_count:
        unavailable.append("unsupported_question_modifier")
        notes.append(
            "Only an exact total or the single highest vendor is supported; averages, counts, exclusions, comparisons, trends, and multi-vendor top-N requests are unavailable."
        )
    monthly_series_signal = bool(
        re.search(r"\b(each|every)\s+(calendar\s+)?month\b", normalized)
        or re.search(r"\bby\s+(calendar\s+)?month\b", normalized)
        or re.search(r"\bmonthly\b", normalized)
    )
    top_language = bool(
        re.search(r"\b(highest|top|most)\b", normalized)
        and re.search(r"\b(vendor|spend)\b", normalized)
    )
    explicit_total_language = bool(
        re.search(
            r"\b(total|overall|as a whole|how much|all vendor spend)\b",
            normalized,
        )
    )
    generic_total_language = bool(
        re.search(r"\bvendor spend\b", normalized) and not top_language
    )
    total_language = explicit_total_language or generic_total_language
    if top_language and explicit_total_language:
        ambiguous.append("intent")
    elif top_language:
        intent = "top_vendor_by_month" if monthly_series_signal else "top_vendor"
    elif total_language:
        intent = "total_spend"
    else:
        missing.append("intent")
    if monthly_series_signal and not top_language:
        unavailable.append("unsupported_monthly_measure")
        notes.append(
            "Monthly series are supported only for the highest-vendor intent; ETOP will not reinterpret a requested monthly total or breakdown as a yearly total."
        )

    if re.search(r"\b(select|insert|update|delete|drop|alter|truncate)\b", normalized):
        unavailable.append("arbitrary_sql")
        notes.append(
            "SQL text is never executed from the question. Use one of the supported vendor-spend question forms."
        )

    if re.search(r"\b(cash paid|cash payments?|payments? made|open ap|open payable)\b", normalized):
        unavailable.append("unsupported_financial_measure")
        notes.append(
            "The connected source supports signed posted AP GL-distribution evidence, not cash-paid or current-open-payable facts."
        )

    combined_matches = list(re.finditer(
        r"\baccount\s+(?P<account>\d{2,8})\s*-\s*(?P<division>\d{1,4})\b",
        normalized,
    ))
    if len(combined_matches) > 1:
        ambiguous.extend(["account", "division"])
        notes.append(
            "More than one combined account-division clause was supplied; ETOP will not choose one."
        )
    combined = combined_matches[0] if len(combined_matches) == 1 else None
    combined_account = combined.group("account") if combined else None
    combined_division = combined.group("division") if combined else None
    if combined is not None:
        notes.append(
            f"Interpreted account {combined_account}-{combined_division} as GL account {combined_account} in division {combined_division}, per the Product Owner's AP question convention."
        )

    standalone_accounts = sorted(
        set(
            re.findall(
                r"\baccount\s+(\d{2,8})\b(?!\s*-)",
                normalized,
            )
        )
    )
    account_values = sorted(
        {value for value in [combined_account, *standalone_accounts] if value}
    )
    if len(account_values) > 1 or "account" in ambiguous:
        ambiguous.append("account")
        account = None
    else:
        account = account_values[0] if account_values else None

    standalone_divisions = sorted(
        set(re.findall(r"\bdivision\s*#?\s*(\d{1,4})\b", normalized))
    )
    division_values = sorted(
        {value for value in [combined_division, *standalone_divisions] if value}
    )
    if len(division_values) > 1 or "division" in ambiguous:
        ambiguous.append("division")
        division = None
    else:
        division = division_values[0] if division_values else None
    if division is None and "division" not in ambiguous:
        missing.append("division")

    # Dimension values must not double as date slots. Mask every supported
    # account/division clause before looking for a year.
    time_text = re.sub(
        r"\baccount\s+\d{2,8}\s*-\s*\d{1,4}\b",
        "account_dimension",
        normalized,
    )
    time_text = re.sub(
        r"\baccount\s+\d{2,8}\b",
        "account_dimension",
        time_text,
    )
    time_text = re.sub(
        r"\bdivision\s*#?\s*\d{1,4}\b",
        "division_dimension",
        time_text,
    )
    year_values = _unique_int_matches(r"\b(20\d{2})\b", time_text)
    explicit_year = year_values[0] if len(year_values) == 1 else None
    if len(year_values) > 1:
        ambiguous.append("year")

    month_tokens = {
        MONTH_NUMBERS[token]
        for token in re.findall(
            r"\b(" + "|".join(sorted(MONTH_NUMBERS, key=len, reverse=True)) + r")\b",
            time_text,
        )
    }
    numeric_months = _unique_int_matches(r"\bmonth\s+(1[0-2]|0?[1-9])\b", time_text)
    month_values = sorted(month_tokens.union(numeric_months))

    period_values = _unique_int_matches(
        r"\b(?:accounting\s+|erp\s+)?period\s+(1[0-3]|0?[1-9])\b",
        time_text,
    )

    time_basis = None
    year = None
    month = None
    accounting_period = None
    range_start = None
    range_end_exclusive = None

    calendar_signal = bool(
        month_values
        or monthly_series_signal
        or "this month" in normalized
        or "this year" in normalized
        or "calendar year" in normalized
    )
    accounting_signal = bool(
        period_values
        or "accounting year" in normalized
        or "erp year" in normalized
    )
    if re.search(r"\b(?:erp\s+)?accounting\s+month\b", normalized):
        unavailable.append("unsupported_accounting_month")
        notes.append(
            "ERP accounting months are not inferred. Use an explicit ERP accounting period or a calendar month."
        )

    if monthly_series_signal and month_values:
        ambiguous.append("time_scope")
        notes.append(
            "A monthly-series question cannot also select one named month; ETOP will not choose between them."
        )
    elif re.search(r"\bthis month\s+or\s+this year\b", normalized):
        ambiguous.append("time_scope")
    elif calendar_signal and accounting_signal:
        ambiguous.append("time_basis")
    elif "fiscal year" in normalized:
        unavailable.append("fiscal_calendar")
        year = explicit_year
        notes.append(
            "Fiscal-year interpretation is unavailable until the Product Owner supplies the fiscal calendar and period-to-calendar mapping."
        )
    elif len(period_values) > 1:
        ambiguous.append("accounting_period")
    elif period_values:
        accounting_period = period_values[0]
        year = explicit_year
        if year is None and "year" not in ambiguous:
            missing.append("accounting_year")
        else:
            time_basis = "erp_accounting_period"
            notes.append(
                f"Uses PMGYR={year} and PMGPR={accounting_period}; the period is not relabeled as a calendar month."
            )
    elif monthly_series_signal:
        time_basis = "calendar_invoice_date"
        year = explicit_year or (current_date.year if "this year" in normalized else None)
        if year is None and "year" not in ambiguous:
            time_basis = None
            missing.append("calendar_year")
        else:
            range_start, range_end_exclusive = _year_bounds(year)
            notes.append(
                "Returns one ordered calendar-month leader row for each month in the requested year using PMGDTEINV invoice date."
            )
    elif "this month" in normalized:
        time_basis = "calendar_invoice_date"
        year = current_date.year
        month = current_date.month
        range_start, range_end_exclusive = _month_bounds(year, month)
        notes.append(
            "Interpreted 'this month' as the current calendar month using PMGDTEINV invoice date."
        )
    elif len(month_values) > 1:
        ambiguous.append("month")
    elif month_values:
        time_basis = "calendar_invoice_date"
        month = month_values[0]
        year = explicit_year or current_date.year
        range_start, range_end_exclusive = _month_bounds(year, month)
        if explicit_year is None:
            notes.append(
                f"No year was stated for the month; used current calendar year {year}."
            )
        notes.append("Calendar month filtering uses PMGDTEINV invoice date.")
    elif "this year" in normalized:
        time_basis = "calendar_invoice_date"
        year = current_date.year
        range_start, range_end_exclusive = _year_bounds(year)
        notes.append(
            "Interpreted 'this year' as the current calendar year using PMGDTEINV invoice date."
        )
    elif "calendar year" in normalized:
        year = explicit_year
        if year is None and "year" not in ambiguous:
            missing.append("calendar_year")
        else:
            time_basis = "calendar_invoice_date"
            range_start, range_end_exclusive = _year_bounds(year)
            notes.append("Calendar-year filtering uses PMGDTEINV invoice date.")
    elif "accounting year" in normalized or "erp year" in normalized:
        year = explicit_year
        if year is None and "year" not in ambiguous:
            missing.append("accounting_year")
        else:
            time_basis = "erp_accounting_year"
            notes.append(
                f"Uses PMGYR={year} exactly; ETOP does not relabel the ERP accounting year as calendar or fiscal."
            )
    elif explicit_year is not None:
        year = explicit_year
        time_basis = "calendar_invoice_date"
        range_start, range_end_exclusive = _year_bounds(year)
        notes.append(
            f"Interpreted the unqualified year {year} as a calendar invoice-date range using PMGDTEINV. Say 'ERP accounting year {year}' to use PMGYR instead."
        )
    elif "year" not in ambiguous:
        missing.append("time_scope")

    return APSpendParsedQuestion(
        parser_version=PARSER_VERSION,
        original_question=original,
        normalized_question=normalized,
        intent=intent,
        division=division,
        account=account,
        time_basis=time_basis,
        year=year,
        month=month,
        accounting_period=accounting_period,
        range_start=range_start,
        range_end_exclusive=range_end_exclusive,
        interpretation_notes=notes,
        missing_slots=sorted(set(missing)),
        ambiguous_slots=sorted(set(ambiguous)),
        unavailable_slots=sorted(set(unavailable)),
    )
