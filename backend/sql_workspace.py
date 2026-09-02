from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import time
from datetime import date, datetime, time as datetime_time
from decimal import Decimal
from pathlib import Path
from typing import Any

from typing import Annotated

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.database import madden_database
from core.sql_validator import (
    apply_row_limit,
    normalize_and_validate_sql,
)
from core.test_path_override import resolve_test_path_override
from modules.workflow_foundation.service import (
    WorkflowAuthenticationRequired,
    workflow_foundation_service,
)


load_dotenv()

router = APIRouter(prefix="/sql", tags=["SQL Workspace"])

BASE_DIR = Path(__file__).resolve().parent
SQLITE_PATH = resolve_test_path_override(
    "ETOP_TEST_SQL_WORKSPACE_DB", BASE_DIR / "sql_workspace.db"
)

DEFAULT_LIMIT = int(os.getenv("SQL_DEFAULT_LIMIT", "500"))
MAX_LIMIT = int(os.getenv("SQL_MAX_LIMIT", "5000"))


def _connect() -> sqlite3.Connection:
    """Open a connection to sql_workspace.db with a concurrency mitigation.

    This is the one feature intentionally left on SQLite rather than MySQL
    (see docs/migration notes). busy_timeout makes a writer that contends
    with another connection wait briefly instead of immediately raising
    "database is locked".

    Deliberately NOT using PRAGMA journal_mode=WAL here: docker-compose.yml
    bind-mounts sql_workspace.db as a single file
    (./backend/sql_workspace.db:/app/backend/sql_workspace.db), not a
    directory. WAL mode writes recent commits to a separate `-wal` sidecar
    file that would land outside that mount, in the container's ephemeral
    layer - a container recreation before SQLite auto-checkpoints could
    silently lose those writes. The default rollback-journal mode's
    `-journal` file doesn't have that problem (it's cleaned up immediately
    after each commit), so it's the safer choice given how this file is
    mounted today.
    """

    connection = sqlite3.connect(SQLITE_PATH)
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def _current_user_id(
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    """The requesting account's user_id, for scoping saved queries/history.

    Every /sql/* route already requires the sql_workspace module grant
    (ModuleAccessMiddleware), so a valid Bearer token is always present by
    the time this runs - the None fallback is defense-in-depth only, not
    an expected path. Returns user_id (stable) rather than username, so
    ownership survives a username change.
    """

    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    try:
        session = workflow_foundation_service.session_for_token(token)
    except WorkflowAuthenticationRequired:
        return None
    return session["user"]["user_id"]


CurrentUserId = Annotated[str | None, Depends(_current_user_id)]


class ExecuteSqlRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=250_000)
    row_limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


class SavedQueryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(default="General", max_length=100)
    description: str = Field(default="", max_length=2_000)
    sql: str = Field(min_length=1, max_length=250_000)


class SavedQueryUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(default="General", max_length=100)
    description: str = Field(default="", max_length=2_000)
    sql: str = Field(min_length=1, max_length=250_000)


def _add_column_if_missing(
    connection: sqlite3.Connection, table: str, column: str, ddl: str
) -> None:
    existing = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def initialize_sql_workspace_database() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'General',
                description TEXT NOT NULL DEFAULT '',
                sql_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                created_by TEXT
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS query_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sql_text TEXT NOT NULL,
                success INTEGER NOT NULL,
                row_count INTEGER NOT NULL DEFAULT 0,
                execution_ms REAL NOT NULL DEFAULT 0,
                error_message TEXT,
                executed_at TEXT NOT NULL,
                created_by TEXT
            )
            """
        )

        # Existing databases created before created_by existed - added via
        # ALTER rather than relying on CREATE TABLE IF NOT EXISTS, which is
        # a no-op once the table already exists. NULL created_by (every
        # pre-existing row) is treated as "shared/legacy" everywhere this
        # is queried below - visible and editable by anyone, preserving
        # today's behavior for old data. Only new rows going forward are
        # scoped to their creator.
        _add_column_if_missing(
            connection, "saved_queries", "created_by", "created_by TEXT"
        )
        _add_column_if_missing(
            connection, "query_history", "created_by", "created_by TEXT"
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_saved_queries_title
            ON saved_queries(title)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_saved_queries_category
            ON saved_queries(category)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_query_history_executed_at
            ON query_history(executed_at DESC)
            """
        )

        connection.commit()


initialize_sql_workspace_database()


