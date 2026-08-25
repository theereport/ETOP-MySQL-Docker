from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .schemas import AutomationDefinition, AutomationSchedule


BACKEND_DIR = Path(__file__).resolve().parents[2]

_TIME_PATTERN = re.compile(r"^(?P<hour>\d{2}):(?P<minute>\d{2})$")

# Browsers normally provide an IANA name. These aliases cover common values
# entered by Windows operators without turning a fixed EST/CST offset into a
# schedule that is wrong for half of the year.
_TIMEZONE_ALIASES = {
    "utc": "UTC",
    "etc/utc": "UTC",
    "z": "UTC",
    "eastern": "America/New_York",
    "eastern time": "America/New_York",
    "eastern standard time": "America/New_York",
    "est": "America/New_York",
    "us/eastern": "America/New_York",
    "central": "America/Chicago",
    "central time": "America/Chicago",
    "central standard time": "America/Chicago",
    "cst": "America/Chicago",
    "us/central": "America/Chicago",
    "mountain": "America/Denver",
    "mountain time": "America/Denver",
    "mountain standard time": "America/Denver",
    "mst": "America/Denver",
    "us/mountain": "America/Denver",
    "pacific": "America/Los_Angeles",
    "pacific time": "America/Los_Angeles",
    "pacific standard time": "America/Los_Angeles",
    "pst": "America/Los_Angeles",
    "us/pacific": "America/Los_Angeles",
    "alaskan standard time": "America/Anchorage",
    "hawaiian standard time": "Pacific/Honolulu",
}


@dataclass(frozen=True)
class AutomationValidationIssue:
    code: str
    field: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "field": self.field,
            "message": self.message,
        }


class AutomationValidationError(ValueError):
    def __init__(
        self,
        issues: list[AutomationValidationIssue],
    ) -> None:
        self.issues = tuple(issues)
        super().__init__(" ".join(issue.message for issue in issues))


def parse_schedule_time(value: str) -> tuple[int, int]:
    match = _TIME_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ValueError("Schedule time must use HH:MM format.")

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))

    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(
            "Schedule time must use a valid 24-hour time."
        )

    return hour, minute


def normalize_timezone_name(value: str) -> str:
    supplied = value.strip()
    if not supplied:
        raise ValueError("Enter a timezone for the schedule.")

    normalized = _TIMEZONE_ALIASES.get(supplied.casefold(), supplied)

    try:
        timezone = ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f'Unknown timezone "{supplied}". Use an IANA timezone such as '
            '"America/New_York".'
        ) from exc
    except (OSError, ValueError) as exc:
        raise ValueError(
            f'Timezone "{supplied}" could not be loaded.'
        ) from exc

    return timezone.key


def load_timezone(value: str) -> ZoneInfo:
    return ZoneInfo(normalize_timezone_name(value))


def resolve_script_path(script_path: str) -> Path:
    expanded = os.path.expandvars(
        os.path.expanduser(script_path.strip())
    )
    path = Path(expanded)

    if not path.is_absolute():
        path = BACKEND_DIR / path

    return path.resolve()


def _schedule_issues(
    schedule: AutomationSchedule,
) -> list[AutomationValidationIssue]:
    issues: list[AutomationValidationIssue] = []

    if schedule.frequency == "manual":
        return issues

    try:
        parse_schedule_time(schedule.time)
    except ValueError as exc:
        issues.append(
            AutomationValidationIssue(
                code="invalid_schedule_time",
                field="schedule.time",
                message=str(exc),
            )
        )

    try:
        normalize_timezone_name(schedule.timezone)
    except ValueError as exc:
        issues.append(
            AutomationValidationIssue(
                code="invalid_schedule_timezone",
                field="schedule.timezone",
                message=str(exc),
            )
        )

    if schedule.frequency == "weekly":
        if not schedule.days_of_week:
            issues.append(
                AutomationValidationIssue(
                    code="missing_schedule_days",
                    field="schedule.daysOfWeek",
                    message=(
                        "Select at least one weekday for a weekly schedule."
                    ),
                )
            )
        elif any(
            not isinstance(day, int) or not 0 <= day <= 6
            for day in schedule.days_of_week
        ):
            issues.append(
                AutomationValidationIssue(
                    code="invalid_schedule_day",
                    field="schedule.daysOfWeek",
                    message=(
                        "Weekly schedule days must be integers from 0 "
                        "(Sunday) through 6 (Saturday)."
                    ),
                )
            )

    if schedule.frequency == "monthly":
        requested_day = schedule.day_of_month
        if (
            requested_day is None
            or not isinstance(requested_day, int)
            or not 1 <= requested_day <= 31
        ):
            issues.append(
                AutomationValidationIssue(
                    code="invalid_month_day",
                    field="schedule.dayOfMonth",
                    message=(
                        "Monthly schedule day must be between 1 and 31."
                    ),
                )
            )

    if schedule.frequency == "custom":
        issues.append(
            AutomationValidationIssue(
                code="custom_schedule_unavailable",
                field="schedule.cronExpression",
                message=(
                    "Custom cron schedules are not enabled. Use daily, "
                    "weekly, monthly, or manual."
                ),
            )
        )

    return issues


