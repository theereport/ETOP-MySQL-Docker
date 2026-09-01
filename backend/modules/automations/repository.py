from __future__ import annotations

import json
from calendar import monthrange
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, text

from data.mysql import (
    automation_executions_table,
    automations_table,
    get_engine,
    metadata,
    reports_table,
)
from .schemas import (
    AutomationDefinition,
    AutomationExecution,
)


def initialize_automations_database() -> None:
    """Startup hook: creates the automations/automation_executions tables."""

    metadata.create_all(get_engine(), checkfirst=True)
from .validation import (
    AutomationValidationError,
    AutomationValidationIssue,
    health_for_automation,
    load_timezone,
    normalize_timezone_name,
    parse_schedule_time,
    validate_automation,
    validate_for_activation,
)


class AutomationStateConflict(RuntimeError):
    """Raised when durable execution state makes a mutation unsafe."""


def _saved_report_exists(connection, report_id: str) -> bool:
    return connection.execute(
        select(reports_table.c.id).where(reports_table.c.id == report_id).limit(1)
    ).first() is not None


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def calculate_next_run(
    automation: AutomationDefinition,
    *,
    after: datetime | None = None,
) -> str | None:
    schedule = automation.schedule

    if (
        automation.status != "active"
        or schedule.frequency == "manual"
    ):
        return None

    timezone = load_timezone(schedule.timezone)
    current = after or datetime.now(timezone)

    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone)
    else:
        current = current.astimezone(timezone)

    hour, minute = parse_schedule_time(schedule.time)

    if schedule.frequency == "daily":
        candidate = current.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

        if candidate <= current:
            candidate += timedelta(days=1)

        return candidate.isoformat()

    if schedule.frequency == "weekly":
        selected_days = sorted(
            {
                day
                for day in schedule.days_of_week
                if 0 <= day <= 6
            }
        )

        if not selected_days:
            selected_days = [0]

        for offset in range(0, 8):
            candidate_day = current + timedelta(days=offset)
            schedule_day = (candidate_day.weekday() + 1) % 7

            if schedule_day not in selected_days:
                continue

            candidate = candidate_day.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )

            if candidate > current:
                return candidate.isoformat()

        return None

    if schedule.frequency == "monthly":
        requested_day = schedule.day_of_month or 1

        for month_offset in range(0, 14):
            year = current.year + (
                current.month - 1 + month_offset
            ) // 12
            month = (
                current.month - 1 + month_offset
            ) % 12 + 1

            last_day = monthrange(year, month)[1]
            day = min(max(requested_day, 1), last_day)

            candidate = datetime(
                year,
                month,
                day,
                hour,
                minute,
                tzinfo=timezone,
            )

            if candidate > current:
                return candidate.isoformat()

        return None

    if schedule.frequency == "custom":
        raise ValueError(
            "Custom cron schedules are not enabled yet. "
            "Use daily, weekly, or monthly."
        )

    return None


def validate_repository_bindings(
    automation: AutomationDefinition,
) -> None:
    if automation.source_type != "report":
        return

    with get_engine().connect() as connection:
        report_exists = _saved_report_exists(
            connection,
            automation.report_id,
        )

    if not report_exists:
        raise AutomationValidationError(
            [
                AutomationValidationIssue(
                    code="saved_report_missing",
                    field="reportId",
                    message=(
                        "The selected saved report no longer exists. Select "
                        "an available report before running this automation."
                    ),
                )
            ]
        )


def save_automation(
    automation: AutomationDefinition,
) -> AutomationDefinition:
    if automation.schedule.frequency != "manual":
        automation.schedule.timezone = normalize_timezone_name(
            automation.schedule.timezone
        )

    validate_for_activation(automation)

    now = _now_iso()

    automation.updated_at = now

    if not automation.created_at:
        automation.created_at = now

    automation.next_run_at = calculate_next_run(
        automation
    )

    payload = automation.model_dump(
        by_alias=True,
    )

    if automation.status == "active" and automation.source_type == "report":
        with get_engine().connect() as connection:
            if not _saved_report_exists(connection, automation.report_id):
                raise AutomationValidationError(
                    [
                        AutomationValidationIssue(
                            code="saved_report_missing",
                            field="reportId",
                            message=(
                                "The selected saved report no longer exists. "
                                "Select an available report before enabling "
                                "this automation."
                            ),
                        )
                    ]
                )

    values = {
        "id": automation.id,
        "name": automation.name,
        "status": automation.status,
        "source_type": automation.source_type,
        "frequency": automation.schedule.frequency,
        "timezone": automation.schedule.timezone,
        "next_run_at": automation.next_run_at,
        "last_run_at": automation.last_run_at,
        "last_run_status": automation.last_run_status,
        "definition_json": json.dumps(payload),
        "created_at": automation.created_at,
        "updated_at": automation.updated_at,
    }

    with get_engine().begin() as connection:
        running = connection.execute(
            select(automation_executions_table.c.id)
            .where(
                automation_executions_table.c.automation_id == automation.id,
                automation_executions_table.c.status == "running",
            )
            .limit(1)
            .with_for_update()
        ).first()

        if running is not None:
            raise AutomationStateConflict(
                "Automation cannot be changed while its execution is running."
            )

        existing = connection.execute(
            select(automations_table.c.id)
            .where(automations_table.c.id == automation.id)
            .with_for_update()
        ).first()

        if existing is None:
            connection.execute(automations_table.insert().values(**values))
        else:
            update_values = dict(values)
            update_values.pop("id")
            connection.execute(
                automations_table.update()
                .where(automations_table.c.id == automation.id)
                .values(**update_values)
            )

    return automation


