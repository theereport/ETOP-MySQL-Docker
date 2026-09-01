"""One-off data migration: copies the lockbox_review.db tables (used by
modules/document_intelligence/lockbox_review/database.py) from SQLite into
MySQL (the ETOP_DB_* schema).

Usage (from the backend/ directory, with ETOP_DB_* configured in .env):

    .venv/Scripts/python.exe scripts/migrate_lockbox_review_to_mysql.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from data.mysql import (  # noqa: E402
    get_engine,
    lockbox_customer_notes_table,
    lockbox_transaction_reviews_table,
    metadata,
)

SOURCE_DB = (
    BACKEND_DIR
    / "modules"
    / "document_intelligence"
    / "lockbox_review"
    / "lockbox_review.db"
)

_MIGRATION_ORDER = [
    (
        "transaction_reviews",
        lockbox_transaction_reviews_table,
        ["job_id", "transaction_id"],
    ),
    ("customer_notes", lockbox_customer_notes_table, ["note_id"]),
]


def _fetch_sqlite_rows(table_name: str) -> list[dict]:
    if not SOURCE_DB.exists():
        return []
    connection = sqlite3.connect(SOURCE_DB)
    connection.row_factory = sqlite3.Row
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
            row = dict(row)
            row.pop("note_id", None)
            if table is lockbox_customer_notes_table:
                pk_condition = [
                    table.c.customer_number == row["customer_number"],
                    table.c.source_job_id == row["source_job_id"],
                    table.c.source_transaction_id == row["source_transaction_id"],
                    table.c.created_at == row["created_at"],
                ]
            else:
                pk_condition = [table.c[col] == row[col] for col in pk_columns]
            existing = connection.execute(table.select().where(*pk_condition)).first()
            if existing is None:
                connection.execute(table.insert().values(**row))
            else:
                update_values = {
                    k: v
                    for k, v in row.items()
                    if k not in pk_columns and k in table.c
                }
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
