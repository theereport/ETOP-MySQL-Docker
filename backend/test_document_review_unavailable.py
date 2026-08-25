from __future__ import annotations

import json
import importlib
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path

from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parent
MODULES_ROOT = BACKEND_ROOT / "modules"
DOCUMENT_INTELLIGENCE_ROOT = MODULES_ROOT / "document_intelligence"


def _namespace(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module


if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if "modules" not in sys.modules:
    _namespace("modules", MODULES_ROOT)
_namespace("modules.document_intelligence", DOCUMENT_INTELLIGENCE_ROOT)

review_store = importlib.import_module(
    "modules.document_intelligence.review_store"
)
DocumentReviewSaveRequest = importlib.import_module(
    "modules.document_intelligence.review_schemas"
).DocumentReviewSaveRequest


class DocumentReviewUnavailableTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_database_path = review_store.DATABASE_PATH
        review_store.DATABASE_PATH = (
            Path(self.temporary_directory.name) / "document-reviews.db"
        )

    def tearDown(self) -> None:
        review_store.DATABASE_PATH = self.original_database_path
        self.temporary_directory.cleanup()

    def test_unknown_or_conflicting_unavailable_field_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            DocumentReviewSaveRequest(
                expected_processing_run_id="run-1",
                unavailable_fields=["unknown_business_field"],
            )
        with self.assertRaises(ValidationError):
            DocumentReviewSaveRequest(
                expected_processing_run_id="run-1",
                corrected_fields={"invoice_number": "SYNTH-CORRECTED"},
                unavailable_fields=["invoice_number"],
            )
        with self.assertRaises(ValueError):
            review_store.pack_review_fields(
                {},
                ["unknown_business_field"],
            )

    def test_save_reload_history_and_new_run_reset_without_migration(self) -> None:
        packed = review_store.pack_review_fields(
            {
                "vendor_name": "SYNTH-CORRECTED-VENDOR",
                "legacy_scalar": 17,
            },
            ["invoice_number", "total_amount"],
        )
        saved = review_store.save_review(
            "synthetic-job-review",
            processing_run_id="run-1",
            status="approved",
            reviewer="Synthetic Reviewer",
            notes="Synthetic reviewer-clear evidence.",
            corrected_fields=packed,
        )
        self.assertEqual(
            saved["review"]["corrected_fields"],
            {
                "vendor_name": "SYNTH-CORRECTED-VENDOR",
                "legacy_scalar": 17,
            },
        )
        self.assertEqual(
            saved["review"]["unavailable_fields"],
            ["invoice_number", "total_amount"],
        )
        self.assertEqual(
            saved["history"][0]["unavailable_fields"],
            ["invoice_number", "total_amount"],
        )

        reloaded = review_store.get_review("synthetic-job-review")
        self.assertEqual(reloaded, saved)
        with sqlite3.connect(review_store.DATABASE_PATH) as connection:
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(document_reviews)"
                ).fetchall()
            }
            raw_payload = connection.execute(
                "SELECT corrected_fields_json FROM document_reviews "
                "WHERE job_id = ?",
                ("synthetic-job-review",),
            ).fetchone()[0]
        self.assertNotIn("unavailable_fields", columns)
        self.assertEqual(
            json.loads(raw_payload)[
                review_store.UNAVAILABLE_FIELDS_METADATA_KEY
            ],
            ["invoice_number", "total_amount"],
        )

        reset = review_store.begin_review_for_processing_run(
            "synthetic-job-review",
            "run-2",
        )
        self.assertEqual(reset["review"]["processing_run_id"], "run-2")
        self.assertEqual(reset["review"]["status"], "pending")
        self.assertEqual(reset["review"]["corrected_fields"], {})
        self.assertEqual(reset["review"]["unavailable_fields"], [])
        self.assertEqual(len(reset["history"]), 2)
        self.assertEqual(
            reset["history"][1]["unavailable_fields"],
            ["invoice_number", "total_amount"],
        )


if __name__ == "__main__":
    unittest.main()
