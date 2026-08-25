"""Append-oriented local persistence for Payment Notes evidence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable
from typing import Any

from data.database import get_connection


ZERO_HASH = "0" * 64


class PaymentNotesConflict(RuntimeError):
    """An idempotency or evidence precondition was not met."""


class PaymentNotesNotFound(LookupError):
    """A local Payment Notes record does not exist."""


class PaymentNotesIntegrityError(RuntimeError):
    """Stored Payment Notes evidence failed its hash verification."""


class PaymentNotesRepository:
    def __init__(
        self,
        connection_factory: Callable[[], sqlite3.Connection] = get_connection,
    ) -> None:
        self._connection_factory = connection_factory
        self._initialize_lock = threading.Lock()
        self._initialized = False

    @staticmethod
    def canonical_json(value: Any) -> str:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )

    @classmethod
    def sha256(cls, value: Any) -> str:
        return hashlib.sha256(cls.canonical_json(value).encode("utf-8")).hexdigest()

    def _connection(self) -> sqlite3.Connection:
        connection = self._connection_factory()
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection

    def initialize(self) -> None:
        with self._initialize_lock:
            if self._initialized:
                return
            connection = self._connection()
            try:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS pn_route_references (
                        reference_id TEXT PRIMARY KEY,
                        version_label TEXT NOT NULL,
                        source_name TEXT NOT NULL,
                        source_sha256 TEXT NOT NULL CHECK(length(source_sha256) = 64),
                        source_size INTEGER NOT NULL CHECK(source_size > 0),
                        parser_version TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
                        created_by TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        request_sha256 TEXT NOT NULL CHECK(length(request_sha256) = 64),
                        UNIQUE(created_by, idempotency_key)
                    );

                    CREATE UNIQUE INDEX IF NOT EXISTS uq_pn_route_content_version
                    ON pn_route_references(source_sha256, version_label);

                    CREATE TABLE IF NOT EXISTS pn_route_reference_activations (
                        activation_id TEXT PRIMARY KEY,
                        reference_id TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        request_sha256 TEXT NOT NULL CHECK(length(request_sha256) = 64),
                        previous_hash TEXT NOT NULL CHECK(length(previous_hash) = 64),
                        record_hash TEXT NOT NULL UNIQUE CHECK(length(record_hash) = 64),
                        UNIQUE(actor, idempotency_key),
                        FOREIGN KEY(reference_id) REFERENCES pn_route_references(reference_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_pn_route_activation_current
                    ON pn_route_reference_activations(occurred_at DESC, activation_id DESC);

                    CREATE TABLE IF NOT EXISTS pn_runs (
                        run_id TEXT PRIMARY KEY,
                        source_name TEXT NOT NULL,
                        source_sha256 TEXT NOT NULL CHECK(length(source_sha256) = 64),
                        source_size INTEGER NOT NULL CHECK(source_size > 0),
                        route_reference_id TEXT NOT NULL,
                        route_reference_sha256 TEXT NOT NULL CHECK(length(route_reference_sha256) = 64),
                        date_from TEXT NOT NULL,
                        date_to TEXT NOT NULL,
                        status TEXT NOT NULL,
                        deposit_count INTEGER NOT NULL CHECK(deposit_count >= 0),
                        physical_item_count INTEGER NOT NULL CHECK(physical_item_count >= 0),
                        quarantined_row_count INTEGER NOT NULL CHECK(quarantined_row_count >= 0),
                        payload_json TEXT NOT NULL,
                        payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
                        created_by TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        request_sha256 TEXT NOT NULL CHECK(length(request_sha256) = 64),
                        UNIQUE(created_by, idempotency_key),
                        FOREIGN KEY(route_reference_id) REFERENCES pn_route_references(reference_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_pn_runs_created
                    ON pn_runs(created_at DESC, run_id DESC);

                    CREATE UNIQUE INDEX IF NOT EXISTS uq_pn_run_content_scope
                    ON pn_runs(source_sha256, route_reference_id, date_from, date_to);

                    CREATE TABLE IF NOT EXISTS pn_review_events (
                        event_id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        item_id TEXT NOT NULL,
                        decision TEXT NOT NULL CHECK(decision IN (
                            'accept_candidate', 'leave_unmatched', 'hold'
                        )),
                        selected_payment_id TEXT,
                        reason TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        request_sha256 TEXT NOT NULL CHECK(length(request_sha256) = 64),
                        previous_hash TEXT NOT NULL CHECK(length(previous_hash) = 64),
                        record_hash TEXT NOT NULL UNIQUE CHECK(length(record_hash) = 64),
                        UNIQUE(actor, idempotency_key),
                        FOREIGN KEY(run_id) REFERENCES pn_runs(run_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_pn_review_item
                    ON pn_review_events(run_id, item_id, occurred_at, event_id);
                    """
                )
                for table in (
                    "pn_route_references",
                    "pn_route_reference_activations",
                    "pn_runs",
                    "pn_review_events",
                ):
                    connection.executescript(
                        f"""
                        CREATE TRIGGER IF NOT EXISTS {table}_no_update
                        BEFORE UPDATE ON {table}
                        BEGIN
                            SELECT RAISE(ABORT, '{table} is append-only.');
                        END;
                        CREATE TRIGGER IF NOT EXISTS {table}_no_delete
                        BEFORE DELETE ON {table}
                        BEGIN
                            SELECT RAISE(ABORT, '{table} is append-only.');
                        END;
                        """
                    )
                connection.commit()
            finally:
                connection.close()
            self._initialized = True

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    def create_route_reference(
        self,
        *,
        reference_id: str,
        version_label: str,
        payload: dict[str, Any],
        actor: str,
        occurred_at: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._ensure_initialized()
        request = {
            "version_label": version_label,
            "source_sha256": payload["source_sha256"],
            "payload_sha256": self.sha256(payload),
        }
        request_hash = self.sha256(request)
        connection = self._connection()
        try:
            existing = connection.execute(
                """
                SELECT * FROM pn_route_references
                WHERE created_by = ? AND idempotency_key = ?
                """,
                (actor, idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_sha256"] != request_hash:
                    raise PaymentNotesConflict(
                        "Route-reference idempotency key was reused with different content."
                    )
                return self._route_row(existing)
            same_content = connection.execute(
                """
                SELECT * FROM pn_route_references
                WHERE source_sha256 = ? AND version_label = ?
                """,
                (payload["source_sha256"], version_label),
            ).fetchone()
            if same_content:
                return self._route_row(same_content)
            connection.execute(
                """
                INSERT INTO pn_route_references (
                    reference_id, version_label, source_name, source_sha256,
                    source_size, parser_version, payload_json, payload_sha256,
                    created_by, created_at, idempotency_key, request_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reference_id,
                    version_label,
                    payload["source_name"],
                    payload["source_sha256"],
                    payload["source_size"],
                    payload["parser_version"],
                    self.canonical_json(payload),
                    request["payload_sha256"],
                    actor,
                    occurred_at,
                    idempotency_key,
                    request_hash,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM pn_route_references WHERE reference_id = ?",
                (reference_id,),
            ).fetchone()
            return self._route_row(row)
        finally:
            connection.close()

    def list_route_references(self) -> list[dict[str, Any]]:
        self._ensure_initialized()
        connection = self._connection()
        try:
            rows = connection.execute(
                "SELECT * FROM pn_route_references ORDER BY created_at DESC, reference_id DESC"
            ).fetchall()
            return [self._route_row(row) for row in rows]
        finally:
            connection.close()

    def get_route_reference(self, reference_id: str) -> dict[str, Any]:
        self._ensure_initialized()
        connection = self._connection()
        try:
            row = connection.execute(
                "SELECT * FROM pn_route_references WHERE reference_id = ?",
                (reference_id,),
            ).fetchone()
            if row is None:
                raise PaymentNotesNotFound(f"Route reference {reference_id} was not found.")
            return self._route_row(row)
        finally:
            connection.close()

    def activate_route_reference(
        self,
        *,
        activation_id: str,
        reference_id: str,
        actor: str,
        occurred_at: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._ensure_initialized()
        request = {"reference_id": reference_id}
        request_hash = self.sha256(request)
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            reference = connection.execute(
                "SELECT reference_id FROM pn_route_references WHERE reference_id = ?",
                (reference_id,),
            ).fetchone()
            if reference is None:
                raise PaymentNotesNotFound(
                    f"Route reference {reference_id} was not found."
                )
            existing = connection.execute(
                """
                SELECT * FROM pn_route_reference_activations
                WHERE actor = ? AND idempotency_key = ?
                """,
                (actor, idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_sha256"] != request_hash:
                    raise PaymentNotesConflict(
                        "Route activation idempotency key was reused with a different reference."
                    )
                return dict(existing)
            previous = connection.execute(
                """
                SELECT record_hash FROM pn_route_reference_activations
                ORDER BY rowid DESC LIMIT 1
                """
            ).fetchone()
            previous_hash = previous["record_hash"] if previous else ZERO_HASH
            record = {
                "activation_id": activation_id,
                "reference_id": reference_id,
                "actor": actor,
                "occurred_at": occurred_at,
                "request_sha256": request_hash,
                "previous_hash": previous_hash,
            }
            record_hash = self.sha256(record)
            connection.execute(
                """
                INSERT INTO pn_route_reference_activations (
                    activation_id, reference_id, actor, occurred_at,
                    idempotency_key, request_sha256, previous_hash, record_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    activation_id,
                    reference_id,
                    actor,
                    occurred_at,
                    idempotency_key,
                    request_hash,
                    previous_hash,
                    record_hash,
                ),
            )
            connection.commit()
            return {**record, "idempotency_key": idempotency_key, "record_hash": record_hash}
        finally:
            connection.close()

    def get_active_route_reference(self) -> dict[str, Any] | None:
        self._ensure_initialized()
        connection = self._connection()
        try:
            activation_rows = connection.execute(
                """
                SELECT rowid AS chain_ordinal, *
                FROM pn_route_reference_activations
                ORDER BY rowid
                """
            ).fetchall()
            self._verify_activation_chain(activation_rows)
            row = connection.execute(
                """
                SELECT r.*, a.activation_id, a.occurred_at AS activated_at,
                       a.actor AS activated_by, a.record_hash AS activation_hash
                FROM pn_route_reference_activations a
                JOIN pn_route_references r ON r.reference_id = a.reference_id
                ORDER BY a.rowid DESC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            payload = self._route_row(row)
            payload.update(
                {
                    "activation_id": row["activation_id"],
                    "activated_at": row["activated_at"],
                    "activated_by": row["activated_by"],
                    "activation_hash": row["activation_hash"],
                }
            )
            return payload
        finally:
            connection.close()

    def create_run(
        self,
        *,
        run_id: str,
        payload: dict[str, Any],
        actor: str,
        occurred_at: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._ensure_initialized()
        request = {
            "source_sha256": payload["source"]["sha256"],
            "route_reference_id": payload["route_reference"]["reference_id"],
            "route_reference_sha256": payload["route_reference"]["source_sha256"],
            "date_from": payload["date_from"],
            "date_to": payload["date_to"],
        }
        request_hash = self.sha256(request)
        payload_hash = self.sha256(payload)
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM pn_runs WHERE created_by = ? AND idempotency_key = ?",
                (actor, idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_sha256"] != request_hash:
                    raise PaymentNotesConflict(
                        "Run idempotency key was reused with different source or bounds."
                    )
                return self._run_row(existing, include_payload=True)
            same_scope = connection.execute(
                """
                SELECT * FROM pn_runs
                WHERE source_sha256 = ? AND route_reference_id = ?
                  AND date_from = ? AND date_to = ?
                """,
                (
                    payload["source"]["sha256"],
                    payload["route_reference"]["reference_id"],
                    payload["date_from"],
                    payload["date_to"],
                ),
            ).fetchone()
            if same_scope:
                return self._run_row(same_scope, include_payload=True)
            proposed_payment_ids = {
                str(item.get("match", {}).get("selected_payment_id") or "")
                for item in payload.get("items", [])
            } - {""}
            if proposed_payment_ids:
                prior_uses = self._payment_uses_on_connection(
                    connection,
                    proposed_payment_ids,
                )
                if prior_uses:
                    raise PaymentNotesConflict(
                        "CROSS_RUN_REUSE_POLICY_UNRESOLVED: a selected Payment Note "
                        "appeared in prior run evidence while the run was being saved."
                    )
            connection.execute(
                """
                INSERT INTO pn_runs (
                    run_id, source_name, source_sha256, source_size,
                    route_reference_id, route_reference_sha256, date_from,
                    date_to, status, deposit_count, physical_item_count,
                    quarantined_row_count, payload_json, payload_sha256,
                    created_by, created_at, idempotency_key, request_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    payload["source"]["name"],
                    payload["source"]["sha256"],
                    payload["source"]["size"],
                    payload["route_reference"]["reference_id"],
                    payload["route_reference"]["source_sha256"],
                    payload["date_from"],
                    payload["date_to"],
                    payload["status"],
                    len(payload["deposits"]),
                    len(payload["items"]),
                    len(payload["quarantined_rows"]),
                    self.canonical_json(payload),
                    payload_hash,
                    actor,
                    occurred_at,
                    idempotency_key,
                    request_hash,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM pn_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            return self._run_row(row, include_payload=True)
        finally:
            connection.close()

    def get_run(self, run_id: str) -> dict[str, Any]:
        self._ensure_initialized()
        connection = self._connection()
        try:
            row = connection.execute(
                "SELECT * FROM pn_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise PaymentNotesNotFound(f"Payment Notes run {run_id} was not found.")
            result = self._run_row(row, include_payload=True)
            reviews = connection.execute(
                """
                SELECT * FROM pn_review_events
                WHERE run_id = ? ORDER BY occurred_at, event_id
                """,
                (run_id,),
            ).fetchall()
            self._verify_review_chains(reviews)
            result["reviews"] = [dict(review) for review in reviews]
            return result
        finally:
            connection.close()

    def list_runs(self, limit: int, offset: int) -> list[dict[str, Any]]:
        self._ensure_initialized()
        bounded = max(1, min(limit, 200))
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT * FROM pn_runs
                ORDER BY created_at DESC, run_id DESC LIMIT ? OFFSET ?
                """,
                (bounded, max(0, offset)),
            ).fetchall()
            return [self._run_row(row, include_payload=False) for row in rows]
        finally:
            connection.close()

    def count_runs(self) -> int:
        self._ensure_initialized()
        connection = self._connection()
        try:
            return int(connection.execute("SELECT COUNT(*) FROM pn_runs").fetchone()[0])
        finally:
            connection.close()

    def prior_run_payment_uses(
        self,
        payment_ids: set[str],
        *,
        exclude_run_id: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Return conservative historical use evidence for WHSIGPAY identities."""

        self._ensure_initialized()
        wanted = {str(value).strip() for value in payment_ids if str(value).strip()}
        if not wanted:
            return {}
        connection = self._connection()
        try:
            return self._payment_uses_on_connection(
                connection,
                wanted,
                exclude_run_id=exclude_run_id,
            )
        finally:
            connection.close()

    def append_review(
        self,
        *,
        event_id: str,
        run_id: str,
        item_id: str,
        decision: str,
        selected_payment_id: str | None,
        reason: str,
        actor: str,
        occurred_at: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._ensure_initialized()
        request = {
            "run_id": run_id,
            "item_id": item_id,
            "decision": decision,
            "selected_payment_id": selected_payment_id,
            "reason": reason,
        }
        request_hash = self.sha256(request)
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            run_row = connection.execute(
                "SELECT * FROM pn_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if run_row is None:
                raise PaymentNotesNotFound(f"Payment Notes run {run_id} was not found.")
            existing = connection.execute(
                "SELECT * FROM pn_review_events WHERE actor = ? AND idempotency_key = ?",
                (actor, idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_sha256"] != request_hash:
                    raise PaymentNotesConflict(
                        "Review idempotency key was reused with a different decision."
                    )
                return dict(existing)
            if decision == "accept_candidate" and selected_payment_id:
                prior_uses = self._payment_uses_on_connection(
                    connection,
                    {selected_payment_id},
                    exclude_run_id=run_id,
                )
                if prior_uses:
                    raise PaymentNotesConflict(
                        "CROSS_RUN_REUSE_POLICY_UNRESOLVED: the selected Payment Note "
                        "appears in prior run evidence and cannot be accepted."
                    )
                run_payload = json.loads(run_row["payload_json"])
                review_rows = connection.execute(
                    """
                    SELECT * FROM pn_review_events
                    WHERE run_id = ? ORDER BY occurred_at, event_id
                    """,
                    (run_id,),
                ).fetchall()
                latest = {str(row["item_id"]): row for row in review_rows}
                for other in run_payload.get("items", []):
                    other_id = str(other.get("item_id", ""))
                    if not other_id or other_id == item_id:
                        continue
                    current = latest.get(other_id)
                    if current is not None:
                        effective = (
                            current["selected_payment_id"]
                            if current["decision"] == "accept_candidate"
                            else None
                        )
                    else:
                        effective = other.get("match", {}).get("selected_payment_id")
                    if effective == selected_payment_id:
                        raise PaymentNotesConflict(
                            "The selected Payment Note is already assigned to another bank item in this run."
                        )
            prior = connection.execute(
                """
                SELECT record_hash FROM pn_review_events
                WHERE run_id = ? AND item_id = ?
                ORDER BY occurred_at DESC, event_id DESC LIMIT 1
                """,
                (run_id, item_id),
            ).fetchone()
            previous_hash = prior["record_hash"] if prior else ZERO_HASH
            record = {
                "event_id": event_id,
                **request,
                "actor": actor,
                "occurred_at": occurred_at,
                "request_sha256": request_hash,
                "previous_hash": previous_hash,
            }
            record_hash = self.sha256(record)
            connection.execute(
                """
                INSERT INTO pn_review_events (
                    event_id, run_id, item_id, decision, selected_payment_id,
                    reason, actor, occurred_at, idempotency_key, request_sha256,
                    previous_hash, record_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    run_id,
                    item_id,
                    decision,
                    selected_payment_id,
                    reason,
                    actor,
                    occurred_at,
                    idempotency_key,
                    request_hash,
                    previous_hash,
                    record_hash,
                ),
            )
            connection.commit()
            return {**record, "idempotency_key": idempotency_key, "record_hash": record_hash}
        finally:
            connection.close()

    @classmethod
    def _payment_uses_on_connection(
        cls,
        connection: sqlite3.Connection,
        payment_ids: set[str],
        *,
        exclude_run_id: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        uses: dict[str, list[dict[str, Any]]] = {}
        run_rows = connection.execute(
            "SELECT * FROM pn_runs ORDER BY created_at, run_id"
        ).fetchall()
        included_run_ids: set[str] = set()
        for row in run_rows:
            run_id = str(row["run_id"])
            if exclude_run_id and run_id == exclude_run_id:
                continue
            stored = cls._run_row(row, include_payload=True)
            included_run_ids.add(run_id)
            for item in stored["payload"].get("items", []):
                payment_id = str(
                    item.get("match", {}).get("selected_payment_id") or ""
                )
                if payment_id in payment_ids:
                    uses.setdefault(payment_id, []).append(
                        {
                            "payment_id": payment_id,
                            "run_id": run_id,
                            "item_id": str(item.get("item_id") or ""),
                            "source_type": "automatic_match",
                        }
                    )
        if included_run_ids:
            placeholders = ",".join("?" for _ in included_run_ids)
            review_rows = connection.execute(
                f"""
                SELECT * FROM pn_review_events
                WHERE run_id IN ({placeholders})
                ORDER BY run_id, occurred_at, event_id
                """,
                tuple(sorted(included_run_ids)),
            ).fetchall()
            cls._verify_review_chains(review_rows)
            for row in review_rows:
                payment_id = str(row["selected_payment_id"] or "")
                if row["decision"] == "accept_candidate" and payment_id in payment_ids:
                    uses.setdefault(payment_id, []).append(
                        {
                            "payment_id": payment_id,
                            "run_id": str(row["run_id"]),
                            "item_id": str(row["item_id"]),
                            "source_type": "manual_review",
                        }
                    )
        return {
            payment_id: sorted(
                records,
                key=lambda item: (
                    item["run_id"],
                    item["item_id"],
                    item["source_type"],
                ),
            )
            for payment_id, records in sorted(uses.items())
        }

    @classmethod
    def _route_row(cls, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        payload = json.loads(result.pop("payload_json"))
        if cls.sha256(payload) != result["payload_sha256"]:
            raise PaymentNotesIntegrityError(
                f"Route reference {result['reference_id']} payload hash is invalid."
            )
        result["payload"] = payload
        return result

    @classmethod
    def _run_row(cls, row: sqlite3.Row, *, include_payload: bool) -> dict[str, Any]:
        result = dict(row)
        payload_json = result.pop("payload_json")
        payload = json.loads(payload_json)
        if cls.sha256(payload) != result["payload_sha256"]:
            raise PaymentNotesIntegrityError(
                f"Payment Notes run {result['run_id']} payload hash is invalid."
            )
        if include_payload:
            result["payload"] = payload
        return result

    @classmethod
    def _verify_activation_chain(cls, rows: list[sqlite3.Row]) -> None:
        previous_hash = ZERO_HASH
        for row in rows:
            record = {
                "activation_id": row["activation_id"],
                "reference_id": row["reference_id"],
                "actor": row["actor"],
                "occurred_at": row["occurred_at"],
                "request_sha256": row["request_sha256"],
                "previous_hash": row["previous_hash"],
            }
            if row["previous_hash"] != previous_hash or cls.sha256(record) != row["record_hash"]:
                raise PaymentNotesIntegrityError(
                    "Route-reference activation evidence hash chain is invalid."
                )
            previous_hash = row["record_hash"]

    @classmethod
    def _verify_review_chains(cls, rows: list[sqlite3.Row]) -> None:
        previous: dict[str, str] = {}
        for row in rows:
            item_key = str(row["item_id"])
            expected_previous = previous.get(item_key, ZERO_HASH)
            record = {
                "event_id": row["event_id"],
                "run_id": row["run_id"],
                "item_id": row["item_id"],
                "decision": row["decision"],
                "selected_payment_id": row["selected_payment_id"],
                "reason": row["reason"],
                "actor": row["actor"],
                "occurred_at": row["occurred_at"],
                "request_sha256": row["request_sha256"],
                "previous_hash": row["previous_hash"],
            }
            if row["previous_hash"] != expected_previous or cls.sha256(record) != row["record_hash"]:
                raise PaymentNotesIntegrityError(
                    f"Review evidence hash chain is invalid for item {item_key}."
                )
            previous[item_key] = row["record_hash"]


payment_notes_repository = PaymentNotesRepository()


__all__ = [
    "PaymentNotesConflict",
    "PaymentNotesIntegrityError",
    "PaymentNotesNotFound",
    "PaymentNotesRepository",
    "payment_notes_repository",
]
