from __future__ import annotations

import json
from calendar import monthrange
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from data.database import get_connection

from .schemas import (
    AutomationDefinition,
    AutomationExecution,
)


@contextmanager
def _connection():
    """Wraps get_connection() to guarantee the connection is closed.

    sqlite3.Connection's own context-manager protocol only commits or
    rolls back the open transaction on exit - it never closes the
    connection. Every `with _connection() as connection:` call in this
    module was leaking a file handle. On Windows this locks workbench.db
    open indefinitely (confirmed live: TemporaryDirectory.cleanup() in
    this module's own tests fails with WinError 32 because a prior
    connection was never released); on Linux the leak is silent until the
    process exhausts its file-descriptor limit."""

    connection = get_connection()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_automations_database() -> None:
    """Startup migration hook for the shared SQLite initialization boundary."""

    with _connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS automations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                source_type TEXT NOT NULL,
                frequency TEXT NOT NULL DEFAULT 'manual',
                timezone TEXT NOT NULL DEFAULT 'America/New_York',
                next_run_at TEXT,
                last_run_at TEXT,
                last_run_status TEXT,
                definition_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_automations_due
            ON automations(status, next_run_at);
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_automations_updated
            ON automations(updated_at DESC);
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS automation_executions (
                id TEXT PRIMARY KEY,
                automation_id TEXT NOT NULL,
                automation_name TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                duration_ms INTEGER,
                row_count INTEGER,
                output_file_name TEXT NOT NULL DEFAULT '',
                output_file_path TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                error_details TEXT NOT NULL DEFAULT '',
                triggered_by TEXT NOT NULL,
                FOREIGN KEY (automation_id)
                    REFERENCES automations(id)
                    ON DELETE CASCADE
            );
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_automation_executions_recent
            ON automation_executions(started_at DESC);
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_automation_executions_automation
            ON automation_executions(automation_id, started_at DESC);
            """
        )

        connection.commit()
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


def _saved_report_exists(connection: Any, report_id: str) -> bool:
    return connection.execute(
        """
        SELECT 1
        FROM reports
        WHERE id = ?
        LIMIT 1
        """,
        (report_id,),
    ).fetchone() is not None


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

    with _connection() as connection:
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

    with _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        running = connection.execute(
            """
            SELECT 1
            FROM automation_executions
            WHERE automation_id = ?
              AND status = 'running'
            LIMIT 1
            """,
            (automation.id,),
        ).fetchone()

        if running is not None:
            raise AutomationStateConflict(
                "Automation cannot be changed while its execution is running."
            )

        if (
            automation.status == "active"
            and automation.source_type == "report"
        ):
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

        connection.execute(
            """
            INSERT INTO automations (
                id,
                name,
                status,
                source_type,
                frequency,
                timezone,
                next_run_at,
                last_run_at,
                last_run_status,
                definition_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                status = excluded.status,
                source_type = excluded.source_type,
                frequency = excluded.frequency,
                timezone = excluded.timezone,
                next_run_at = excluded.next_run_at,
                last_run_at = excluded.last_run_at,
                last_run_status = excluded.last_run_status,
                definition_json = excluded.definition_json,
                updated_at = excluded.updated_at
            """,
            (
                automation.id,
                automation.name,
                automation.status,
                automation.source_type,
                automation.schedule.frequency,
                automation.schedule.timezone,
                automation.next_run_at,
                automation.last_run_at,
                automation.last_run_status,
                json.dumps(payload),
                automation.created_at,
                automation.updated_at,
            ),
        )
        connection.commit()

    return automation


def get_automation(
    automation_id: str,
) -> AutomationDefinition | None:
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT definition_json
            FROM automations
            WHERE id = ?
            """,
            (automation_id,),
        ).fetchone()

    if row is None:
        return None

    return AutomationDefinition.model_validate_json(
        row["definition_json"]
    )


