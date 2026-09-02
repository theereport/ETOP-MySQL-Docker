from __future__ import annotations

from typing import Any

import mysql.connector

from core.database import ERP_FULL_TABLE_SCAN_TIMEOUT_SECONDS, madden_database

# get_po_fill_rate_summary() (repository.py) computes this same
# TMPOHD/TMPODT join per vendor, live, on the interactive vendor-evidence
# request path. Confirmed live it is inherently expensive for the
# highest-volume vendors (tens of thousands of POs each) - timing ranged
# from ~1s to ~40s for the same query on the same vendor, occasionally
# exceeding the shared 60s statement timeout. TMPOHD has no usable index
# on TPHDTECRT, and TMPODT is 6.2M+ rows, so there is no per-vendor query
# shape that reliably avoids scanning a large fraction of both tables.
#
# This computes the identical aggregation for every vendor in one pass
# (GROUP BY vendor) with an extended session timeout, so the interactive
# path can read a cached per-vendor row instead of running the expensive
# join live. It is a deliberate, infrequent batch read, never part of the
# interactive request path - the same pattern already used for
# cash_flow_forecasting's AP due-date cache.


class PoFillRateCacheRefreshFailed(RuntimeError):
    """Raised when the extended-timeout TMPOHD/TMPODT scan cannot complete."""


def scan_all_vendor_po_fill_rates(
    *, window_days: int = 365
) -> list[dict[str, Any]]:
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
        raise PoFillRateCacheRefreshFailed(
            f"Could not connect to MaddenCo for the PO fill-rate cache "
            f"refresh: {exc}"
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
                SELECT
                    header.TPHNBVND AS vendor_number,
                    COUNT(DISTINCT header.TPHNB) AS po_count,
                    COALESCE(SUM(line.TPDQTYORD), 0) AS quantity_ordered,
                    COALESCE(SUM(line.TPDQTYRCV), 0) AS quantity_received,
                    COALESCE(SUM(line.TPDQTYBO), 0) AS quantity_backorder
                FROM TMPOHD AS header
                INNER JOIN TMPODT AS line
                    ON line.TPHNB = header.TPHNB
                WHERE header.TPHDTECRT >= DATE_FORMAT(
                    CURDATE() - INTERVAL %s DAY, '%%Y%%m%%d'
                )
                GROUP BY header.TPHNBVND
                """,
                (window_days,),
            )
            rows = cursor.fetchall()
        except mysql.connector.Error as exc:
            raise PoFillRateCacheRefreshFailed(
                f"The TMPOHD/TMPODT fill-rate scan did not complete: {exc}"
            ) from exc
        finally:
            cursor.close()
        return rows
    finally:
        connection.close()
