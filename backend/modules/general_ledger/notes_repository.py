from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine

from core.evidence_integrity import verify_snapshot_hash
from data.mysql import general_ledger_notes_table, get_engine, metadata


class GLNoteIntegrityError(RuntimeError):
    """Raised when a stored GL note fails its SHA-256 integrity check."""


class GeneralLedgerNotesRepository:
    """Local append-only ETOP evidence: professional GL reconciliation notes.

    A note is scoped to a G/L account number, and optionally to a division,
    department, period, and year. Notes are append-only (enforced by
    convention in this repository layer) and never write to the ERP.
    """

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialization_lock = threading.Lock()

    def initialize(self) -> None:
        with self._initialization_lock:
            metadata.create_all(
                self._engine,
                checkfirst=True,
                tables=[general_ledger_notes_table],
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
                general_ledger_notes_table.insert().values(
                    note_id=record["note_id"],
                    account_number=record["account_number"],
                    division=record["division"],
                    department=record["department"],
                    period=record["period"],
                    year=record["year"],
                    account_description=record["account_description"],
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
            raise RuntimeError("The general ledger note was not persisted.")
        return stored

    def _get_note(self, connection, note_id: str) -> dict[str, Any] | None:
        row = connection.execute(
            select(general_ledger_notes_table).where(
                general_ledger_notes_table.c.note_id == note_id
            )
        ).mappings().first()
        return self._note_from_row(row) if row is not None else None

    def get_note(self, note_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self._engine.connect() as connection:
            return self._get_note(connection, note_id)

    def list_notes(self, account_number: int) -> list[dict[str, Any]]:
        self.initialize()
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(general_ledger_notes_table)
                .where(
                    general_ledger_notes_table.c.account_number
                    == account_number
                )
                .order_by(
                    general_ledger_notes_table.c.created_at.desc(),
                    general_ledger_notes_table.c.note_id.desc(),
                )
            ).mappings().all()
        return [self._note_from_row(row) for row in rows]

    @staticmethod
    def _note_from_row(row) -> dict[str, Any]:
        snapshot_json = row["evidence_snapshot_json"]
        expected_hash = row["evidence_snapshot_sha256"]
        verify_snapshot_hash(
            snapshot_json,
            expected_hash,
            error=GLNoteIntegrityError,
            message=(
                "Stored general ledger note evidence failed its SHA-256 "
                "integrity check."
            ),
        )
        result = dict(row)
        result["erp_write"] = bool(result["erp_write"])
        result["evidence_snapshot"] = json.loads(
            result.pop("evidence_snapshot_json")
        )
        result["evidence_snapshot_sha256"] = expected_hash
        return result


general_ledger_notes_repository = GeneralLedgerNotesRepository()


def initialize_general_ledger_database() -> None:
    """Startup migration hook for the shared SQLite initialization boundary."""

    general_ledger_notes_repository.initialize()
