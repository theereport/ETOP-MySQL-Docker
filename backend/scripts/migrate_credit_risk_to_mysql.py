"""One-off data migration: copies the credit_risk potential-customer tables
from SQLite (backend/data/workbench.db) into MySQL (the ETOP_DB_* schema).

credit_risk_band_sets/credit_risk_bands are not migrated here - they're
governed seed data recreated identically by CreditRiskRepository.initialize()
on any fresh schema. credit_risk_assessments/credit_line_proposals/
credit_portfolio_reviews/credit_order_recommendations are empty in
production as of writing.

Usage (from the backend/ directory, with ETOP_DB_* configured in .env):

    .venv/Scripts/python.exe scripts/migrate_credit_risk_to_mysql.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from data.database import get_connection  # noqa: E402
from data.mysql import (  # noqa: E402
    credit_potential_customer_documents_table,
    credit_potential_customers_table,
    get_engine,
    metadata,
)

_MIGRATION_ORDER = [
    ("credit_potential_customers", credit_potential_customers_table, ["potential_customer_id"]),
    (
        "credit_potential_customer_documents",
        credit_potential_customer_documents_table,
        ["potential_customer_id"],
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
