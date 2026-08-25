import json
import sqlite3

from datetime import datetime, timezone
from uuid import uuid4

from data.database import (
    get_connection,
    initialize_database,
)

from .schemas import (
    ReportCreate,
    ReportRecord,
    ReportUpdate,
)


def initialize_reports_database() -> None:
    """Startup migration hook for the shared SQLite initialization boundary."""

    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'General',
                sql_text TEXT NOT NULL,
                database_name TEXT NOT NULL DEFAULT 'ERP',
                output_format TEXT NOT NULL DEFAULT 'xlsx',
                parameters_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reports_name
            ON reports(name);
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reports_updated_at
            ON reports(updated_at);
            """
        )

        connection.commit()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_parameters(
    parameters: list,
) -> str:
    return json.dumps(
        [
            parameter.model_dump()
            for parameter in parameters
        ],
        ensure_ascii=False,
    )


def _deserialize_parameters(
    parameters_json: str | None,
) -> list:
    if not parameters_json:
        return []

    try:
        parsed = json.loads(
            parameters_json,
        )

        return parsed if isinstance(parsed, list) else []

    except json.JSONDecodeError:
        return []


def _row_to_report(
    row: sqlite3.Row,
) -> ReportRecord:
    return ReportRecord(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        category=row["category"],
        sql=row["sql_text"],
        database=row["database_name"],
        outputFormat=row["output_format"],
        parameters=_deserialize_parameters(
            row["parameters_json"],
        ),
        createdAt=row["created_at"],
        updatedAt=row["updated_at"],
    )


def list_reports() -> list[ReportRecord]:
    initialize_database()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                name,
                description,
                category,
                sql_text,
                database_name,
                output_format,
                parameters_json,
                created_at,
                updated_at
            FROM reports
            ORDER BY
                updated_at DESC,
                name ASC;
            """
        ).fetchall()

    return [
        _row_to_report(row)
        for row in rows
    ]


def get_report(
    report_id: str,
) -> ReportRecord | None:
    initialize_database()

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                id,
                name,
                description,
                category,
                sql_text,
                database_name,
                output_format,
                parameters_json,
                created_at,
                updated_at
            FROM reports
            WHERE id = ?;
            """,
            (report_id,),
        ).fetchone()

    if row is None:
        return None

    return _row_to_report(row)


def create_report(
    payload: ReportCreate,
) -> ReportRecord:
    initialize_database()

    now = _utc_now()
    report_id = payload.id or f"report-{uuid4().hex}"

    report = ReportRecord(
        id=report_id,
        name=payload.name.strip(),
        description=payload.description,
        category=payload.category,
        sql=payload.sql.strip(),
        parameters=payload.parameters,
        database=payload.database,
        outputFormat=payload.outputFormat,
        createdAt=now,
        updatedAt=now,
    )

    try:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO reports (
                    id,
                    name,
                    description,
                    category,
                    sql_text,
                    database_name,
                    output_format,
                    parameters_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    report.id,
                    report.name,
                    report.description,
                    report.category,
                    report.sql,
                    report.database,
                    report.outputFormat,
                    _serialize_parameters(
                        report.parameters,
                    ),
                    report.createdAt.isoformat(),
                    report.updatedAt.isoformat(),
                ),
            )

            connection.commit()

    except sqlite3.IntegrityError as exc:
        raise ValueError(
            f"A report with ID '{report_id}' already exists."
        ) from exc

    return report


def update_report(
    report_id: str,
    payload: ReportUpdate,
) -> ReportRecord | None:
    initialize_database()

    existing_report = get_report(
        report_id,
    )

    if existing_report is None:
        return None

    updates = payload.model_dump(
        exclude_unset=True,
    )

    updated_data = existing_report.model_dump()

    updated_data.update(
        updates,
    )

    updated_data["id"] = existing_report.id
    updated_data["createdAt"] = existing_report.createdAt
    updated_data["updatedAt"] = _utc_now()

    updated_report = ReportRecord.model_validate(
        updated_data,
    )

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE reports
            SET
                name = ?,
                description = ?,
                category = ?,
                sql_text = ?,
                database_name = ?,
                output_format = ?,
                parameters_json = ?,
                updated_at = ?
            WHERE id = ?;
            """,
            (
                updated_report.name.strip(),
                updated_report.description,
                updated_report.category,
                updated_report.sql.strip(),
                updated_report.database,
                updated_report.outputFormat,
                _serialize_parameters(
                    updated_report.parameters,
                ),
                updated_report.updatedAt.isoformat(),
                report_id,
            ),
        )

        connection.commit()

    return get_report(
        report_id,
    )


def delete_report(
    report_id: str,
) -> bool:
    initialize_database()

    with get_connection() as connection:
        cursor = connection.execute(
            """
            DELETE FROM reports
            WHERE id = ?;
            """,
            (report_id,),
        )

        connection.commit()

        return cursor.rowcount > 0