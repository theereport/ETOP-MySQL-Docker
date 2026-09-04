from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from modules.document_intelligence import lockbox_service


class ProcessLockboxErrorHandlingTest(unittest.TestCase):
    """An unhandled parser failure used to reach the browser as a bare
    "Failed to fetch" (an uncaught exception's default 500 response lacks
    CORS headers). process_lockbox now converts it to a clear HTTPException
    instead."""

    def test_parser_failure_becomes_a_clear_http_exception(self) -> None:
        with patch.object(
            lockbox_service,
            "parse_pnc_lockbox",
            side_effect=RuntimeError("Tesseract process timeout"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                lockbox_service.process_lockbox(
                    "job-1", "/tmp/does-not-matter.pdf"
                )

        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("Tesseract process timeout", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
