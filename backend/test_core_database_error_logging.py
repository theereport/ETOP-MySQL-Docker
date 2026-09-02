from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

import mysql.connector
from fastapi import HTTPException

os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("MYSQL_USER", "test")
os.environ.setdefault("MYSQL_PASSWORD", "test")
os.environ.setdefault("MYSQL_DATABASE", "test")

# A handful of other test files (e.g. test_ap_vendor_spend_intelligence.py)
# replace sys.modules["core"]/["core.database"] with a minimal fake module
# at import time and never restore it - fine for their own narrow needs,
# but if pytest collects one of those files first (alphabetically, several
# do), this file's own `import core.database` would silently get their
# fake stub instead of the real module. Force a real one regardless of
# collection order.
for _stale in ("core", "core.database"):
    if _stale in sys.modules and not hasattr(
        sys.modules[_stale], "__file__"
    ):
        del sys.modules[_stale]

from core.database import MaddenDatabase


class DatabaseErrorLoggingTests(unittest.TestCase):
    """A real driver failure was previously invisible server-side - only
    surfaced as an HTTP response, with nothing logged. Verifies the fix:
    the error is now also logged, without changing what the client sees
    (sql_workspace.py deliberately relies on that client-facing detail for
    its own query-debugging feature)."""

    def test_cursor_error_is_logged_and_still_raised_to_client(self) -> None:
        database = MaddenDatabase()
        simulated_error = mysql.connector.Error("Unknown column 'foo' in 'where clause'")

        with patch.object(
            database, "_create_connection", side_effect=simulated_error
        ):
            with self.assertLogs("core.database", level="ERROR") as logs:
                with self.assertRaises(HTTPException) as raised:
                    with database._cursor():
                        pass

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("Unknown column", str(raised.exception.detail))
        self.assertTrue(
            any("Madden database query failed" in message for message in logs.output)
        )

    def test_snapshot_error_is_logged_and_still_raised_to_client(self) -> None:
        database = MaddenDatabase()
        simulated_error = mysql.connector.Error("Connection refused")

        with patch.object(
            database, "_create_connection", side_effect=simulated_error
        ):
            with self.assertLogs("core.database", level="ERROR") as logs:
                with self.assertRaises(HTTPException) as raised:
                    with database.read_consistent_snapshot():
                        pass

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("Connection refused", str(raised.exception.detail))
        self.assertTrue(
            any(
                "consistent read-only snapshot failed" in message
                for message in logs.output
            )
        )


if __name__ == "__main__":
    unittest.main()
