from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import mysql.connector

from core.database import ERP_FULL_TABLE_SCAN_TIMEOUT_SECONDS, madden_database


# PMHD retains full AP history, not just open items - confirmed live that
# PMHNBCHK (check number) is populated once an invoice has been paid, and
# ~5.39M of ~5.44M rows already carry one. The WHERE clause below (unpaid =
# PMHNBCHK is 0 or NULL) is required for "open ledger" to mean what it
# says; without it, a full scan returns paid history back to whenever this
# instance stopped purging PMHD (confirmed live: $7.26B / 5.39M rows
# unfiltered vs $90.9M / ~41K rows once filtered to unpaid). This same gap
# exists in cash_flow_forecasting/ap_due_date_cache_source.py's PMHD scan
# and vendor_intelligence/repository.py's per-vendor scan.
#
# PMHNBCHK = 0 alone is still not sufficient: a voided entry never gets a
# check number either, so it stays "unpaid" forever. PMHCODSEL = 'V'
# marks these - confirmed live that 12,166 of 12,289 such rows carry a
# non-zero PMHGLREFVD (void GL reference), while zero of the genuinely
# open rows do, and the 'V' rows carry nonsense dates (1950-2034) versus
# the real open rows' 2024-2026 range. Excluding them moves the open
# balance from $90.9M/40,725 invoices to the real $93.0M/28,814 invoices
# (voided entries net negative, so removing them raises the balance).
#
# PMHD also has 5M+ rows with no due-date-usable index - the same
# constraint documented in cash_flow_forecasting/ap_due_date_cache_source.py.
# This reuses that scan technique (dedicated connection, extended session
# timeout) rather than the shared 60-second-timeout madden_database helper,
# but extends the selected columns to include invoice identity
# (PMHNBVND/PMHNBINV) and invoice date (PMHDTEINV), which the cash-flow
# cache discards - the AP module needs per-invoice rows, not weekly-bucketed
# totals.
#
# Confirmed live (2026-09): PMHD's only index is the primary key
# (PMHNBVND, PMHNBINV, PMHNBPMT) - neither PMHNBCHK nor PMHCODSEL (the two
# WHERE-clause columns) are covered by it, so this is a genuine full scan of
# the whole table (6.26M rows and growing) every run; MySQL cannot skip rows
# via this or any other index for this filter. The 2-year invoice-date floor
# below does NOT reduce that scan cost (PMHDTEINV isn't indexed either, so
# MySQL still reads every row to evaluate it) - it exists to shrink the
# *result set* handed to replace_open_ledger() and, more importantly, the
# vendor/year scope passed into scan_gl_divisions_for_open_invoices()
# afterward (see _refresh_open_ledger_divisions in service.py), which scales
# with how many distinct vendor/year pairs come out of this scan. Rows with
# a missing/malformed invoice date are kept rather than dropped, since we
# can't judge those as "old" and this cache must never silently omit a
# genuinely open invoice.
#
# Confirmed live: the MaddenCo server's own `max_execution_time` GLOBAL
# variable is 0 (unlimited) - the timeout below is entirely self-imposed by
# this app, not a server-side ceiling we're up against. Shared with
# cash_flow_forecasting/ap_due_date_cache_source.py's PMHD scan via
# core.database.ERP_FULL_TABLE_SCAN_TIMEOUT_SECONDS - see that constant's
# docstring for why.
OPEN_LEDGER_MIN_INVOICE_AGE_DAYS = 365 * 2


class ErpLedgerScanFailed(RuntimeError):
    """Raised when the extended-timeout PMHD/PMVEND scan cannot complete."""


