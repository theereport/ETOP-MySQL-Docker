from __future__ import annotations

from typing import Any

import mysql.connector

from core.database import madden_database


# PMHD (open vendor payables) has 5M+ rows and its only index is the
# composite PK (PMHNBVND, PMHNBINV, PMHNBPMT) - confirmed live that even
# COUNT(*) with a narrow PMHDTEDUE range, and a DISTINCT on the leading
# PK column, both exceed the platform's normal 60-second statement
# timeout (the same class of constraint already documented for
# EOMINV/TMPODT elsewhere in this codebase). A raw, unfiltered full scan
# of just the columns this module needs completed in ~87 seconds when
# given more time, so this reads PMHD once with an extended session
# timeout and caches the result - it is a deliberate, infrequent batch
# read, never part of the interactive request path.
AP_CACHE_REFRESH_TIMEOUT_SECONDS = 240


class ApDueDateCacheRefreshFailed(RuntimeError):
    """Raised when the extended-timeout PMHD scan cannot complete."""


def scan_all_open_ap_invoices() -> list[dict[str, Any]]:
    config = dict(madden_database.config)
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
                f"{AP_CACHE_REFRESH_TIMEOUT_SECONDS * 1000}"
            )
        except mysql.connector.Error:
            pass
        try:
            cursor.execute(
                """
                SELECT PMHDTEDUE, PMHAMTINV, PMHAMTDIS,
                       TRIM(PMHFLGHLD) AS PMHFLGHLD
                FROM PMHD
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
