"""One-off data migration: copies the cash_flow_forecasting tables from
SQLite (backend/data/workbench.db) into MySQL (the ETOP_DB_* schema).

Only cash_flow_ap_due_date_cache has real data as of writing (the
snapshots/weeks/actuals evidence tables are empty in production), but all
four are migrated for completeness and future-proofing.

Usage (from the backend/ directory, with ETOP_DB_* configured in .env):

    .venv/Scripts/python.exe scripts/migrate_cash_flow_forecasting_to_mysql.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from data.database import get_connection  # noqa: E402
from data.mysql import (  # noqa: E402
    cash_flow_ap_due_date_cache_table,
    cash_flow_forecast_actuals_table,
    cash_flow_forecast_snapshots_table,
    cash_flow_forecast_weeks_table,
    get_engine,
    metadata,
)

_MIGRATION_ORDER = [
    ("cash_flow_forecast_snapshots", cash_flow_forecast_snapshots_table, ["snapshot_id"]),
    ("cash_flow_forecast_weeks", cash_flow_forecast_weeks_table, ["week_id"]),
    ("cash_flow_forecast_actuals", cash_flow_forecast_actuals_table, ["actual_id"]),
    ("cash_flow_ap_due_date_cache", cash_flow_ap_due_date_cache_table, ["week_start"]),
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