def _connect() -> mysql.connector.MySQLConnection:
    # Deliberately NOT from madden_database's connection pool: this is a
    # single dedicated connection held for up to ERP_FULL_TABLE_SCAN_TIMEOUT_SECONDS
    # with its own extended SESSION MAX_EXECUTION_TIME. Pooling it would let
    # that extended session setting leak onto an unrelated later checkout of
    # the same physical connection (pool_reset_session doesn't reset
    # MAX_EXECUTION_TIME), and would tie up one of the pool's few connections
    # for the whole scan.
    config = {
        key: value
        for key, value in madden_database.config.items()
        if key not in ("pool_name", "pool_size")
    }
    try:
        return mysql.connector.connect(**config)
    except mysql.connector.Error as exc:
        raise ErpLedgerScanFailed(
            f"Could not connect to MaddenCo for the AP ledger refresh: {exc}"
        ) from exc


def scan_open_ap_ledger() -> list[dict[str, Any]]:
    connection = _connect()
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
            cutoff = (
                date.today() - timedelta(days=OPEN_LEDGER_MIN_INVOICE_AGE_DAYS)
            ).strftime("%Y%m%d")
            cursor.execute(
                """
                SELECT PMHNBVND,
                       TRIM(PMHNBINV) AS PMHNBINV,
                       PMHDTEINV, PMHDTEDUE, PMHAMTINV, PMHAMTDIS,
                       TRIM(PMHFLGHLD) AS PMHFLGHLD
                FROM PMHD
                WHERE (PMHNBCHK = 0 OR PMHNBCHK IS NULL)
                  AND (PMHCODSEL IS NULL OR TRIM(PMHCODSEL) != 'V')
                  AND (
                    PMHDTEINV >= %s
                    OR PMHDTEINV IS NULL
                    OR PMHDTEINV = '00000000'
                  )
                """,
                (cutoff,),
            )
            rows = cursor.fetchall()
        except mysql.connector.Error as exc:
            raise ErpLedgerScanFailed(
                f"The PMHD open-ledger scan did not complete: {exc}"
            ) from exc
        finally:
            cursor.close()
        return rows
    finally:
        connection.close()


def scan_gl_divisions_for_open_invoices(
    vendor_numbers: list[str], years: list[int]
) -> list[dict[str, Any]]:
    """Returns raw PMGLDS distribution rows for the given vendors across the
    given accounting years, using the table's only secondary index
    (PMGYR, PMGNBVND). This is a coarse scope, not an invoice-level filter -
    a vendor's full year of GL activity comes back, not just its currently
    open invoices; the caller filters down to the open set and picks a GL
    account/division/department per invoice afterward.

    Measured live against this instance: ~1,286 vendors behind ~41K open
    invoices, scoped to the years those invoices' dates fall in, returned
    3.98M rows in ~32 seconds. Accepted as a background-job cost (same
    pattern as scan_open_ap_ledger), not a live request path."""

    if not vendor_numbers or not years:
        return []
    connection = _connect()
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
        year_placeholders = ", ".join(["%s"] * len(years))
        vendor_placeholders = ", ".join(["%s"] * len(vendor_numbers))
        try:
            cursor.execute(
                f"""
                SELECT PMGNBVND,
                       TRIM(PMGNBINV) AS PMGNBINV,
                       PMGNBGLDV, PMGNBGLDP, PMGNBGL, PMGAMTINV
                FROM PMGLDS
                WHERE PMGYR IN ({year_placeholders})
                  AND PMGNBVND IN ({vendor_placeholders})
                """,
                (*years, *vendor_numbers),
            )
            rows = cursor.fetchall()
        except mysql.connector.Error as exc:
            raise ErpLedgerScanFailed(
                f"The PMGLDS division scan did not complete: {exc}"
            ) from exc
        finally:
            cursor.close()
        return rows
    finally:
        connection.close()


def scan_vendor_terms_codes() -> list[dict[str, Any]]:
    connection = _connect()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
        except mysql.connector.Error:
            pass
        try:
            cursor.execute(
                """
                SELECT PVNUMVEN, PVCODTREM, TRIM(PVNAMVEN) AS PVNAMVEN
                FROM PMVEND
                """
            )
            rows = cursor.fetchall()
        except mysql.connector.Error as exc:
            raise ErpLedgerScanFailed(
                f"The PMVEND vendor-terms scan did not complete: {exc}"
            ) from exc
        finally:
            cursor.close()
        return rows
    finally:
        connection.close()
