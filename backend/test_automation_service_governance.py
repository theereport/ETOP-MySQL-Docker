from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_DATABASE_PATH: Path | None = None


def _get_connection() -> sqlite3.Connection:
    if _DATABASE_PATH is None:
        raise RuntimeError("Test database is not configured.")

    connection = sqlite3.connect(
        _DATABASE_PATH,
        timeout=5,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def _test_connection():
    """Guarantees the connection is closed - sqlite3.Connection's own
    context-manager protocol only commits/rolls back, it never closes,
    which otherwise locks the temp workbench.db open on Windows."""

    connection = _get_connection()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


from sqlalchemy import create_engine  # noqa: E402

from data.mysql import (  # noqa: E402
    _reset_engine_override,
    _set_engine_override,
)

from modules.automations.repository import (  # noqa: E402
    AutomationStateConflict,
    automation_service_health,
    calculate_next_run,
    clear_executions,
    create_execution,
    delete_automation,
    get_automation,
    list_due_automations,
    quarantine_invalid_active_automations,
    recover_interrupted_executions,
    save_automation,
    update_after_run,
)
from modules.automations.schemas import (  # noqa: E402
    AutomationDefinition,
    AutomationExecution,
)
import modules.automations.validation as automation_validation  # noqa: E402
from modules.automations.validation import (  # noqa: E402
    AutomationValidationError,
    normalize_timezone_name,
    validate_for_activation,
)


def _initialize_database(path: Path) -> None:
    # sqlite3.Connection's context-manager protocol only commits/rolls
    # back on exit, it never closes - without the explicit close() below,
    # this connection stays open for the rest of the process and Windows
    # refuses to delete the temp directory in tearDown (WinError 32).
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE automations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                source_type TEXT NOT NULL,
                frequency TEXT NOT NULL,
                timezone TEXT NOT NULL,
                next_run_at TEXT,
                last_run_at TEXT,
                last_run_status TEXT,
                definition_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE reports (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                sql_text TEXT NOT NULL
            );

            CREATE TABLE automation_executions (
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
        connection.commit()
    finally:
        connection.close()


def _automation(
    automation_id: str = "automation-1",
    *,
    status: str = "active",
    frequency: str = "daily",
    timezone: str = "America/New_York",
    source_type: str = "sql",
    script_path: str = "",
) -> AutomationDefinition:
    now = "2026-08-05T12:00:00-04:00"
    return AutomationDefinition(
        id=automation_id,
        name="Governed Automation",
        status=status,
        sourceType=source_type,
        sql="SELECT 1" if source_type == "sql" else "",
        scriptPath=script_path,
        schedule={
            "frequency": frequency,
            "time": "08:30",
            "daysOfWeek": [0, 2],
            "dayOfMonth": 15,
            "cronExpression": "",
            "timezone": timezone,
        },
        createdAt=now,
        updatedAt=now,
    )


def _execution(
    automation_id: str = "automation-1",
    execution_id: str = "execution-1",
) -> AutomationExecution:
    return AutomationExecution(
        id=execution_id,
        automationId=automation_id,
        automationName="Governed Automation",
        status="running",
        startedAt="2026-08-05T08:00:00-04:00",
        completedAt=None,
        durationMs=None,
        rowCount=None,
        outputFileName="",
        outputFilePath="",
        message="Automation execution started.",
        errorDetails="",
        triggeredBy="schedule",
    )


class AutomationGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        global _DATABASE_PATH
        self.temp_directory = tempfile.TemporaryDirectory()
        _DATABASE_PATH = Path(self.temp_directory.name) / "workbench.db"
        _initialize_database(_DATABASE_PATH)
        # automations, automation_executions, AND reports (now that the
        # reports module has also moved off SQLite) all go through
        # get_engine() from data.mysql - overriding it here redirects all
        # three at once to this temp SQLite file, so these tests never
        # touch the real MySQL etop schema.
        self._test_engine = create_engine(f"sqlite:///{_DATABASE_PATH}")
        _set_engine_override(self._test_engine)

    def tearDown(self) -> None:
        global _DATABASE_PATH
        _reset_engine_override()
        # Disposing releases the pooled sqlite3 connection's file handle -
        # without this, TemporaryDirectory.cleanup() below fails with
        # WinError 32 for the same reason _connection()/_test_connection()
        # have to explicitly .close() their sqlite3 connections.
        self._test_engine.dispose()
        _DATABASE_PATH = None
        self.temp_directory.cleanup()

    def test_timezone_alias_is_normalized_and_next_run_is_aware(self) -> None:
        automation = _automation(timezone="Eastern Standard Time")

        saved = save_automation(automation)

        self.assertEqual(saved.schedule.timezone, "America/New_York")
        self.assertIsNotNone(saved.next_run_at)
        next_run = datetime.fromisoformat(saved.next_run_at or "")
        self.assertIsNotNone(next_run.tzinfo)
        self.assertEqual(
            normalize_timezone_name("US/Eastern"),
            "America/New_York",
        )

    def test_schedule_validation_rejects_invalid_week_and_custom(self) -> None:
        invalid_week = _automation(frequency="weekly")
        invalid_week.schedule.days_of_week = [7]

        with self.assertRaisesRegex(
            AutomationValidationError,
            r"0 \(Sunday\) through 6 \(Saturday\)",
        ):
            validate_for_activation(invalid_week)

        custom = _automation(frequency="custom")
        with self.assertRaisesRegex(
            AutomationValidationError,
            "Custom cron schedules are not enabled",
        ):
            save_automation(custom)

    def test_active_script_must_be_an_existing_file(self) -> None:
        directory = Path(self.temp_directory.name) / "not-a-script.py"
        directory.mkdir()
        automation = _automation(
            source_type="python",
            script_path=str(directory),
        )

        with self.assertRaisesRegex(
            AutomationValidationError,
            "Script path is not a file",
        ):
            save_automation(automation)

        script = Path(self.temp_directory.name) / "valid.py"
        script.write_text(
            "print('ok')\n",
            encoding="utf-8",
        )
        automation.script_path = str(script)

        # Scripts must live under an allowlisted root (see validation.py) -
        # this test's temp directory stands in for an operator-configured
        # ETOP_AUTOMATION_SCRIPTS_ROOT for the scope of this one test.
        with unittest.mock.patch.object(
            automation_validation,
            "ALLOWED_SCRIPT_ROOTS",
            (Path(self.temp_directory.name).resolve(),),
        ):
            saved = save_automation(automation)
        self.assertEqual(saved.script_path, str(script))

    def test_active_script_outside_allowed_root_is_rejected(self) -> None:
        # No ETOP_AUTOMATION_SCRIPTS_ROOT override here - this proves the
        # built-in default allowlist actually excludes an arbitrary
        # location (this test's own temp directory), not just that some
        # allowlist exists.
        script = Path(self.temp_directory.name) / "valid.py"
        script.write_text("print('ok')\n", encoding="utf-8")
        automation = _automation(
            source_type="python",
            script_path=str(script),
        )

        with self.assertRaisesRegex(
            AutomationValidationError,
            "Script files must live under",
        ):
            save_automation(automation)

    def test_active_output_folder_outside_allowed_root_is_rejected(
        self,
    ) -> None:
        automation = _automation(source_type="sql")
        automation.delivery.output_folder = str(
            Path(self.temp_directory.name) / "drop"
        )

        with self.assertRaisesRegex(
            AutomationValidationError,
            "Output folder must live under",
        ):
            save_automation(automation)

    def test_active_output_folder_under_backend_data_is_allowed(
        self,
    ) -> None:
        # BACKEND_DIR here is this test file's own directory (backend/),
        # matching validation.py's _DEFAULT_OUTPUT_ROOTS[0] - the existing,
        # already-established "automation run outputs" default location.
        automation = _automation(source_type="sql")
        automation.delivery.output_folder = str(
            BACKEND_DIR / "data" / "automation_outputs" / "sub"
        )

        saved = save_automation(automation)
        self.assertTrue(saved.delivery.output_folder.endswith("sub"))

    def test_active_saved_report_must_still_exist(self) -> None:
        automation = _automation(source_type="sql")
        automation.source_type = "report"
        automation.sql = ""
        automation.report_id = "missing-report"

        with self.assertRaisesRegex(
            AutomationValidationError,
            "selected saved report no longer exists",
        ):
            save_automation(automation)

        with _test_connection() as connection:
            connection.execute(
                """
                INSERT INTO reports (id, name, sql_text)
                VALUES ('missing-report', 'Existing report', 'SELECT 1')
                """
            )
            connection.commit()

        saved = save_automation(automation)
        self.assertEqual(saved.report_id, "missing-report")

    def test_due_comparison_uses_instants_not_iso_text_order(self) -> None:
        saved = save_automation(_automation())
        saved.next_run_at = "2026-01-01T08:30:00-05:00"
        earlier = save_automation(_automation("automation-2"))
        earlier.next_run_at = "2026-01-01T14:15:00+01:00"

        with _test_connection() as connection:
            for item in (saved, earlier):
                connection.execute(
                    """
                    UPDATE automations
                    SET next_run_at = ?, definition_json = ?
                    WHERE id = ?
                    """,
                    (
                        item.next_run_at,
                        json.dumps(item.model_dump(by_alias=True)),
                        item.id,
                    ),
                )
            connection.commit()

        due = list_due_automations(
            datetime.fromisoformat("2026-01-01T13:30:01+00:00")
        )
        self.assertEqual(
            [item.id for item in due],
            [earlier.id, saved.id],
        )

        not_due = list_due_automations(
            datetime.fromisoformat("2026-01-01T13:29:59+00:00")
        )
        self.assertEqual(
            [item.id for item in not_due],
            [earlier.id],
        )

    def test_durable_claim_prevents_duplicate_running_execution(self) -> None:
        save_automation(_automation())

        self.assertTrue(create_execution(_execution()))
        self.assertFalse(
            create_execution(_execution(execution_id="execution-2"))
        )

        with self.assertRaisesRegex(
            AutomationStateConflict,
            "cannot be changed",
        ):
            save_automation(_automation())

        with self.assertRaisesRegex(
            AutomationStateConflict,
            "cannot be deleted",
        ):
            delete_automation("automation-1")

        with self.assertRaisesRegex(
            AutomationStateConflict,
            "cannot be cleared",
        ):
            clear_executions()

    def test_restart_recovery_quarantines_without_replay(self) -> None:
        automation = save_automation(_automation())
        self.assertTrue(create_execution(_execution()))

        recovered = recover_interrupted_executions(
            datetime.fromisoformat("2026-08-05T08:05:00-04:00")
        )

        self.assertEqual(recovered, ["execution-1"])
        persisted = get_automation(automation.id)
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status, "error")
        self.assertEqual(persisted.last_run_status, "failed")
        self.assertIsNone(persisted.next_run_at)

        with _test_connection() as connection:
            row = connection.execute(
                """
                SELECT status, error_details
                FROM automation_executions
                WHERE id = 'execution-1'
                """
            ).fetchone()

        self.assertEqual(row["status"], "failed")
        self.assertIn("Automatic replay is blocked", row["error_details"])
        self.assertEqual(list_due_automations(), [])

    def test_run_completion_preserves_operator_pause(self) -> None:
        stale_running_definition = save_automation(_automation())
        paused = stale_running_definition.model_copy(deep=True)
        paused.status = "paused"
        paused.next_run_at = None

        with _test_connection() as connection:
            connection.execute(
                """
                UPDATE automations
                SET status = 'paused', next_run_at = NULL,
                    definition_json = ?
                WHERE id = ?
                """,
                (
                    json.dumps(paused.model_dump(by_alias=True)),
                    paused.id,
                ),
            )
            connection.commit()

        updated = update_after_run(
            stale_running_definition,
            status="success",
            completed_at=datetime.fromisoformat(
                "2026-08-05T08:35:00-04:00"
            ),
        )

        self.assertEqual(updated.status, "paused")
        self.assertIsNone(updated.next_run_at)
        self.assertEqual(updated.last_run_status, "success")

    def test_runtime_failure_stops_future_schedule(self) -> None:
        automation = save_automation(_automation())

        updated = update_after_run(
            automation,
            status="failed",
            completed_at=datetime.fromisoformat(
                "2026-08-05T08:35:00-04:00"
            ),
        )

        self.assertEqual(updated.status, "error")
        self.assertIsNone(updated.next_run_at)
        self.assertEqual(updated.last_run_status, "failed")

        health = automation_service_health(scheduler_running=True)
        self.assertEqual(health["status"], "degraded")
        self.assertEqual(health["counts"]["error"], 1)
        self.assertEqual(
            health["automations"][0]["state"],
            "blocked",
        )

    def test_invalid_legacy_active_definition_is_quarantined(self) -> None:
        legacy = _automation(
            source_type="python",
            script_path=str(Path(self.temp_directory.name) / "missing.py"),
        )
        legacy.next_run_at = "2026-08-06T08:30:00-04:00"

        with _test_connection() as connection:
            connection.execute(
                """
                INSERT INTO automations (
                    id, name, status, source_type, frequency, timezone,
                    next_run_at, last_run_at, last_run_status,
                    definition_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    legacy.id,
                    legacy.name,
                    legacy.status,
                    legacy.source_type,
                    legacy.schedule.frequency,
                    legacy.schedule.timezone,
                    legacy.next_run_at,
                    legacy.last_run_at,
                    legacy.last_run_status,
                    json.dumps(legacy.model_dump(by_alias=True)),
                    legacy.created_at,
                    legacy.updated_at,
                ),
            )
            connection.commit()

        self.assertEqual(
            quarantine_invalid_active_automations(),
            [legacy.id],
        )
        persisted = get_automation(legacy.id)
        self.assertEqual(persisted.status, "error")
        self.assertIsNone(persisted.next_run_at)

    def test_month_end_schedule_clamps_to_last_calendar_day(self) -> None:
        automation = _automation(frequency="monthly")
        automation.schedule.day_of_month = 31

        next_run = calculate_next_run(
            automation,
            after=datetime.fromisoformat("2026-02-01T12:00:00-05:00"),
        )

        self.assertEqual(
            datetime.fromisoformat(next_run or "").date().isoformat(),
            "2026-02-28",
        )

    def test_weekday_numbers_match_the_sunday_first_designer(self) -> None:
        automation = _automation(frequency="weekly")
        automation.schedule.days_of_week = [1]

        next_run = calculate_next_run(
            automation,
            after=datetime.fromisoformat("2026-08-09T12:00:00-04:00"),
        )

        self.assertEqual(
            datetime.fromisoformat(next_run or "").date().isoformat(),
            "2026-08-10",
        )


if __name__ == "__main__":
    unittest.main()