def record_history(
    sql_text: str,
    success: bool,
    row_count: int,
    execution_ms: float,
    error_message: str | None,
    created_by: str | None,
) -> None:
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO query_history (
                sql_text,
                success,
                row_count,
                execution_ms,
                error_message,
                executed_at,
                created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sql_text,
                1 if success else 0,
                row_count,
                execution_ms,
                error_message,
                datetime.now().isoformat(timespec="seconds"),
                created_by,
            ),
        )

        connection.commit()



def execute_mysql_query(
    validated_sql: str,
    row_limit: int,
    created_by: str | None,
) -> dict[str, Any]:
    """
    Executes validated read-only SQL through the shared MaddenDatabase
    service and records the result in local query history.
    """

    limited_sql = apply_row_limit(validated_sql, row_limit)
    started_at = time.perf_counter()

    try:
        rows = madden_database.fetch_all(limited_sql)
        columns = list(rows[0].keys()) if rows else []

        execution_ms = round(
            (time.perf_counter() - started_at) * 1000,
            2,
        )

        record_history(
            sql_text=validated_sql,
            success=True,
            row_count=len(rows),
            execution_ms=execution_ms,
            error_message=None,
            created_by=created_by,
        )

        return {
            "success": True,
            "sql": validated_sql,
            "executed_sql": limited_sql,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "row_limit": row_limit,
            "limit_applied": limited_sql != validated_sql,
            "execution_ms": execution_ms,
        }

    except HTTPException as database_error:
        execution_ms = round(
            (time.perf_counter() - started_at) * 1000,
            2,
        )

        error_message = str(database_error.detail)

        record_history(
            sql_text=validated_sql,
            success=False,
            row_count=0,
            execution_ms=execution_ms,
            error_message=error_message,
            created_by=created_by,
        )

        raise

@router.get("/connection")
def test_sql_connection() -> dict[str, Any]:
    """Tests the shared MaddenCo database service."""

    details = madden_database.test_connection()

    return {
        **details,
        "default_limit": DEFAULT_LIMIT,
        "maximum_limit": MAX_LIMIT,
    }

@router.post("/validate")
def validate_sql(request: ExecuteSqlRequest) -> dict[str, Any]:
    validated_sql = normalize_and_validate_sql(request.sql)
    executable_sql = apply_row_limit(
        validated_sql,
        request.row_limit,
    )

    return {
        "valid": True,
        "sql": validated_sql,
        "executed_sql": executable_sql,
        "limit_applied": executable_sql != validated_sql,
        "row_limit": request.row_limit,
    }


@router.post("/execute")
def execute_sql(
    request: ExecuteSqlRequest, current_user_id: CurrentUserId
) -> dict[str, Any]:
    validated_sql = normalize_and_validate_sql(request.sql)

    return execute_mysql_query(
        validated_sql=validated_sql,
        row_limit=request.row_limit,
        created_by=current_user_id,
    )


@router.post("/export")
def export_sql_results(
    request: ExecuteSqlRequest, current_user_id: CurrentUserId
) -> StreamingResponse:
    validated_sql = normalize_and_validate_sql(request.sql)

    result = execute_mysql_query(
        validated_sql=validated_sql,
        row_limit=request.row_limit,
        created_by=current_user_id,
    )

    output = io.StringIO(newline="")
    writer = csv.writer(output)

    writer.writerow(result["columns"])

    for row in result["rows"]:
        writer.writerow(
            [
                json.dumps(value)
                if isinstance(value, (dict, list))
                else value
                for value in row.values()
            ]
        )

    output.seek(0)

    filename = (
        "sql-results-"
        + datetime.now().strftime("%Y%m%d-%H%M%S")
        + ".csv"
    )

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            )
        },
    )


