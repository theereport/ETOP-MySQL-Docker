from __future__ import annotations

import logging
import threading
from datetime import datetime

from .repository import (
    list_due_automations,
    quarantine_automation,
    quarantine_invalid_active_automations,
    recover_interrupted_executions,
)
from .router import execute_and_record
from .validation import AutomationValidationError


logger = logging.getLogger(__name__)


class AutomationScheduler:
    def __init__(
        self,
        interval_seconds: int = 30,
    ) -> None:
        self.interval_seconds = (
            interval_seconds
        )
        self._stop_event = (
            threading.Event()
        )
        self._thread: (
            threading.Thread | None
        ) = None
        self._last_cycle_at: str | None = None
        self._last_error: str | None = None
        self._recovered_execution_count = 0
        self._quarantined_automation_count = 0

    @property
    def running(self) -> bool:
        return bool(
            self._thread
            and self._thread.is_alive()
        )

    def start(self) -> None:
        if self.running:
            return

        try:
            recovered = recover_interrupted_executions()
            quarantined = quarantine_invalid_active_automations()
            self._recovered_execution_count += len(recovered)
            self._quarantined_automation_count += len(quarantined)
            self._last_error = None

            if recovered:
                logger.warning(
                    "Recovered and quarantined %s interrupted automation "
                    "execution(s).",
                    len(recovered),
                )

            if quarantined:
                logger.warning(
                    "Quarantined %s invalid active automation(s).",
                    len(quarantined),
                )
        except Exception as exc:
            self._last_error = (
                "Automation scheduler recovery failed: "
                f"{type(exc).__name__}: {exc}"
            )
            logger.exception(self._last_error)

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="etop-automation-scheduler",
            daemon=True,
        )
        self._thread.start()

        logger.info(
            "Automation scheduler started."
        )

    def stop(self) -> None:
        self._stop_event.set()

        if self._thread:
            self._thread.join(
                timeout=5
            )

        logger.info(
            "Automation scheduler stopped."
        )

    def diagnostics(self) -> dict[str, object]:
        return {
            "running": self.running,
            "intervalSeconds": self.interval_seconds,
            "lastCycleAt": self._last_cycle_at,
            "lastError": self._last_error,
            "recoveredExecutions": self._recovered_execution_count,
            "quarantinedAutomations": self._quarantined_automation_count,
        }

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            cycle_had_error = False
            try:
                self._last_cycle_at = (
                    datetime.now().astimezone().isoformat()
                )
                due_automations = (
                    list_due_automations()
                )

                for automation in due_automations:
                    if self._stop_event.is_set():
                        break

                    try:
                        execute_and_record(
                            automation,
                            "schedule",
                        )
                    except AutomationValidationError as exc:
                        cycle_had_error = True
                        quarantine_automation(automation.id)
                        self._last_error = (
                            "Scheduled automation was quarantined: "
                            f"{automation.name}: {exc}"
                        )
                        logger.exception(
                            "Scheduled automation was quarantined: %s",
                            automation.name,
                        )
                    except Exception as exc:
                        cycle_had_error = True
                        self._last_error = (
                            "Scheduled automation failed: "
                            f"{automation.name}: {type(exc).__name__}: {exc}"
                        )
                        logger.exception(
                            "Scheduled automation failed: %s",
                            automation.name,
                        )

            except Exception as exc:
                cycle_had_error = True
                self._last_error = (
                    "Automation scheduler cycle failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                logger.exception(
                    "Automation scheduler cycle failed."
                )

            if not cycle_had_error:
                self._last_error = None

            self._stop_event.wait(
                self.interval_seconds
            )


automation_scheduler = AutomationScheduler()
