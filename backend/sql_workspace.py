from __future__ import annotations

import csv
import io
import json
import os
import re
import sqlite3
import time
from contextlib import closing
from datetime import date, datetime, time as datetime_time
from decimal import Decimal
from pathlib import Path
from typing import Any

import mysql.connector
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


load_dotenv()

router = APIRouter(prefix="/sql", tags=["SQL Workspace"])

BASE_DIR = Path(__file__).resolve().parent
SQLITE_PATH = BASE_DIR / "sql_workspace.db"

DEFAULT_LIMIT = int(os.getenv("SQL_DEFAULT_LIMIT", "500"))
MAX_LIMIT = int(os.getenv("SQL_MAX_LIMIT", "5000"))
SQL_TIMEOUT_SECONDS = int(os.getenv("SQL_TIMEOUT_SECONDS", "60"))

ALLOWED_STARTING_KEYWORDS = {
    "SELECT",
    "WITH",
    "SHOW",
    "DESCRIBE",
    "DESC",
    "EXPLAIN",
}

FORBIDDEN_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "REPLACE",
    "MERGE",
    "UPSERT",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "RENAME",
    "GRANT",
    "REVOKE",
    "LOCK",
    "UNLOCK",
    "CALL",
    "EXEC",
    "EXECUTE",
    "LOAD",
    "HANDLER",
    "INTO OUTFILE",
    "INTO DUMPFILE",
    "SET PASSWORD",
    "START TRANSACTION",
    "BEGIN",
    "COMMIT",
    "ROLLBACK",
    "SAVEPOINT",
    "RELEASE SAVEPOINT",
    "KILL",
    "SHUTDOWN",
    "INSTALL",
    "UNINSTALL",
}

READ_UNCOMMITTED_PREFIX = re.compile(
    r"""
    ^\s*
    SET\s+
    (?:SESSION\s+)?
    TRANSACTION\s+
    ISOLATION\s+
    LEVEL\s+
    READ\s+
    UNCOMMITTED
    \s*;
    """,
    re.IGNORECASE | re.VERBOSE,
)


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


