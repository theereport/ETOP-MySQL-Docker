"""One-off data migration: copies the accounts_payable tables from SQLite
(backend/data/workbench.db) into MySQL (the ETOP_DB_* schema).

Usage (from the backend/ directory, with ETOP_DB_* configured in .env):

    .venv/Scripts/python.exe scripts/migrate_accounts_payable_to_mysql.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from data.database import get_connection  # noqa: E402
from data.mysql import (  # noqa: E402
    ap_cash_scenarios_table,
    ap_control_cases_table,
    ap_control_reviews_table,
    ap_duplicate_candidates_table,
    ap_erp_open_ledger_cache_table,
    ap_erp_vendor_terms_cache_table,
    ap_exception_actions_table,
    ap_invoice_events_table,
    ap_invoice_revisions_table,
    ap_invoices_table,
    ap_vendor_terms_reference_table,
    ap_warehouse_approval_actions_table,
    get_engine,
    metadata,
)

_MIGRATION_ORDER = [
    ("ap_invoices", ap_invoices_table, ["ap_invoice_id"]),
    ("ap_invoice_revisions", ap_invoice_revisions_table, ["revision_id"]),
    ("ap_invoice_events", ap_invoice_events_table, ["event_id"]),
    ("ap_duplicate_candidates", ap_duplicate_candidates_table, ["candidate_id"]),
    ("ap_control_cases", ap_control_cases_table, ["control_case_id"]),
    ("ap_control_reviews", ap_control_reviews_table, ["review_id"]),
    ("ap_cash_scenarios", ap_cash_scenarios_table, ["cash_scenario_id"]),
    ("ap_exception_actions", ap_exception_actions_table, ["action_id"]),
    (
        "ap_erp_open_ledger_cache",
        ap_erp_open_ledger_cache_table,
        ["vendor_number", "invoice_number"],
    ),
    ("ap_erp_vendor_terms_cache", ap_erp_vendor_terms_cache_table, ["vendor_number"]),
    ("ap_vendor_terms_reference", ap_vendor_terms_reference_table, ["terms_code"]),
    (
        "ap_warehouse_approval_actions",
        ap_warehouse_approval_actions_table,
        ["action_id"],
    ),
]


def _fetch_sqlite_rows(table_name: str) -> list[dict]:
    connection = get_connection()
    try:
        rows = connection.execute(
            f"SELECT * FROM {table_name} ORDER BY rowid"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _migrate_table(table_name: str, table, pk_columns: list[str]) -> tuple[int, int]:
    source_rows = _fetch_sqlite_rows(table_name)

    with get_engine().begin() as connection:
        for row in source_rows:
            pk_condition = [table.c[col] == row[col] for col in pk_columns]
            existing = connection.execute(table.select().where(*pk_condition)).first()
            if existing is None:
                connection.execute(table.insert().values(**row))
            else:
                update_values = {k: v for k, v in row.items() if k not in pk_columns}
                if update_values:
                    connection.execute(
                        table.update().where(*pk_condition).values(**update_values)
                    )
        mysql_count = len(connection.execute(table.select()).all())

    return len(source_rows), mysql_count


def main() -> None:
    print("Ensuring MySQL tables exist...")
    metadata.create_all(
        get_engine(),
        checkfirst=True,
        tables=[table for _, table, _ in _MIGRATION_ORDER],
    )

    any_mismatch = False
    for table_name, table, pk_columns in _MIGRATION_ORDER:
        source_count, mysql_count = _migrate_table(table_name, table, pk_columns)
        status = "OK" if source_count == mysql_count else "MISMATCH"
        if status != "OK":
            any_mismatch = True
        print(f"{table_name}: sqlite={source_count} mysql={mysql_count} [{status}]")

    if any_mismatch:
        raise SystemExit("One or more tables had a row-count mismatch - see above.")
    print("Migration complete.")


if __name__ == "__main__":
    main()
