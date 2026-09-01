"""One-off data migration: copies the 19 workflow_foundation tables from
SQLite (backend/data/workbench.db) into MySQL (the ETOP_DB_* schema), then
validates the row counts match on both sides.

Tables are migrated in FK-dependency order. wf_task_assignments,
wf_task_events, and wf_audit_events have a new auto-increment `sequence`
surrogate key that didn't exist in SQLite (it replaces ordering that used
to rely on SQLite's implicit rowid) - rows are inserted in their original
rowid order so the new sequence values preserve the same relative
ordering, which matters for both "latest assignee" lookups and the audit
hash chain's integrity check.

Usage (from the backend/ directory, with ETOP_DB_* configured in .env):

    .venv/Scripts/python.exe scripts/migrate_workflow_foundation_to_mysql.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from data.database import get_connection  # noqa: E402
from data.mysql import get_engine, metadata  # noqa: E402
from data.mysql import (  # noqa: E402
    wf_access_profiles_table,
    wf_audit_events_table,
    wf_definitions_table,
    wf_invitation_events_table,
    wf_module_access_events_table,
    wf_modules_table,
    wf_notifications_table,
    wf_password_reset_events_table,
    wf_password_reset_tokens_table,
    wf_persons_table,
    wf_role_assignments_table,
    wf_roles_table,
    wf_sessions_table,
    wf_task_assignments_table,
    wf_task_events_table,
    wf_tasks_table,
    wf_user_accounts_table,
    wf_user_invitations_table,
    wf_user_module_access_table,
)

# (table_name, Table object, primary-key column(s), drop-generated-columns)
# Order matters - each table's FK targets must be migrated first.
_MIGRATION_ORDER = [
    ("wf_persons", wf_persons_table, ["person_id"], None),
    ("wf_roles", wf_roles_table, ["role_id"], None),
    ("wf_modules", wf_modules_table, ["module_id"], None),
    ("wf_definitions", wf_definitions_table, ["definition_id", "version"], None),
    ("wf_user_accounts", wf_user_accounts_table, ["user_id"], None),
    ("wf_role_assignments", wf_role_assignments_table, ["role_assignment_id"], None),
    ("wf_sessions", wf_sessions_table, ["session_id"], None),
    ("wf_access_profiles", wf_access_profiles_table, ["user_id"], None),
    (
        "wf_user_module_access",
        wf_user_module_access_table,
        ["user_id", "module_id"],
        None,
    ),
    (
        "wf_module_access_events",
        wf_module_access_events_table,
        ["access_event_id"],
        None,
    ),
    (
        "wf_user_invitations",
        wf_user_invitations_table,
        ["invitation_id"],
        {"pending_username_key"},  # generated column - never inserted directly
    ),
    ("wf_invitation_events", wf_invitation_events_table, ["invitation_event_id"], None),
    (
        "wf_password_reset_tokens",
        wf_password_reset_tokens_table,
        ["reset_id"],
        None,
    ),
    (
        "wf_password_reset_events",
        wf_password_reset_events_table,
        ["reset_event_id"],
        None,
    ),
    ("wf_tasks", wf_tasks_table, ["task_id"], None),
    (
        "wf_task_assignments",
        wf_task_assignments_table,
        ["assignment_event_id"],
        {"sequence"},  # auto-increment surrogate - let MySQL assign it
    ),
    (
        "wf_task_events",
        wf_task_events_table,
        ["event_id"],
        {"sequence"},
    ),
    ("wf_notifications", wf_notifications_table, ["notification_id"], None),
    (
        "wf_audit_events",
        wf_audit_events_table,
        ["audit_id"],
        {"sequence"},
    ),
]


def _fetch_sqlite_rows(table_name: str) -> list[dict]:
    # get_connection()'s own context-manager protocol only commits/rolls
    # back on exit - it never closes the connection - so this needs an
    # explicit close() or the workbench.db file handle leaks.
    connection = get_connection()
    try:
        rows = connection.execute(
            f"SELECT * FROM {table_name} ORDER BY rowid"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _migrate_table(
    table_name: str, table, pk_columns: list[str], drop_columns: set[str] | None
) -> tuple[int, int]:
    source_rows = _fetch_sqlite_rows(table_name)
    drop_columns = drop_columns or set()

    with get_engine().begin() as connection:
        for row in source_rows:
            values = {k: v for k, v in row.items() if k not in drop_columns}
            pk_condition = [table.c[col] == row[col] for col in pk_columns]
            existing = connection.execute(
                table.select().where(*pk_condition)
            ).first()
            if existing is None:
                connection.execute(table.insert().values(**values))
            else:
                update_values = {
                    k: v for k, v in values.items() if k not in pk_columns
                }
                if update_values:
                    connection.execute(
                        table.update().where(*pk_condition).values(**update_values)
                    )

        mysql_count = len(connection.execute(table.select()).all())

    return len(source_rows), mysql_count


def main() -> None:
    print("Ensuring MySQL tables exist...")
    metadata.create_all(get_engine(), checkfirst=True)

    any_mismatch = False
    for table_name, table, pk_columns, drop_columns in _MIGRATION_ORDER:
        source_count, mysql_count = _migrate_table(
            table_name, table, pk_columns, drop_columns
        )
        status = "OK" if source_count == mysql_count else "MISMATCH"
        if source_count != mysql_count:
            any_mismatch = True
        print(
            f"{table_name}: sqlite={source_count} mysql={mysql_count} [{status}]"
        )

    if any_mismatch:
        raise SystemExit("One or more tables had a row-count mismatch - see above.")

    print("Migration complete.")


if __name__ == "__main__":
    main()