def _source_issues(
    automation: AutomationDefinition,
) -> list[AutomationValidationIssue]:
    issues: list[AutomationValidationIssue] = []

    if automation.source_type == "sql" and not automation.sql.strip():
        issues.append(
            AutomationValidationIssue(
                code="missing_sql",
                field="sql",
                message="Enter SQL before enabling or running this automation.",
            )
        )

    if (
        automation.source_type == "report"
        and not automation.report_id.strip()
    ):
        issues.append(
            AutomationValidationIssue(
                code="missing_report",
                field="reportId",
                message=(
                    "Select a saved report before enabling or running this "
                    "automation."
                ),
            )
        )

    if automation.source_type in {"powershell", "python"}:
        if not automation.script_path.strip():
            issues.append(
                AutomationValidationIssue(
                    code="missing_script_path",
                    field="scriptPath",
                    message=(
                        "Enter a script file before enabling or running this "
                        "automation."
                    ),
                )
            )
        else:
            path = resolve_script_path(automation.script_path)
            if not path.exists():
                issues.append(
                    AutomationValidationIssue(
                        code="script_file_missing",
                        field="scriptPath",
                        message=f"Script file was not found: {path}",
                    )
                )
            elif not path.is_file():
                issues.append(
                    AutomationValidationIssue(
                        code="script_path_not_file",
                        field="scriptPath",
                        message=f"Script path is not a file: {path}",
                    )
                )
            else:
                allowed_suffixes = (
                    {".ps1"}
                    if automation.source_type == "powershell"
                    else {".py", ".pyw"}
                )
                if path.suffix.casefold() not in allowed_suffixes:
                    expected = (
                        ".ps1"
                        if automation.source_type == "powershell"
                        else ".py or .pyw"
                    )
                    issues.append(
                        AutomationValidationIssue(
                            code="script_type_mismatch",
                            field="scriptPath",
                            message=(
                                f"The selected {automation.source_type} "
                                f"automation requires a {expected} file."
                            ),
                        )
                    )

    if (
        automation.delivery.method == "email"
        and not automation.delivery.recipients
    ):
        issues.append(
            AutomationValidationIssue(
                code="missing_email_recipient",
                field="delivery.recipients",
                message=(
                    "Email delivery requires at least one recipient before "
                    "the automation can run."
                ),
            )
        )

    return issues


def validate_automation(
    automation: AutomationDefinition,
) -> list[AutomationValidationIssue]:
    issues: list[AutomationValidationIssue] = []

    if not automation.id.strip():
        issues.append(
            AutomationValidationIssue(
                code="missing_automation_id",
                field="id",
                message="Automation ID is required.",
            )
        )

    if not automation.name.strip():
        issues.append(
            AutomationValidationIssue(
                code="missing_automation_name",
                field="name",
                message="Automation name is required.",
            )
        )

    issues.extend(_schedule_issues(automation.schedule))
    issues.extend(_source_issues(automation))
    return issues


def validate_for_activation(
    automation: AutomationDefinition,
) -> None:
    if automation.status != "active":
        return

    issues = validate_automation(automation)
    if issues:
        raise AutomationValidationError(issues)


def validate_for_execution(
    automation: AutomationDefinition,
) -> None:
    issues = validate_automation(automation)
    if issues:
        raise AutomationValidationError(issues)


def health_for_automation(
    automation: AutomationDefinition,
) -> dict[str, object]:
    issues = validate_automation(automation)

    if automation.status == "error":
        issues = [
            AutomationValidationIssue(
                code="automation_quarantined",
                field="status",
                message=(
                    "Automation is stopped in error state. Review its latest "
                    "execution or validation issue, then explicitly reactivate it."
                ),
            ),
            *issues,
        ]

    if automation.status in {"draft", "paused"}:
        state = "disabled"
    elif issues:
        state = "blocked"
    elif automation.schedule.frequency == "manual":
        state = "ready"
    else:
        state = "scheduled"

    return {
        "automationId": automation.id,
        "state": state,
        "issues": [issue.as_dict() for issue in issues],
        "nextRunAt": automation.next_run_at,
        "lastRunAt": automation.last_run_at,
        "lastRunStatus": automation.last_run_status,
    }