def get_automation(
    automation_id: str,
) -> AutomationDefinition | None:
    with get_engine().connect() as connection:
        row = connection.execute(
            select(automations_table.c.definition_json).where(
                automations_table.c.id == automation_id
            )
        ).first()

    if row is None:
        return None

    return AutomationDefinition.model_validate_json(row.definition_json)


def list_automations() -> list[AutomationDefinition]:
    with get_engine().connect() as connection:
        rows = connection.execute(
            select(automations_table.c.definition_json).order_by(
                automations_table.c.updated_at.desc(),
                automations_table.c.name.asc(),
            )
        ).all()

    return [
        AutomationDefinition.model_validate_json(row.definition_json)
        for row in rows
    ]


def delete_automation(automation_id: str) -> bool:
    with get_engine().begin() as connection:
        running = connection.execute(
            select(automation_executions_table.c.id)
            .where(
                automation_executions_table.c.automation_id == automation_id,
                automation_executions_table.c.status == "running",
            )
            .limit(1)
            .with_for_update()
        ).first()

        if running is not None:
            raise AutomationStateConflict(
                "Automation cannot be deleted while its execution is running."
            )

        result = connection.execute(
            delete(automations_table).where(
                automations_table.c.id == automation_id
            )
        )

    return result.rowcount > 0


def list_due_automations(
    now: datetime | None = None,
) -> list[AutomationDefinition]:
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.astimezone()
    current_utc = current.astimezone(UTC)

    with get_engine().connect() as connection:
        rows = connection.execute(
            select(
                automations_table.c.next_run_at,
                automations_table.c.definition_json,
            )
            .where(
                automations_table.c.status == "active",
                automations_table.c.next_run_at.is_not(None),
            )
            .order_by(automations_table.c.next_run_at.asc())
        ).all()

    due: list[tuple[datetime, AutomationDefinition]] = []

    for row in rows:
        try:
            next_run = datetime.fromisoformat(row.next_run_at)
        except (TypeError, ValueError):
            continue

        if next_run.tzinfo is None:
            continue

        if next_run.astimezone(UTC) <= current_utc:
            due.append(
                (
                    next_run.astimezone(UTC),
                    AutomationDefinition.model_validate_json(
                        row.definition_json
                    ),
                )
            )

    due.sort(key=lambda item: item[0])
    return [automation for _, automation in due]


def update_after_run(
    automation: AutomationDefinition,
    *,
    status: str,
    completed_at: datetime,
) -> AutomationDefinition:
    with get_engine().begin() as connection:
        row = connection.execute(
            select(automations_table.c.definition_json)
            .where(automations_table.c.id == automation.id)
            .with_for_update()
        ).first()

        if row is None:
            return automation

        current = AutomationDefinition.model_validate_json(
            row.definition_json
        )
        current.last_run_at = completed_at.isoformat()
        current.last_run_status = status
        current.updated_at = completed_at.isoformat()

        if status == "failed":
            current.status = "error"

        current.next_run_at = calculate_next_run(
            current,
            after=completed_at,
        )

        payload = current.model_dump(
            by_alias=True,
        )

        connection.execute(
            automations_table.update()
            .where(automations_table.c.id == automation.id)
            .values(
                status=current.status,
                next_run_at=current.next_run_at,
                last_run_at=current.last_run_at,
                last_run_status=current.last_run_status,
                definition_json=json.dumps(payload),
                updated_at=current.updated_at,
            )
        )

    return current


