from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.config import settings as platform_settings

from .schemas import AutomationDefinition, AutomationSchedule


BACKEND_DIR = Path(__file__).resolve().parents[2]

# Automation authors supply script_path/output_folder as free-text (only an
# "automation_center" module grant is required, not an admin-tier role -
# see access_policy.py), so both were previously accepted as any absolute
# path with no containment check: script_path let an automation execute any
# file the OS user could run, and output_folder let it write anywhere that
# user could write. Constrained to explicit allowlisted roots - a safe
# built-in default, plus an optional operator-configured extra root (a
# deliberate, documented opt-in rather than open-by-default).
_DEFAULT_SCRIPT_ROOT = BACKEND_DIR / "data" / "automation_scripts"
_EXTRA_SCRIPT_ROOT = os.getenv("ETOP_AUTOMATION_SCRIPTS_ROOT", "").strip()
ALLOWED_SCRIPT_ROOTS: tuple[Path, ...] = tuple(
    root.resolve()
    for root in (
        [_DEFAULT_SCRIPT_ROOT]
        + ([Path(_EXTRA_SCRIPT_ROOT)] if _EXTRA_SCRIPT_ROOT else [])
    )
)

# backend/data - the existing, already-documented "automation run outputs"
# default location - and the sibling repo-root data/ tree
# (core.config.PlatformSettings.data_root) are both already-established,
# already-writable runtime-data areas; the backend *source* tree
# (modules/, core/, main.py, ...) is deliberately excluded.
_DEFAULT_OUTPUT_ROOTS = (BACKEND_DIR / "data", platform_settings.data_root)
_EXTRA_OUTPUT_ROOT = os.getenv("ETOP_AUTOMATION_OUTPUT_ROOT", "").strip()
ALLOWED_OUTPUT_ROOTS: tuple[Path, ...] = tuple(
    root.resolve()
    for root in (
        list(_DEFAULT_OUTPUT_ROOTS)
        + ([Path(_EXTRA_OUTPUT_ROOT)] if _EXTRA_OUTPUT_ROOT else [])
    )
)


def is_within_allowed_roots(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(
        path == root or path.is_relative_to(root) for root in roots
    )

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
                elif not is_within_allowed_roots(path, ALLOWED_SCRIPT_ROOTS):
                    issues.append(
                        AutomationValidationIssue(
                            code="script_path_outside_allowed_root",
                            field="scriptPath",
                            message=(
                                "Script files must live under "
                                f"{_DEFAULT_SCRIPT_ROOT} (or an operator-"
                                "configured ETOP_AUTOMATION_SCRIPTS_ROOT)."
                            ),
                        )
                    )

    configured_output_folder = automation.delivery.output_folder.strip()
    if configured_output_folder:
        expanded = os.path.expandvars(
            os.path.expanduser(configured_output_folder)
        )
        output_path = Path(expanded)
        if not output_path.is_absolute():
            output_path = BACKEND_DIR / output_path
        output_path = output_path.resolve()

        if not is_within_allowed_roots(output_path, ALLOWED_OUTPUT_ROOTS):
            issues.append(
                AutomationValidationIssue(
                    code="output_folder_outside_allowed_root",
                    field="delivery.outputFolder",
                    message=(
                        "Output folder must live under "
                        f"{_DEFAULT_OUTPUT_ROOTS[0]} or "
                        f"{_DEFAULT_OUTPUT_ROOTS[1]} (or an operator-"
                        "configured ETOP_AUTOMATION_OUTPUT_ROOT)."
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
