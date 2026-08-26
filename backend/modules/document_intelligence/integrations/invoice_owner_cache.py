"""Local cache of TMAROP's currently-open invoice ownership.

TMAROP has 15M+ rows and no usable index on TARONUMINV (confirmed live via
EXPLAIN: `possible_keys` is null for both a bare equality lookup and an
`IN (...)` lookup). A single equality lookup measured ~24 seconds; under
concurrent batch load, the per-transaction chunked lookup this cache
replaces was exceeding the platform's 60-second statement timeout and
surfacing as a caught exception -> `read_unavailable=True` ->
`invoice_owner_evidence_incomplete`, blocking otherwise-exact due-date-
bucket matches from auto-clearing.

A full scan of just the two columns this needs (invoice number, customer
number), filtered to open rows only, measured ~8 seconds for ~283K rows -
this is a deliberate, infrequent batch read using an extended session
timeout, never part of the interactive request path. The result is
cached locally in SQLite, where the primary key gives O(1) lookups.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import mysql.connector

from core.database import madden_database
from invoice_number_rules import normalize_erp_invoice


INVOICE_OWNER_CACHE_REFRESH_TIMEOUT_SECONDS = 120


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InvoiceOwnerCacheRefreshFailed(RuntimeError):
    """Raised when the extended-timeout TMAROP scan cannot complete."""


def scan_all_open_invoice_owners() -> list[dict[str, Any]]:
    config = dict(madden_database.config)
    try:
        connection = mysql.connector.connect(**config)
    except mysql.connector.Error as exc:
        raise InvoiceOwnerCacheRefreshFailed(
            "Could not connect to MaddenCo for the invoice-owner cache "
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
                f"{INVOICE_OWNER_CACHE_REFRESH_TIMEOUT_SECONDS * 1000}"
            )
        except mysql.connector.Error:
            pass
        try:
            cursor.execute(
                """
                SELECT CAST(TARONUMINV AS CHAR) AS invoice_number,
                       CAST(TARONUMCST AS CHAR) AS customer_number
                FROM TMAROP
                WHERE TAROAMTOPN <> 0
                """
            )
            rows = cursor.fetchall()
        except mysql.connector.Error as exc:
            raise InvoiceOwnerCacheRefreshFailed(
                f"The TMAROP current-open-owner scan did not complete: {exc}"
            ) from exc
        finally:
            cursor.close()
        return rows
    finally:
        connection.close()


def default_database_path() -> Path:
    project_root = Path(__file__).resolve().parents[4]
    return project_root / "data" / "etop_state" / "invoice_owner_cache.db"


class InvoiceOwnerCacheRepository:
    """SQLite-backed cache of current TMAROP invoice ownership.

    This is a plain, wholesale-replaceable cache, not an append-only
    ledger - each refresh discards the prior snapshot entirely, matching
    the AP due-date cache pattern in cash_flow_forecasting.
    """

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(
            database_path
            if database_path is not None
            else default_database_path()
        )
        self._initialized = False

    def _connection(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        if self._initialized:
            return
        with closing(self._connection()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS current_invoice_owners (
                    invoice_number TEXT PRIMARY KEY,
                    customer_numbers TEXT NOT NULL,
                    refreshed_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS invoice_owner_cache_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            connection.commit()
        self._initialized = True

    def replace_all(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        refreshed_at: str | None = None,
    ) -> int:
        self.initialize()
        refreshed_at = refreshed_at or _utc_now()

        owners: dict[str, set[str]] = {}
        for row in rows:
            invoice = normalize_erp_invoice(row.get("invoice_number"))
            customer = str(
                row.get("customer_number") or ""
            ).strip().removesuffix(".0")
            if not invoice or not customer:
                continue
            owners.setdefault(invoice, set()).add(customer)

        with closing(self._connection()) as connection:
            connection.execute("BEGIN IMMEDIATE;")
            try:
                connection.execute("DELETE FROM current_invoice_owners;")
                connection.executemany(
                    """
                    INSERT INTO current_invoice_owners (
                        invoice_number, customer_numbers, refreshed_at
                    ) VALUES (?, ?, ?);
                    """,
                    [
                        (
                            invoice,
                            ",".join(sorted(customers)),
                            refreshed_at,
                        )
                        for invoice, customers in owners.items()
                    ],
                )
                connection.execute(
                    """
                    INSERT INTO invoice_owner_cache_metadata (key, value)
                    VALUES ('refreshed_at', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value;
                    """,
                    (refreshed_at,),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return len(owners)

    def refreshed_at(self) -> str | None:
        self.initialize()
        with closing(self._connection()) as connection:
            row = connection.execute(
                "SELECT value FROM invoice_owner_cache_metadata "
                "WHERE key = 'refreshed_at';"
            ).fetchone()
        return row["value"] if row is not None else None

    def get_owners(
        self,
        invoice_numbers: Sequence[str],
    ) -> dict[str, set[str]] | None:
        """Return cached owners for the requested invoices, or None if
        this cache has never been refreshed (distinct from "refreshed,
        but none of these invoices are currently open")."""

        if self.refreshed_at() is None:
            return None

        normalized = list(dict.fromkeys(invoice_numbers))
        result: dict[str, set[str]] = {
            invoice: set() for invoice in normalized
        }
        if not normalized:
            return result

        chunk_size = 500
        with closing(self._connection()) as connection:
            for start in range(0, len(normalized), chunk_size):
                chunk = normalized[start : start + chunk_size]
                placeholders = ", ".join(["?"] * len(chunk))
                rows = connection.execute(
                    f"""
                    SELECT invoice_number, customer_numbers
                    FROM current_invoice_owners
                    WHERE invoice_number IN ({placeholders});
                    """,
                    chunk,
                ).fetchall()
                for row in rows:
                    customers = {
                        value
                        for value in row["customer_numbers"].split(",")
                        if value
                    }
                    result[row["invoice_number"]] = customers
        return result


invoice_owner_cache_repository = InvoiceOwnerCacheRepository()


def refresh_invoice_owner_cache(
    cache: InvoiceOwnerCacheRepository = invoice_owner_cache_repository,
) -> dict[str, Any]:
    try:
        rows = scan_all_open_invoice_owners()
    except InvoiceOwnerCacheRefreshFailed as exc:
        return {
            "status": "unavailable_source_capability",
            "message": str(exc),
        }
    refreshed_at = _utc_now()
    invoices_cached = cache.replace_all(rows, refreshed_at=refreshed_at)
    return {
        "status": "ok",
        "invoices_cached": invoices_cached,
        "source_rows": len(rows),
        "refreshed_at": refreshed_at,
    }
