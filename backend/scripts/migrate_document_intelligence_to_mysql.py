"""One-off data migration: copies the document_intelligence core tables from
SQLite into MySQL (the ETOP_DB_* schema).

document_intelligence.db was actually split across two physical SQLite files
by a path-resolution bug: modules/document_intelligence/settings.py resolves
an ABSOLUTE path (<repo_root>/data/modules/document_intelligence/
document_intelligence.db), used by repository.py for doc_jobs/doc_results/
doc_processing_runs. But payer_mapping_repository.py, manual_enterprise_
group_repository.py, and cash_application/learning_repository.py each
defaulted to the RELATIVE string "data/modules/document_intelligence/
document_intelligence.db" via core.test_path_override.resolve_test_path_
override - and since the real backend process's cwd is backend/ (confirmed
via ETOP-Launcher/ETOP_Launcher.pyw), that relative path actually resolved
to <repo_root>/backend/data/modules/document_intelligence/document_
intelligence.db, a SECOND physical file, which is where payer_customer_
mapping/manual_enterprise_groups/manual_enterprise_group_members' real data
actually lives (the repo-root copy's versions of those same tables are
empty/stale).

This script sources each table from whichever physical file actually holds
its real data, consolidating both into one MySQL schema. document_training's
training_sessions has its own equivalent split (a stray empty copy sits
under backend/modules/.../training/document_training.db) - real data lives
under data/modules/.../training/document_training.db, resolved via the same
absolute settings.data_root path. document_learning.db (learning_examples)
has no split - only one copy exists, under backend/modules/, with 0 rows.

Usage (from the backend/ directory, with ETOP_DB_* configured in .env):

    .venv/Scripts/python.exe scripts/migrate_document_intelligence_to_mysql.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from data.mysql import (  # noqa: E402
    document_learning_examples_table,
    document_training_sessions_table,
    doc_jobs_table,
    doc_processing_runs_table,
    doc_results_table,
    get_engine,
    manual_enterprise_group_members_table,
    manual_enterprise_groups_table,
    metadata,
    payer_customer_mapping_table,
)

DOC_JOBS_DB = REPO_ROOT / "data" / "modules" / "document_intelligence" / "document_intelligence.db"
PAYER_MAPPING_DB = BACKEND_DIR / "data" / "modules" / "document_intelligence" / "document_intelligence.db"
TRAINING_DB = REPO_ROOT / "data" / "modules" / "document_intelligence" / "training" / "document_training.db"
LEARNING_DB = BACKEND_DIR / "modules" / "document_intelligence" / "document_learning.db"

_SIMPLE_TABLES = [
    (DOC_JOBS_DB, "doc_jobs", doc_jobs_table, ["job_id"]),
    (DOC_JOBS_DB, "doc_results", doc_results_table, ["job_id"]),
    (DOC_JOBS_DB, "doc_processing_runs", doc_processing_runs_table, ["processing_run_id"]),
    # payer_customer_mapping.mapping_id and learning_examples.id are
    # autoincrement surrogates not worth preserving - dedupe on each
    # table's real natural-unique columns instead, and let MySQL assign
    # fresh ids.
    (
        PAYER_MAPPING_DB,
        "payer_customer_mapping",
        payer_customer_mapping_table,
        ["routing_number", "bank_account_last4", "normalized_payer_name"],
    ),
    (TRAINING_DB, "training_sessions", document_training_sessions_table, ["session_id"]),
    (LEARNING_DB, "learning_examples", document_learning_examples_table, ["fingerprint"]),
]

_DROP_BEFORE_INSERT = {
    "payer_customer_mapping": ("mapping_id",),
    "learning_examples": ("id",),
}


def _fetch_sqlite_rows(db_path: Path, table_name: str) -> list[dict]:
    if not db_path.exists():
        return []
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        try:
            rows = connection.execute(
                f"SELECT * FROM {table_name} ORDER BY rowid"
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _migrate_simple_table(
    db_path: Path, table_name: str, table, pk_columns: list[str]
) -> tuple[int, int]:
    source_rows = _fetch_sqlite_rows(db_path, table_name)

    with get_engine().begin() as connection:
        for row in source_rows:
            row = dict(row)
            for column in _DROP_BEFORE_INSERT.get(table_name, ()):
                row.pop(column, None)
            pk_condition = [table.c[col] == row[col] for col in pk_columns if col in row]
            existing = (
                connection.execute(table.select().where(*pk_condition)).first()
                if pk_condition
                else None
            )
            if existing is None:
                insert_values = {k: v for k, v in row.items() if k in table.c}
                connection.execute(table.insert().values(**insert_values))
            else:
                update_values = {
                    k: v for k, v in row.items() if k not in pk_columns and k in table.c
                }
                if update_values:
                    connection.execute(
                        table.update().where(*pk_condition).values(**update_values)
                    )
        mysql_count = len(connection.execute(table.select()).all())

    return len(source_rows), mysql_count


def _migrate_manual_enterprise_groups() -> None:
    """Groups get fresh auto-increment ids on MySQL; members' group_id must
    be remapped to match. customer_number is unique across members, so it's
    used to make this idempotent (skip a member already migrated); a group
    with no un-migrated members left is skipped too so re-running the
    script doesn't create duplicate empty groups."""

    group_rows = _fetch_sqlite_rows(PAYER_MAPPING_DB, "manual_enterprise_groups")
    member_rows = _fetch_sqlite_rows(
        PAYER_MAPPING_DB, "manual_enterprise_group_members"
    )
    members_by_group: dict[int, list[dict]] = {}
    for row in member_rows:
        members_by_group.setdefault(row["group_id"], []).append(row)

    with get_engine().begin() as connection:
        existing_members = {
            row[0]
            for row in connection.execute(
                select(manual_enterprise_group_members_table.c.customer_number)
            ).all()
        }
        for row in group_rows:
            members = [
                member
                for member in members_by_group.get(row["group_id"], [])
                if member["customer_number"] not in existing_members
            ]
            if not members:
                continue
            result = connection.execute(
                manual_enterprise_groups_table.insert().values(
                    created_by=row["created_by"], created_at=row["created_at"]
                )
            )
            new_group_id = result.inserted_primary_key[0]
            for member in members:
                connection.execute(
                    manual_enterprise_group_members_table.insert().values(
                        group_id=new_group_id,
                        customer_number=member["customer_number"],
                        added_by=member["added_by"],
                        added_at=member["added_at"],
                    )
                )


