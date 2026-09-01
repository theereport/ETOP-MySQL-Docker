"""One-off data migration: copies the lockbox_preparation.db tables from
SQLite into MySQL (the ETOP_DB_* schema).

preparation_schema (a singleton row tracking an in-place SQLite schema
version) is not migrated - it existed only to drive the old ALTER-TABLE-
based v2->v3 migration, and MySQL always gets the current schema directly.

Some payload_json/result_json rows measured up to ~7.25MB, so this script
avoids the row-by-row check-then-insert pattern used in the smaller phase-2
batches: it fetches existing primary keys in bulk first, then bulk-inserts
only the missing rows in size-aware chunks (bounded by both row count and
cumulative byte size, since a handful of multi-MB outlier rows could
otherwise land in the same oversized packet).

Usage (from the backend/ directory, with ETOP_DB_* configured in .env):

    .venv/Scripts/python.exe scripts/migrate_lockbox_preparation_to_mysql.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from data.mysql import (  # noqa: E402
    get_engine,
    lockbox_preparation_events_table,
    lockbox_preparation_jobs_table,
    lockbox_preparation_transactions_table,
    metadata,
)

SOURCE_DB = REPO_ROOT / "data" / "etop_state" / "lockbox_preparation.db"

_MAX_ROWS_PER_CHUNK = 200
_MAX_BYTES_PER_CHUNK = 8_000_000


def _fetch_sqlite_rows(table_name: str, order_by: str) -> list[dict]:
    connection = sqlite3.connect(SOURCE_DB)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            f"SELECT * FROM {table_name} ORDER BY {order_by}"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _row_size(row: dict) -> int:
    return sum(len(str(value)) for value in row.values() if value is not None)


def _chunked(rows: list[dict]) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_bytes = 0
    for row in rows:
        size = _row_size(row)
        if current and (
            len(current) >= _MAX_ROWS_PER_CHUNK
            or current_bytes + size > _MAX_BYTES_PER_CHUNK
        ):
            chunks.append(current)
            current = []
            current_bytes = 0
        current.append(row)
        current_bytes += size
    if current:
        chunks.append(current)
    return chunks


def _migrate_table(
    table_name: str,
    table,
    pk_columns: list[str],
    order_by: str,
) -> tuple[int, int]:
    source_rows = _fetch_sqlite_rows(table_name, order_by)

    with get_engine().begin() as connection:
        if len(pk_columns) == 1:
            existing_keys = {
                row[0]
                for row in connection.execute(select(table.c[pk_columns[0]])).all()
            }
            missing = [
                row for row in source_rows if row[pk_columns[0]] not in existing_keys
            ]
        else:
            existing_keys = {
                tuple(row[col] for col in pk_columns)
                for row in connection.execute(
                    select(*[table.c[col] for col in pk_columns])
                ).all()
            }
            missing = [
                row
                for row in source_rows
                if tuple(row[col] for col in pk_columns) not in existing_keys
            ]

        for chunk in _chunked(missing):
            connection.execute(table.insert(), chunk)

        mysql_count = len(connection.execute(select(table)).all())

    return len(source_rows), mysql_count


def main() -> None:
    print("Ensuring MySQL tables exist...")
    tables = [
        lockbox_preparation_jobs_table,
        lockbox_preparation_transactions_table,
        lockbox_preparation_events_table,
    ]
    metadata.create_all(get_engine(), checkfirst=True, tables=tables)

    if not SOURCE_DB.exists():
        print(f"No source database at {SOURCE_DB} - nothing to migrate.")
        return

    any_mismatch = False
    for table_name, table, pk_columns, order_by in (
        ("preparation_jobs", lockbox_preparation_jobs_table, ["job_id"], "created_at"),
        (
            "preparation_transactions",
            lockbox_preparation_transactions_table,
            ["job_id", "transaction_id"],
            "job_id, ordinal",
        ),
        (
            "preparation_events",
            lockbox_preparation_events_table,
            ["event_id"],
            "event_id",
        ),
    ):
        source_count, mysql_count = _migrate_table(
            table_name, table, pk_columns, order_by
        )
        status = "OK" if source_count == mysql_count else "MISMATCH"
        if status != "OK":
            any_mismatch = True
        print(f"{table_name}: sqlite={source_count} mysql={mysql_count} [{status}]")

    if any_mismatch:
        raise SystemExit("One or more tables had a row-count mismatch - see above.")
    print("Migration complete.")


if __name__ == "__main__":
    main()
