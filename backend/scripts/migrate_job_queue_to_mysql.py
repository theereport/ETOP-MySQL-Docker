"""One-off data migration: copies the job_queue_jobs table from SQLite
(backend/data/workbench.db) into MySQL (the ETOP_DB_* schema), then
validates the row counts match on both sides.

Usage (from the backend/ directory, with ETOP_DB_* configured in .env):

    .venv/Scripts/python.exe scripts/migrate_job_queue_to_mysql.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from data.database import get_connection  # noqa: E402
from data.mysql import get_engine, job_queue_jobs_table, metadata  # noqa: E402


def _fetch_sqlite_rows() -> list[dict]:
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT * FROM job_queue_jobs ORDER BY rowid"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def main() -> None:
    print("Ensuring MySQL table exists...")
    metadata.create_all(get_engine(), checkfirst=True, tables=[job_queue_jobs_table])

    source_rows = _fetch_sqlite_rows()

    with get_engine().begin() as connection:
        for row in source_rows:
            existing = connection.execute(
                job_queue_jobs_table.select().where(
                    job_queue_jobs_table.c.job_id == row["job_id"]
                )
            ).first()
            if existing is None:
                connection.execute(job_queue_jobs_table.insert().values(**row))
            else:
                update_values = {k: v for k, v in row.items() if k != "job_id"}
                connection.execute(
                    job_queue_jobs_table.update()
                    .where(job_queue_jobs_table.c.job_id == row["job_id"])
                    .values(**update_values)
                )
        mysql_count = len(connection.execute(job_queue_jobs_table.select()).all())

    status = "OK" if len(source_rows) == mysql_count else "MISMATCH"
    print(f"job_queue_jobs: sqlite={len(source_rows)} mysql={mysql_count} [{status}]")
    if status != "OK":
        raise SystemExit("Row count mismatch.")
    print("Migration complete.")


if __name__ == "__main__":
    main()