def create_execution(
    execution: AutomationExecution,
) -> bool:
    with get_engine().begin() as connection:
        result = connection.execute(
            text(
                """
                INSERT INTO automation_executions (
                    id,
                    automation_id,
                    automation_name,
                    status,
                    started_at,
                    completed_at,
                    duration_ms,
                    row_count,
                    output_file_name,
                    output_file_path,
                    message,
                    error_details,
                    triggered_by
                )
                SELECT
                    :id, :automation_id, :automation_name, :status,
                    :started_at, :completed_at, :duration_ms, :row_count,
                    :output_file_name, :output_file_path, :message,
                    :error_details, :triggered_by
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM automation_executions
                    WHERE automation_id = :automation_id
                      AND status = 'running'
                )
                """
            ),
            {
                "id": execution.id,
                "automation_id": execution.automation_id,
                "automation_name": execution.automation_name,
                "status": execution.status,
                "started_at": execution.started_at,
                "completed_at": execution.completed_at,
                "duration_ms": execution.duration_ms,
                "row_count": execution.row_count,
                "output_file_name": execution.output_file_name,
                "output_file_path": execution.output_file_path,
                "message": execution.message,
                "error_details": execution.error_details,
                "triggered_by": execution.triggered_by,
            },
        )

    return result.rowcount > 0


def finish_execution(
    execution_id: str,
    *,
    status: str,
    completed_at: str,
    duration_ms: int,
    row_count: int | None,
    output_file_name: str,
    output_file_path: str,
    message: str,
    error_details: str,
) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            automation_executions_table.update()
            .where(automation_executions_table.c.id == execution_id)
            .values(
                status=status,
                completed_at=completed_at,
                duration_ms=duration_ms,
                row_count=row_count,
                output_file_name=output_file_name,
                output_file_path=output_file_path,
                message=message,
                error_details=error_details,
            )
        )


def list_executions(
    limit: int = 250,
) -> list[AutomationExecution]:
    with get_engine().connect() as connection:
        rows = connection.execute(
            select(automation_executions_table)
            .order_by(automation_executions_table.c.started_at.desc())
            .limit(limit)
        ).all()

    return [
        AutomationExecution(
            id=row.id,
            automationId=row.automation_id,
            automationName=row.automation_name,
            status=row.status,
            startedAt=row.started_at,
            completedAt=row.completed_at,
            durationMs=row.duration_ms,
            rowCount=row.row_count,
            outputFileName=row.output_file_name,
            outputFilePath=row.output_file_path,
            message=row.message,
            errorDetails=row.error_details,
            triggeredBy=row.triggered_by,
        )
        for row in rows
    ]


def clear_executions() -> int:
    with get_engine().begin() as connection:
        running_count = connection.execute(
            select(func.count())
            .select_from(automation_executions_table)
            .where(automation_executions_table.c.status == "running")
        ).scalar_one()

        if running_count > 0:
            raise AutomationStateConflict(
                "Execution history cannot be cleared while an automation "
                "is running."
            )

        result = connection.execute(delete(automation_executions_table))

    return result.rowcount


def _duration_since(started_at: str, completed_at: datetime) -> int | None:
    try:
        started = datetime.fromisoformat(started_at)
    except (TypeError, ValueError):
        return None

    if started.tzinfo is None:
        started = started.astimezone()

    completed = completed_at
    if completed.tzinfo is None:
        completed = completed.astimezone()

    return max(
        0,
        round(
            (
                completed.astimezone(UTC)
                - started.astimezone(UTC)
            ).total_seconds()
            * 1000
        ),
    )


def recover_interrupted_executions(
    recovered_at: datetime | None = None,
) -> list[str]:
    """Fail closed on durable runs left in progress by a backend stop.

    The interrupted run is never silently replayed because the external
    script or report may already have produced a partial side effect. The
    automation is quarantined until an operator reviews and reactivates it.
    """

    completed_at = recovered_at or datetime.now().astimezone()
    if completed_at.tzinfo is None:
        completed_at = completed_at.astimezone()
    completed_iso = completed_at.isoformat()

    with get_engine().begin() as connection:
        rows = connection.execute(
            select(
                automation_executions_table.c.id,
                automation_executions_table.c.automation_id,
                automation_executions_table.c.started_at,
            )
            .where(automation_executions_table.c.status == "running")
            .order_by(automation_executions_table.c.started_at.asc())
            .with_for_update()
        ).all()

        recovered_ids: list[str] = []

        for row in rows:
            execution_id = str(row.id)
            automation_id = str(row.automation_id)
            recovered_ids.append(execution_id)

            connection.execute(
                automation_executions_table.update()
                .where(
                    automation_executions_table.c.id == execution_id,
                    automation_executions_table.c.status == "running",
                )
                .values(
                    status="failed",
                    completed_at=completed_iso,
                    duration_ms=_duration_since(row.started_at, completed_at),
                    message="Automation execution was interrupted.",
                    error_details=(
                        "The backend stopped before this execution recorded "
                        "completion. Automatic replay is blocked to prevent "
                        "duplicate effects; review the prior run and "
                        "explicitly retry or reactivate the automation."
                    ),
                )
            )

            definition_row = connection.execute(
                select(automations_table.c.definition_json).where(
                    automations_table.c.id == automation_id
                )
            ).first()

            if definition_row is None:
                continue

            automation = AutomationDefinition.model_validate_json(
                definition_row.definition_json
            )
            automation.status = "error"
            automation.last_run_at = completed_iso
            automation.last_run_status = "failed"
            automation.next_run_at = None
            automation.updated_at = completed_iso

            connection.execute(
                automations_table.update()
                .where(automations_table.c.id == automation_id)
                .values(
                    status="error",
                    next_run_at=None,
                    last_run_at=completed_iso,
                    last_run_status="failed",
                    definition_json=json.dumps(
                        automation.model_dump(by_alias=True)
                    ),
                    updated_at=completed_iso,
                )
            )

    return recovered_ids


