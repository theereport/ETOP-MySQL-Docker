from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable
from typing import Any

from data.database import get_connection


class InventoryNoteIntegrityError(RuntimeError):
    """Raised when a stored inventory note fails its SHA-256 integrity check."""


class InventoryNotesRepository:
    """Local append-only ETOP evidence: professional notes on a product."""

    def __init__(
        self,
        connection_factory: Callable[[], sqlite3.Connection] = get_connection,
    ) -> None:
        self._connection_factory = connection_factory
        self._initialization_lock = threading.Lock()

    def _connection(self) -> sqlite3.Connection:
        connection = self._connection_factory()
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection

    def initialize(self) -> None:
        with self._initialization_lock:
            connection = self._connection()
            try:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS inventory_notes (
                        note_id TEXT PRIMARY KEY,
                        product_number TEXT NOT NULL,
                        product_description TEXT NOT NULL,
                        author_identity TEXT NOT NULL,
                        note TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        source_as_of TEXT NOT NULL,
                        actor_identity_source TEXT NOT NULL
                            CHECK (actor_identity_source = 'operator_supplied'),
                        actor_authority_status TEXT NOT NULL
                            CHECK (
                                actor_authority_status =
                                    'not_independently_verified'
                            ),
                        note_classification TEXT NOT NULL
                            CHECK (
                                note_classification =
                                    'professional_workflow_metadata'
                            ),
                        decision_effect TEXT NOT NULL
                            CHECK (decision_effect = 'none'),
                        erp_write INTEGER NOT NULL DEFAULT 0
                            CHECK (erp_write = 0),
                        evidence_snapshot_json TEXT NOT NULL,
                        evidence_snapshot_sha256 TEXT NOT NULL
                            CHECK (length(evidence_snapshot_sha256) = 64)
                    );

                    CREATE INDEX IF NOT EXISTS idx_inventory_notes_product_time
                    ON inventory_notes(
                        product_number, created_at DESC, note_id DESC
                    );

                    CREATE TRIGGER IF NOT EXISTS inventory_notes_no_update
                    BEFORE UPDATE ON inventory_notes
                    BEGIN
                        SELECT RAISE(ABORT, 'Inventory notes are append-only.');
                    END;

                    CREATE TRIGGER IF NOT EXISTS inventory_notes_no_delete
                    BEFORE DELETE ON inventory_notes
                    BEGIN
                        SELECT RAISE(ABORT, 'Inventory notes are append-only.');
                    END;
                    """
                )
                connection.commit()
            finally:
                connection.close()

    def create_note(self, record: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        snapshot_json = json.dumps(
            record["evidence_snapshot"],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )
        snapshot_sha256 = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()

        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                INSERT INTO inventory_notes (
                    note_id, product_number, product_description,
                    author_identity, note, created_at, source_as_of,
                    actor_identity_source, actor_authority_status,
                    note_classification, decision_effect, erp_write,
                    evidence_snapshot_json, evidence_snapshot_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?);
                """,
                (
                    record["note_id"],
                    record["product_number"],
                    record["product_description"],
                    record["author_identity"],
                    record["note"],
                    record["created_at"],
                    record["source_as_of"],
                    record["actor_identity_source"],
                    record["actor_authority_status"],
                    record["note_classification"],
                    record["decision_effect"],
                    snapshot_json,
                    snapshot_sha256,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        stored = self.get_note(record["note_id"])
        if stored is None:
            raise RuntimeError("The inventory note was not persisted.")
        return stored

    def get_note(self, note_id: str) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                "SELECT * FROM inventory_notes WHERE note_id = ?;",
                (note_id,),
            ).fetchone()
        finally:
            connection.close()
        return self._note_from_row(row) if row is not None else None

    def list_notes(self, product_number: str) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT * FROM inventory_notes
                WHERE product_number = ?
                ORDER BY created_at DESC, note_id DESC;
                """,
                (product_number,),
            ).fetchall()
        finally:
            connection.close()
        return [self._note_from_row(row) for row in rows]

    @staticmethod
    def _note_from_row(row: sqlite3.Row) -> dict[str, Any]:
        snapshot_json = row["evidence_snapshot_json"]
        expected_hash = row["evidence_snapshot_sha256"]
        actual_hash = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()
        if actual_hash != expected_hash:
            raise InventoryNoteIntegrityError(
                "Stored inventory note evidence failed its SHA-256 "
                "integrity check."
            )
        result = dict(row)
        result["erp_write"] = bool(result["erp_write"])
        result["evidence_snapshot"] = json.loads(
            result.pop("evidence_snapshot_json")
        )
        result["evidence_snapshot_sha256"] = expected_hash
        return result


inventory_notes_repository = InventoryNotesRepository()


def initialize_inventory_purchasing_database() -> None:
    """Startup migration hook for the shared SQLite initialization boundary."""

    inventory_notes_repository.initialize()
