from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any

from data.database import get_connection

from .repository import AccountsPayableRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_madden_date(value: object) -> date | None:
    """Parse MaddenCo's YYYYMMDD varchar date encoding. Duplicated (not
    imported) from cash_flow_forecasting/computation.py - this module is
    deliberately independent of cash_flow_forecasting, and this is a small,
    generic parsing utility, not shared business logic."""

    text = str(value or "").strip()
    if len(text) != 8 or text == "00000000":
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


class AccountsPayableErpLedgerRepository:
    """Local cache of MaddenCo's open AP ledger (PMHD) and vendor terms
    codes (PMVEND), scanned in full via erp_ledger_scan.py because PMHD has
    5M+ rows with no due-date-usable index (see erp_ledger_scan.py). Not
    append-only - a plain, wholesale-replaced performance cache, same as
    cash_flow_forecasting's cash_flow_ap_due_date_cache, except this one
    retains invoice-level rows instead of pre-aggregated weekly buckets."""

    def __init__(
        self,
        connection_factory: Callable[[], sqlite3.Connection] = get_connection,
    ) -> None:
        self._connection_factory = connection_factory
        self._initialization_lock = threading.Lock()

    def _connection(self) -> sqlite3.Connection:
        connection = self._connection_factory()
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._initialization_lock:
            connection = self._connection()
            try:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS ap_erp_open_ledger_cache (
                        vendor_number TEXT NOT NULL,
                        invoice_number TEXT NOT NULL,
                        invoice_date TEXT,
                        due_date TEXT,
                        amount_invoiced REAL NOT NULL,
                        amount_discount REAL NOT NULL,
                        on_hold INTEGER NOT NULL DEFAULT 0,
                        refreshed_at TEXT NOT NULL,
                        PRIMARY KEY (vendor_number, invoice_number)
                    );

                    CREATE INDEX IF NOT EXISTS idx_ap_erp_open_ledger_due_date
                    ON ap_erp_open_ledger_cache(due_date);

                    CREATE TABLE IF NOT EXISTS ap_erp_vendor_terms_cache (
                        vendor_number TEXT PRIMARY KEY,
                        terms_code TEXT,
                        refreshed_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS ap_vendor_terms_reference (
                        terms_code TEXT PRIMARY KEY,
                        discount_percent REAL NOT NULL DEFAULT 0,
                        num_periods INTEGER,
                        num_months INTEGER,
                        num_days INTEGER,
                        second_period INTEGER,
                        third_period INTEGER,
                        next_period INTEGER,
                        day_of_month INTEGER,
                        cutoff_day INTEGER,
                        description TEXT NOT NULL DEFAULT '',
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS ap_warehouse_approval_actions (
                        action_id TEXT PRIMARY KEY,
                        vendor_number TEXT NOT NULL,
                        invoice_number TEXT NOT NULL,
                        from_status TEXT NOT NULL,
                        to_status TEXT NOT NULL CHECK (
                            to_status IN (
                                'needs_approval',
                                'approved_by_warehouse',
                                'approved_and_entered_by_ap'
                            )
                        ),
                        actor_identity TEXT NOT NULL,
                        actor_identity_source TEXT NOT NULL DEFAULT 'operator_supplied'
                            CHECK (
                                actor_identity_source IN (
                                    'operator_supplied', 'sso'
                                )
                            ),
                        notes TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_ap_warehouse_approval_actions_invoice
                    ON ap_warehouse_approval_actions(
                        vendor_number,
                        invoice_number,
                        created_at DESC
                    );

                    CREATE TRIGGER IF NOT EXISTS ap_warehouse_approval_actions_no_update
                    BEFORE UPDATE ON ap_warehouse_approval_actions
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'AP warehouse approval actions are append-only.'
                        );
                    END;

                    CREATE TRIGGER IF NOT EXISTS ap_warehouse_approval_actions_no_delete
                    BEFORE DELETE ON ap_warehouse_approval_actions
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'AP warehouse approval actions are append-only.'
                        );
                    END;
                    """
                )
                ledger_columns = {
                    str(row[1])
                    for row in connection.execute(
                        "PRAGMA table_info(ap_erp_open_ledger_cache)"
                    ).fetchall()
                }
                if "gl_division" not in ledger_columns:
                    connection.execute(
                        "ALTER TABLE ap_erp_open_ledger_cache "
                        "ADD COLUMN gl_division TEXT"
                    )
                if "gl_department" not in ledger_columns:
                    connection.execute(
                        "ALTER TABLE ap_erp_open_ledger_cache "
                        "ADD COLUMN gl_department TEXT"
                    )
                if "gl_account" not in ledger_columns:
                    connection.execute(
                        "ALTER TABLE ap_erp_open_ledger_cache "
                        "ADD COLUMN gl_account TEXT"
                    )
                terms_cache_columns = {
                    str(row[1])
                    for row in connection.execute(
                        "PRAGMA table_info(ap_erp_vendor_terms_cache)"
                    ).fetchall()
                }
                if "vendor_name" not in terms_cache_columns:
                    connection.execute(
                        "ALTER TABLE ap_erp_vendor_terms_cache "
                        "ADD COLUMN vendor_name TEXT"
                    )
                connection.commit()
            finally:
                connection.close()

    def replace_open_ledger(self, rows: list[dict[str, Any]]) -> int:
        """Wholesale replace: DELETE + bulk INSERT in one transaction, same
        pattern as cash_flow_forecasting's cache refresh. Rows without a
        usable vendor+invoice identity are skipped (never cached as
        anonymous evidence).

        PMHD's real primary key is (PMHNBVND, PMHNBINV, PMHNBPMT) - an
        invoice can have multiple payment-split rows, which this cache
        intentionally does not select PMHNBPMT for (it needs invoice-level
        totals, not payment-split-level detail). Multiple rows for the same
        vendor+invoice are aggregated here: amounts summed, due date taken
        as the earliest known (a company must plan for the earliest
        installment), on_hold set if any split is on hold - erring toward
        disclosure, not silence."""

        self.initialize()
        refreshed_at = _now()
        aggregated: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            vendor_number = str(row.get("PMHNBVND") or "").strip()
            invoice_number = str(row.get("PMHNBINV") or "").strip()
            if not vendor_number or vendor_number == "0" or not invoice_number:
                continue
            key = (vendor_number, invoice_number)
            invoice_date = parse_madden_date(row.get("PMHDTEINV"))
            due_date = parse_madden_date(row.get("PMHDTEDUE"))
            on_hold = str(row.get("PMHFLGHLD") or "").strip().upper() == "Y"
            amount_invoiced = float(row.get("PMHAMTINV") or 0)
            amount_discount = float(row.get("PMHAMTDIS") or 0)

            existing = aggregated.get(key)
            if existing is None:
                aggregated[key] = {
                    "invoice_date": invoice_date,
                    "due_date": due_date,
                    "amount_invoiced": amount_invoiced,
                    "amount_discount": amount_discount,
                    "on_hold": on_hold,
                }
                continue
            existing["amount_invoiced"] += amount_invoiced
            existing["amount_discount"] += amount_discount
            existing["on_hold"] = existing["on_hold"] or on_hold
            if invoice_date and (
                existing["invoice_date"] is None
                or invoice_date < existing["invoice_date"]
            ):
                existing["invoice_date"] = invoice_date
            if due_date and (
                existing["due_date"] is None or due_date < existing["due_date"]
            ):
                existing["due_date"] = due_date

        prepared: list[tuple[Any, ...]] = [
            (
                vendor_number,
                invoice_number,
                values["invoice_date"].isoformat() if values["invoice_date"] else None,
                values["due_date"].isoformat() if values["due_date"] else None,
                values["amount_invoiced"],
                values["amount_discount"],
                1 if values["on_hold"] else 0,
                refreshed_at,
            )
            for (vendor_number, invoice_number), values in aggregated.items()
        ]

        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute("DELETE FROM ap_erp_open_ledger_cache;")
            connection.executemany(
                """
                INSERT INTO ap_erp_open_ledger_cache (
                    vendor_number, invoice_number, invoice_date, due_date,
                    amount_invoiced, amount_discount, on_hold, refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                prepared,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return len(prepared)

    def replace_vendor_terms_cache(self, rows: list[dict[str, Any]]) -> int:
        self.initialize()
        refreshed_at = _now()
        prepared = [
            (
                str(row.get("PVNUMVEN") or "").strip(),
                str(row.get("PVCODTREM") or "").strip() or None,
                str(row.get("PVNAMVEN") or "").strip() or None,
                refreshed_at,
            )
            for row in rows
            if str(row.get("PVNUMVEN") or "").strip()
            and str(row.get("PVNUMVEN") or "").strip() != "0"
        ]
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute("DELETE FROM ap_erp_vendor_terms_cache;")
            connection.executemany(
                """
                INSERT INTO ap_erp_vendor_terms_cache (
                    vendor_number, terms_code, vendor_name, refreshed_at
                ) VALUES (?, ?, ?, ?);
                """,
                prepared,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return len(prepared)

    def open_ledger_refreshed_at(self) -> str | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                "SELECT MAX(refreshed_at) AS refreshed_at "
                "FROM ap_erp_open_ledger_cache;"
            ).fetchone()
        finally:
            connection.close()
        return row["refreshed_at"] if row is not None else None

    def open_ledger_summary(self, as_of_date: date) -> dict[str, Any]:
        """Aggregates the cached invoice-level open ledger as of a given
        date. On-hold invoices are always broken out separately rather than
        silently folded into or excluded from the other figures, matching
        cash_flow_forecasting's own disclosure precedent for hold status."""

        self.initialize()
        as_of = as_of_date.isoformat()
        within_7_days = (as_of_date + timedelta(days=7)).isoformat()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_count,
                    COALESCE(SUM(amount_invoiced - amount_discount), 0) AS total_balance,
                    COALESCE(SUM(CASE WHEN on_hold = 1 THEN 1 ELSE 0 END), 0) AS on_hold_count,
                    COALESCE(SUM(CASE WHEN on_hold = 1 THEN amount_invoiced - amount_discount ELSE 0 END), 0) AS on_hold_amount,
                    COALESCE(SUM(CASE WHEN on_hold = 0 AND due_date = ? THEN 1 ELSE 0 END), 0) AS due_today_count,
                    COALESCE(SUM(CASE WHEN on_hold = 0 AND due_date = ? THEN amount_invoiced - amount_discount ELSE 0 END), 0) AS due_today_amount,
                    COALESCE(SUM(CASE WHEN on_hold = 0 AND due_date IS NOT NULL AND due_date < ? THEN 1 ELSE 0 END), 0) AS past_due_count,
                    COALESCE(SUM(CASE WHEN on_hold = 0 AND due_date IS NOT NULL AND due_date < ? THEN amount_invoiced - amount_discount ELSE 0 END), 0) AS past_due_amount,
                    COALESCE(SUM(CASE WHEN on_hold = 0 AND due_date BETWEEN ? AND ? THEN amount_invoiced - amount_discount ELSE 0 END), 0) AS due_within_7_days_amount
                FROM ap_erp_open_ledger_cache;
                """,
                (as_of, as_of, as_of, as_of, as_of, within_7_days),
            ).fetchone()
            refreshed_at = connection.execute(
                "SELECT MAX(refreshed_at) AS refreshed_at "
                "FROM ap_erp_open_ledger_cache;"
            ).fetchone()["refreshed_at"]
        finally:
            connection.close()
        return {**dict(row), "refreshed_at": refreshed_at}

    def list_vendor_terms_reference(self) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                "SELECT * FROM ap_vendor_terms_reference ORDER BY terms_code;"
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def upsert_vendor_terms_reference(
        self,
        *,
        terms_code: str,
        discount_percent: float,
        num_periods: int | None,
        num_months: int | None,
        num_days: int | None,
        second_period: int | None,
        third_period: int | None,
        next_period: int | None,
        day_of_month: int | None,
        cutoff_day: int | None,
        description: str,
    ) -> None:
        self.initialize()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                INSERT INTO ap_vendor_terms_reference (
                    terms_code, discount_percent, num_periods, num_months,
                    num_days, second_period, third_period, next_period,
                    day_of_month, cutoff_day, description, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(terms_code) DO UPDATE SET
                    discount_percent = excluded.discount_percent,
                    num_periods = excluded.num_periods,
                    num_months = excluded.num_months,
                    num_days = excluded.num_days,
                    second_period = excluded.second_period,
                    third_period = excluded.third_period,
                    next_period = excluded.next_period,
                    day_of_month = excluded.day_of_month,
                    cutoff_day = excluded.cutoff_day,
                    description = excluded.description,
                    updated_at = excluded.updated_at;
                """,
                (
                    terms_code, discount_percent, num_periods, num_months,
                    num_days, second_period, third_period, next_period,
                    day_of_month, cutoff_day, description, _now(),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def discount_eligibility_summary(self, as_of_date: date) -> dict[str, Any]:
        """Only terms codes with a true flat 'N days from invoice date'
        discount rule (discount_percent > 0 and num_days > 0) are computed
        here. A discount-bearing code that instead relies on day_of_month/
        cutoff_day ("proximo") logic is deliberately excluded and listed
        separately - not silently treated as zero."""

        self.initialize()
        as_of = as_of_date.isoformat()
        connection = self._connection()
        try:
            has_reference = connection.execute(
                "SELECT COUNT(*) AS count FROM ap_vendor_terms_reference;"
            ).fetchone()["count"]
            eligible = connection.execute(
                """
                SELECT
                    COUNT(*) AS eligible_count,
                    COALESCE(SUM(l.amount_invoiced * t.discount_percent / 100.0), 0)
                        AS eligible_amount
                FROM ap_erp_open_ledger_cache l
                JOIN ap_erp_vendor_terms_cache v
                    ON v.vendor_number = l.vendor_number
                JOIN ap_vendor_terms_reference t
                    ON t.terms_code = v.terms_code
                WHERE l.on_hold = 0
                    AND t.discount_percent > 0
                    AND t.num_days > 0
                    AND l.invoice_date IS NOT NULL
                    AND date(l.invoice_date, '+' || t.num_days || ' days') >= ?;
                """,
                (as_of,),
            ).fetchone()
            excluded = connection.execute(
                """
                SELECT terms_code, description FROM ap_vendor_terms_reference
                WHERE discount_percent > 0
                    AND (num_days IS NULL OR num_days <= 0)
                ORDER BY terms_code;
                """
            ).fetchall()
        finally:
            connection.close()
        return {
            "has_reference_data": bool(has_reference),
            "eligible_count": eligible["eligible_count"],
            "eligible_amount": eligible["eligible_amount"],
            "excluded_codes": [dict(row) for row in excluded],
        }

    def update_open_ledger_gl_fields(
        self,
        gl_fields: dict[tuple[str, str], tuple[str | None, str | None, str | None]],
    ) -> int:
        """Populates gl_division/gl_account/gl_department on already-cached
        open-ledger rows, each a (division, account, department) tuple from
        the same winning GL distribution line. Never inserts new rows - an
        invoice must already be in the open-ledger cache (i.e. currently
        unpaid) for its GL detail to matter here."""

        self.initialize()
        if not gl_fields:
            return 0
        prepared = [
            (division, account, department, vendor_number, invoice_number)
            for (vendor_number, invoice_number), (
                division, account, department,
            ) in gl_fields.items()
        ]
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.executemany(
                """
                UPDATE ap_erp_open_ledger_cache
                SET gl_division = ?, gl_account = ?, gl_department = ?
                WHERE vendor_number = ? AND invoice_number = ?;
                """,
                prepared,
            )
            updated = connection.total_changes
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return updated

    def _latest_warehouse_status(
        self, connection: sqlite3.Connection, vendor_number: str, invoice_number: str
    ) -> str:
        row = connection.execute(
            """
            SELECT to_status FROM ap_warehouse_approval_actions
            WHERE vendor_number = ? AND invoice_number = ?
            ORDER BY created_at DESC, action_id DESC
            LIMIT 1;
            """,
            (vendor_number, invoice_number),
        ).fetchone()
        return row["to_status"] if row is not None else "needs_approval"

    def record_warehouse_approval_action(
        self,
        *,
        action_id: str,
        vendor_number: str,
        invoice_number: str,
        to_status: str,
        actor_identity: str,
        actor_identity_source: str,
        notes: str,
        created_at: str,
    ) -> dict[str, Any]:
        self.initialize()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            from_status = self._latest_warehouse_status(
                connection, vendor_number, invoice_number
            )
            connection.execute(
                """
                INSERT INTO ap_warehouse_approval_actions (
                    action_id, vendor_number, invoice_number, from_status,
                    to_status, actor_identity, actor_identity_source,
                    notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    action_id,
                    vendor_number,
                    invoice_number,
                    from_status,
                    to_status,
                    actor_identity,
                    actor_identity_source,
                    notes,
                    created_at,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return {
            "action_id": action_id,
            "vendor_number": vendor_number,
            "invoice_number": invoice_number,
            "from_status": from_status,
            "to_status": to_status,
            "actor_identity": actor_identity,
            "actor_identity_source": actor_identity_source,
            "notes": notes,
            "created_at": created_at,
        }

    def warehouse_approval_queue(
        self, division: str | None
    ) -> dict[str, Any]:
        """Every currently-open ERP invoice (from the same open-ledger cache
        the dashboard uses), bucketed by its latest warehouse-approval
        action status (or 'needs_approval' when none exists yet), optionally
        filtered to one GL division. An invoice with no action row is never
        materialized as a row in ap_warehouse_approval_actions - status is
        always derived, matching ap_control_cases' derivation precedent.

        Linkage to a local ap_invoices row (once one exists via OCR capture)
        is a best-effort match on vendor_number + normalized invoice
        number - nullable and disclosed, not a guaranteed join."""

        self.initialize()
        # ap_invoices belongs to AccountsPayableRepository, which may not
        # have run its own lazy CREATE TABLE IF NOT EXISTS yet if this is
        # the first accounts_payable call this process makes - initialize
        # it here (via the same connection_factory this instance uses) so
        # the LEFT JOIN below never fails with "no such table".
        AccountsPayableRepository(self._connection_factory).initialize()
        where = "WHERE l.gl_division = ?" if division else ""
        parameters: tuple[Any, ...] = (division,) if division else ()
        connection = self._connection()
        try:
            rows = connection.execute(
                f"""
                SELECT
                    l.vendor_number,
                    v.vendor_name,
                    l.invoice_number,
                    l.invoice_date,
                    l.due_date,
                    l.amount_invoiced,
                    l.amount_discount,
                    l.on_hold,
                    l.gl_division,
                    l.gl_account,
                    l.gl_department,
                    COALESCE(latest.to_status, 'needs_approval') AS status,
                    latest.actor_identity AS last_actor_identity,
                    latest.created_at AS last_action_at,
                    i.ap_invoice_id AS linked_ap_invoice_id
                FROM ap_erp_open_ledger_cache l
                LEFT JOIN ap_erp_vendor_terms_cache v
                    ON v.vendor_number = l.vendor_number
                LEFT JOIN (
                    SELECT
                        vendor_number,
                        invoice_number,
                        to_status,
                        actor_identity,
                        created_at,
                        ROW_NUMBER() OVER (
                            PARTITION BY vendor_number, invoice_number
                            ORDER BY created_at DESC, action_id DESC
                        ) AS rn
                    FROM ap_warehouse_approval_actions
                ) latest
                    ON latest.vendor_number = l.vendor_number
                    AND latest.invoice_number = l.invoice_number
                    AND latest.rn = 1
                LEFT JOIN ap_invoices i
                    ON i.vendor_number = l.vendor_number
                    AND i.normalized_invoice_number = UPPER(l.invoice_number)
                {where}
                ORDER BY l.due_date IS NULL, l.due_date, l.vendor_number, l.invoice_number;
                """,
                parameters,
            ).fetchall()
            divisions = connection.execute(
                """
                SELECT DISTINCT gl_division FROM ap_erp_open_ledger_cache
                WHERE gl_division IS NOT NULL
                ORDER BY gl_division;
                """
            ).fetchall()
        finally:
            connection.close()
        return {
            "items": [dict(row) for row in rows],
            "available_divisions": [row["gl_division"] for row in divisions],
        }


accounts_payable_erp_ledger_repository = AccountsPayableErpLedgerRepository()


def initialize_accounts_payable_erp_ledger_database() -> None:
    """Startup migration hook for the shared SQLite initialization boundary."""

    accounts_payable_erp_ledger_repository.initialize()