@router.get("/saved")
def get_saved_queries(
    current_user_id: CurrentUserId,
    search: str = Query(default="", max_length=200),
    category: str = Query(default="", max_length=100),
) -> dict[str, Any]:
    # created_by IS NULL = a query saved before per-user scoping existed -
    # treated as shared/legacy, visible to everyone (see initialize_
    # sql_workspace_database's migration comment).
    conditions: list[str] = ["(created_by = ? OR created_by IS NULL)"]
    parameters: list[Any] = [current_user_id]

    if search.strip():
        search_value = f"%{search.strip()}%"

        conditions.append(
            """
            (
                title LIKE ?
                OR category LIKE ?
                OR description LIKE ?
                OR sql_text LIKE ?
            )
            """
        )

        parameters.extend(
            [
                search_value,
                search_value,
                search_value,
                search_value,
            ]
        )

    if category.strip():
        conditions.append("category = ?")
        parameters.append(category.strip())

    where_clause = (
        "WHERE " + " AND ".join(conditions)
        if conditions
        else ""
    )

    with _connect() as connection:
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            f"""
            SELECT
                id,
                title,
                category,
                description,
                sql_text AS sql,
                created_at,
                updated_at
            FROM saved_queries
            {where_clause}
            ORDER BY updated_at DESC, title ASC
            """,
            parameters,
        ).fetchall()

    return {
        "queries": [dict(row) for row in rows],
        "count": len(rows),
    }


@router.post("/saved")
def create_saved_query(
    request: SavedQueryCreate,
    current_user_id: CurrentUserId,
) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")

    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO saved_queries (
                title,
                category,
                description,
                sql_text,
                created_at,
                updated_at,
                created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.title.strip(),
                request.category.strip() or "General",
                request.description.strip(),
                request.sql.strip(),
                now,
                now,
                current_user_id,
            ),
        )

        saved_query_id = cursor.lastrowid
        connection.commit()

    return {
        "success": True,
        "id": saved_query_id,
        "message": "Query saved locally.",
    }


@router.put("/saved/{saved_query_id}")
def update_saved_query(
    saved_query_id: int,
    request: SavedQueryUpdate,
    current_user_id: CurrentUserId,
) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")

    with _connect() as connection:
        # created_by IS NULL (legacy/shared, saved before per-user scoping
        # existed) stays editable by anyone, matching get_saved_queries.
        cursor = connection.execute(
            """
            UPDATE saved_queries
            SET
                title = ?,
                category = ?,
                description = ?,
                sql_text = ?,
                updated_at = ?
            WHERE id = ? AND (created_by = ? OR created_by IS NULL)
            """,
            (
                request.title.strip(),
                request.category.strip() or "General",
                request.description.strip(),
                request.sql.strip(),
                now,
                saved_query_id,
                current_user_id,
            ),
        )

        connection.commit()

    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail="Saved query not found.",
        )

    return {
        "success": True,
        "message": "Saved query updated.",
    }


@router.delete("/saved/{saved_query_id}")
def delete_saved_query(
    saved_query_id: int, current_user_id: CurrentUserId
) -> dict[str, Any]:
    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM saved_queries WHERE id = ? AND (created_by = ? OR created_by IS NULL)",
            (saved_query_id, current_user_id),
        )

        connection.commit()

    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail="Saved query not found.",
        )

    return {
        "success": True,
        "message": "Saved query deleted.",
    }


@router.get("/categories")
def get_saved_query_categories() -> dict[str, Any]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT category
            FROM saved_queries
            WHERE TRIM(category) <> ''
            ORDER BY category ASC
            """
        ).fetchall()

    return {
        "categories": [row[0] for row in rows],
    }


@router.get("/history")
def get_query_history(
    current_user_id: CurrentUserId,
    limit: int = Query(default=50, ge=1, le=250),
) -> dict[str, Any]:
    with _connect() as connection:
        connection.row_factory = sqlite3.Row

        # created_by IS NULL = run before per-user scoping existed - shown
        # to everyone as shared/legacy history, same treatment as saved
        # queries.
        rows = connection.execute(
            """
            SELECT
                id,
                sql_text AS sql,
                success,
                row_count,
                execution_ms,
                error_message,
                executed_at
            FROM query_history
            WHERE created_by = ? OR created_by IS NULL
            ORDER BY id DESC
            LIMIT ?
            """,
            (current_user_id, limit),
        ).fetchall()

    history = []

    for row in rows:
        item = dict(row)
        item["success"] = bool(item["success"])
        history.append(item)

    return {
        "history": history,
        "count": len(history),
    }


@router.delete("/history")
def clear_query_history(current_user_id: CurrentUserId) -> dict[str, Any]:
    with _connect() as connection:
        # Only clears the requesting user's own history (plus legacy
        # unattributed rows, same shared treatment as reads above) - never
        # another user's history.
        connection.execute(
            "DELETE FROM query_history WHERE created_by = ? OR created_by IS NULL",
            (current_user_id,),
        )
        connection.commit()

    return {
        "success": True,
        "message": "Query history cleared.",
    }
