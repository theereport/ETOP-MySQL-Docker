from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable
from typing import Any

from data.database import get_connection


ZERO_HASH = "0" * 64


class FinancialCloseConflict(RuntimeError):
    """An idempotency, version, or lifecycle precondition was not met."""


class FinancialCloseNotFound(LookupError):
    """A local close-readiness record was not found."""


class FinancialCloseIntegrityError(RuntimeError):
    """Stored close-readiness evidence failed its integrity check."""


class FinancialCloseRepository:
    """Immutable close definitions and append-only control evidence."""

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

    @staticmethod
    def canonical_json(value: Any) -> str:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @classmethod
    def sha256(cls, value: Any) -> str:
        return hashlib.sha256(cls.canonical_json(value).encode("utf-8")).hexdigest()

    def initialize(self) -> None:
        with self._initialization_lock:
            connection = self._connection()
            try:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS fc_cycles (
                        cycle_id TEXT PRIMARY KEY,
                        entity_label TEXT NOT NULL,
                        period_label TEXT NOT NULL,
                        period_start TEXT NOT NULL,
                        period_end TEXT NOT NULL,
                        target_completion_date TEXT,
                        description TEXT NOT NULL,
                        created_by_user_id TEXT NOT NULL,
                        created_by_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        request_sha256 TEXT NOT NULL CHECK(length(request_sha256) = 64),
                        definition_sha256 TEXT NOT NULL CHECK(length(definition_sha256) = 64),
                        authority_effect TEXT NOT NULL CHECK(authority_effect = 'none'),
                        close_effect TEXT NOT NULL CHECK(close_effect = 'none'),
                        approval_effect TEXT NOT NULL CHECK(approval_effect = 'none'),
                        posting_effect TEXT NOT NULL CHECK(posting_effect = 'none'),
                        erp_write INTEGER NOT NULL CHECK(erp_write = 0),
                        UNIQUE(created_by_user_id, idempotency_key),
                        FOREIGN KEY(created_by_user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_fc_cycles_period
                    ON fc_cycles(period_end DESC, period_start DESC, cycle_id);

                    CREATE TRIGGER IF NOT EXISTS fc_cycles_no_update
                    BEFORE UPDATE ON fc_cycles
                    BEGIN
                        SELECT RAISE(ABORT, 'Financial close cycles are immutable.');
                    END;

                    CREATE TRIGGER IF NOT EXISTS fc_cycles_no_delete
                    BEFORE DELETE ON fc_cycles
                    BEGIN
                        SELECT RAISE(ABORT, 'Financial close cycles are immutable.');
                    END;

                    CREATE TABLE IF NOT EXISTS fc_control_items (
                        control_id TEXT PRIMARY KEY,
                        cycle_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        planned_date TEXT,
                        preparer_user_id TEXT NOT NULL,
                        preparer_json TEXT NOT NULL,
                        reviewer_user_id TEXT NOT NULL,
                        reviewer_json TEXT NOT NULL,
                        created_by_user_id TEXT NOT NULL,
                        created_by_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        request_sha256 TEXT NOT NULL CHECK(length(request_sha256) = 64),
                        definition_sha256 TEXT NOT NULL CHECK(length(definition_sha256) = 64),
                        authority_effect TEXT NOT NULL CHECK(authority_effect = 'none'),
                        close_effect TEXT NOT NULL CHECK(close_effect = 'none'),
                        CHECK(preparer_user_id <> reviewer_user_id),
                        UNIQUE(created_by_user_id, idempotency_key),
                        FOREIGN KEY(cycle_id) REFERENCES fc_cycles(cycle_id),
                        FOREIGN KEY(preparer_user_id) REFERENCES wf_user_accounts(user_id),
                        FOREIGN KEY(reviewer_user_id) REFERENCES wf_user_accounts(user_id),
                        FOREIGN KEY(created_by_user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_fc_controls_cycle
                    ON fc_control_items(cycle_id, planned_date, created_at, control_id);

                    CREATE INDEX IF NOT EXISTS idx_fc_controls_participants
                    ON fc_control_items(preparer_user_id, reviewer_user_id, cycle_id);

                    CREATE TRIGGER IF NOT EXISTS fc_controls_no_update
                    BEFORE UPDATE ON fc_control_items
                    BEGIN
                        SELECT RAISE(ABORT, 'Financial close control items are immutable.');
                    END;

                    CREATE TRIGGER IF NOT EXISTS fc_controls_no_delete
                    BEFORE DELETE ON fc_control_items
                    BEGIN
                        SELECT RAISE(ABORT, 'Financial close control items are immutable.');
                    END;

                    CREATE TABLE IF NOT EXISTS fc_control_events (
                        event_id TEXT PRIMARY KEY,
                        cycle_id TEXT NOT NULL,
                        control_id TEXT,
                        event_type TEXT NOT NULL CHECK(event_type IN (
                            'cycle_created', 'control_created',
                            'preparation_recorded', 'review_recorded'
                        )),
                        actor_user_id TEXT NOT NULL,
                        actor_json TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        details_json TEXT NOT NULL,
                        subject_version INTEGER NOT NULL CHECK(subject_version >= 1),
                        idempotency_key TEXT NOT NULL,
                        request_sha256 TEXT NOT NULL CHECK(length(request_sha256) = 64),
                        previous_hash TEXT NOT NULL CHECK(length(previous_hash) = 64),
                        record_hash TEXT NOT NULL UNIQUE CHECK(length(record_hash) = 64),
                        schema_version TEXT NOT NULL CHECK(schema_version = '1.0'),
                        authority_effect TEXT NOT NULL CHECK(authority_effect = 'none'),
                        close_effect TEXT NOT NULL CHECK(close_effect = 'none'),
                        UNIQUE(actor_user_id, idempotency_key),
                        UNIQUE(control_id, subject_version),
                        CHECK(
                            (event_type = 'cycle_created' AND control_id IS NULL)
                            OR
                            (event_type <> 'cycle_created' AND control_id IS NOT NULL)
                        ),
                        FOREIGN KEY(cycle_id) REFERENCES fc_cycles(cycle_id),
                        FOREIGN KEY(control_id) REFERENCES fc_control_items(control_id),
                        FOREIGN KEY(actor_user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_fc_events_cycle
                    ON fc_control_events(cycle_id, occurred_at, event_id);

                    CREATE UNIQUE INDEX IF NOT EXISTS uq_fc_cycle_created_event
                    ON fc_control_events(cycle_id)
                    WHERE control_id IS NULL;

                    CREATE INDEX IF NOT EXISTS idx_fc_events_control
                    ON fc_control_events(control_id, subject_version, event_id);

                    CREATE TRIGGER IF NOT EXISTS fc_events_no_update
                    BEFORE UPDATE ON fc_control_events
                    BEGIN
                        SELECT RAISE(ABORT, 'Financial close control events are append-only.');
                    END;

                    CREATE TRIGGER IF NOT EXISTS fc_events_no_delete
                    BEFORE DELETE ON fc_control_events
                    BEGIN
                        SELECT RAISE(ABORT, 'Financial close control events are append-only.');
                    END;

                    CREATE TABLE IF NOT EXISTS fc_control_templates (
                        template_id TEXT PRIMARY KEY,
                        created_by_user_id TEXT NOT NULL,
                        created_by_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        request_sha256 TEXT NOT NULL CHECK(length(request_sha256) = 64),
                        definition_sha256 TEXT NOT NULL CHECK(length(definition_sha256) = 64),
                        authority_effect TEXT NOT NULL CHECK(authority_effect = 'none'),
                        policy_effect TEXT NOT NULL CHECK(policy_effect = 'none'),
                        automation_effect TEXT NOT NULL CHECK(automation_effect = 'none'),
                        UNIQUE(created_by_user_id, idempotency_key),
                        FOREIGN KEY(created_by_user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE TRIGGER IF NOT EXISTS fc_templates_no_update
                    BEFORE UPDATE ON fc_control_templates
                    BEGIN
                        SELECT RAISE(ABORT, 'Financial close template identities are immutable.');
                    END;

                    CREATE TRIGGER IF NOT EXISTS fc_templates_no_delete
                    BEFORE DELETE ON fc_control_templates
                    BEGIN
                        SELECT RAISE(ABORT, 'Financial close template identities are immutable.');
                    END;

                    CREATE TABLE IF NOT EXISTS fc_template_versions (
                        template_id TEXT NOT NULL,
                        version INTEGER NOT NULL CHECK(version >= 1),
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        change_note TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status = 'local_user_authored_planning_draft'),
                        created_by_user_id TEXT NOT NULL,
                        created_by_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        request_sha256 TEXT NOT NULL CHECK(length(request_sha256) = 64),
                        previous_version_sha256 TEXT NOT NULL CHECK(length(previous_version_sha256) = 64),
                        version_sha256 TEXT NOT NULL UNIQUE CHECK(length(version_sha256) = 64),
                        policy_effect TEXT NOT NULL CHECK(policy_effect = 'none'),
                        automation_effect TEXT NOT NULL CHECK(automation_effect = 'none'),
                        PRIMARY KEY(template_id, version),
                        UNIQUE(created_by_user_id, idempotency_key),
                        FOREIGN KEY(template_id) REFERENCES fc_control_templates(template_id),
                        FOREIGN KEY(created_by_user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_fc_template_versions_latest
                    ON fc_template_versions(template_id, version DESC);

                    CREATE TRIGGER IF NOT EXISTS fc_template_versions_no_update
                    BEFORE UPDATE ON fc_template_versions
                    BEGIN
                        SELECT RAISE(ABORT, 'Financial close template versions are immutable.');
                    END;

                    CREATE TRIGGER IF NOT EXISTS fc_template_versions_no_delete
                    BEFORE DELETE ON fc_template_versions
                    BEGIN
                        SELECT RAISE(ABORT, 'Financial close template versions are immutable.');
                    END;

                    CREATE TABLE IF NOT EXISTS fc_template_items (
                        item_id TEXT PRIMARY KEY,
                        template_id TEXT NOT NULL,
                        template_version INTEGER NOT NULL CHECK(template_version >= 1),
                        ordinal INTEGER NOT NULL CHECK(ordinal >= 1),
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        planned_offset_days INTEGER NOT NULL,
                        preparer_user_id TEXT NOT NULL,
                        preparer_json TEXT NOT NULL,
                        reviewer_user_id TEXT NOT NULL,
                        reviewer_json TEXT NOT NULL,
                        item_sha256 TEXT NOT NULL CHECK(length(item_sha256) = 64),
                        authority_effect TEXT NOT NULL CHECK(authority_effect = 'none'),
                        policy_effect TEXT NOT NULL CHECK(policy_effect = 'none'),
                        CHECK(preparer_user_id <> reviewer_user_id),
                        UNIQUE(template_id, template_version, ordinal),
                        FOREIGN KEY(template_id, template_version)
                            REFERENCES fc_template_versions(template_id, version),
                        FOREIGN KEY(preparer_user_id) REFERENCES wf_user_accounts(user_id),
                        FOREIGN KEY(reviewer_user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_fc_template_items_version
                    ON fc_template_items(template_id, template_version, ordinal);

                    CREATE TRIGGER IF NOT EXISTS fc_template_items_no_update
                    BEFORE UPDATE ON fc_template_items
                    BEGIN
                        SELECT RAISE(ABORT, 'Financial close template items are immutable.');
                    END;

                    CREATE TRIGGER IF NOT EXISTS fc_template_items_no_delete
                    BEFORE DELETE ON fc_template_items
                    BEGIN
                        SELECT RAISE(ABORT, 'Financial close template items are immutable.');
                    END;

                    CREATE TABLE IF NOT EXISTS fc_template_events (
                        event_id TEXT PRIMARY KEY,
                        template_id TEXT NOT NULL,
                        event_type TEXT NOT NULL CHECK(event_type IN (
                            'template_created', 'template_version_created',
                            'cycle_instantiated'
                        )),
                        actor_user_id TEXT NOT NULL,
                        actor_json TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        details_json TEXT NOT NULL,
                        sequence INTEGER NOT NULL CHECK(sequence >= 1),
                        idempotency_key TEXT NOT NULL,
                        request_sha256 TEXT NOT NULL CHECK(length(request_sha256) = 64),
                        previous_hash TEXT NOT NULL CHECK(length(previous_hash) = 64),
                        record_hash TEXT NOT NULL UNIQUE CHECK(length(record_hash) = 64),
                        schema_version TEXT NOT NULL CHECK(schema_version = '1.0'),
                        authority_effect TEXT NOT NULL CHECK(authority_effect = 'none'),
                        policy_effect TEXT NOT NULL CHECK(policy_effect = 'none'),
                        automation_effect TEXT NOT NULL CHECK(automation_effect = 'none'),
                        UNIQUE(template_id, sequence),
                        UNIQUE(actor_user_id, idempotency_key),
                        FOREIGN KEY(template_id) REFERENCES fc_control_templates(template_id),
                        FOREIGN KEY(actor_user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_fc_template_events
                    ON fc_template_events(template_id, sequence);

                    CREATE TRIGGER IF NOT EXISTS fc_template_events_no_update
                    BEFORE UPDATE ON fc_template_events
                    BEGIN
                        SELECT RAISE(ABORT, 'Financial close template events are append-only.');
                    END;

                    CREATE TRIGGER IF NOT EXISTS fc_template_events_no_delete
                    BEFORE DELETE ON fc_template_events
                    BEGIN
                        SELECT RAISE(ABORT, 'Financial close template events are append-only.');
                    END;

                    CREATE TABLE IF NOT EXISTS fc_cycle_template_snapshots (
                        snapshot_id TEXT PRIMARY KEY,
                        cycle_id TEXT NOT NULL UNIQUE,
                        template_id TEXT NOT NULL,
                        template_version INTEGER NOT NULL CHECK(template_version >= 1),
                        template_version_sha256 TEXT NOT NULL CHECK(length(template_version_sha256) = 64),
                        calendar_anchor_date TEXT NOT NULL,
                        snapshot_json TEXT NOT NULL,
                        created_by_user_id TEXT NOT NULL,
                        created_by_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        request_sha256 TEXT NOT NULL CHECK(length(request_sha256) = 64),
                        snapshot_sha256 TEXT NOT NULL UNIQUE CHECK(length(snapshot_sha256) = 64),
                        authority_effect TEXT NOT NULL CHECK(authority_effect = 'none'),
                        policy_effect TEXT NOT NULL CHECK(policy_effect = 'none'),
                        automation_effect TEXT NOT NULL CHECK(automation_effect = 'none'),
                        close_effect TEXT NOT NULL CHECK(close_effect = 'none'),
                        approval_effect TEXT NOT NULL CHECK(approval_effect = 'none'),
                        posting_effect TEXT NOT NULL CHECK(posting_effect = 'none'),
                        erp_write INTEGER NOT NULL CHECK(erp_write = 0),
                        UNIQUE(created_by_user_id, idempotency_key),
                        FOREIGN KEY(cycle_id) REFERENCES fc_cycles(cycle_id),
                        FOREIGN KEY(template_id, template_version)
                            REFERENCES fc_template_versions(template_id, version),
                        FOREIGN KEY(created_by_user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE TRIGGER IF NOT EXISTS fc_cycle_template_snapshots_no_update
                    BEFORE UPDATE ON fc_cycle_template_snapshots
                    BEGIN
                        SELECT RAISE(ABORT, 'Financial close cycle template snapshots are immutable.');
                    END;

                    CREATE TRIGGER IF NOT EXISTS fc_cycle_template_snapshots_no_delete
                    BEFORE DELETE ON fc_cycle_template_snapshots
                    BEGIN
                        SELECT RAISE(ABORT, 'Financial close cycle template snapshots are immutable.');
                    END;
                    """
                )
                connection.commit()
            finally:
                connection.close()

    @classmethod
    def _cycle_definition(cls, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "cycle_id": record["cycle_id"],
            "entity_label": record["entity_label"],
            "period_label": record["period_label"],
            "period_start": record["period_start"],
            "period_end": record["period_end"],
            "target_completion_date": record.get("target_completion_date"),
            "description": record["description"],
            "created_by": record["created_by"],
            "created_by_user_id": record.get(
                "created_by_user_id", record["created_by"]["user_id"]
            ),
            "created_at": record["created_at"],
            "idempotency_key": record["idempotency_key"],
            "request_sha256": record["request_sha256"],
            "authority_effect": "none",
            "close_effect": "none",
            "approval_effect": "none",
            "posting_effect": "none",
            "erp_write": False,
        }

    @classmethod
    def _control_definition(cls, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "control_id": record["control_id"],
            "cycle_id": record["cycle_id"],
            "title": record["title"],
            "description": record["description"],
            "planned_date": record.get("planned_date"),
            "preparer": record["preparer"],
            "preparer_user_id": record.get(
                "preparer_user_id", record["preparer"]["user_id"]
            ),
            "reviewer": record["reviewer"],
            "reviewer_user_id": record.get(
                "reviewer_user_id", record["reviewer"]["user_id"]
            ),
            "created_by": record["created_by"],
            "created_by_user_id": record.get(
                "created_by_user_id", record["created_by"]["user_id"]
            ),
            "created_at": record["created_at"],
            "idempotency_key": record["idempotency_key"],
            "request_sha256": record["request_sha256"],
            "authority_effect": "none",
            "close_effect": "none",
        }

    @classmethod
    def _template_definition(cls, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "template_id": record["template_id"],
            "created_by": record["created_by"],
            "created_by_user_id": record.get(
                "created_by_user_id", record["created_by"]["user_id"]
            ),
            "created_at": record["created_at"],
            "idempotency_key": record["idempotency_key"],
            "request_sha256": record["request_sha256"],
            "authority_effect": "none",
            "policy_effect": "none",
            "automation_effect": "none",
        }

    @classmethod
    def _template_item_basis(cls, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "item_id": record["item_id"],
            "template_id": record["template_id"],
            "template_version": record["template_version"],
            "ordinal": record["ordinal"],
            "title": record["title"],
            "description": record["description"],
            "planned_offset_days": record["planned_offset_days"],
            "preparer": record["preparer"],
            "preparer_user_id": record.get(
                "preparer_user_id", record["preparer"]["user_id"]
            ),
            "reviewer": record["reviewer"],
            "reviewer_user_id": record.get(
                "reviewer_user_id", record["reviewer"]["user_id"]
            ),
            "authority_effect": "none",
            "policy_effect": "none",
        }

    @classmethod
    def _template_version_basis(cls, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "template_id": record["template_id"],
            "version": record["version"],
            "title": record["title"],
            "description": record["description"],
            "change_note": record["change_note"],
            "status": "local_user_authored_planning_draft",
            "created_by": record["created_by"],
            "created_by_user_id": record.get(
                "created_by_user_id", record["created_by"]["user_id"]
            ),
            "created_at": record["created_at"],
            "idempotency_key": record["idempotency_key"],
            "request_sha256": record["request_sha256"],
            "previous_version_sha256": record["previous_version_sha256"],
            "item_sha256": [item["item_sha256"] for item in record["items"]],
            "policy_effect": "none",
            "automation_effect": "none",
        }

    @classmethod
    def _template_event_basis(cls, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_id": record["event_id"],
            "template_id": record["template_id"],
            "event_type": record["event_type"],
            "actor": record["actor"],
            "actor_user_id": record.get(
                "actor_user_id", record["actor"]["user_id"]
            ),
            "occurred_at": record["occurred_at"],
            "details": record["details"],
            "sequence": record["sequence"],
            "idempotency_key": record["idempotency_key"],
            "request_sha256": record["request_sha256"],
            "previous_hash": record["previous_hash"],
            "schema_version": "1.0",
            "authority_effect": "none",
            "policy_effect": "none",
            "automation_effect": "none",
        }

    @classmethod
    def _cycle_template_snapshot_basis(
        cls,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "snapshot_id": record["snapshot_id"],
            "cycle_id": record["cycle_id"],
            "template_id": record["template_id"],
            "template_version": record["template_version"],
            "template_version_sha256": record["template_version_sha256"],
            "calendar_anchor_date": record["calendar_anchor_date"],
            "snapshot": record["snapshot"],
            "created_by": record["created_by"],
            "created_by_user_id": record.get(
                "created_by_user_id", record["created_by"]["user_id"]
            ),
            "created_at": record["created_at"],
            "idempotency_key": record["idempotency_key"],
            "request_sha256": record["request_sha256"],
            "authority_effect": "none",
            "policy_effect": "none",
            "automation_effect": "none",
            "close_effect": "none",
            "approval_effect": "none",
            "posting_effect": "none",
            "erp_write": False,
        }

    @classmethod
    def _event_basis(cls, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_id": record["event_id"],
            "cycle_id": record["cycle_id"],
            "control_id": record.get("control_id"),
            "event_type": record["event_type"],
            "actor": record["actor"],
            "actor_user_id": record.get(
                "actor_user_id", record["actor"]["user_id"]
            ),
            "occurred_at": record["occurred_at"],
            "details": record["details"],
            "subject_version": record["subject_version"],
            "idempotency_key": record["idempotency_key"],
            "request_sha256": record["request_sha256"],
            "previous_hash": record["previous_hash"],
            "schema_version": "1.0",
            "authority_effect": "none",
            "close_effect": "none",
        }

    @classmethod
    def _decode_cycle(cls, row: sqlite3.Row) -> dict[str, Any]:
        result = {
            "cycle_id": row["cycle_id"],
            "entity_label": row["entity_label"],
            "period_label": row["period_label"],
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "target_completion_date": row["target_completion_date"],
            "description": row["description"],
            "created_by": json.loads(row["created_by_json"]),
            "created_by_user_id": row["created_by_user_id"],
            "created_at": row["created_at"],
            "idempotency_key": row["idempotency_key"],
            "request_sha256": row["request_sha256"],
            "definition_sha256": row["definition_sha256"],
            "authority_effect": row["authority_effect"],
            "close_effect": row["close_effect"],
            "approval_effect": row["approval_effect"],
            "posting_effect": row["posting_effect"],
            "erp_write": bool(row["erp_write"]),
        }
        actual = cls.sha256(cls._cycle_definition(result))
        if actual != result["definition_sha256"]:
            raise FinancialCloseIntegrityError(
                f"Financial close cycle {result['cycle_id']} failed its definition integrity check."
            )
        return result

    @classmethod
    def _decode_control(cls, row: sqlite3.Row) -> dict[str, Any]:
        result = {
            "control_id": row["control_id"],
            "cycle_id": row["cycle_id"],
            "title": row["title"],
            "description": row["description"],
            "planned_date": row["planned_date"],
            "preparer": json.loads(row["preparer_json"]),
            "preparer_user_id": row["preparer_user_id"],
            "reviewer": json.loads(row["reviewer_json"]),
            "reviewer_user_id": row["reviewer_user_id"],
            "created_by": json.loads(row["created_by_json"]),
            "created_by_user_id": row["created_by_user_id"],
            "created_at": row["created_at"],
            "idempotency_key": row["idempotency_key"],
            "request_sha256": row["request_sha256"],
            "definition_sha256": row["definition_sha256"],
            "authority_effect": row["authority_effect"],
            "close_effect": row["close_effect"],
        }
        actual = cls.sha256(cls._control_definition(result))
        if actual != result["definition_sha256"]:
            raise FinancialCloseIntegrityError(
                f"Financial close control {result['control_id']} failed its definition integrity check."
            )
        return result

    @classmethod
    def _decode_template(cls, row: sqlite3.Row) -> dict[str, Any]:
        result = {
            "template_id": row["template_id"],
            "created_by": json.loads(row["created_by_json"]),
            "created_by_user_id": row["created_by_user_id"],
            "created_at": row["created_at"],
            "idempotency_key": row["idempotency_key"],
            "request_sha256": row["request_sha256"],
            "definition_sha256": row["definition_sha256"],
            "authority_effect": row["authority_effect"],
            "policy_effect": row["policy_effect"],
            "automation_effect": row["automation_effect"],
        }
        if cls.sha256(cls._template_definition(result)) != result["definition_sha256"]:
            raise FinancialCloseIntegrityError(
                f"Financial close template {result['template_id']} failed its identity integrity check."
            )
        return result

    @classmethod
    def _decode_template_item(cls, row: sqlite3.Row) -> dict[str, Any]:
        result = {
            "item_id": row["item_id"],
            "template_id": row["template_id"],
            "template_version": row["template_version"],
            "ordinal": row["ordinal"],
            "title": row["title"],
            "description": row["description"],
            "planned_offset_days": row["planned_offset_days"],
            "preparer": json.loads(row["preparer_json"]),
            "preparer_user_id": row["preparer_user_id"],
            "reviewer": json.loads(row["reviewer_json"]),
            "reviewer_user_id": row["reviewer_user_id"],
            "item_sha256": row["item_sha256"],
            "authority_effect": row["authority_effect"],
            "policy_effect": row["policy_effect"],
        }
        if cls.sha256(cls._template_item_basis(result)) != result["item_sha256"]:
            raise FinancialCloseIntegrityError(
                f"Financial close template item {result['item_id']} failed its integrity check."
            )
        return result

    @classmethod
    def _decode_template_event(cls, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "event_id": row["event_id"],
            "template_id": row["template_id"],
            "event_type": row["event_type"],
            "actor": json.loads(row["actor_json"]),
            "actor_user_id": row["actor_user_id"],
            "occurred_at": row["occurred_at"],
            "details": json.loads(row["details_json"]),
            "sequence": row["sequence"],
            "idempotency_key": row["idempotency_key"],
            "request_sha256": row["request_sha256"],
            "previous_hash": row["previous_hash"],
            "record_hash": row["record_hash"],
            "schema_version": row["schema_version"],
            "authority_effect": row["authority_effect"],
            "policy_effect": row["policy_effect"],
            "automation_effect": row["automation_effect"],
        }

    @classmethod
    def _decode_cycle_template_snapshot(cls, row: sqlite3.Row) -> dict[str, Any]:
        result = {
            "snapshot_id": row["snapshot_id"],
            "cycle_id": row["cycle_id"],
            "template_id": row["template_id"],
            "template_version": row["template_version"],
            "template_version_sha256": row["template_version_sha256"],
            "calendar_anchor_date": row["calendar_anchor_date"],
            "snapshot": json.loads(row["snapshot_json"]),
            "created_by": json.loads(row["created_by_json"]),
            "created_by_user_id": row["created_by_user_id"],
            "created_at": row["created_at"],
            "idempotency_key": row["idempotency_key"],
            "request_sha256": row["request_sha256"],
            "snapshot_sha256": row["snapshot_sha256"],
            "authority_effect": row["authority_effect"],
            "policy_effect": row["policy_effect"],
            "automation_effect": row["automation_effect"],
            "close_effect": row["close_effect"],
            "approval_effect": row["approval_effect"],
            "posting_effect": row["posting_effect"],
            "erp_write": bool(row["erp_write"]),
        }
        actual = cls.sha256(cls._cycle_template_snapshot_basis(result))
        if actual != result["snapshot_sha256"]:
            raise FinancialCloseIntegrityError(
                f"Financial close cycle snapshot {result['snapshot_id']} failed its integrity check."
            )
        return result

    @classmethod
    def _decode_event(cls, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "event_id": row["event_id"],
            "cycle_id": row["cycle_id"],
            "control_id": row["control_id"],
            "event_type": row["event_type"],
            "actor": json.loads(row["actor_json"]),
            "actor_user_id": row["actor_user_id"],
            "occurred_at": row["occurred_at"],
            "details": json.loads(row["details_json"]),
            "subject_version": row["subject_version"],
            "idempotency_key": row["idempotency_key"],
            "request_sha256": row["request_sha256"],
            "previous_hash": row["previous_hash"],
            "record_hash": row["record_hash"],
            "schema_version": row["schema_version"],
            "authority_effect": row["authority_effect"],
            "close_effect": row["close_effect"],
        }

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        control_id = record.get("control_id")
        if control_id is None:
            prior = connection.execute(
                """
                SELECT * FROM fc_control_events
                WHERE cycle_id = ? AND control_id IS NULL
                ORDER BY subject_version DESC, rowid DESC LIMIT 1
                """,
                (record["cycle_id"],),
            ).fetchone()
        else:
            prior = connection.execute(
                """
                SELECT * FROM fc_control_events
                WHERE control_id = ?
                ORDER BY subject_version DESC, rowid DESC LIMIT 1
                """,
                (control_id,),
            ).fetchone()
        previous_hash = prior["record_hash"] if prior else ZERO_HASH
        next_version = int(prior["subject_version"]) + 1 if prior else 1
        if record.get("expected_version") is not None:
            current_version = int(prior["subject_version"]) if prior else 0
            if current_version != record["expected_version"]:
                raise FinancialCloseConflict(
                    "Control version changed. "
                    f"Expected {record['expected_version']}; current version is {current_version}."
                )
        complete = {
            **record,
            "subject_version": next_version,
            "previous_hash": previous_hash,
        }
        record_hash = self.sha256(self._event_basis(complete))
        connection.execute(
            """
            INSERT INTO fc_control_events(
                event_id, cycle_id, control_id, event_type,
                actor_user_id, actor_json, occurred_at, details_json,
                subject_version, idempotency_key, request_sha256,
                previous_hash, record_hash, schema_version,
                authority_effect, close_effect
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '1.0', 'none', 'none')
            """,
            (
                record["event_id"],
                record["cycle_id"],
                control_id,
                record["event_type"],
                record["actor"]["user_id"],
                self.canonical_json(record["actor"]),
                record["occurred_at"],
                self.canonical_json(record["details"]),
                next_version,
                record["idempotency_key"],
                record["request_sha256"],
                previous_hash,
                record_hash,
            ),
        )
        row = connection.execute(
            "SELECT * FROM fc_control_events WHERE event_id = ?",
            (record["event_id"],),
        ).fetchone()
        return self._decode_event(row)

    def _insert_template_event(
        self,
        connection: sqlite3.Connection,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        prior = connection.execute(
            """
            SELECT * FROM fc_template_events
            WHERE template_id = ?
            ORDER BY sequence DESC, rowid DESC LIMIT 1
            """,
            (record["template_id"],),
        ).fetchone()
        previous_hash = prior["record_hash"] if prior else ZERO_HASH
        sequence = int(prior["sequence"]) + 1 if prior else 1
        complete = {
            **record,
            "sequence": sequence,
            "previous_hash": previous_hash,
        }
        record_hash = self.sha256(self._template_event_basis(complete))
        connection.execute(
            """
            INSERT INTO fc_template_events(
                event_id, template_id, event_type, actor_user_id, actor_json,
                occurred_at, details_json, sequence, idempotency_key,
                request_sha256, previous_hash, record_hash, schema_version,
                authority_effect, policy_effect, automation_effect
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '1.0', 'none', 'none', 'none')
            """,
            (
                record["event_id"],
                record["template_id"],
                record["event_type"],
                record["actor"]["user_id"],
                self.canonical_json(record["actor"]),
                record["occurred_at"],
                self.canonical_json(record["details"]),
                sequence,
                record["idempotency_key"],
                record["request_sha256"],
                previous_hash,
                record_hash,
            ),
        )
        row = connection.execute(
            "SELECT * FROM fc_template_events WHERE event_id = ?",
            (record["event_id"],),
        ).fetchone()
        return self._decode_template_event(row)

    def _insert_cycle_record(
        self,
        connection: sqlite3.Connection,
        record: dict[str, Any],
        creation_event: dict[str, Any],
    ) -> dict[str, Any]:
        definition_sha256 = self.sha256(self._cycle_definition(record))
        connection.execute(
            """
            INSERT INTO fc_cycles(
                cycle_id, entity_label, period_label, period_start, period_end,
                target_completion_date, description, created_by_user_id,
                created_by_json, created_at, idempotency_key,
                request_sha256, definition_sha256, authority_effect,
                close_effect, approval_effect, posting_effect, erp_write
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'none', 'none', 'none', 'none', 0)
            """,
            (
                record["cycle_id"],
                record["entity_label"],
                record["period_label"],
                record["period_start"],
                record["period_end"],
                record.get("target_completion_date"),
                record["description"],
                record["created_by"]["user_id"],
                self.canonical_json(record["created_by"]),
                record["created_at"],
                record["idempotency_key"],
                record["request_sha256"],
                definition_sha256,
            ),
        )
        self._insert_event(connection, creation_event)
        row = connection.execute(
            "SELECT * FROM fc_cycles WHERE cycle_id = ?", (record["cycle_id"],)
        ).fetchone()
        return self._decode_cycle(row)

    def _insert_control_record(
        self,
        connection: sqlite3.Connection,
        record: dict[str, Any],
        creation_event: dict[str, Any],
    ) -> dict[str, Any]:
        definition_sha256 = self.sha256(self._control_definition(record))
        connection.execute(
            """
            INSERT INTO fc_control_items(
                control_id, cycle_id, title, description, planned_date,
                preparer_user_id, preparer_json, reviewer_user_id,
                reviewer_json, created_by_user_id, created_by_json,
                created_at, idempotency_key, request_sha256,
                definition_sha256, authority_effect, close_effect
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'none', 'none')
            """,
            (
                record["control_id"],
                record["cycle_id"],
                record["title"],
                record["description"],
                record.get("planned_date"),
                record["preparer"]["user_id"],
                self.canonical_json(record["preparer"]),
                record["reviewer"]["user_id"],
                self.canonical_json(record["reviewer"]),
                record["created_by"]["user_id"],
                self.canonical_json(record["created_by"]),
                record["created_at"],
                record["idempotency_key"],
                record["request_sha256"],
                definition_sha256,
            ),
        )
        self._insert_event(connection, creation_event)
        row = connection.execute(
            "SELECT * FROM fc_control_items WHERE control_id = ?",
            (record["control_id"],),
        ).fetchone()
        return self._decode_control(row)

    def create_cycle(
        self,
        record: dict[str, Any],
        creation_event: dict[str, Any],
    ) -> dict[str, Any]:
        self.initialize()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            existing = connection.execute(
                """
                SELECT * FROM fc_cycles
                WHERE created_by_user_id = ? AND idempotency_key = ?
                """,
                (record["created_by"]["user_id"], record["idempotency_key"]),
            ).fetchone()
            if existing:
                if existing["request_sha256"] != record["request_sha256"]:
                    raise FinancialCloseConflict(
                        "That cycle idempotency key was already used with a different request."
                    )
                connection.commit()
                return self._decode_cycle(existing)
            stored = self._insert_cycle_record(connection, record, creation_event)
            connection.commit()
            return stored
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_control(
        self,
        record: dict[str, Any],
        creation_event: dict[str, Any],
    ) -> dict[str, Any]:
        self.initialize()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            cycle_row = connection.execute(
                "SELECT * FROM fc_cycles WHERE cycle_id = ?", (record["cycle_id"],)
            ).fetchone()
            if cycle_row is None:
                raise FinancialCloseNotFound(
                    f"Financial close cycle {record['cycle_id']} was not found."
                )
            self._decode_cycle(cycle_row)
            cycle_integrity = self._verify_cycle_chain(connection, record["cycle_id"])
            if not cycle_integrity["valid"]:
                raise FinancialCloseIntegrityError(
                    f"Financial close cycle {record['cycle_id']} has a broken evidence chain."
                )
            existing = connection.execute(
                """
                SELECT * FROM fc_control_items
                WHERE created_by_user_id = ? AND idempotency_key = ?
                """,
                (record["created_by"]["user_id"], record["idempotency_key"]),
            ).fetchone()
            if existing:
                if existing["request_sha256"] != record["request_sha256"]:
                    raise FinancialCloseConflict(
                        "That control idempotency key was already used with a different request."
                    )
                connection.commit()
                return self._decode_control(existing)
            stored = self._insert_control_record(
                connection,
                record,
                creation_event,
            )
            connection.commit()
            return stored
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise FinancialCloseConflict(
                "The control could not be created because its immutable identity evidence is invalid."
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def append_control_event(self, record: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            existing = connection.execute(
                """
                SELECT * FROM fc_control_events
                WHERE actor_user_id = ? AND idempotency_key = ?
                """,
                (record["actor"]["user_id"], record["idempotency_key"]),
            ).fetchone()
            if existing:
                if existing["request_sha256"] != record["request_sha256"]:
                    raise FinancialCloseConflict(
                        "That event idempotency key was already used with a different request."
                    )
                connection.commit()
                return self._decode_event(existing)
            control = connection.execute(
                "SELECT * FROM fc_control_items WHERE control_id = ? AND cycle_id = ?",
                (record["control_id"], record["cycle_id"]),
            ).fetchone()
            if control is None:
                raise FinancialCloseNotFound(
                    f"Financial close control {record['control_id']} was not found in cycle {record['cycle_id']}."
                )
            integrity = self._verify_control_chain(connection, record["control_id"])
            if not integrity["valid"]:
                raise FinancialCloseIntegrityError(
                    f"Financial close control {record['control_id']} has a broken evidence chain."
                )
            cycle_integrity = self._verify_cycle_chain(connection, record["cycle_id"])
            if not cycle_integrity["valid"]:
                raise FinancialCloseIntegrityError(
                    f"Financial close cycle {record['cycle_id']} has a broken evidence chain."
                )
            result = self._insert_event(connection, record)
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _load_template_version(
        self,
        connection: sqlite3.Connection,
        template_id: str,
        version: int,
    ) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT * FROM fc_template_versions
            WHERE template_id = ? AND version = ?
            """,
            (template_id, version),
        ).fetchone()
        if row is None:
            raise FinancialCloseNotFound(
                f"Financial close template {template_id} version {version} was not found."
            )
        item_rows = connection.execute(
            """
            SELECT * FROM fc_template_items
            WHERE template_id = ? AND template_version = ?
            ORDER BY ordinal, item_id
            """,
            (template_id, version),
        ).fetchall()
        items = [self._decode_template_item(item) for item in item_rows]
        if not items:
            raise FinancialCloseIntegrityError(
                f"Financial close template {template_id} version {version} has no planning items."
            )
        result = {
            "template_id": row["template_id"],
            "version": row["version"],
            "title": row["title"],
            "description": row["description"],
            "change_note": row["change_note"],
            "status": row["status"],
            "created_by": json.loads(row["created_by_json"]),
            "created_by_user_id": row["created_by_user_id"],
            "created_at": row["created_at"],
            "idempotency_key": row["idempotency_key"],
            "request_sha256": row["request_sha256"],
            "previous_version_sha256": row["previous_version_sha256"],
            "version_sha256": row["version_sha256"],
            "policy_effect": row["policy_effect"],
            "automation_effect": row["automation_effect"],
            "items": items,
        }
        actual = self.sha256(self._template_version_basis(result))
        if actual != result["version_sha256"]:
            raise FinancialCloseIntegrityError(
                f"Financial close template {template_id} version {version} failed its integrity check."
            )
        return result

    def _list_template_versions(
        self,
        connection: sqlite3.Connection,
        template_id: str,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT version FROM fc_template_versions
            WHERE template_id = ? ORDER BY version
            """,
            (template_id,),
        ).fetchall()
        versions = [
            self._load_template_version(connection, template_id, int(row["version"]))
            for row in rows
        ]
        expected_previous = ZERO_HASH
        for expected_version, version in enumerate(versions, start=1):
            if (
                version["version"] != expected_version
                or version["previous_version_sha256"] != expected_previous
            ):
                raise FinancialCloseIntegrityError(
                    f"Financial close template {template_id} has a broken version lineage."
                )
            expected_previous = version["version_sha256"]
        return versions

    def _verify_template_event_chain(
        self,
        connection: sqlite3.Connection,
        template_id: str,
    ) -> dict[str, Any]:
        rows = connection.execute(
            """
            SELECT * FROM fc_template_events
            WHERE template_id = ? ORDER BY sequence, rowid
            """,
            (template_id,),
        ).fetchall()
        if not rows or rows[0]["event_type"] != "template_created":
            return {
                "valid": False,
                "checked_records": len(rows),
                "first_invalid_event_id": (
                    rows[0]["event_id"] if rows else "missing_template_created_event"
                ),
                "algorithm": "sha256_hash_chain",
            }
        expected_previous = ZERO_HASH
        expected_sequence = 1
        for row in rows:
            event = self._decode_template_event(row)
            actual_hash = self.sha256(self._template_event_basis(event))
            if (
                event["sequence"] != expected_sequence
                or event["previous_hash"] != expected_previous
                or event["record_hash"] != actual_hash
            ):
                return {
                    "valid": False,
                    "checked_records": len(rows),
                    "first_invalid_event_id": event["event_id"],
                    "algorithm": "sha256_hash_chain",
                }
            expected_previous = event["record_hash"]
            expected_sequence += 1
        return {
            "valid": True,
            "checked_records": len(rows),
            "first_invalid_event_id": None,
            "algorithm": "sha256_hash_chain",
        }

    def _verify_template_record_bindings(
        self,
        connection: sqlite3.Connection,
        template_id: str,
        versions: list[dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Bind the valid hash chain to every immutable version and snapshot."""

        def invalid(record_id: str) -> dict[str, Any]:
            return {
                "valid": False,
                "checked_records": len(events),
                "first_invalid_event_id": record_id,
                "algorithm": "sha256_hash_chain",
            }

        if not versions or not events:
            return invalid("missing_template_definition_or_event")

        initial = events[0]
        version_one = versions[0]
        if (
            initial["event_type"] != "template_created"
            or initial["request_sha256"] != version_one["request_sha256"]
            or initial["details"].get("version") != 1
            or initial["details"].get("item_count") != len(version_one["items"])
        ):
            return invalid(initial["event_id"])

        version_events = [
            event
            for event in events
            if event["event_type"] == "template_version_created"
        ]
        if len(version_events) != len(versions) - 1:
            return invalid("template_version_event_count_mismatch")
        for version in versions[1:]:
            matching = [
                event
                for event in version_events
                if event["details"].get("version") == version["version"]
            ]
            if len(matching) != 1:
                return invalid(
                    matching[0]["event_id"]
                    if matching
                    else f"missing_template_version_event:{version['version']}"
                )
            event = matching[0]
            if (
                event["request_sha256"] != version["request_sha256"]
                or event["details"].get("previous_version")
                != version["version"] - 1
                or event["details"].get("previous_version_sha256")
                != version["previous_version_sha256"]
                or event["details"].get("item_count") != len(version["items"])
                or event["details"].get("change_note") != version["change_note"]
            ):
                return invalid(event["event_id"])

        snapshot_rows = connection.execute(
            """
            SELECT * FROM fc_cycle_template_snapshots
            WHERE template_id = ? ORDER BY created_at, snapshot_id
            """,
            (template_id,),
        ).fetchall()
        snapshots = [
            self._decode_cycle_template_snapshot(row) for row in snapshot_rows
        ]
        instantiation_events = [
            event for event in events if event["event_type"] == "cycle_instantiated"
        ]
        if len(instantiation_events) != len(snapshots):
            return invalid("template_instantiation_event_count_mismatch")
        snapshots_by_id = {snapshot["snapshot_id"]: snapshot for snapshot in snapshots}
        for event in instantiation_events:
            snapshot_id = event["details"].get("snapshot_id")
            snapshot = snapshots_by_id.get(snapshot_id)
            if snapshot is None:
                return invalid(event["event_id"])
            if (
                event["request_sha256"] != snapshot["request_sha256"]
                or event["details"].get("cycle_id") != snapshot["cycle_id"]
                or event["details"].get("template_version")
                != snapshot["template_version"]
                or event["details"].get("template_version_sha256")
                != snapshot["template_version_sha256"]
                or event["details"].get("snapshot_sha256")
                != snapshot["snapshot_sha256"]
                or event["details"].get("calendar_anchor_date")
                != snapshot["calendar_anchor_date"]
            ):
                return invalid(event["event_id"])

        return {
            "valid": True,
            "checked_records": len(events),
            "first_invalid_event_id": None,
            "algorithm": "sha256_hash_chain",
        }

    def _assert_template_record_bindings(
        self,
        connection: sqlite3.Connection,
        template_id: str,
        versions: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        integrity = self._verify_template_event_chain(connection, template_id)
        if not integrity["valid"]:
            raise FinancialCloseIntegrityError(
                f"Financial close template {template_id} has a broken event chain."
            )
        event_rows = connection.execute(
            """
            SELECT * FROM fc_template_events
            WHERE template_id = ? ORDER BY sequence, rowid
            """,
            (template_id,),
        ).fetchall()
        events = [self._decode_template_event(row) for row in event_rows]
        integrity = self._verify_template_record_bindings(
            connection,
            template_id,
            versions,
            events,
        )
        if not integrity["valid"]:
            raise FinancialCloseIntegrityError(
                f"Financial close template {template_id} has an event-to-record binding failure at {integrity['first_invalid_event_id']}."
            )
        return events, integrity

    def _template_bundle(
        self,
        connection: sqlite3.Connection,
        template_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM fc_control_templates WHERE template_id = ?",
            (template_id,),
        ).fetchone()
        if row is None:
            raise FinancialCloseNotFound(
                f"Financial close template {template_id} was not found."
            )
        template = self._decode_template(row)
        versions = self._list_template_versions(connection, template_id)
        if not versions:
            raise FinancialCloseIntegrityError(
                f"Financial close template {template_id} has no immutable version."
            )
        events, integrity = self._assert_template_record_bindings(
            connection,
            template_id,
            versions,
        )
        return {
            "template": template,
            "versions": versions,
            "events": events,
            "integrity": integrity,
        }

    def _insert_template_version(
        self,
        connection: sqlite3.Connection,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        prepared_items: list[dict[str, Any]] = []
        for item in record["items"]:
            prepared = {**item}
            prepared["item_sha256"] = self.sha256(
                self._template_item_basis(prepared)
            )
            prepared_items.append(prepared)
        complete = {**record, "items": prepared_items}
        version_sha256 = self.sha256(self._template_version_basis(complete))
        connection.execute(
            """
            INSERT INTO fc_template_versions(
                template_id, version, title, description, change_note, status,
                created_by_user_id, created_by_json, created_at,
                idempotency_key, request_sha256, previous_version_sha256,
                version_sha256, policy_effect, automation_effect
            ) VALUES (?, ?, ?, ?, ?, 'local_user_authored_planning_draft', ?, ?, ?, ?, ?, ?, ?, 'none', 'none')
            """,
            (
                record["template_id"],
                record["version"],
                record["title"],
                record["description"],
                record["change_note"],
                record["created_by"]["user_id"],
                self.canonical_json(record["created_by"]),
                record["created_at"],
                record["idempotency_key"],
                record["request_sha256"],
                record["previous_version_sha256"],
                version_sha256,
            ),
        )
        for item in prepared_items:
            connection.execute(
                """
                INSERT INTO fc_template_items(
                    item_id, template_id, template_version, ordinal, title,
                    description, planned_offset_days, preparer_user_id,
                    preparer_json, reviewer_user_id, reviewer_json,
                    item_sha256, authority_effect, policy_effect
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'none', 'none')
                """,
                (
                    item["item_id"],
                    item["template_id"],
                    item["template_version"],
                    item["ordinal"],
                    item["title"],
                    item["description"],
                    item["planned_offset_days"],
                    item["preparer"]["user_id"],
                    self.canonical_json(item["preparer"]),
                    item["reviewer"]["user_id"],
                    self.canonical_json(item["reviewer"]),
                    item["item_sha256"],
                ),
            )
        return self._load_template_version(
            connection,
            record["template_id"],
            record["version"],
        )

    def create_template(
        self,
        template_record: dict[str, Any],
        version_record: dict[str, Any],
        creation_event: dict[str, Any],
    ) -> dict[str, Any]:
        self.initialize()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            existing = connection.execute(
                """
                SELECT * FROM fc_control_templates
                WHERE created_by_user_id = ? AND idempotency_key = ?
                """,
                (
                    template_record["created_by"]["user_id"],
                    template_record["idempotency_key"],
                ),
            ).fetchone()
            if existing:
                if existing["request_sha256"] != template_record["request_sha256"]:
                    raise FinancialCloseConflict(
                        "That template idempotency key was already used with a different request."
                    )
                result = self._template_bundle(connection, existing["template_id"])
                connection.commit()
                return result
            definition_sha256 = self.sha256(
                self._template_definition(template_record)
            )
            connection.execute(
                """
                INSERT INTO fc_control_templates(
                    template_id, created_by_user_id, created_by_json, created_at,
                    idempotency_key, request_sha256, definition_sha256,
                    authority_effect, policy_effect, automation_effect
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'none', 'none', 'none')
                """,
                (
                    template_record["template_id"],
                    template_record["created_by"]["user_id"],
                    self.canonical_json(template_record["created_by"]),
                    template_record["created_at"],
                    template_record["idempotency_key"],
                    template_record["request_sha256"],
                    definition_sha256,
                ),
            )
            self._insert_template_version(connection, version_record)
            self._insert_template_event(connection, creation_event)
            result = self._template_bundle(
                connection,
                template_record["template_id"],
            )
            connection.commit()
            return result
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise FinancialCloseConflict(
                "The local planning template could not be created because its immutable identity evidence is invalid."
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_template_version(
        self,
        version_record: dict[str, Any],
        version_event: dict[str, Any],
        *,
        expected_latest_version: int,
    ) -> dict[str, Any]:
        self.initialize()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            template_row = connection.execute(
                "SELECT * FROM fc_control_templates WHERE template_id = ?",
                (version_record["template_id"],),
            ).fetchone()
            if template_row is None:
                raise FinancialCloseNotFound(
                    f"Financial close template {version_record['template_id']} was not found."
                )
            self._decode_template(template_row)
            existing = connection.execute(
                """
                SELECT * FROM fc_template_versions
                WHERE created_by_user_id = ? AND idempotency_key = ?
                """,
                (
                    version_record["created_by"]["user_id"],
                    version_record["idempotency_key"],
                ),
            ).fetchone()
            if existing:
                if existing["request_sha256"] != version_record["request_sha256"]:
                    raise FinancialCloseConflict(
                        "That template-version idempotency key was already used with a different request."
                    )
                result = self._template_bundle(
                    connection,
                    existing["template_id"],
                )
                connection.commit()
                return result
            versions = self._list_template_versions(
                connection,
                version_record["template_id"],
            )
            self._assert_template_record_bindings(
                connection,
                version_record["template_id"],
                versions,
            )
            latest = versions[-1]
            if latest["version"] != expected_latest_version:
                raise FinancialCloseConflict(
                    "Template version changed. "
                    f"Expected {expected_latest_version}; current version is {latest['version']}."
                )
            if version_record["version"] != latest["version"] + 1:
                raise FinancialCloseConflict(
                    "The proposed immutable template version is not the next version."
                )
            if version_record["previous_version_sha256"] != latest["version_sha256"]:
                raise FinancialCloseConflict(
                    "The proposed template version is not bound to the current immutable version hash."
                )
            self._insert_template_version(connection, version_record)
            self._insert_template_event(connection, version_event)
            result = self._template_bundle(
                connection,
                version_record["template_id"],
            )
            connection.commit()
            return result
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise FinancialCloseConflict(
                "The new local planning-template version could not be appended."
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @classmethod
    def cycle_template_snapshot_sha256(cls, record: dict[str, Any]) -> str:
        return cls.sha256(cls._cycle_template_snapshot_basis(record))

    @staticmethod
    def _revalidate_instantiation_identities(
        connection: sqlite3.Connection,
        selected_version: dict[str, Any],
    ) -> None:
        """Recheck assignment preconditions while the write lock is held."""
        for item in selected_version["items"]:
            preparer_user_id = item["preparer_user_id"]
            reviewer_user_id = item["reviewer_user_id"]
            if preparer_user_id == reviewer_user_id:
                raise FinancialCloseConflict(
                    "Template instantiation requires distinct active preparer and reviewer identities for every item."
                )
            rows = connection.execute(
                """
                SELECT user_id, status FROM wf_user_accounts
                WHERE user_id IN (?, ?)
                """,
                (preparer_user_id, reviewer_user_id),
            ).fetchall()
            statuses = {row["user_id"]: row["status"] for row in rows}
            if (
                statuses.get(preparer_user_id) != "active"
                or statuses.get(reviewer_user_id) != "active"
            ):
                raise FinancialCloseConflict(
                    "Template instantiation requires every configured preparer and reviewer to remain active when the atomic write begins."
                )

    def instantiate_template_cycle(
        self,
        *,
        cycle_record: dict[str, Any],
        cycle_event: dict[str, Any],
        control_records: list[tuple[dict[str, Any], dict[str, Any]]],
        snapshot_record: dict[str, Any],
        template_event: dict[str, Any],
    ) -> dict[str, Any]:
        self.initialize()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            existing = connection.execute(
                """
                SELECT * FROM fc_cycle_template_snapshots
                WHERE created_by_user_id = ? AND idempotency_key = ?
                """,
                (
                    snapshot_record["created_by"]["user_id"],
                    snapshot_record["idempotency_key"],
                ),
            ).fetchone()
            if existing:
                if existing["request_sha256"] != snapshot_record["request_sha256"]:
                    raise FinancialCloseConflict(
                        "That template-instantiation idempotency key was already used with a different request."
                    )
                decoded = self._decode_cycle_template_snapshot(existing)
                cycle_row = connection.execute(
                    "SELECT * FROM fc_cycles WHERE cycle_id = ?",
                    (decoded["cycle_id"],),
                ).fetchone()
                if cycle_row is None:
                    raise FinancialCloseIntegrityError(
                        "The idempotent template snapshot has no preserved cycle."
                    )
                result = self._decode_cycle(cycle_row)
                connection.commit()
                return result
            conflicting_cycle = connection.execute(
                """
                SELECT cycle_id FROM fc_cycles
                WHERE created_by_user_id = ? AND idempotency_key = ?
                """,
                (
                    cycle_record["created_by"]["user_id"],
                    cycle_record["idempotency_key"],
                ),
            ).fetchone()
            if conflicting_cycle:
                raise FinancialCloseConflict(
                    "That idempotency key already identifies a cycle without this template snapshot."
                )
            template_row = connection.execute(
                "SELECT * FROM fc_control_templates WHERE template_id = ?",
                (snapshot_record["template_id"],),
            ).fetchone()
            if template_row is None:
                raise FinancialCloseNotFound(
                    f"Financial close template {snapshot_record['template_id']} was not found."
                )
            self._decode_template(template_row)
            versions = self._list_template_versions(
                connection,
                snapshot_record["template_id"],
            )
            selected = next(
                (
                    version
                    for version in versions
                    if version["version"] == snapshot_record["template_version"]
                ),
                None,
            )
            if selected is None:
                raise FinancialCloseNotFound(
                    f"Financial close template {snapshot_record['template_id']} version {snapshot_record['template_version']} was not found."
                )
            if selected["version_sha256"] != snapshot_record["template_version_sha256"]:
                raise FinancialCloseConflict(
                    "The requested template version hash no longer matches the immutable source."
                )
            self._revalidate_instantiation_identities(connection, selected)
            self._assert_template_record_bindings(
                connection,
                snapshot_record["template_id"],
                versions,
            )
            expected_snapshot_sha256 = self.cycle_template_snapshot_sha256(
                snapshot_record
            )
            if expected_snapshot_sha256 != snapshot_record["snapshot_sha256"]:
                raise FinancialCloseConflict(
                    "The proposed cycle template snapshot hash is invalid."
                )
            stored_cycle = self._insert_cycle_record(
                connection,
                cycle_record,
                cycle_event,
            )
            for control_record, control_event in control_records:
                self._insert_control_record(
                    connection,
                    control_record,
                    control_event,
                )
            connection.execute(
                """
                INSERT INTO fc_cycle_template_snapshots(
                    snapshot_id, cycle_id, template_id, template_version,
                    template_version_sha256, calendar_anchor_date,
                    snapshot_json, created_by_user_id, created_by_json,
                    created_at, idempotency_key, request_sha256,
                    snapshot_sha256, authority_effect, policy_effect,
                    automation_effect, close_effect, approval_effect,
                    posting_effect, erp_write
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'none', 'none', 'none', 'none', 'none', 'none', 0)
                """,
                (
                    snapshot_record["snapshot_id"],
                    snapshot_record["cycle_id"],
                    snapshot_record["template_id"],
                    snapshot_record["template_version"],
                    snapshot_record["template_version_sha256"],
                    snapshot_record["calendar_anchor_date"],
                    self.canonical_json(snapshot_record["snapshot"]),
                    snapshot_record["created_by"]["user_id"],
                    self.canonical_json(snapshot_record["created_by"]),
                    snapshot_record["created_at"],
                    snapshot_record["idempotency_key"],
                    snapshot_record["request_sha256"],
                    snapshot_record["snapshot_sha256"],
                ),
            )
            self._insert_template_event(connection, template_event)
            connection.commit()
            return stored_cycle
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise FinancialCloseConflict(
                "The template cycle could not be instantiated atomically from its immutable source snapshot."
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_templates(self) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT template_id FROM fc_control_templates
                ORDER BY created_at DESC, template_id
                """
            ).fetchall()
            return [
                self._template_bundle(connection, row["template_id"])
                for row in rows
            ]
        finally:
            connection.close()

    def get_template(self, template_id: str) -> dict[str, Any]:
        self.initialize()
        connection = self._connection()
        try:
            return self._template_bundle(connection, template_id)
        finally:
            connection.close()

    def get_template_version(
        self,
        template_id: str,
        version: int,
    ) -> dict[str, Any]:
        self.initialize()
        connection = self._connection()
        try:
            template_row = connection.execute(
                "SELECT * FROM fc_control_templates WHERE template_id = ?",
                (template_id,),
            ).fetchone()
            if template_row is None:
                raise FinancialCloseNotFound(
                    f"Financial close template {template_id} was not found."
                )
            self._decode_template(template_row)
            versions = self._list_template_versions(connection, template_id)
            self._assert_template_record_bindings(
                connection,
                template_id,
                versions,
            )
            selected = next(
                (item for item in versions if item["version"] == version),
                None,
            )
            if selected is None:
                raise FinancialCloseNotFound(
                    f"Financial close template {template_id} version {version} was not found."
                )
            return selected
        finally:
            connection.close()

    def get_cycle_template_snapshot(
        self,
        cycle_id: str,
    ) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT * FROM fc_cycle_template_snapshots WHERE cycle_id = ?
                """,
                (cycle_id,),
            ).fetchone()
            return self._decode_cycle_template_snapshot(row) if row else None
        finally:
            connection.close()

    def get_event_by_idempotency(
        self,
        actor_user_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT * FROM fc_control_events
                WHERE actor_user_id = ? AND idempotency_key = ?
                """,
                (actor_user_id, idempotency_key),
            ).fetchone()
            return self._decode_event(row) if row else None
        finally:
            connection.close()

    def get_cycle(self, cycle_id: str) -> dict[str, Any]:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                "SELECT * FROM fc_cycles WHERE cycle_id = ?", (cycle_id,)
            ).fetchone()
            if row is None:
                raise FinancialCloseNotFound(
                    f"Financial close cycle {cycle_id} was not found."
                )
            return self._decode_cycle(row)
        finally:
            connection.close()

    def list_cycles(self) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT * FROM fc_cycles
                ORDER BY period_end DESC, period_start DESC, created_at DESC, cycle_id
                """
            ).fetchall()
            return [self._decode_cycle(row) for row in rows]
        finally:
            connection.close()

    def get_control(self, cycle_id: str, control_id: str) -> dict[str, Any]:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT * FROM fc_control_items
                WHERE cycle_id = ? AND control_id = ?
                """,
                (cycle_id, control_id),
            ).fetchone()
            if row is None:
                raise FinancialCloseNotFound(
                    f"Financial close control {control_id} was not found in cycle {cycle_id}."
                )
            return self._decode_control(row)
        finally:
            connection.close()

    def list_controls(self, cycle_id: str) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT * FROM fc_control_items
                WHERE cycle_id = ?
                ORDER BY
                    CASE WHEN planned_date IS NULL THEN 1 ELSE 0 END,
                    planned_date, created_at, control_id
                """,
                (cycle_id,),
            ).fetchall()
            return [self._decode_control(row) for row in rows]
        finally:
            connection.close()

    def list_events(
        self,
        cycle_id: str,
        control_id: str | None = None,
    ) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            if control_id is None:
                rows = connection.execute(
                    """
                    SELECT * FROM fc_control_events
                    WHERE cycle_id = ?
                    ORDER BY occurred_at, rowid
                    """,
                    (cycle_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM fc_control_events
                    WHERE cycle_id = ? AND control_id = ?
                    ORDER BY subject_version, rowid
                    """,
                    (cycle_id, control_id),
                ).fetchall()
            return [self._decode_event(row) for row in rows]
        finally:
            connection.close()

    def _verify_control_chain(
        self,
        connection: sqlite3.Connection,
        control_id: str,
    ) -> dict[str, Any]:
        rows = connection.execute(
            """
            SELECT * FROM fc_control_events
            WHERE control_id = ?
            ORDER BY subject_version, rowid
            """,
            (control_id,),
        ).fetchall()
        if not rows or rows[0]["event_type"] != "control_created":
            return {
                "valid": False,
                "checked_records": len(rows),
                "first_invalid_event_id": (
                    rows[0]["event_id"] if rows else "missing_control_created_event"
                ),
                "algorithm": "sha256_hash_chain",
            }
        if sum(row["event_type"] == "control_created" for row in rows) != 1:
            duplicate = next(
                row for row in rows[1:] if row["event_type"] == "control_created"
            )
            return {
                "valid": False,
                "checked_records": len(rows),
                "first_invalid_event_id": duplicate["event_id"],
                "algorithm": "sha256_hash_chain",
            }
        expected_previous = ZERO_HASH
        expected_version = 1
        for row in rows:
            event = self._decode_event(row)
            actual_hash = self.sha256(self._event_basis(event))
            if (
                event["subject_version"] != expected_version
                or event["previous_hash"] != expected_previous
                or event["record_hash"] != actual_hash
            ):
                return {
                    "valid": False,
                    "checked_records": len(rows),
                    "first_invalid_event_id": event["event_id"],
                    "algorithm": "sha256_hash_chain",
                }
            expected_previous = event["record_hash"]
            expected_version += 1
        return {
            "valid": True,
            "checked_records": len(rows),
            "first_invalid_event_id": None,
            "algorithm": "sha256_hash_chain",
        }

    def verify_control_chain(self, control_id: str) -> dict[str, Any]:
        self.initialize()
        connection = self._connection()
        try:
            return self._verify_control_chain(connection, control_id)
        finally:
            connection.close()

    def _verify_cycle_chain(
        self,
        connection: sqlite3.Connection,
        cycle_id: str,
    ) -> dict[str, Any]:
        rows = connection.execute(
            """
            SELECT * FROM fc_control_events
            WHERE cycle_id = ? AND control_id IS NULL
            ORDER BY subject_version, rowid
            """,
            (cycle_id,),
        ).fetchall()
        if len(rows) != 1 or rows[0]["event_type"] != "cycle_created":
            return {
                "valid": False,
                "checked_records": len(rows),
                "first_invalid_event_id": (
                    rows[1]["event_id"]
                    if len(rows) > 1
                    else rows[0]["event_id"]
                    if rows
                    else "missing_cycle_created_event"
                ),
                "algorithm": "sha256_hash_chain",
            }
        expected_previous = ZERO_HASH
        expected_version = 1
        for row in rows:
            event = self._decode_event(row)
            actual_hash = self.sha256(self._event_basis(event))
            if (
                event["subject_version"] != expected_version
                or event["previous_hash"] != expected_previous
                or event["record_hash"] != actual_hash
            ):
                return {
                    "valid": False,
                    "checked_records": len(rows),
                    "first_invalid_event_id": event["event_id"],
                    "algorithm": "sha256_hash_chain",
                }
            expected_previous = event["record_hash"]
            expected_version += 1
        return {
            "valid": True,
            "checked_records": len(rows),
            "first_invalid_event_id": None,
            "algorithm": "sha256_hash_chain",
        }

    def verify_cycle_chain(self, cycle_id: str) -> dict[str, Any]:
        self.initialize()
        connection = self._connection()
        try:
            return self._verify_cycle_chain(connection, cycle_id)
        finally:
            connection.close()


financial_close_repository = FinancialCloseRepository()


__all__ = [
    "FinancialCloseConflict",
    "FinancialCloseIntegrityError",
    "FinancialCloseNotFound",
    "FinancialCloseRepository",
    "financial_close_repository",
]
