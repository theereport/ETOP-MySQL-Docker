from __future__ import annotations

import unittest

from modules.document_intelligence.lockbox_review.queue_export import (
    _safe_file_part,
)
from modules.document_intelligence.lockbox_service import (
    LOCKBOX_RESULT_DIR,
    result_path,
)


class SafeFilePartTests(unittest.TestCase):
    """_safe_file_part is the one sanitizer this codebase already trusts
    for turning a job_id into a filesystem path segment (queue_export.py).
    result_path/create_lockbox_export/create_reviewed_export all build a
    path directly from a raw job_id - a URL path parameter with no format
    constraint in router.py - so they must all use it too."""

    def test_strips_path_traversal_sequences(self) -> None:
        self.assertNotIn("..", _safe_file_part("../../etc/passwd", "x"))
        self.assertNotIn("/", _safe_file_part("../../etc/passwd", "x"))

    def test_strips_absolute_path_markers(self) -> None:
        cleaned = _safe_file_part("/etc/passwd", "x")
        self.assertFalse(cleaned.startswith("/"))

    def test_legitimate_uuid_job_id_is_unchanged(self) -> None:
        job_id = "550e8400-e29b-41d4-a716-446655440000"
        self.assertEqual(_safe_file_part(job_id, "x"), job_id)

    def test_empty_or_fully_stripped_value_falls_back(self) -> None:
        self.assertEqual(_safe_file_part("../..", "fallback"), "fallback")
        self.assertEqual(_safe_file_part("", "fallback"), "fallback")


class ResultPathTraversalTests(unittest.TestCase):
    """result_path() (lockbox_service.py) is the simplest of the three
    fixed call sites to test directly - pure, no DB/network dependency."""

    def test_malicious_job_id_cannot_escape_result_dir(self) -> None:
        malicious = "../../../../etc/passwd"
        path = result_path(malicious)

        self.assertEqual(path.parent, LOCKBOX_RESULT_DIR)
        self.assertTrue(
            path.resolve().is_relative_to(LOCKBOX_RESULT_DIR.resolve())
        )

    def test_normal_uuid_job_id_still_resolves_as_before(self) -> None:
        job_id = "550e8400-e29b-41d4-a716-446655440000"
        path = result_path(job_id)

        self.assertEqual(path, LOCKBOX_RESULT_DIR / f"{job_id}.json")


if __name__ == "__main__":
    unittest.main()
