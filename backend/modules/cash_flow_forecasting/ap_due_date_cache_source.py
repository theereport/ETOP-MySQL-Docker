from __future__ import annotations

from typing import Any

import mysql.connector

from core.database import ERP_FULL_TABLE_SCAN_TIMEOUT_SECONDS, madden_database


# PMHD retains full AP history, not just open items - confirmed live that
# PMHNBCHK (check number) is populated once an invoice has been paid, and
# ~5.39M of ~5.44M rows already carry one. Without filtering on it, this
# scan was including already-paid invoices as projected future cash
# outflow (confirmed live: $7.26B / 5.39M rows unfiltered vs $90.9M / ~41K
# rows once filtered to PMHNBCHK = 0 or NULL). The WHERE clause below is
# required for "open" to mean what it says.
#
# PMHNBCHK = 0 alone is still not sufficient: a voided entry never gets a
# check number either, so it stays "unpaid" forever. PMHCODSEL = 'V'
# marks these - confirmed live that 12,166 of 12,289 such rows carry a
# non-zero PMHGLREFVD (void GL reference) versus zero of the genuinely
# open rows, and the 'V' rows carry nonsense dates (1950-2034) versus the
# real open rows' 2024-2026 range. Excluding them moves the real open
# balance from $90.9M/40,725 invoices to $93.0M/28,814 invoices (voided
# entries net negative, so removing them raises the balance) - this would
# otherwise have projected voided, decades-old entries as future cash
# outflow.
#
# PMHD also has 5M+ rows and its only index is the composite PK
# (PMHNBVND, PMHNBINV, PMHNBPMT) - confirmed live that even COUNT(*) with
# a narrow PMHDTEDUE range, and a DISTINCT on the leading PK column, both
# exceed the platform's normal 60-second statement timeout (the same
# class of constraint already documented for EOMINV/TMPODT elsewhere in
# this codebase). A raw, unfiltered full scan of just the columns this
# module needs completed in ~87 seconds when given more time, so this
# reads PMHD once with an extended session timeout and caches the result
# - it is a deliberate, infrequent batch read, never part of the
# interactive request path. The timeout itself is shared with
# accounts_payable/erp_ledger_scan.py's PMHD scan via
# core.database.ERP_FULL_TABLE_SCAN_TIMEOUT_SECONDS - see that constant's
# docstring for why: both modules do a comparably unfiltered full scan of
# the same table and previously carried independently-chosen ceilings
# (240s here, 600s there) that would have started failing at different
# points as PMHD keeps growing.


class ApDueDateCacheRefreshFailed(RuntimeError):
    """Raised when the extended-timeout PMHD scan cannot complete."""


def scan_all_open_ap_invoices() -> list[dict[str, Any]]:
    # Deliberately NOT from madden_database's connection pool - see the
    # identical note in accounts_payable/erp_ledger_scan.py._connect(): this
    # is a single dedicated connection with its own extended SESSION
    # MAX_EXECUTION_TIME, which pool_reset_session would not clear before a
    # later, unrelated caller reused the same pooled connection.
    config = {
        key: value
        for key, value in madden_database.config.items()
        if key not in ("pool_name", "pool_size")
    }
    try:
        connection = mysql.connector.connect(**config)
    except mysql.connector.Error as exc:
        raise ApDueDateCacheRefreshFailed(
            f"Could not connect to MaddenCo for the AP cache refresh: {exc}"
        ) from exc

    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
        except mysql.connector.Error:
            pass
        try:
            cursor.execute(
                "SET SESSION MAX_EXECUTION_TIME = "
                f"{ERP_FULL_TABLE_SCAN_TIMEOUT_SECONDS * 1000}"
            )
        except mysql.connector.Error:
            pass
        try:
            cursor.execute(
                """
                SELECT PMHDTEDUE, PMHAMTINV, PMHAMTDIS,
                       TRIM(PMHFLGHLD) AS PMHFLGHLD
                FROM PMHD
                WHERE (PMHNBCHK = 0 OR PMHNBCHK IS NULL)
                  AND (PMHCODSEL IS NULL OR TRIM(PMHCODSEL) != 'V')
                """
            )
            rows = cursor.fetchall()
        except mysql.connector.Error as exc:
            raise ApDueDateCacheRefreshFailed(
                f"The PMHD scan did not complete: {exc}"
            ) from exc
        finally:
            cursor.close()
        return rows
    finally:
        connection.close()
