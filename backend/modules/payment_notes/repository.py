"""Append-oriented local persistence for Payment Notes evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine

from data.mysql import (
    get_engine,
    metadata,
    pn_review_events_table,
    pn_route_reference_activations_table,
    pn_route_references_table,
    pn_runs_table,
)


ZERO_HASH = "0" * 64

_sqlite_locking_configured: set[int] = set()


def _configure_sqlite_locking(engine: Engine) -> None:
    """Make engine.begin() take a real exclusive lock on SQLite.

    pysqlite manages its own implicit transaction independently of
    SQLAlchemy's BEGIN/COMMIT, which can silently drop a write under
    concurrent access (see SQLAlchemy's "Serializable isolation" recipe).
    This also upgrades the lock to BEGIN IMMEDIATE so the hash-chain reads
    in activate_route_reference/append_review are correctly serialized
    against concurrent writers - the portable equivalent for MySQL is the
    .with_for_update() locks used in those same methods.
    """

    if engine.dialect.name != "sqlite" or id(engine) in _sqlite_locking_configured:
        return
    _sqlite_locking_configured.add(id(engine))

    @event.listens_for(engine, "connect")
    def _disable_pysqlite_transaction_tracking(dbapi_connection, _record) -> None:
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _begin_immediate(connection) -> None:
        connection.exec_driver_sql("BEGIN IMMEDIATE")


class PaymentNotesConflict(RuntimeError):
    """An idempotency or evidence precondition was not met."""


class PaymentNotesNotFound(LookupError):
    """A local Payment Notes record does not exist."""


class PaymentNotesIntegrityError(RuntimeError):
    """Stored Payment Notes evidence failed its hash verification."""


class PaymentNotesRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine
        self._initialized = False

    @property
    def engine(self) -> Engine:
        return self._engine if self._engine is not None else get_engine()

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

    def initialize(self) -> None:
        if self._initialized:
            return
        _configure_sqlite_locking(self.engine)
        metadata.create_all(
            self.engine,
            checkfirst=True,
            tables=[
                pn_route_references_table,
                pn_route_reference_activations_table,
                pn_runs_table,
                pn_review_events_table,
            ],
        )
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
        table = pn_route_references_table
        request = {
            "version_label": version_label,
            "source_sha256": payload["source_sha256"],
            "payload_sha256": self.sha256(payload),
        }
        request_hash = self.sha256(request)
        with self.engine.begin() as connection:
            existing = connection.execute(
                select(table).where(
                    table.c.created_by == actor,
                    table.c.idempotency_key == idempotency_key,
                )
            ).mappings().first()
            if existing:
                if existing["request_sha256"] != request_hash:
                    raise PaymentNotesConflict(
                        "Route-reference idempotency key was reused with different content."
                    )
                return self._route_row(existing)
            same_content = connection.execute(
                select(table).where(
                    table.c.source_sha256 == payload["source_sha256"],
                    table.c.version_label == version_label,
                )
            ).mappings().first()
            if same_content:
                return self._route_row(same_content)
            connection.execute(
                table.insert().values(
                    reference_id=reference_id,
                    version_label=version_label,
                    source_name=payload["source_name"],
                    source_sha256=payload["source_sha256"],
                    source_size=payload["source_size"],
                    parser_version=payload["parser_version"],
                    payload_json=self.canonical_json(payload),
                    payload_sha256=request["payload_sha256"],
                    created_by=actor,
                    created_at=occurred_at,
                    idempotency_key=idempotency_key,
                    request_sha256=request_hash,
                )
            )
            row = connection.execute(
                select(table).where(table.c.reference_id == reference_id)
            ).mappings().first()
            return self._route_row(row)

    def list_route_references(self) -> list[dict[str, Any]]:
        self._ensure_initialized()
        table = pn_route_references_table
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(table).order_by(
                    table.c.created_at.desc(), table.c.reference_id.desc()
                )
            ).mappings().all()
            return [self._route_row(row) for row in rows]

    def get_route_reference(self, reference_id: str) -> dict[str, Any]:
        self._ensure_initialized()
        table = pn_route_references_table
        with self.engine.connect() as connection:
            row = connection.execute(
                select(table).where(table.c.reference_id == reference_id)
            ).mappings().first()
            if row is None:
                raise PaymentNotesNotFound(f"Route reference {reference_id} was not found.")
            return self._route_row(row)

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
        references = pn_route_references_table
        activations = pn_route_reference_activations_table
        request = {"reference_id": reference_id}
        request_hash = self.sha256(request)
        with self.engine.begin() as connection:
            reference = connection.execute(
                select(references.c.reference_id)
                .where(references.c.reference_id == reference_id)
                .with_for_update()
            ).first()
            if reference is None:
                raise PaymentNotesNotFound(
                    f"Route reference {reference_id} was not found."
                )
            existing = connection.execute(
                select(activations).where(
                    activations.c.actor == actor,
                    activations.c.idempotency_key == idempotency_key,
                )
            ).mappings().first()
            if existing:
                if existing["request_sha256"] != request_hash:
                    raise PaymentNotesConflict(
                        "Route activation idempotency key was reused with a different reference."
                    )
                return dict(existing)
            previous = connection.execute(
                select(activations.c.record_hash)
                .order_by(activations.c.sequence.desc())
                .limit(1)
                .with_for_update()
            ).first()
            previous_hash = previous[0] if previous else ZERO_HASH
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
                activations.insert().values(
                    activation_id=activation_id,
                    reference_id=reference_id,
                    actor=actor,
                    occurred_at=occurred_at,
                    idempotency_key=idempotency_key,
                    request_sha256=request_hash,
                    previous_hash=previous_hash,
                    record_hash=record_hash,
                )
            )
            return {**record, "idempotency_key": idempotency_key, "record_hash": record_hash}

    def get_active_route_reference(self) -> dict[str, Any] | None:
        self._ensure_initialized()
        references = pn_route_references_table
        activations = pn_route_reference_activations_table
        with self.engine.connect() as connection:
            activation_rows = connection.execute(
                select(activations).order_by(activations.c.sequence)
            ).mappings().all()
            self._verify_activation_chain(activation_rows)
            row = connection.execute(
                select(
                    references,
                    activations.c.activation_id,
                    activations.c.occurred_at.label("activated_at"),
                    activations.c.actor.label("activated_by"),
                    activations.c.record_hash.label("activation_hash"),
                )
                .select_from(
                    activations.join(
                        references,
                        references.c.reference_id == activations.c.reference_id,
                    )
                )
                .order_by(activations.c.sequence.desc())
                .limit(1)
            ).mappings().first()
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
        table = pn_runs_table
        request = {
            "source_sha256": payload["source"]["sha256"],
            "route_reference_id": payload["route_reference"]["reference_id"],
            "route_reference_sha256": payload["route_reference"]["source_sha256"],
            "date_from": payload["date_from"],
            "date_to": payload["date_to"],
        }
        request_hash = self.sha256(request)
        payload_hash = self.sha256(payload)
        with self.engine.begin() as connection:
            existing = connection.execute(
                select(table).where(
                    table.c.created_by == actor,
                    table.c.idempotency_key == idempotency_key,
                )
            ).mappings().first()
            if existing:
                if existing["request_sha256"] != request_hash:
                    raise PaymentNotesConflict(
                        "Run idempotency key was reused with different source or bounds."
                    )
                return self._run_row(existing, include_payload=True)
            same_scope = connection.execute(
                select(table).where(
                    table.c.source_sha256 == payload["source"]["sha256"],
                    table.c.route_reference_id
                    == payload["route_reference"]["reference_id"],
                    table.c.date_from == payload["date_from"],
                    table.c.date_to == payload["date_to"],
                )
            ).mappings().first()
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
                table.insert().values(
                    run_id=run_id,
                    source_name=payload["source"]["name"],
                    source_sha256=payload["source"]["sha256"],
                    source_size=payload["source"]["size"],
                    route_reference_id=payload["route_reference"]["reference_id"],
                    route_reference_sha256=payload["route_reference"]["source_sha256"],
                    date_from=payload["date_from"],
                    date_to=payload["date_to"],
                    status=payload["status"],
                    deposit_count=len(payload["deposits"]),
                    physical_item_count=len(payload["items"]),
                    quarantined_row_count=len(payload["quarantined_rows"]),
                    payload_json=self.canonical_json(payload),
                    payload_sha256=payload_hash,
                    created_by=actor,
                    created_at=occurred_at,
                    idempotency_key=idempotency_key,
                    request_sha256=request_hash,
                )
            )
            row = connection.execute(
                select(table).where(table.c.run_id == run_id)
            ).mappings().first()
            return self._run_row(row, include_payload=True)

    def get_run(self, run_id: str) -> dict[str, Any]:
        self._ensure_initialized()
        runs = pn_runs_table
        reviews_table = pn_review_events_table
        with self.engine.connect() as connection:
            row = connection.execute(
                select(runs).where(runs.c.run_id == run_id)
            ).mappings().first()
            if row is None:
                raise PaymentNotesNotFound(f"Payment Notes run {run_id} was not found.")
            result = self._run_row(row, include_payload=True)
            reviews = connection.execute(
                select(reviews_table)
                .where(reviews_table.c.run_id == run_id)
                .order_by(reviews_table.c.occurred_at, reviews_table.c.event_id)
            ).mappings().all()
            self._verify_review_chains(reviews)
            result["reviews"] = [dict(review) for review in reviews]
            return result

    def list_runs(self, limit: int, offset: int) -> list[dict[str, Any]]:
        self._ensure_initialized()
        table = pn_runs_table
        bounded = max(1, min(limit, 200))
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(table)
                .order_by(table.c.created_at.desc(), table.c.run_id.desc())
                .limit(bounded)
                .offset(max(0, offset))
            ).mappings().all()
            return [self._run_row(row, include_payload=False) for row in rows]

    def count_runs(self) -> int:
        self._ensure_initialized()
        table = pn_runs_table
        with self.engine.connect() as connection:
            return int(
                connection.execute(select(func.count()).select_from(table)).scalar()
            )

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
        with self.engine.connect() as connection:
            return self._payment_uses_on_connection(
                connection,
                wanted,
                exclude_run_id=exclude_run_id,
            )

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
        runs = pn_runs_table
        reviews_table = pn_review_events_table
        request = {
            "run_id": run_id,
            "item_id": item_id,
            "decision": decision,
            "selected_payment_id": selected_payment_id,
            "reason": reason,
        }
        request_hash = self.sha256(request)
        with self.engine.begin() as connection:
            run_row = connection.execute(
                select(runs).where(runs.c.run_id == run_id).with_for_update()
            ).mappings().first()
            if run_row is None:
                raise PaymentNotesNotFound(f"Payment Notes run {run_id} was not found.")
            existing = connection.execute(
                select(reviews_table).where(
                    reviews_table.c.actor == actor,
                    reviews_table.c.idempotency_key == idempotency_key,
                )
            ).mappings().first()
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
                    select(reviews_table)
                    .where(reviews_table.c.run_id == run_id)
                    .order_by(reviews_table.c.occurred_at, reviews_table.c.event_id)
                ).mappings().all()
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
                select(reviews_table.c.record_hash)
                .where(
                    reviews_table.c.run_id == run_id,
                    reviews_table.c.item_id == item_id,
                )
                .order_by(
                    reviews_table.c.occurred_at.desc(),
                    reviews_table.c.event_id.desc(),
                )
                .limit(1)
                .with_for_update()
            ).first()
            previous_hash = prior[0] if prior else ZERO_HASH
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
                reviews_table.insert().values(
                    event_id=event_id,
                    run_id=run_id,
                    item_id=item_id,
                    decision=decision,
                    selected_payment_id=selected_payment_id,
                    reason=reason,
                    actor=actor,
                    occurred_at=occurred_at,
                    idempotency_key=idempotency_key,
                    request_sha256=request_hash,
                    previous_hash=previous_hash,
                    record_hash=record_hash,
                )
            )
            return {**record, "idempotency_key": idempotency_key, "record_hash": record_hash}

    @classmethod
    def _payment_uses_on_connection(
        cls,
        connection,
        payment_ids: set[str],
        *,
        exclude_run_id: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        runs = pn_runs_table
        reviews_table = pn_review_events_table
        uses: dict[str, list[dict[str, Any]]] = {}
        run_rows = connection.execute(
            select(runs).order_by(runs.c.created_at, runs.c.run_id)
        ).mappings().all()
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
            review_rows = connection.execute(
                select(reviews_table)
                .where(reviews_table.c.run_id.in_(included_run_ids))
                .order_by(
                    reviews_table.c.run_id,
                    reviews_table.c.occurred_at,
                    reviews_table.c.event_id,
                )
            ).mappings().all()
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
    def _route_row(cls, row) -> dict[str, Any]:
        result = dict(row)
        payload = json.loads(result.pop("payload_json"))
        if cls.sha256(payload) != result["payload_sha256"]:
            raise PaymentNotesIntegrityError(
                f"Route reference {result['reference_id']} payload hash is invalid."
            )
        result["payload"] = payload
        return result

    @classmethod
    def _run_row(cls, row, *, include_payload: bool) -> dict[str, Any]:
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
    def _verify_activation_chain(cls, rows) -> None:
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
    def _verify_review_chains(cls, rows) -> None:
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
