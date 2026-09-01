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

from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

import mysql.connector
from sqlalchemy import select
from sqlalchemy.engine import Engine

from core.database import madden_database
from data.mysql import (
    get_engine,
    invoice_owner_cache_metadata_table,
    invoice_owner_cache_table,
    metadata,
)
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


_TABLES = [invoice_owner_cache_table, invoice_owner_cache_metadata_table]
_INSERT_CHUNK_SIZE = 5_000


class InvoiceOwnerCacheRepository:
    """MySQL-backed cache of current TMAROP invoice ownership.

    This is a plain, wholesale-replaceable cache, not an append-only
    ledger - each refresh discards the prior snapshot entirely, matching
    the AP due-date cache pattern in cash_flow_forecasting.
    """

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        metadata.create_all(self._engine, checkfirst=True, tables=_TABLES)
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

        table = invoice_owner_cache_table
        meta = invoice_owner_cache_metadata_table
        insert_rows = [
            {
                "invoice_number": invoice,
                "customer_numbers": ",".join(sorted(customers)),
                "refreshed_at": refreshed_at,
            }
            for invoice, customers in owners.items()
        ]
        with self._engine.begin() as connection:
            connection.execute(table.delete())
            for start in range(0, len(insert_rows), _INSERT_CHUNK_SIZE):
                chunk = insert_rows[start : start + _INSERT_CHUNK_SIZE]
                if chunk:
                    connection.execute(table.insert(), chunk)
            existing = connection.execute(
                select(meta.c.meta_key).where(meta.c.meta_key == "refreshed_at")
            ).first()
            if existing is None:
                connection.execute(
                    meta.insert().values(
                        meta_key="refreshed_at", meta_value=refreshed_at
                    )
                )
            else:
                connection.execute(
                    meta.update()
                    .where(meta.c.meta_key == "refreshed_at")
                    .values(meta_value=refreshed_at)
                )
        return len(owners)

    def refreshed_at(self) -> str | None:
        self.initialize()
        meta = invoice_owner_cache_metadata_table
        with self._engine.connect() as connection:
            value = connection.execute(
                select(meta.c.meta_value).where(meta.c.meta_key == "refreshed_at")
            ).scalar()
        return value

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

        table = invoice_owner_cache_table
        chunk_size = 500
        with self._engine.connect() as connection:
            for start in range(0, len(normalized), chunk_size):
                chunk = normalized[start : start + chunk_size]
                rows = connection.execute(
                    select(table.c.invoice_number, table.c.customer_numbers).where(
                        table.c.invoice_number.in_(chunk)
                    )
                ).all()
                for invoice_number, customer_numbers in rows:
                    customers = {
                        value for value in customer_numbers.split(",") if value
                    }
                    result[invoice_number] = customers
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