def initialize_sql_workspace_database() -> None:
    with sqlite3.connect(SQLITE_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'General',
                description TEXT NOT NULL DEFAULT '',
                sql_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
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
                executed_at TEXT NOT NULL
            )
            """
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


def get_mysql_config() -> dict[str, Any]:
    required_values = {
        "host": os.getenv("MYSQL_HOST"),
        "database": os.getenv("MYSQL_DATABASE"),
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
    }

    missing = [
        key.upper()
        for key, value in required_values.items()
        if value is None or not value.strip()
    ]

    if missing:
        raise HTTPException(
            status_code=500,
            detail=(
                "Missing MySQL settings in backend/.env: "
                + ", ".join(missing)
            ),
        )

    return {
        "host": required_values["host"],
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "database": required_values["database"],
        "user": required_values["user"],
        "password": required_values["password"],
        "connection_timeout": 10,
        "autocommit": True,
        "use_pure": True,
        "charset": "utf8mb4",
        "collation": "utf8mb4_unicode_ci",
    }


def remove_comments_and_strings(sql: str) -> str:
    """
    Removes SQL comments and quoted string contents before security scanning.

    This prevents harmless text such as:
        SELECT 'delete this text'
    from being incorrectly blocked.
    """

    result: list[str] = []
    index = 0
    length = len(sql)

    while index < length:
        character = sql[index]

        if character in {"'", '"', "`"}:
            quote = character
            result.append(" ")

            index += 1

            while index < length:
                current = sql[index]

                if current == "\\":
                    index += 2
                    continue

                if current == quote:
                    if (
                        index + 1 < length
                        and sql[index + 1] == quote
                    ):
                        index += 2
                        continue

                    index += 1
                    break

                index += 1

            continue

        if (
            character == "-"
            and index + 1 < length
            and sql[index + 1] == "-"
        ):
            index += 2

            while index < length and sql[index] not in "\r\n":
                index += 1

            result.append(" ")
            continue

        if character == "#":
            index += 1

            while index < length and sql[index] not in "\r\n":
                index += 1

            result.append(" ")
            continue

        if (
            character == "/"
            and index + 1 < length
            and sql[index + 1] == "*"
        ):
            end_position = sql.find("*/", index + 2)

            if end_position == -1:
                raise HTTPException(
                    status_code=400,
                    detail="The SQL contains an unclosed block comment.",
                )

            index = end_position + 2
            result.append(" ")
            continue

        result.append(character)
        index += 1

    return "".join(result)


def count_sql_statements(sql: str) -> int:
    sanitized = remove_comments_and_strings(sql)
    statements = [
        statement.strip()
        for statement in sanitized.split(";")
        if statement.strip()
    ]

    return len(statements)


def normalize_and_validate_sql(raw_sql: str) -> str:
    sql = raw_sql.strip()

    if not sql:
        raise HTTPException(
            status_code=400,
            detail="Enter a SQL query before running it.",
        )

    # Many of the user's existing Workbench queries start with this exact
    # read-uncommitted statement. The backend removes it and controls the
    # database session itself.
    sql = READ_UNCOMMITTED_PREFIX.sub("", sql, count=1).strip()

    if not sql:
        raise HTTPException(
            status_code=400,
            detail="No executable SELECT query was found.",
        )

    statement_count = count_sql_statements(sql)

    if statement_count > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                "Only one SQL statement can be executed at a time. "
                "Remove any additional statements."
            ),
        )

    sql = sql.rstrip().rstrip(";").strip()

    sanitized = remove_comments_and_strings(sql)
    normalized = re.sub(r"\s+", " ", sanitized).strip().upper()

    first_keyword_match = re.match(r"^([A-Z]+)", normalized)

    if not first_keyword_match:
        raise HTTPException(
            status_code=400,
            detail="The SQL statement could not be identified.",
        )

    first_keyword = first_keyword_match.group(1)

    if first_keyword not in ALLOWED_STARTING_KEYWORDS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"SQL statements beginning with {first_keyword} are blocked. "
                "Only read-only SELECT, WITH, SHOW, DESCRIBE, DESC, "
                "and EXPLAIN statements are allowed."
            ),
        )

    for forbidden_keyword in FORBIDDEN_KEYWORDS:
        keyword_pattern = (
            r"\b"
            + re.escape(forbidden_keyword).replace(r"\ ", r"\s+")
            + r"\b"
        )

        if re.search(keyword_pattern, normalized):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"The statement contains blocked SQL command: "
                    f"{forbidden_keyword}."
                ),
            )

    if re.search(r"\bINTO\s+(OUTFILE|DUMPFILE)\b", normalized):
        raise HTTPException(
            status_code=400,
            detail="File-writing SQL commands are blocked.",
        )

    return sql


def apply_row_limit(sql: str, requested_limit: int) -> str:
    """
    Adds a LIMIT to SELECT and WITH queries when one is not already present.

    SHOW, DESCRIBE, and EXPLAIN are not modified.
    """

    sanitized = remove_comments_and_strings(sql)
    normalized = re.sub(r"\s+", " ", sanitized).strip().upper()

    if not normalized.startswith(("SELECT", "WITH")):
        return sql

    if re.search(r"\bLIMIT\s+\d+", normalized):
        return sql

    return f"{sql}\nLIMIT {requested_limit}"


def serialize_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, (datetime, date, datetime_time)):
        return value.isoformat()

    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()

    return value


def record_history(
    sql_text: str,
    success: bool,
    row_count: int,
    execution_ms: float,
    error_message: str | None,
) -> None:
    with sqlite3.connect(SQLITE_PATH) as connection:
        connection.execute(
            """
            INSERT INTO query_history (
                sql_text,
                success,
                row_count,
                execution_ms,
                error_message,
                executed_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                sql_text,
                1 if success else 0,
                row_count,
                execution_ms,
                error_message,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )

        connection.commit()


