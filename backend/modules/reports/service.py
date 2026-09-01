import json

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from data.mysql import get_engine, metadata, reports_table

from .schemas import (
    ReportCreate,
    ReportRecord,
    ReportUpdate,
)


def initialize_reports_database() -> None:
    """Startup hook: creates the reports table in MySQL."""

    metadata.create_all(get_engine(), checkfirst=True, tables=[reports_table])


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
    row,
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
    initialize_reports_database()

    with get_engine().connect() as connection:
        rows = connection.execute(
            reports_table.select().order_by(
                reports_table.c.updated_at.desc(),
                reports_table.c.name.asc(),
            )
        ).mappings().all()

    return [
        _row_to_report(row)
        for row in rows
    ]


def get_report(
    report_id: str,
) -> ReportRecord | None:
    initialize_reports_database()

    with get_engine().connect() as connection:
        row = connection.execute(
            reports_table.select().where(reports_table.c.id == report_id)
        ).mappings().first()

    if row is None:
        return None

    return _row_to_report(row)


def create_report(
    payload: ReportCreate,
) -> ReportRecord:
    initialize_reports_database()

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
        with get_engine().begin() as connection:
            connection.execute(
                reports_table.insert().values(
                    id=report.id,
                    name=report.name,
                    description=report.description,
                    category=report.category,
                    sql_text=report.sql,
                    database_name=report.database,
                    output_format=report.outputFormat,
                    parameters_json=_serialize_parameters(report.parameters),
                    created_at=report.createdAt.isoformat(),
                    updated_at=report.updatedAt.isoformat(),
                )
            )
    except IntegrityError as exc:
        raise ValueError(
            f"A report with ID '{report_id}' already exists."
        ) from exc

    return report


def update_report(
    report_id: str,
    payload: ReportUpdate,
) -> ReportRecord | None:
    initialize_reports_database()

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

    with get_engine().begin() as connection:
        connection.execute(
            reports_table.update()
            .where(reports_table.c.id == report_id)
            .values(
                name=updated_report.name.strip(),
                description=updated_report.description,
                category=updated_report.category,
                sql_text=updated_report.sql.strip(),
                database_name=updated_report.database,
                output_format=updated_report.outputFormat,
                parameters_json=_serialize_parameters(
                    updated_report.parameters,
                ),
                updated_at=updated_report.updatedAt.isoformat(),
            )
        )

    return get_report(
        report_id,
    )


def delete_report(
    report_id: str,
) -> bool:
    initialize_reports_database()

    with get_engine().begin() as connection:
        result = connection.execute(
            reports_table.delete().where(reports_table.c.id == report_id)
        )

        return result.rowcount > 0
