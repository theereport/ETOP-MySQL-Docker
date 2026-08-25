from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from modules.document_intelligence.lockbox_review import database


class CustomerNotesDatabaseTest(unittest.TestCase):
    def test_notes_are_customer_scoped_and_keep_origin_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "lockbox-review.db"
            missing_legacy = Path(directory) / "missing-legacy.db"
            with (
                patch.object(database, "DATABASE_PATH", target),
                patch.object(
                    database,
                    "LEGACY_DATABASE_PATH",
                    missing_legacy,
                ),
            ):
                first = database.append_customer_note(
                    "400001",
                    customer_name="Example Customer",
                    body="Requested remittance detail.",
                    author="Reviewer One",
                    source_job_id="job-1",
                    source_transaction_id="G-100",
                    source_check_number="00123",
                )
                second = database.append_customer_note(
                    "400001",
                    customer_name="Example Customer",
                    body="Customer replied by phone.",
                    author="Reviewer Two",
                    source_job_id="job-2",
                    source_transaction_id="G-200",
                    source_check_number="00456",
                )
                database.append_customer_note(
                    "500002",
                    customer_name="Different Customer",
                    body="Must not appear for 400001.",
                    author="Reviewer Three",
                    source_job_id="job-3",
                    source_transaction_id="G-300",
                    source_check_number="00789",
                )

                stored = database.get_customer_notes("400001")

            self.assertEqual(
                [note["note_id"] for note in stored],
                [first["note_id"], second["note_id"]],
            )
            self.assertEqual(stored[0]["body"], "Requested remittance detail.")
            self.assertEqual(stored[0]["author"], "Reviewer One")
            self.assertEqual(stored[0]["source_job_id"], "job-1")
            self.assertEqual(stored[0]["source_transaction_id"], "G-100")
            self.assertEqual(stored[0]["source_check_number"], "00123")
            self.assertTrue(stored[0]["created_at"].endswith("+00:00"))

    def test_customer_notes_reject_update_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "lockbox-review.db"
            missing_legacy = Path(directory) / "missing-legacy.db"
            with (
                patch.object(database, "DATABASE_PATH", target),
                patch.object(
                    database,
                    "LEGACY_DATABASE_PATH",
                    missing_legacy,
                ),
            ):
                saved = database.append_customer_note(
                    "400001",
                    customer_name="Example Customer",
                    body="Immutable note.",
                    author="Reviewer One",
                    source_job_id="job-1",
                    source_transaction_id="G-100",
                    source_check_number="00123",
                )

                with closing(sqlite3.connect(target)) as connection:
                    with self.assertRaisesRegex(
                        sqlite3.IntegrityError,
                        "append-only",
                    ):
                        connection.execute(
                            "UPDATE customer_notes SET body = ? WHERE note_id = ?",
                            ("Changed", saved["note_id"]),
                        )
                    connection.rollback()
                    with self.assertRaisesRegex(
                        sqlite3.IntegrityError,
                        "append-only",
                    ):
                        connection.execute(
                            "DELETE FROM customer_notes WHERE note_id = ?",
                            (saved["note_id"],),
                        )
                    connection.rollback()

                stored = database.get_customer_notes("400001")

            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0]["body"], "Immutable note.")


if __name__ == "__main__":
    unittest.main()