def execute_mysql_query(
    validated_sql: str,
    row_limit: int,
) -> dict[str, Any]:
    limited_sql = apply_row_limit(validated_sql, row_limit)
    started_at = time.perf_counter()

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**get_mysql_config())

        cursor = connection.cursor(dictionary=True)

        # Application-level read-only protection in addition to the
        # database user's read-only permissions.
        try:
            cursor.execute(
                "SET SESSION TRANSACTION READ ONLY"
            )
        except mysql.connector.Error:
            # Some MySQL-compatible servers or account configurations may
            # not allow this command. The query validator and read-only
            # database account remain in effect.
            pass

        try:
            cursor.execute(
                f"SET SESSION MAX_EXECUTION_TIME = "
                f"{SQL_TIMEOUT_SECONDS * 1000}"
            )
        except mysql.connector.Error:
            pass

        cursor.execute(limited_sql)
        raw_rows = cursor.fetchall()

        columns = list(cursor.column_names or [])

        rows = [
            {
                column: serialize_value(row.get(column))
                for column in columns
            }
            for row in raw_rows
        ]

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

    except mysql.connector.Error as database_error:
        execution_ms = round(
            (time.perf_counter() - started_at) * 1000,
            2,
        )

        error_message = str(database_error)

        record_history(
            sql_text=validated_sql,
            success=False,
            row_count=0,
            execution_ms=execution_ms,
            error_message=error_message,
        )

        raise HTTPException(
            status_code=400,
            detail=f"MySQL error: {error_message}",
        ) from database_error

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()


@router.get("/connection")
def test_sql_connection() -> dict[str, Any]:
    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**get_mysql_config())
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                DATABASE() AS database_name,
                CURRENT_USER() AS connected_user,
                @@hostname AS server_name,
                VERSION() AS server_version
            """
        )

        details = cursor.fetchone() or {}

        return {
            "connected": True,
            "database": details.get("database_name"),
            "user": details.get("connected_user"),
            "server": details.get("server_name"),
            "version": details.get("server_version"),
            "default_limit": DEFAULT_LIMIT,
            "maximum_limit": MAX_LIMIT,
        }

    except mysql.connector.Error as database_error:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to connect to MySQL: {database_error}",
        ) from database_error

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()


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
def execute_sql(request: ExecuteSqlRequest) -> dict[str, Any]:
    validated_sql = normalize_and_validate_sql(request.sql)

    return execute_mysql_query(
        validated_sql=validated_sql,
        row_limit=request.row_limit,
    )


@router.post("/export")
def export_sql_results(request: ExecuteSqlRequest) -> StreamingResponse:
    validated_sql = normalize_and_validate_sql(request.sql)

    result = execute_mysql_query(
        validated_sql=validated_sql,
        row_limit=request.row_limit,
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
    search: str = Query(default="", max_length=200),
    category: str = Query(default="", max_length=100),
) -> dict[str, Any]:
    conditions: list[str] = []
    parameters: list[Any] = []

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

    with sqlite3.connect(SQLITE_PATH) as connection:
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
) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")

    with sqlite3.connect(SQLITE_PATH) as connection:
        cursor = connection.execute(
            """
            INSERT INTO saved_queries (
                title,
                category,
                description,
                sql_text,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                request.title.strip(),
                request.category.strip() or "General",
                request.description.strip(),
                request.sql.strip(),
                now,
                now,
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
) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")

    with sqlite3.connect(SQLITE_PATH) as connection:
        cursor = connection.execute(
            """
            UPDATE saved_queries
            SET
                title = ?,
                category = ?,
                description = ?,
                sql_text = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                request.title.strip(),
                request.category.strip() or "General",
                request.description.strip(),
                request.sql.strip(),
                now,
                saved_query_id,
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
def delete_saved_query(saved_query_id: int) -> dict[str, Any]:
    with sqlite3.connect(SQLITE_PATH) as connection:
        cursor = connection.execute(
            "DELETE FROM saved_queries WHERE id = ?",
            (saved_query_id,),
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
    with sqlite3.connect(SQLITE_PATH) as connection:
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
    limit: int = Query(default=50, ge=1, le=250),
) -> dict[str, Any]:
    with sqlite3.connect(SQLITE_PATH) as connection:
        connection.row_factory = sqlite3.Row

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
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
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
def clear_query_history() -> dict[str, Any]:
    with sqlite3.connect(SQLITE_PATH) as connection:
        connection.execute("DELETE FROM query_history")
        connection.commit()

    return {
        "success": True,
        "message": "Query history cleared.",
    }