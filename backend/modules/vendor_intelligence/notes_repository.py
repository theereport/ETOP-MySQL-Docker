from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine

from data.mysql import get_engine, metadata, vendor_notes_table


class VendorNoteIntegrityError(RuntimeError):
    """Raised when a stored vendor note fails its SHA-256 check."""


class VendorNotesRepository:
    """Local append-only ETOP evidence: professional vendor notes."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialization_lock = threading.Lock()

    def initialize(self) -> None:
        with self._initialization_lock:
            metadata.create_all(
                self._engine, checkfirst=True, tables=[vendor_notes_table]
            )

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

        with self._engine.begin() as connection:
            connection.execute(
                vendor_notes_table.insert().values(
                    note_id=record["note_id"],
                    vendor_number=record["vendor_number"],
                    vendor_name=record["vendor_name"],
                    author_identity=record["author_identity"],
                    note=record["note"],
                    created_at=record["created_at"],
                    source_as_of=record["source_as_of"],
                    actor_identity_source=record["actor_identity_source"],
                    actor_authority_status=record["actor_authority_status"],
                    note_classification=record["note_classification"],
                    decision_effect=record["decision_effect"],
                    erp_write=0,
                    evidence_snapshot_json=snapshot_json,
                    evidence_snapshot_sha256=snapshot_sha256,
                )
            )
            stored = self._get_note(connection, record["note_id"])

        if stored is None:
            raise RuntimeError("The vendor note was not persisted.")
        return stored

    def _get_note(self, connection, note_id: str) -> dict[str, Any] | None:
        row = connection.execute(
            select(vendor_notes_table).where(
                vendor_notes_table.c.note_id == note_id
            )
        ).mappings().first()
        return self._note_from_row(row) if row is not None else None

    def get_note(self, note_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self._engine.connect() as connection:
            return self._get_note(connection, note_id)

    def list_notes(self, vendor_number: int) -> list[dict[str, Any]]:
        self.initialize()
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(vendor_notes_table)
                .where(vendor_notes_table.c.vendor_number == vendor_number)
                .order_by(
                    vendor_notes_table.c.created_at.desc(),
                    vendor_notes_table.c.note_id.desc(),
                )
            ).mappings().all()
        return [self._note_from_row(row) for row in rows]

    @staticmethod
    def _note_from_row(row) -> dict[str, Any]:
        snapshot_json = row["evidence_snapshot_json"]
        expected_hash = row["evidence_snapshot_sha256"]
        actual_hash = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()
        if actual_hash != expected_hash:
            raise VendorNoteIntegrityError(
                "Stored vendor note evidence failed its SHA-256 integrity "
                "check."
            )
        result = dict(row)
        result["erp_write"] = bool(result["erp_write"])
        result["evidence_snapshot"] = json.loads(
            result.pop("evidence_snapshot_json")
        )
        result["evidence_snapshot_sha256"] = expected_hash
        return result


vendor_notes_repository = VendorNotesRepository()


def initialize_vendor_intelligence_database() -> None:
    """Startup migration hook for the shared SQLite initialization boundary."""

    vendor_notes_repository.initialize()