def main() -> None:
    print("Ensuring MySQL tables exist...")
    metadata.create_all(
        get_engine(),
        checkfirst=True,
        tables=[
            doc_jobs_table,
            doc_results_table,
            doc_processing_runs_table,
            payer_customer_mapping_table,
            manual_enterprise_groups_table,
            manual_enterprise_group_members_table,
            document_training_sessions_table,
            document_learning_examples_table,
        ],
    )

    any_mismatch = False
    for db_path, table_name, table, pk_columns in _SIMPLE_TABLES:
        source_count, mysql_count = _migrate_simple_table(
            db_path, table_name, table, pk_columns
        )
        status = "OK" if source_count == mysql_count else "MISMATCH"
        if status != "OK":
            any_mismatch = True
        print(f"{table_name}: sqlite={source_count} mysql={mysql_count} [{status}]")

    group_rows = _fetch_sqlite_rows(PAYER_MAPPING_DB, "manual_enterprise_groups")
    member_rows = _fetch_sqlite_rows(
        PAYER_MAPPING_DB, "manual_enterprise_group_members"
    )
    _migrate_manual_enterprise_groups()
    with get_engine().connect() as connection:
        mysql_group_count = len(
            connection.execute(manual_enterprise_groups_table.select()).all()
        )
        mysql_member_count = len(
            connection.execute(manual_enterprise_group_members_table.select()).all()
        )
    group_status = "OK" if len(group_rows) == mysql_group_count else "MISMATCH"
    member_status = "OK" if len(member_rows) == mysql_member_count else "MISMATCH"
    if group_status != "OK":
        any_mismatch = True
    if member_status != "OK":
        any_mismatch = True
    print(
        f"manual_enterprise_groups: sqlite={len(group_rows)} "
        f"mysql={mysql_group_count} [{group_status}]"
    )
    print(
        f"manual_enterprise_group_members: sqlite={len(member_rows)} "
        f"mysql={mysql_member_count} [{member_status}]"
    )

    if any_mismatch:
        raise SystemExit("One or more tables had a row-count mismatch - see above.")
    print("Migration complete.")


if __name__ == "__main__":
    main()
