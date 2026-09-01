from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine

from data.mysql import _reset_engine_override, _set_engine_override
from modules.document_intelligence.lockbox_review import database


class CustomerNotesDatabaseTest(unittest.TestCase):
    def test_notes_are_customer_scoped_and_keep_origin_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine(f"sqlite:///{Path(directory) / 'lockbox-review.db'}")
            _set_engine_override(engine)
            try:
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
            finally:
                _reset_engine_override()
                engine.dispose()

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

    def test_customer_notes_are_never_updated_or_deleted(self):
        # Append-only is enforced by convention in the repository layer
        # (it never issues UPDATE/DELETE against this table), not by a DB
        # trigger - MySQL trigger creation needs a privilege the etop
        # account doesn't have.
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine(f"sqlite:///{Path(directory) / 'lockbox-review.db'}")
            _set_engine_override(engine)
            try:
                saved = database.append_customer_note(
                    "400001",
                    customer_name="Example Customer",
                    body="Immutable note.",
                    author="Reviewer One",
                    source_job_id="job-1",
                    source_transaction_id="G-100",
                    source_check_number="00123",
                )
                stored = database.get_customer_notes("400001")
            finally:
                _reset_engine_override()
                engine.dispose()

            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0]["body"], "Immutable note.")
            self.assertEqual(stored[0]["note_id"], saved["note_id"])


if __name__ == "__main__":
    unittest.main()