def quarantine_automation(
    automation_id: str,
) -> bool:
    now = _now_iso()

    with get_engine().begin() as connection:
        row = connection.execute(
            select(automations_table.c.definition_json)
            .where(automations_table.c.id == automation_id)
            .with_for_update()
        ).first()

        if row is None:
            return False

        automation = AutomationDefinition.model_validate_json(
            row.definition_json
        )
        automation.status = "error"
        automation.next_run_at = None
        automation.updated_at = now

        connection.execute(
            automations_table.update()
            .where(automations_table.c.id == automation.id)
            .values(
                status="error",
                next_run_at=None,
                definition_json=json.dumps(
                    automation.model_dump(by_alias=True)
                ),
                updated_at=now,
            )
        )

    return True


def quarantine_invalid_active_automations() -> list[str]:
    """Stop invalid legacy schedules instead of silently skipping them."""

    now = _now_iso()

    with get_engine().begin() as connection:
        rows = connection.execute(
            select(
                automations_table.c.id,
                automations_table.c.next_run_at,
                automations_table.c.definition_json,
            )
            .where(automations_table.c.status == "active")
            .with_for_update()
        ).all()

        quarantined: list[str] = []

        for row in rows:
            automation = AutomationDefinition.model_validate_json(
                row.definition_json
            )
            issues = validate_automation(automation)

            if automation.source_type == "report":
                if not _saved_report_exists(
                    connection,
                    automation.report_id,
                ):
                    issues.append(
                        AutomationValidationIssue(
                            code="saved_report_missing",
                            field="reportId",
                            message=(
                                "The selected saved report no longer exists."
                            ),
                        )
                    )

            if automation.schedule.frequency != "manual":
                try:
                    next_run = datetime.fromisoformat(row.next_run_at)
                    if next_run.tzinfo is None:
                        raise ValueError
                except (TypeError, ValueError):
                    issues.append(
                        AutomationValidationIssue(
                            code="invalid_next_run",
                            field="nextRunAt",
                            message=(
                                "The saved next-run timestamp is missing or "
                                "invalid. Reactivate the automation to create "
                                "a new governed schedule."
                            ),
                        )
                    )

            if not issues:
                continue

            automation.status = "error"
            automation.next_run_at = None
            automation.updated_at = now
            quarantined.append(automation.id)

            connection.execute(
                automations_table.update()
                .where(automations_table.c.id == automation.id)
                .values(
                    status="error",
                    next_run_at=None,
                    definition_json=json.dumps(
                        automation.model_dump(by_alias=True)
                    ),
                    updated_at=now,
                )
            )

    return quarantined


def automation_service_health(
    *,
    scheduler_running: bool,
) -> dict[str, object]:
    automations = list_automations()

    with get_engine().connect() as connection:
        running_count = connection.execute(
            select(func.count())
            .select_from(automation_executions_table)
            .where(automation_executions_table.c.status == "running")
        ).scalar_one()

        failed_count = connection.execute(
            select(func.count())
            .select_from(automation_executions_table)
            .where(automation_executions_table.c.status == "failed")
        ).scalar_one()

    automation_health = [
        health_for_automation(automation)
        for automation in automations
    ]
    blocked_count = sum(
        item["state"] == "blocked"
        for item in automation_health
    )
    error_count = sum(
        automation.status == "error"
        for automation in automations
    )

    if not scheduler_running:
        status = "stopped"
    elif blocked_count or error_count:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "service": "automation",
        "serviceVersion": "1.0",
        "status": status,
        "schedulerRunning": scheduler_running,
        "counts": {
            "definitions": len(automations),
            "active": sum(
                automation.status == "active"
                for automation in automations
            ),
            "blocked": blocked_count,
            "error": error_count,
            "running": running_count,
            "failedExecutions": failed_count,
        },
        "automations": automation_health,
    }