def list_automations() -> list[AutomationDefinition]:
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT definition_json
            FROM automations
            ORDER BY updated_at DESC, name ASC
            """
        ).fetchall()

    return [
        AutomationDefinition.model_validate_json(
            row["definition_json"]
        )
        for row in rows
    ]


def delete_automation(automation_id: str) -> bool:
    with _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        running = connection.execute(
            """
            SELECT 1
            FROM automation_executions
            WHERE automation_id = ?
              AND status = 'running'
            LIMIT 1
            """,
            (automation_id,),
        ).fetchone()

        if running is not None:
            raise AutomationStateConflict(
                "Automation cannot be deleted while its execution is running."
            )

        cursor = connection.execute(
            """
            DELETE FROM automations
            WHERE id = ?
            """,
            (automation_id,),
        )
        connection.commit()

    return cursor.rowcount > 0


def list_due_automations(
    now: datetime | None = None,
) -> list[AutomationDefinition]:
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.astimezone()
    current_utc = current.astimezone(UTC)

    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT
                next_run_at,
                definition_json
            FROM automations
            WHERE status = 'active'
              AND next_run_at IS NOT NULL
            ORDER BY next_run_at ASC
            """
        ).fetchall()

    due: list[tuple[datetime, AutomationDefinition]] = []

    for row in rows:
        try:
            next_run = datetime.fromisoformat(row["next_run_at"])
        except (TypeError, ValueError):
            continue

        if next_run.tzinfo is None:
            continue

        if next_run.astimezone(UTC) <= current_utc:
            due.append(
                (
                    next_run.astimezone(UTC),
                    AutomationDefinition.model_validate_json(
                        row["definition_json"]
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
    with _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT definition_json
            FROM automations
            WHERE id = ?
            """,
            (automation.id,),
        ).fetchone()

        if row is None:
            return automation

        current = AutomationDefinition.model_validate_json(
            row["definition_json"]
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
            """
            UPDATE automations
            SET
                status = ?,
                next_run_at = ?,
                last_run_at = ?,
                last_run_status = ?,
                definition_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                current.status,
                current.next_run_at,
                current.last_run_at,
                current.last_run_status,
                json.dumps(payload),
                current.updated_at,
                current.id,
            ),
        )
        connection.commit()

    return current


def create_execution(
    execution: AutomationExecution,
) -> bool:
    with _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
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
            SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1
                FROM automation_executions
                WHERE automation_id = ?
                  AND status = 'running'
            )
            """,
            (
                execution.id,
                execution.automation_id,
                execution.automation_name,
                execution.status,
                execution.started_at,
                execution.completed_at,
                execution.duration_ms,
                execution.row_count,
                execution.output_file_name,
                execution.output_file_path,
                execution.message,
                execution.error_details,
                execution.triggered_by,
                execution.automation_id,
            ),
        )
        connection.commit()

    return cursor.rowcount > 0


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
    with _connection() as connection:
        connection.execute(
            """
            UPDATE automation_executions
            SET
                status = ?,
                completed_at = ?,
                duration_ms = ?,
                row_count = ?,
                output_file_name = ?,
                output_file_path = ?,
                message = ?,
                error_details = ?
            WHERE id = ?
            """,
            (
                status,
                completed_at,
                duration_ms,
                row_count,
                output_file_name,
                output_file_path,
                message,
                error_details,
                execution_id,
            ),
        )
        connection.commit()


def list_executions(
    limit: int = 250,
) -> list[AutomationExecution]:
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT
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
            FROM automation_executions
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        AutomationExecution(
            id=row["id"],
            automationId=row["automation_id"],
            automationName=row["automation_name"],
            status=row["status"],
            startedAt=row["started_at"],
            completedAt=row["completed_at"],
            durationMs=row["duration_ms"],
            rowCount=row["row_count"],
            outputFileName=row["output_file_name"],
            outputFilePath=row["output_file_path"],
            message=row["message"],
            errorDetails=row["error_details"],
            triggeredBy=row["triggered_by"],
        )
        for row in rows
    ]


def clear_executions() -> int:
    with _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        running = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM automation_executions
            WHERE status = 'running'
            """
        ).fetchone()

        if running is not None and int(running["count"]) > 0:
            raise AutomationStateConflict(
                "Execution history cannot be cleared while an automation "
                "is running."
            )

        cursor = connection.execute(
            "DELETE FROM automation_executions"
        )
        connection.commit()

    return cursor.rowcount


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

    with _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            """
            SELECT
                id,
                automation_id,
                started_at
            FROM automation_executions
            WHERE status = 'running'
            ORDER BY started_at ASC
            """
        ).fetchall()

        recovered_ids: list[str] = []

        for row in rows:
            execution_id = str(row["id"])
            automation_id = str(row["automation_id"])
            recovered_ids.append(execution_id)

            connection.execute(
                """
                UPDATE automation_executions
                SET
                    status = 'failed',
                    completed_at = ?,
                    duration_ms = ?,
                    message = ?,
                    error_details = ?
                WHERE id = ?
                  AND status = 'running'
                """,
                (
                    completed_iso,
                    _duration_since(row["started_at"], completed_at),
                    "Automation execution was interrupted.",
                    (
                        "The backend stopped before this execution recorded "
                        "completion. Automatic replay is blocked to prevent "
                        "duplicate effects; review the prior run and "
                        "explicitly retry or reactivate the automation."
                    ),
                    execution_id,
                ),
            )

            definition_row = connection.execute(
                """
                SELECT definition_json
                FROM automations
                WHERE id = ?
                """,
                (automation_id,),
            ).fetchone()

            if definition_row is None:
                continue

            automation = AutomationDefinition.model_validate_json(
                definition_row["definition_json"]
            )
            automation.status = "error"
            automation.last_run_at = completed_iso
            automation.last_run_status = "failed"
            automation.next_run_at = None
            automation.updated_at = completed_iso

            connection.execute(
                """
                UPDATE automations
                SET
                    status = 'error',
                    next_run_at = NULL,
                    last_run_at = ?,
                    last_run_status = 'failed',
                    definition_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    completed_iso,
                    json.dumps(automation.model_dump(by_alias=True)),
                    completed_iso,
                    automation_id,
                ),
            )

        connection.commit()

    return recovered_ids


def quarantine_automation(
    automation_id: str,
) -> bool:
    now = _now_iso()

    with _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT definition_json
            FROM automations
            WHERE id = ?
            """,
            (automation_id,),
        ).fetchone()

        if row is None:
            return False

        automation = AutomationDefinition.model_validate_json(
            row["definition_json"]
        )
        automation.status = "error"
        automation.next_run_at = None
        automation.updated_at = now

        connection.execute(
            """
            UPDATE automations
            SET
                status = 'error',
                next_run_at = NULL,
                definition_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                json.dumps(automation.model_dump(by_alias=True)),
                now,
                automation.id,
            ),
        )
        connection.commit()

    return True


def quarantine_invalid_active_automations() -> list[str]:
    """Stop invalid legacy schedules instead of silently skipping them."""

    now = _now_iso()

    with _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            """
            SELECT id, next_run_at, definition_json
            FROM automations
            WHERE status = 'active'
            """
        ).fetchall()

        quarantined: list[str] = []

        for row in rows:
            automation = AutomationDefinition.model_validate_json(
                row["definition_json"]
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
                    next_run = datetime.fromisoformat(row["next_run_at"])
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
                """
                UPDATE automations
                SET
                    status = 'error',
                    next_run_at = NULL,
                    definition_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    json.dumps(automation.model_dump(by_alias=True)),
                    now,
                    automation.id,
                ),
            )

        connection.commit()

    return quarantined


def automation_service_health(
    *,
    scheduler_running: bool,
) -> dict[str, object]:
    automations = list_automations()

    with _connection() as connection:
        running_row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM automation_executions
            WHERE status = 'running'
            """
        ).fetchone()

        failed_row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM automation_executions
            WHERE status = 'failed'
            """
        ).fetchone()

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
            "running": int(running_row["count"]) if running_row else 0,
            "failedExecutions": (
                int(failed_row["count"]) if failed_row else 0
            ),
        },
        "automations": automation_health,
    }
