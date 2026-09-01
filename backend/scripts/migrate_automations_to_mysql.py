"""One-off data migration: copies the automations/automation_executions
tables from SQLite (backend/data/workbench.db) into MySQL (the ETOP_DB_*
schema), then validates the row counts match on both sides.

Usage (from the backend/ directory, with ETOP_DB_* configured in .env):

    .venv/Scripts/python.exe scripts/migrate_automations_to_mysql.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from data.database import get_connection  # noqa: E402
from modules.automations.mysql_engine import (  # noqa: E402
    automation_executions_table,
    automations_table,
    get_engine,
)
from modules.automations.repository import (  # noqa: E402
    initialize_automations_database,
)


def _fetch_sqlite_rows(table_name: str) -> list[dict]:
    # get_connection()'s own context-manager protocol only commits/rolls
    # back on exit - it never closes the connection - so this needs an
    # explicit close() or the workbench.db file handle leaks (see the same
    # note on repository.py's _connection() wrapper).
    connection = get_connection()
    try:
        rows = connection.execute(f"SELECT * FROM {table_name}").fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _migrate_table(table_name: str, table) -> tuple[int, int]:
    source_rows = _fetch_sqlite_rows(table_name)

    with get_engine().begin() as connection:
        for row in source_rows:
            existing = connection.execute(
                table.select().where(table.c.id == row["id"])
            ).first()
            if existing is None:
                connection.execute(table.insert().values(**row))
            else:
                connection.execute(
                    table.update()
                    .where(table.c.id == row["id"])
                    .values(**{k: v for k, v in row.items() if k != "id"})
                )

        mysql_count = len(connection.execute(table.select()).all())

    return len(source_rows), mysql_count


def main() -> None:
    print("Ensuring MySQL tables exist...")
    initialize_automations_database()

    for table_name, table in (
        ("automations", automations_table),
        ("automation_executions", automation_executions_table),
    ):
        source_count, mysql_count = _migrate_table(table_name, table)
        status = "OK" if source_count == mysql_count else "MISMATCH"
        print(
            f"{table_name}: sqlite={source_count} mysql={mysql_count} "
            f"[{status}]"
        )

        if source_count != mysql_count:
            raise SystemExit(
                f"Row count mismatch for {table_name}: "
                f"expected {source_count}, found {mysql_count} in MySQL."
            )

    print("Migration complete.")


if __name__ == "__main__":
    main()
