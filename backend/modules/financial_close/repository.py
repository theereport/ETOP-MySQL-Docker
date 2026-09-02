from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from data.mysql import (
    fc_control_events_table,
    fc_control_items_table,
    fc_control_templates_table,
    fc_cycle_template_snapshots_table,
    fc_cycles_table,
    fc_template_events_table,
    fc_template_items_table,
    fc_template_versions_table,
    get_engine,
    metadata,
    wf_user_accounts_table,
)


ZERO_HASH = "0" * 64

_FC_TABLES = [
    fc_cycles_table,
    fc_control_items_table,
    fc_control_events_table,
    fc_control_templates_table,
    fc_template_versions_table,
    fc_template_items_table,
    fc_template_events_table,
    fc_cycle_template_snapshots_table,
]


class FinancialCloseConflict(RuntimeError):
    """An idempotency, version, or lifecycle precondition was not met."""


class FinancialCloseNotFound(LookupError):
    """A local close-readiness record was not found."""


class FinancialCloseIntegrityError(RuntimeError):
    """Stored close-readiness evidence failed its integrity check."""


class FinancialCloseRepository:
    """Immutable close definitions and append-only control evidence."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialization_lock = threading.Lock()

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
            metadata.create_all(self._engine, checkfirst=True, tables=_FC_TABLES)

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
    def _decode_cycle(cls, row: Any) -> dict[str, Any]:
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
    def _decode_control(cls, row: Any) -> dict[str, Any]:
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
    def _decode_template(cls, row: Any) -> dict[str, Any]:
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
    def _decode_template_item(cls, row: Any) -> dict[str, Any]:
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
    def _decode_template_event(cls, row: Any) -> dict[str, Any]:
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
    def _decode_cycle_template_snapshot(cls, row: Any) -> dict[str, Any]:
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
    def _decode_event(cls, row: Any) -> dict[str, Any]:
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
        connection: Any,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        table = fc_control_events_table
        control_id = record.get("control_id")
        if control_id is None:
            prior = connection.execute(
                select(table)
                .where(table.c.cycle_id == record["cycle_id"], table.c.control_id.is_(None))
                .order_by(table.c.subject_version.desc(), table.c.sequence.desc())
                .limit(1)
                .with_for_update()
            ).mappings().first()
        else:
            prior = connection.execute(
                select(table)
                .where(table.c.control_id == control_id)
                .order_by(table.c.subject_version.desc(), table.c.sequence.desc())
                .limit(1)
                .with_for_update()
            ).mappings().first()
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
            table.insert().values(
                event_id=record["event_id"],
                cycle_id=record["cycle_id"],
                control_id=control_id,
                event_type=record["event_type"],
                actor_user_id=record["actor"]["user_id"],
                actor_json=self.canonical_json(record["actor"]),
                occurred_at=record["occurred_at"],
                details_json=self.canonical_json(record["details"]),
                subject_version=next_version,
                idempotency_key=record["idempotency_key"],
                request_sha256=record["request_sha256"],
                previous_hash=previous_hash,
                record_hash=record_hash,
                schema_version="1.0",
                authority_effect="none",
                close_effect="none",
            )
        )
        row = connection.execute(
            select(table).where(table.c.event_id == record["event_id"])
        ).mappings().first()
        return self._decode_event(row)

    def _insert_template_event(
        self,
        connection: Any,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        table = fc_template_events_table
        prior = connection.execute(
            select(table)
            .where(table.c.template_id == record["template_id"])
            .order_by(table.c.sequence.desc())
            .limit(1)
            .with_for_update()
        ).mappings().first()
        previous_hash = prior["record_hash"] if prior else ZERO_HASH
        sequence = int(prior["sequence"]) + 1 if prior else 1
        complete = {
            **record,
            "sequence": sequence,
            "previous_hash": previous_hash,
        }
        record_hash = self.sha256(self._template_event_basis(complete))
        connection.execute(
            table.insert().values(
                event_id=record["event_id"],
                template_id=record["template_id"],
                event_type=record["event_type"],
                actor_user_id=record["actor"]["user_id"],
                actor_json=self.canonical_json(record["actor"]),
                occurred_at=record["occurred_at"],
                details_json=self.canonical_json(record["details"]),
                sequence=sequence,
                idempotency_key=record["idempotency_key"],
                request_sha256=record["request_sha256"],
                previous_hash=previous_hash,
                record_hash=record_hash,
                schema_version="1.0",
                authority_effect="none",
                policy_effect="none",
                automation_effect="none",
            )
        )
        row = connection.execute(
            select(table).where(table.c.event_id == record["event_id"])
        ).mappings().first()
        return self._decode_template_event(row)

    def _insert_cycle_record(
        self,
        connection: Any,
        record: dict[str, Any],
        creation_event: dict[str, Any],
    ) -> dict[str, Any]:
        table = fc_cycles_table
        definition_sha256 = self.sha256(self._cycle_definition(record))
        connection.execute(
            table.insert().values(
                cycle_id=record["cycle_id"],
                entity_label=record["entity_label"],
                period_label=record["period_label"],
                period_start=record["period_start"],
                period_end=record["period_end"],
                target_completion_date=record.get("target_completion_date"),
                description=record["description"],
                created_by_user_id=record["created_by"]["user_id"],
                created_by_json=self.canonical_json(record["created_by"]),
                created_at=record["created_at"],
                idempotency_key=record["idempotency_key"],
                request_sha256=record["request_sha256"],
                definition_sha256=definition_sha256,
                authority_effect="none",
                close_effect="none",
                approval_effect="none",
                posting_effect="none",
                erp_write=0,
            )
        )
        self._insert_event(connection, creation_event)
        row = connection.execute(
            select(table).where(table.c.cycle_id == record["cycle_id"])
        ).mappings().first()
        return self._decode_cycle(row)

    def _insert_control_record(
        self,
        connection: Any,
        record: dict[str, Any],
        creation_event: dict[str, Any],
    ) -> dict[str, Any]:
        table = fc_control_items_table
        definition_sha256 = self.sha256(self._control_definition(record))
        connection.execute(
            table.insert().values(
                control_id=record["control_id"],
                cycle_id=record["cycle_id"],
                title=record["title"],
                description=record["description"],
                planned_date=record.get("planned_date"),
                preparer_user_id=record["preparer"]["user_id"],
                preparer_json=self.canonical_json(record["preparer"]),
                reviewer_user_id=record["reviewer"]["user_id"],
                reviewer_json=self.canonical_json(record["reviewer"]),
                created_by_user_id=record["created_by"]["user_id"],
                created_by_json=self.canonical_json(record["created_by"]),
                created_at=record["created_at"],
                idempotency_key=record["idempotency_key"],
                request_sha256=record["request_sha256"],
                definition_sha256=definition_sha256,
                authority_effect="none",
                close_effect="none",
            )
        )
        self._insert_event(connection, creation_event)
        row = connection.execute(
            select(table).where(table.c.control_id == record["control_id"])
        ).mappings().first()
        return self._decode_control(row)

    def create_cycle(
        self,
        record: dict[str, Any],
        creation_event: dict[str, Any],
    ) -> dict[str, Any]:
        self.initialize()
        table = fc_cycles_table
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(table).where(
                    table.c.created_by_user_id == record["created_by"]["user_id"],
                    table.c.idempotency_key == record["idempotency_key"],
                )
            ).mappings().first()
            if existing:
                if existing["request_sha256"] != record["request_sha256"]:
                    raise FinancialCloseConflict(
                        "That cycle idempotency key was already used with a different request."
                    )
                return self._decode_cycle(existing)
            return self._insert_cycle_record(connection, record, creation_event)

    def create_control(
        self,
        record: dict[str, Any],
        creation_event: dict[str, Any],
    ) -> dict[str, Any]:
        self.initialize()
        cycles = fc_cycles_table
        controls = fc_control_items_table
        try:
            with self._engine.begin() as connection:
                cycle_row = connection.execute(
                    select(cycles).where(cycles.c.cycle_id == record["cycle_id"])
                ).mappings().first()
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
                    select(controls).where(
                        controls.c.created_by_user_id == record["created_by"]["user_id"],
                        controls.c.idempotency_key == record["idempotency_key"],
                    )
                ).mappings().first()
                if existing:
                    if existing["request_sha256"] != record["request_sha256"]:
                        raise FinancialCloseConflict(
                            "That control idempotency key was already used with a different request."
                        )
                    return self._decode_control(existing)
                return self._insert_control_record(
                    connection,
                    record,
                    creation_event,
                )
        except IntegrityError as exc:
            raise FinancialCloseConflict(
                "The control could not be created because its immutable identity evidence is invalid."
            ) from exc

    def append_control_event(self, record: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        events = fc_control_events_table
        controls = fc_control_items_table
        try:
            with self._engine.begin() as connection:
                existing = connection.execute(
                    select(events).where(
                        events.c.actor_user_id == record["actor"]["user_id"],
                        events.c.idempotency_key == record["idempotency_key"],
                    )
                ).mappings().first()
                if existing:
                    if existing["request_sha256"] != record["request_sha256"]:
                        raise FinancialCloseConflict(
                            "That event idempotency key was already used with a different request."
                        )
                    return self._decode_event(existing)
                control = connection.execute(
                    select(controls).where(
                        controls.c.control_id == record["control_id"],
                        controls.c.cycle_id == record["cycle_id"],
                    )
                ).mappings().first()
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
                return self._insert_event(connection, record)
        except IntegrityError as exc:
            raise FinancialCloseConflict(
                "The event could not be recorded because its immutable evidence chain identity is invalid."
            ) from exc

    def _load_template_version(
        self,
        connection: Any,
        template_id: str,
        version: int,
    ) -> dict[str, Any]:
        versions = fc_template_versions_table
        items = fc_template_items_table
        row = connection.execute(
            select(versions).where(
                versions.c.template_id == template_id,
                versions.c.version == version,
            )
        ).mappings().first()
        if row is None:
            raise FinancialCloseNotFound(
                f"Financial close template {template_id} version {version} was not found."
            )
        item_rows = connection.execute(
            select(items)
            .where(items.c.template_id == template_id, items.c.template_version == version)
            .order_by(items.c.ordinal, items.c.item_id)
        ).mappings().all()
        decoded_items = [self._decode_template_item(item) for item in item_rows]
        if not decoded_items:
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
            "items": decoded_items,
        }
        actual = self.sha256(self._template_version_basis(result))
        if actual != result["version_sha256"]:
            raise FinancialCloseIntegrityError(
                f"Financial close template {template_id} version {version} failed its integrity check."
            )
        return result

    def _list_template_versions(
        self,
        connection: Any,
        template_id: str,
    ) -> list[dict[str, Any]]:
        table = fc_template_versions_table
        rows = connection.execute(
            select(table.c.version)
            .where(table.c.template_id == template_id)
            .order_by(table.c.version)
        ).all()
        versions = [
            self._load_template_version(connection, template_id, int(row[0]))
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
        connection: Any,
        template_id: str,
    ) -> dict[str, Any]:
        table = fc_template_events_table
        rows = connection.execute(
            select(table)
            .where(table.c.template_id == template_id)
            .order_by(table.c.sequence)
        ).mappings().all()
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
        connection: Any,
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

        table = fc_cycle_template_snapshots_table
        snapshot_rows = connection.execute(
            select(table)
            .where(table.c.template_id == template_id)
            .order_by(table.c.created_at, table.c.snapshot_id)
        ).mappings().all()
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
        connection: Any,
        template_id: str,
        versions: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        integrity = self._verify_template_event_chain(connection, template_id)
        if not integrity["valid"]:
            raise FinancialCloseIntegrityError(
                f"Financial close template {template_id} has a broken event chain."
            )
        table = fc_template_events_table
        event_rows = connection.execute(
            select(table)
            .where(table.c.template_id == template_id)
            .order_by(table.c.sequence)
        ).mappings().all()
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
        connection: Any,
        template_id: str,
    ) -> dict[str, Any]:
        table = fc_control_templates_table
        row = connection.execute(
            select(table).where(table.c.template_id == template_id)
        ).mappings().first()
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
        connection: Any,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        versions = fc_template_versions_table
        items_table = fc_template_items_table
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
            versions.insert().values(
                template_id=record["template_id"],
                version=record["version"],
                title=record["title"],
                description=record["description"],
                change_note=record["change_note"],
                status="local_user_authored_planning_draft",
                created_by_user_id=record["created_by"]["user_id"],
                created_by_json=self.canonical_json(record["created_by"]),
                created_at=record["created_at"],
                idempotency_key=record["idempotency_key"],
                request_sha256=record["request_sha256"],
                previous_version_sha256=record["previous_version_sha256"],
                version_sha256=version_sha256,
                policy_effect="none",
                automation_effect="none",
            )
        )
        for item in prepared_items:
            connection.execute(
                items_table.insert().values(
                    item_id=item["item_id"],
                    template_id=item["template_id"],
                    template_version=item["template_version"],
                    ordinal=item["ordinal"],
                    title=item["title"],
                    description=item["description"],
                    planned_offset_days=item["planned_offset_days"],
                    preparer_user_id=item["preparer"]["user_id"],
                    preparer_json=self.canonical_json(item["preparer"]),
                    reviewer_user_id=item["reviewer"]["user_id"],
                    reviewer_json=self.canonical_json(item["reviewer"]),
                    item_sha256=item["item_sha256"],
                    authority_effect="none",
                    policy_effect="none",
                )
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
        table = fc_control_templates_table
        try:
            with self._engine.begin() as connection:
                existing = connection.execute(
                    select(table).where(
                        table.c.created_by_user_id
                        == template_record["created_by"]["user_id"],
                        table.c.idempotency_key == template_record["idempotency_key"],
                    )
                ).mappings().first()
                if existing:
                    if existing["request_sha256"] != template_record["request_sha256"]:
                        raise FinancialCloseConflict(
                            "That template idempotency key was already used with a different request."
                        )
                    return self._template_bundle(connection, existing["template_id"])
                definition_sha256 = self.sha256(
                    self._template_definition(template_record)
                )
                connection.execute(
                    table.insert().values(
                        template_id=template_record["template_id"],
                        created_by_user_id=template_record["created_by"]["user_id"],
                        created_by_json=self.canonical_json(
                            template_record["created_by"]
                        ),
                        created_at=template_record["created_at"],
                        idempotency_key=template_record["idempotency_key"],
                        request_sha256=template_record["request_sha256"],
                        definition_sha256=definition_sha256,
                        authority_effect="none",
                        policy_effect="none",
                        automation_effect="none",
                    )
                )
                self._insert_template_version(connection, version_record)
                self._insert_template_event(connection, creation_event)
                return self._template_bundle(
                    connection,
                    template_record["template_id"],
                )
        except IntegrityError as exc:
            raise FinancialCloseConflict(
                "The local planning template could not be created because its immutable identity evidence is invalid."
            ) from exc

    def create_template_version(
        self,
        version_record: dict[str, Any],
        version_event: dict[str, Any],
        *,
        expected_latest_version: int,
    ) -> dict[str, Any]:
        self.initialize()
        templates = fc_control_templates_table
        versions_table = fc_template_versions_table
        try:
            with self._engine.begin() as connection:
                template_row = connection.execute(
                    select(templates).where(
                        templates.c.template_id == version_record["template_id"]
                    )
                ).mappings().first()
                if template_row is None:
                    raise FinancialCloseNotFound(
                        f"Financial close template {version_record['template_id']} was not found."
                    )
                self._decode_template(template_row)
                existing = connection.execute(
                    select(versions_table).where(
                        versions_table.c.created_by_user_id
                        == version_record["created_by"]["user_id"],
                        versions_table.c.idempotency_key
                        == version_record["idempotency_key"],
                    )
                ).mappings().first()
                if existing:
                    if existing["request_sha256"] != version_record["request_sha256"]:
                        raise FinancialCloseConflict(
                            "That template-version idempotency key was already used with a different request."
                        )
                    return self._template_bundle(
                        connection,
                        existing["template_id"],
                    )
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
                return self._template_bundle(
                    connection,
                    version_record["template_id"],
                )
        except IntegrityError as exc:
            raise FinancialCloseConflict(
                "The new local planning-template version could not be appended."
            ) from exc

    @classmethod
    def cycle_template_snapshot_sha256(cls, record: dict[str, Any]) -> str:
        return cls.sha256(cls._cycle_template_snapshot_basis(record))

    @staticmethod
    def _revalidate_instantiation_identities(
        connection: Any,
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
                select(
                    wf_user_accounts_table.c.user_id, wf_user_accounts_table.c.status
                ).where(
                    wf_user_accounts_table.c.user_id.in_(
                        [preparer_user_id, reviewer_user_id]
                    )
                )
            ).all()
            statuses = {row[0]: row[1] for row in rows}
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
        snapshots = fc_cycle_template_snapshots_table
        cycles = fc_cycles_table
        templates = fc_control_templates_table
        try:
            with self._engine.begin() as connection:
                existing = connection.execute(
                    select(snapshots).where(
                        snapshots.c.created_by_user_id
                        == snapshot_record["created_by"]["user_id"],
                        snapshots.c.idempotency_key
                        == snapshot_record["idempotency_key"],
                    )
                ).mappings().first()
                if existing:
                    if existing["request_sha256"] != snapshot_record["request_sha256"]:
                        raise FinancialCloseConflict(
                            "That template-instantiation idempotency key was already used with a different request."
                        )
                    decoded = self._decode_cycle_template_snapshot(existing)
                    cycle_row = connection.execute(
                        select(cycles).where(cycles.c.cycle_id == decoded["cycle_id"])
                    ).mappings().first()
                    if cycle_row is None:
                        raise FinancialCloseIntegrityError(
                            "The idempotent template snapshot has no preserved cycle."
                        )
                    return self._decode_cycle(cycle_row)
                conflicting_cycle = connection.execute(
                    select(cycles.c.cycle_id).where(
                        cycles.c.created_by_user_id
                        == cycle_record["created_by"]["user_id"],
                        cycles.c.idempotency_key == cycle_record["idempotency_key"],
                    )
                ).first()
                if conflicting_cycle:
                    raise FinancialCloseConflict(
                        "That idempotency key already identifies a cycle without this template snapshot."
                    )
                template_row = connection.execute(
                    select(templates).where(
                        templates.c.template_id == snapshot_record["template_id"]
                    )
                ).mappings().first()
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
                    snapshots.insert().values(
                        snapshot_id=snapshot_record["snapshot_id"],
                        cycle_id=snapshot_record["cycle_id"],
                        template_id=snapshot_record["template_id"],
                        template_version=snapshot_record["template_version"],
                        template_version_sha256=snapshot_record[
                            "template_version_sha256"
                        ],
                        calendar_anchor_date=snapshot_record["calendar_anchor_date"],
                        snapshot_json=self.canonical_json(
                            snapshot_record["snapshot"]
                        ),
                        created_by_user_id=snapshot_record["created_by"]["user_id"],
                        created_by_json=self.canonical_json(
                            snapshot_record["created_by"]
                        ),
                        created_at=snapshot_record["created_at"],
                        idempotency_key=snapshot_record["idempotency_key"],
                        request_sha256=snapshot_record["request_sha256"],
                        snapshot_sha256=snapshot_record["snapshot_sha256"],
                        authority_effect="none",
                        policy_effect="none",
                        automation_effect="none",
                        close_effect="none",
                        approval_effect="none",
                        posting_effect="none",
                        erp_write=0,
                    )
                )
                self._insert_template_event(connection, template_event)
                return stored_cycle
        except IntegrityError as exc:
            raise FinancialCloseConflict(
                "The template cycle could not be instantiated atomically from its immutable source snapshot."
            ) from exc

    def list_templates(self) -> list[dict[str, Any]]:
        self.initialize()
        table = fc_control_templates_table
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(table.c.template_id).order_by(
                    table.c.created_at.desc(), table.c.template_id
                )
            ).all()
            return [
                self._template_bundle(connection, row[0])
                for row in rows
            ]

    def get_template(self, template_id: str) -> dict[str, Any]:
        self.initialize()
        with self._engine.connect() as connection:
            return self._template_bundle(connection, template_id)

    def get_template_version(
        self,
        template_id: str,
        version: int,
    ) -> dict[str, Any]:
        self.initialize()
        table = fc_control_templates_table
        with self._engine.connect() as connection:
            template_row = connection.execute(
                select(table).where(table.c.template_id == template_id)
            ).mappings().first()
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

    def get_cycle_template_snapshot(
        self,
        cycle_id: str,
    ) -> dict[str, Any] | None:
        self.initialize()
        table = fc_cycle_template_snapshots_table
        with self._engine.connect() as connection:
            row = connection.execute(
                select(table).where(table.c.cycle_id == cycle_id)
            ).mappings().first()
            return self._decode_cycle_template_snapshot(row) if row else None

    def get_event_by_idempotency(
        self,
        actor_user_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        self.initialize()
        table = fc_control_events_table
        with self._engine.connect() as connection:
            row = connection.execute(
                select(table).where(
                    table.c.actor_user_id == actor_user_id,
                    table.c.idempotency_key == idempotency_key,
                )
            ).mappings().first()
            return self._decode_event(row) if row else None

    def get_cycle(self, cycle_id: str) -> dict[str, Any]:
        self.initialize()
        table = fc_cycles_table
        with self._engine.connect() as connection:
            row = connection.execute(
                select(table).where(table.c.cycle_id == cycle_id)
            ).mappings().first()
            if row is None:
                raise FinancialCloseNotFound(
                    f"Financial close cycle {cycle_id} was not found."
                )
            return self._decode_cycle(row)

    def list_cycles(self) -> list[dict[str, Any]]:
        self.initialize()
        table = fc_cycles_table
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(table).order_by(
                    table.c.period_end.desc(),
                    table.c.period_start.desc(),
                    table.c.created_at.desc(),
                    table.c.cycle_id,
                )
            ).mappings().all()
            return [self._decode_cycle(row) for row in rows]

    def get_control(self, cycle_id: str, control_id: str) -> dict[str, Any]:
        self.initialize()
        table = fc_control_items_table
        with self._engine.connect() as connection:
            row = connection.execute(
                select(table).where(
                    table.c.cycle_id == cycle_id, table.c.control_id == control_id
                )
            ).mappings().first()
            if row is None:
                raise FinancialCloseNotFound(
                    f"Financial close control {control_id} was not found in cycle {cycle_id}."
                )
            return self._decode_control(row)

    def list_controls(self, cycle_id: str) -> list[dict[str, Any]]:
        self.initialize()
        table = fc_control_items_table
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(table)
                .where(table.c.cycle_id == cycle_id)
                .order_by(
                    table.c.planned_date.is_(None),
                    table.c.planned_date,
                    table.c.created_at,
                    table.c.control_id,
                )
            ).mappings().all()
            return [self._decode_control(row) for row in rows]

    def list_events(
        self,
        cycle_id: str,
        control_id: str | None = None,
    ) -> list[dict[str, Any]]:
        self.initialize()
        table = fc_control_events_table
        with self._engine.connect() as connection:
            if control_id is None:
                rows = connection.execute(
                    select(table)
                    .where(table.c.cycle_id == cycle_id)
                    .order_by(table.c.occurred_at, table.c.sequence)
                ).mappings().all()
            else:
                rows = connection.execute(
                    select(table)
                    .where(
                        table.c.cycle_id == cycle_id,
                        table.c.control_id == control_id,
                    )
                    .order_by(table.c.subject_version, table.c.sequence)
                ).mappings().all()
            return [self._decode_event(row) for row in rows]

    def _verify_control_chain(
        self,
        connection: Any,
        control_id: str,
    ) -> dict[str, Any]:
        table = fc_control_events_table
        rows = connection.execute(
            select(table)
            .where(table.c.control_id == control_id)
            .order_by(table.c.subject_version, table.c.sequence)
        ).mappings().all()
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
        with self._engine.connect() as connection:
            return self._verify_control_chain(connection, control_id)

    def _verify_cycle_chain(
        self,
        connection: Any,
        cycle_id: str,
    ) -> dict[str, Any]:
        table = fc_control_events_table
        rows = connection.execute(
            select(table)
            .where(table.c.cycle_id == cycle_id, table.c.control_id.is_(None))
            .order_by(table.c.subject_version, table.c.sequence)
        ).mappings().all()
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
        with self._engine.connect() as connection:
            return self._verify_cycle_chain(connection, cycle_id)


financial_close_repository = FinancialCloseRepository()


__all__ = [
    "FinancialCloseConflict",
    "FinancialCloseIntegrityError",
    "FinancialCloseNotFound",
    "FinancialCloseRepository",
    "financial_close_repository",
]
