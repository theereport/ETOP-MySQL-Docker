"""One-off data migration: copies the invoice_owner_cache.db tables from
SQLite into MySQL (the ETOP_DB_* schema).

This cache is large (~257k rows), so unlike the other migrate_*_to_mysql.py
scripts, this one does a wholesale replace (TRUNCATE + chunked bulk insert)
rather than row-by-row check-then-insert - the row-by-row pattern would take
far too long at this volume, and there's nothing to preserve across rows
since this is a plain, wholesale-replaceable cache (see the module docstring
in integrations/invoice_owner_cache.py).

Usage (from the backend/ directory, with ETOP_DB_* configured in .env):

    .venv/Scripts/python.exe scripts/migrate_invoice_owner_cache_to_mysql.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from data.mysql import (  # noqa: E402
    get_engine,
    invoice_owner_cache_metadata_table,
    invoice_owner_cache_table,
    metadata,
)

SOURCE_DB = REPO_ROOT / "data" / "etop_state" / "invoice_owner_cache.db"
_CHUNK_SIZE = 5_000


def main() -> None:
    print("Ensuring MySQL tables exist...")
    metadata.create_all(
        get_engine(),
        checkfirst=True,
        tables=[invoice_owner_cache_table, invoice_owner_cache_metadata_table],
    )

    if not SOURCE_DB.exists():
        print(f"No source database at {SOURCE_DB} - nothing to migrate.")
        return

    connection = sqlite3.connect(SOURCE_DB)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT invoice_number, customer_numbers, refreshed_at "
            "FROM current_invoice_owners"
        ).fetchall()
        metadata_rows = connection.execute(
            "SELECT key, value FROM invoice_owner_cache_metadata"
        ).fetchall()
    finally:
        connection.close()

    source_count = len(rows)
    print(f"Read {source_count} rows from SQLite.")

    with get_engine().begin() as target:
        target.execute(invoice_owner_cache_table.delete())
        for start in range(0, len(rows), _CHUNK_SIZE):
            chunk = rows[start : start + _CHUNK_SIZE]
            target.execute(
                invoice_owner_cache_table.insert(),
                [
                    {
                        "invoice_number": row["invoice_number"],
                        "customer_numbers": row["customer_numbers"],
                        "refreshed_at": row["refreshed_at"],
                    }
                    for row in chunk
                ],
            )
            print(f"  inserted {min(start + _CHUNK_SIZE, len(rows))}/{len(rows)}")

        target.execute(invoice_owner_cache_metadata_table.delete())
        for row in metadata_rows:
            target.execute(
                invoice_owner_cache_metadata_table.insert().values(
                    meta_key=row["key"], meta_value=row["value"]
                )
            )
        mysql_count = len(
            target.execute(invoice_owner_cache_table.select()).all()
        )

    status = "OK" if mysql_count == source_count else "MISMATCH"
    print(f"current_invoice_owners: sqlite={source_count} mysql={mysql_count} [{status}]")
    if status != "OK":
        raise SystemExit("Row-count mismatch - see above.")
    print("Migration complete.")


if __name__ == "__main__":
    main()
