from __future__ import annotations

import hashlib
import json
import unittest

from core.evidence_integrity import verify_snapshot_hash


class CustomIntegrityError(RuntimeError):
    pass


class VerifySnapshotHashTests(unittest.TestCase):
    def test_matching_hash_does_not_raise(self) -> None:
        snapshot_json = json.dumps({"a": 1}, sort_keys=True, separators=(",", ":"))
        correct_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        verify_snapshot_hash(
            snapshot_json,
            correct_hash,
            error=CustomIntegrityError,
            message="should not fire",
        )

    def test_mismatched_hash_raises_the_given_error_with_the_given_message(
        self,
    ) -> None:
        snapshot_json = json.dumps({"a": 1})
        wrong_hash = "0" * 64
        with self.assertRaises(CustomIntegrityError) as raised:
            verify_snapshot_hash(
                snapshot_json,
                wrong_hash,
                error=CustomIntegrityError,
                message="Stored evidence failed its SHA-256 integrity check.",
            )
        self.assertEqual(
            str(raised.exception),
            "Stored evidence failed its SHA-256 integrity check.",
        )

    def test_never_reserializes_only_hashes_the_given_text(self) -> None:
        # Verification must operate purely on the stored JSON string, never
        # re-serialize a Python value - this is what makes it safe to use
        # across modules whose write-side json.dumps() parameters differ
        # (e.g. one omits default=str while others don't).
        snapshot_json = '{"b":2,"a":1}'  # deliberately NOT sort_keys order
        correct_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        verify_snapshot_hash(
            snapshot_json,
            correct_hash,
            error=CustomIntegrityError,
            message="should not fire",
        )


if __name__ == "__main__":
    unittest.main()
