from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("MYSQL_USER", "test")
os.environ.setdefault("MYSQL_PASSWORD", "test")
os.environ.setdefault("MYSQL_DATABASE", "test")

import sql_workspace


class SavedQueryAndHistoryScopingTests(unittest.TestCase):
    """Covers the fix for saved queries/history being global across every
    user rather than scoped to whoever created them."""

    def setUp(self) -> None:
        # ignore_cleanup_errors: sql_workspace._connect()'s `with` blocks
        # commit/rollback but never call .close() (a pre-existing pattern
        # throughout that module, not introduced here), so on Windows the
        # sqlite file can still be locked by a not-yet-garbage-collected
        # connection when cleanup runs immediately after the test.
        self._tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._original_path = sql_workspace.SQLITE_PATH
        sql_workspace.SQLITE_PATH = Path(self._tmp_dir.name) / "sql_workspace.db"
        sql_workspace.initialize_sql_workspace_database()

    def tearDown(self) -> None:
        sql_workspace.SQLITE_PATH = self._original_path
        self._tmp_dir.cleanup()

    def _create(self, title: str, owner: str | None) -> int:
        response = sql_workspace.create_saved_query(
            sql_workspace.SavedQueryCreate(title=title, sql="SELECT 1"),
            current_user_id=owner,
        )
        return response["id"]

    def test_user_sees_only_their_own_and_legacy_queries(self) -> None:
        self._create("Alice's query", "USR-alice")
        self._create("Bob's query", "USR-bob")
        self._create("Legacy shared query", None)

        alice_titles = {
            row["title"]
            for row in sql_workspace.get_saved_queries(
                current_user_id="USR-alice", search="", category=""
            )["queries"]
        }

        self.assertEqual(
            alice_titles, {"Alice's query", "Legacy shared query"}
        )

    def test_user_cannot_update_someone_elses_query(self) -> None:
        bob_id = self._create("Bob's query", "USR-bob")

        with self.assertRaises(Exception) as raised:
            sql_workspace.update_saved_query(
                bob_id,
                sql_workspace.SavedQueryUpdate(title="Hijacked", sql="SELECT 2"),
                current_user_id="USR-alice",
            )
        self.assertEqual(raised.exception.status_code, 404)

    def test_user_cannot_delete_someone_elses_query(self) -> None:
        bob_id = self._create("Bob's query", "USR-bob")

        with self.assertRaises(Exception) as raised:
            sql_workspace.delete_saved_query(bob_id, current_user_id="USR-alice")
        self.assertEqual(raised.exception.status_code, 404)

    def test_owner_can_update_and_delete_their_own_query(self) -> None:
        alice_id = self._create("Alice's query", "USR-alice")

        updated = sql_workspace.update_saved_query(
            alice_id,
            sql_workspace.SavedQueryUpdate(title="Renamed", sql="SELECT 2"),
            current_user_id="USR-alice",
        )
        self.assertTrue(updated["success"])

        deleted = sql_workspace.delete_saved_query(
            alice_id, current_user_id="USR-alice"
        )
        self.assertTrue(deleted["success"])

    def test_anyone_can_edit_a_legacy_unowned_query(self) -> None:
        legacy_id = self._create("Legacy shared query", None)

        updated = sql_workspace.update_saved_query(
            legacy_id,
            sql_workspace.SavedQueryUpdate(title="Renamed by bob", sql="SELECT 2"),
            current_user_id="USR-bob",
        )
        self.assertTrue(updated["success"])

    def test_history_scoped_to_owner_and_legacy(self) -> None:
        sql_workspace.record_history(
            sql_text="SELECT 1",
            success=True,
            row_count=1,
            execution_ms=1.0,
            error_message=None,
            created_by="USR-alice",
        )
        sql_workspace.record_history(
            sql_text="SELECT 2",
            success=True,
            row_count=1,
            execution_ms=1.0,
            error_message=None,
            created_by="USR-bob",
        )

        alice_history = sql_workspace.get_query_history(current_user_id="USR-alice", limit=50)
        sql_texts = {item["sql"] for item in alice_history["history"]}

        self.assertIn("SELECT 1", sql_texts)
        self.assertNotIn("SELECT 2", sql_texts)

    def test_clear_history_only_removes_own_rows(self) -> None:
        sql_workspace.record_history(
            sql_text="SELECT 1",
            success=True,
            row_count=1,
            execution_ms=1.0,
            error_message=None,
            created_by="USR-alice",
        )
        sql_workspace.record_history(
            sql_text="SELECT 2",
            success=True,
            row_count=1,
            execution_ms=1.0,
            error_message=None,
            created_by="USR-bob",
        )

        sql_workspace.clear_query_history(current_user_id="USR-alice")

        bob_history = sql_workspace.get_query_history(current_user_id="USR-bob", limit=50)
        sql_texts = {item["sql"] for item in bob_history["history"]}
        self.assertIn("SELECT 2", sql_texts)


if __name__ == "__main__":
    unittest.main()
