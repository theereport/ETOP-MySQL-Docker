from __future__ import annotations

import unittest
from typing import Any

from modules.document_intelligence.lockbox_preparation.service import (
    DurableLockboxPreparationService,
)


class _FakeRepository:
    def __init__(
        self,
        *,
        result: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._result = result
        self._error = error

    def get_job_for_rule(
        self,
        source_job_id: str,
        source_file_hash: str,
        rule_version: str,
        *,
        service_version: str,
    ) -> dict[str, Any]:
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class _FakeCoordinator:
    def __init__(self, repository: _FakeRepository) -> None:
        self.repository = repository


def _service(repository: _FakeRepository) -> DurableLockboxPreparationService:
    return DurableLockboxPreparationService(
        coordinator=_FakeCoordinator(repository),
    )


GOLDEN_SNAPSHOT = {
    "state": "complete",
    "complete": True,
    "expected_count": 78,
    "terminal_count": 78,
    "balanced_count": 30,
    "exception_count": 48,
}


class ControlSnapshotMismatchFallsBackInsteadOfBlockingTests(unittest.TestCase):
    """The one Increment 3E/3F R1 control this checks for is a single
    historical reference document, not a general per-document mechanism.
    A record found under the same frozen rule/service identity but that
    doesn't match its exact 78/30/48 shape used to raise RuntimeError,
    permanently 409ing every status/resume/history call for that job.
    It must now be treated the same as no control being available at
    all - a graceful fall-back to the fresh-source review path."""

    def test_exact_golden_shape_is_still_returned(self) -> None:
        service = _service(_FakeRepository(result=dict(GOLDEN_SNAPSHOT)))
        result = service._control_snapshot_if_available("job-1", "hash-1")
        self.assertEqual(result, GOLDEN_SNAPSHOT)

    def test_genuinely_absent_control_returns_none(self) -> None:
        service = _service(
            _FakeRepository(error=KeyError("no matching job/rule identity"))
        )
        result = service._control_snapshot_if_available("job-2", "hash-2")
        self.assertIsNone(result)

    def test_present_but_mismatched_control_falls_back_instead_of_raising(
        self,
    ) -> None:
        mismatched = {**GOLDEN_SNAPSHOT, "balanced_count": 20, "exception_count": 58}
        service = _service(_FakeRepository(result=mismatched))
        with self.assertLogs(
            "modules.document_intelligence.lockbox_preparation.service",
            level="WARNING",
        ) as logs:
            result = service._control_snapshot_if_available("job-3", "hash-3")
        self.assertIsNone(result)
        self.assertTrue(
            any("job-3" in message for message in logs.output)
        )

    def test_incomplete_control_falls_back_instead_of_raising(self) -> None:
        incomplete = {**GOLDEN_SNAPSHOT, "state": "processing", "complete": False}
        service = _service(_FakeRepository(result=incomplete))
        result = service._control_snapshot_if_available("job-4", "hash-4")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
