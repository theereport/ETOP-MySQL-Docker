from __future__ import annotations

from datetime import date
from typing import Any

from core.database import madden_database


# Cash/bank GL accounts (GMGM, division 1, department 0). Confirmed live
# against GMGM: these map one-to-one to the Consolidated Daily Bank
# Balances workbook's own bank columns. Account 1014 (Victory Bank) is a
# real cash-in-bank GL account that has no corresponding column in the
# bank balance workbook and is intentionally excluded - see the
# victory_bank_excluded gap.
CASH_ACCOUNTS: tuple[int, ...] = (1010, 1011, 1012, 1013, 1015, 1016, 1017, 1018, 1019)
CASH_ACCOUNT_DIVISION = 1
CASH_ACCOUNT_DEPARTMENT = 0


def to_madden_date(value: date) -> str:
    """MaddenCo stores these date columns as fixed-width YYYYMMDD text,
    not a native DATE type - format consistently so string BETWEEN
    comparisons are correct."""

    return value.strftime("%Y%m%d")


class CashFlowForecastingRepository:
    """Read-only MaddenCo evidence for cash flow forecasting.

    Every method issues a parameterized SELECT. Nothing here writes to
    the ERP or interprets AR/AP open-item status beyond what MaddenCo's
    own tables record.
    """

    def get_open_ar_invoices_due_between(
        self, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        """Currently-open AR invoice rows due in [start_date, end_date]."""

        return madden_database.fetch_all(
            """
            SELECT TARODTEDUE, TAROAMTOPN, TARONUMINV, TARONUMCST
            FROM TMAROP
            WHERE TRIM(TAROTYPTRN) = 'I'
              AND COALESCE(NULLIF(TRIM(TAROHISTYN), ''), 'N') <> 'Y'
              AND TAROAMTOPN <> 0
              AND TARODTEDUE BETWEEN %s AND %s
            """,
            (to_madden_date(start_date), to_madden_date(end_date)),
        )

    def get_ar_invoices_due_between_any_status(
        self, start_date: date, end_date: date, *, invoiced_on_or_before: date
    ) -> list[dict[str, Any]]:
        """AR invoice rows (open or since closed) due in range, restricted
        to invoices that existed on or before `invoiced_on_or_before`.

        Used only for the prior-year backtest's "projected" figure: the
        due-date/original-amount record is permanent regardless of
        today's paid status, but the invoiced-on-or-before filter keeps
        the backtest honest by excluding invoices that would not yet
        have existed at the historical as-of date being simulated.
        """

        return madden_database.fetch_all(
            """
            SELECT TARODTEDUE, TAROAMTORG, TARONUMINV, TARONUMCST
            FROM TMAROP
            WHERE TRIM(TAROTYPTRN) = 'I'
              AND TARODTEDUE BETWEEN %s AND %s
              AND TARODTE <= %s
            """,
            (
                to_madden_date(start_date),
                to_madden_date(end_date),
                to_madden_date(invoiced_on_or_before),
            ),
        )

    def get_cash_account_je_activity(
        self, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        """All GACDSYS='JE' postings to the tracked cash accounts in
        range - the raw material for the receipt/sweep/LOC/other
        classification done in service.py."""

        placeholders = ",".join(["%s"] * len(CASH_ACCOUNTS))
        return madden_database.fetch_all(
            f"""
            SELECT GADTPST, GAAMT, TRIM(GACDDBCR) AS GACDDBCR,
                   TRIM(GADSR) AS GADSR
            FROM GMAD
            WHERE GMNB IN ({placeholders})
              AND GMNBDIV = %s AND GMNBDPT = %s
              AND TRIM(GACDSYS) = 'JE'
              AND GADTPST BETWEEN %s AND %s
            """,
            (
                *CASH_ACCOUNTS,
                CASH_ACCOUNT_DIVISION,
                CASH_ACCOUNT_DEPARTMENT,
                to_madden_date(start_date),
                to_madden_date(end_date),
            ),
        )

    def get_cash_account_ap_activity(
        self, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        """All GACDSYS='AP' postings to the tracked cash accounts in
        range - the actual AP cash-out ("ACCOUNTS PAYABLE CHECK
        WRITING"/"...VOID CHECKS"), used as backtest/accuracy actuals."""

        placeholders = ",".join(["%s"] * len(CASH_ACCOUNTS))
        return madden_database.fetch_all(
            f"""
            SELECT GADTPST, GAAMT, TRIM(GACDDBCR) AS GACDDBCR,
                   TRIM(GADSR) AS GADSR
            FROM GMAD
            WHERE GMNB IN ({placeholders})
              AND GMNBDIV = %s AND GMNBDPT = %s
              AND TRIM(GACDSYS) = 'AP'
              AND GADTPST BETWEEN %s AND %s
            """,
            (
                *CASH_ACCOUNTS,
                CASH_ACCOUNT_DIVISION,
                CASH_ACCOUNT_DEPARTMENT,
                to_madden_date(start_date),
                to_madden_date(end_date),
            ),
        )


cash_flow_forecasting_repository = CashFlowForecastingRepository()
