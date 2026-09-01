"""SQLAlchemy Core persistence for restart-safe Lockbox preparation."""

from __future__ import annotations

import json
import hashlib
import threading
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import case, func, select
from sqlalchemy.engine import Engine

from data.mysql import (
    get_engine,
    lockbox_preparation_events_table,
    lockbox_preparation_jobs_table,
    lockbox_preparation_transactions_table,
    metadata,
)

from .contracts import SourceTransaction, StartPreparationRequest, dataclass_payload
from .errors import FullCoverageError, IdempotencyConflictError
from .policy import RULE_VERSION
from .reason_codes import build_exception_summary, decorate_transaction
from .states import (
    ACTIVE_TRANSACTION_STATES,
    TERMINAL_TRANSACTION_STATES,
    FileState,
    TransactionState,
    is_terminal_transaction,
    validate_file_transition,
    validate_transaction_transition,
)


SERVICE_VERSION = "lockbox-preparation@0.7.0-wave2-increment4a"

_TABLES = [
    lockbox_preparation_jobs_table,
    lockbox_preparation_transactions_table,
    lockbox_preparation_events_table,
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(
        dataclass_payload(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    return json.loads(value)


class LockboxPreparationRepository:
    """Own durable preparation state without owning operational approval."""

    def __init__(
        self,
        engine: Engine | None = None,
        *,
        rule_version: str = RULE_VERSION,
        service_version: str = SERVICE_VERSION,
    ) -> None:
        self._engine = engine or get_engine()
        self.rule_version = rule_version.strip()
        self.service_version = service_version.strip()
        if not self.rule_version:
            raise ValueError("rule_version is required.")
        if not self.service_version:
            raise ValueError("service_version is required.")
        self._write_lock = threading.RLock()
        self.initialize()

    def initialize(self) -> None:
        with self._write_lock:
            metadata.create_all(self._engine, checkfirst=True, tables=_TABLES)

    def _identity(self, request: StartPreparationRequest) -> tuple[str, str, str]:
        identity_material = (
            f"{request.source_job_id}:{request.source_file_hash}:"
            f"{self.rule_version}"
        )
        job_id = request.job_id.strip() or str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"etop:{identity_material}")
        )
        idempotency_key = (
            request.idempotency_key.strip() or identity_material
        )
        correlation_id = request.correlation_id.strip() or job_id
        return job_id, idempotency_key, correlation_id

    @staticmethod
    def _request_fingerprint(
        transactions: Iterable[SourceTransaction],
    ) -> str:
        payload = [
            dataclass_payload(transaction)
            for transaction in sorted(
                transactions,
                key=lambda item: (item.ordinal, item.transaction_id),
            )
        ]
        return hashlib.sha256(
            _json(payload).encode("utf-8")
        ).hexdigest()

    def _stored_request_fingerprint(
        self,
        connection: Any,
        job_id: str,
    ) -> str:
        table = lockbox_preparation_transactions_table
        rows = connection.execute(
            select(table.c.source_json)
            .where(table.c.job_id == job_id)
            .order_by(table.c.ordinal, table.c.transaction_id)
        ).all()
        return hashlib.sha256(
            _json(
                [_loads(row[0], {}) for row in rows]
            ).encode("utf-8")
        ).hexdigest()

    def register(self, request: StartPreparationRequest) -> dict[str, Any]:
        if not request.source_job_id.strip():
            raise ValueError("source_job_id is required.")
        if not request.source_file_hash.strip():
            raise ValueError("source_file_hash is required.")
        transaction_ids = [
            transaction.transaction_id.strip()
            for transaction in request.transactions
        ]
        if any(not value for value in transaction_ids):
            raise ValueError("Every source transaction needs an ID.")
        if len(set(transaction_ids)) != len(transaction_ids):
            raise ValueError("Source transaction IDs must be unique.")
        ordinals = [transaction.ordinal for transaction in request.transactions]
        if len(set(ordinals)) != len(ordinals):
            raise ValueError("Source transaction ordinals must be unique.")

        job_id, idempotency_key, correlation_id = self._identity(request)
        request_fingerprint = self._request_fingerprint(
            request.transactions
        )
        now = _utc_now()
        jobs = lockbox_preparation_jobs_table
        with self._write_lock, self._engine.begin() as connection:
            existing = connection.execute(
                select(jobs).where(
                    (jobs.c.idempotency_key == idempotency_key)
                    | (jobs.c.job_id == job_id)
                    | (
                        (jobs.c.source_job_id == request.source_job_id)
                        & (jobs.c.source_file_hash == request.source_file_hash)
                        & (jobs.c.rule_version == self.rule_version)
                    )
                )
            ).mappings().first()
            if existing:
                if (
                    existing["source_job_id"] != request.source_job_id
                    or existing["source_file_hash"] != request.source_file_hash
                    or existing["rule_version"] != self.rule_version
                    or int(existing["expected_count"]) != len(request.transactions)
                ):
                    raise IdempotencyConflictError(
                        "The idempotency identity is already bound to "
                        "different source work."
                    )
                existing_fingerprint = str(
                    existing["request_fingerprint"] or ""
                )
                if not existing_fingerprint:
                    existing_fingerprint = self._stored_request_fingerprint(
                        connection,
                        str(existing["job_id"]),
                    )
                    connection.execute(
                        jobs.update()
                        .where(jobs.c.job_id == existing["job_id"])
                        .values(request_fingerprint=existing_fingerprint, updated_at=now)
                    )
                if existing_fingerprint != request_fingerprint:
                    raise IdempotencyConflictError(
                        "The source identity is already bound to a different "
                        "transaction/source fingerprint."
                    )
                return self._get_job(connection, str(existing["job_id"]))

            prior_jobs = connection.execute(
                select(
                    jobs.c.job_id, jobs.c.preparation_generation, jobs.c.rule_version
                )
                .where(
                    jobs.c.source_job_id == request.source_job_id,
                    jobs.c.source_file_hash == request.source_file_hash,
                )
                .order_by(
                    jobs.c.preparation_generation, jobs.c.created_at, jobs.c.job_id
                )
            ).mappings().all()
            preparation_generation = (
                max(
                    (
                        int(row["preparation_generation"])
                        for row in prior_jobs
                    ),
                    default=0,
                )
                + 1
            )

            connection.execute(
                jobs.insert().values(
                    job_id=job_id,
                    source_job_id=request.source_job_id,
                    source_file_hash=request.source_file_hash,
                    source_reference=request.source_reference,
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                    state=FileState.REGISTERED.value,
                    expected_count=len(request.transactions),
                    request_fingerprint=request_fingerprint,
                    preparation_generation=preparation_generation,
                    rule_version=self.rule_version,
                    service_version=self.service_version,
                    created_at=now,
                    updated_at=now,
                )
            )
            self._insert_event(
                connection,
                job_id=job_id,
                event_type="job_registered",
                to_state=FileState.REGISTERED.value,
                payload={
                    "expected_count": len(request.transactions),
                    "source_job_id": request.source_job_id,
                    "source_file_hash": request.source_file_hash,
                    "correlation_id": correlation_id,
                    "preparation_generation": preparation_generation,
                    "rule_version": self.rule_version,
                    "prior_preparation_job_ids": [
                        str(row["job_id"]) for row in prior_jobs
                    ],
                },
                occurred_at=now,
            )
            for transaction in sorted(
                request.transactions,
                key=lambda item: item.ordinal,
            ):
                initial_state = TransactionState.IDENTIFIED
                connection.execute(
                    lockbox_preparation_transactions_table.insert().values(
                        job_id=job_id,
                        transaction_id=transaction.transaction_id,
                        ordinal=transaction.ordinal,
                        state=initial_state.value,
                        source_json=_json(transaction),
                        source_hash=transaction.source_hash,
                        extraction_version=transaction.extraction_version,
                        created_at=now,
                        updated_at=now,
                    )
                )
                self._insert_event(
                    connection,
                    job_id=job_id,
                    transaction_id=transaction.transaction_id,
                    event_type="transaction_identified",
                    to_state=initial_state.value,
                    payload={
                        "ordinal": transaction.ordinal,
                        "source_hash": transaction.source_hash,
                        "extraction_version": transaction.extraction_version,
                    },
                    occurred_at=now,
                )
                if transaction.preexisting_human_disposition is not None:
                    self._transition_transaction_in_connection(
                        connection,
                        job_id,
                        transaction.transaction_id,
                        TransactionState.PREEXISTING_HUMAN_DISPOSITION,
                        result={
                            "source": dataclass_payload(transaction),
                            "preserved_human_disposition": dataclass_payload(
                                transaction.preexisting_human_disposition
                            ),
                        },
                        retry_eligible=False,
                        event_type="human_disposition_preserved",
                    )
                else:
                    self._transition_transaction_in_connection(
                        connection,
                        job_id,
                        transaction.transaction_id,
                        TransactionState.QUEUED,
                        event_type="transaction_queued",
                    )
            self._refresh_counts(connection, job_id)
            return self._get_job(connection, job_id)

    def _insert_event(
        self,
        connection: Any,
        *,
        job_id: str,
        event_type: str,
        payload: Any,
        occurred_at: str,
        transaction_id: str | None = None,
        from_state: str | None = None,
        to_state: str | None = None,
    ) -> None:
        connection.execute(
            lockbox_preparation_events_table.insert().values(
                job_id=job_id,
                transaction_id=transaction_id,
                event_type=event_type,
                from_state=from_state,
                to_state=to_state,
                payload_json=_json(payload),
                occurred_at=occurred_at,
            )
        )

    def append_event(
        self,
        job_id: str,
        event_type: str,
        payload: Any,
        transaction_id: str | None = None,
    ) -> None:
        with self._write_lock, self._engine.begin() as connection:
            self._insert_event(
                connection,
                job_id=job_id,
                transaction_id=transaction_id,
                event_type=event_type,
                payload=payload,
                occurred_at=_utc_now(),
            )

    def transition_file(
        self,
        job_id: str,
        target: FileState | str,
        *,
        event_type: str = "file_state_changed",
        payload: Any = None,
    ) -> bool:
        target_state = FileState(target)
        jobs = lockbox_preparation_jobs_table
        with self._write_lock, self._engine.begin() as connection:
            row = connection.execute(
                select(jobs.c.state, jobs.c.started_at).where(jobs.c.job_id == job_id)
            ).mappings().first()
            if not row:
                raise KeyError(f"Preparation job {job_id} was not found.")
            current = FileState(row["state"])
            if not validate_file_transition(current, target_state):
                return False
            now = _utc_now()
            values: dict[str, Any] = {"state": target_state.value, "updated_at": now}
            if target_state is FileState.RUNNING and row["started_at"] is None:
                values["started_at"] = now
            if target_state is FileState.COMPLETE:
                values["completed_at"] = now
            connection.execute(
                jobs.update().where(jobs.c.job_id == job_id).values(**values)
            )
            self._insert_event(
                connection,
                job_id=job_id,
                event_type=event_type,
                from_state=current.value,
                to_state=target_state.value,
                payload=payload or {},
                occurred_at=now,
            )
            return True

    def _transition_transaction_in_connection(
        self,
        connection: Any,
        job_id: str,
        transaction_id: str,
        target: TransactionState | str,
        *,
        result: Any = None,
        error: Any = None,
        retry_eligible: bool | None = None,
        event_type: str = "transaction_state_changed",
    ) -> bool:
        target_state = TransactionState(target)
        table = lockbox_preparation_transactions_table
        row = connection.execute(
            select(table.c.state, table.c.attempt_count, table.c.retry_eligible).where(
                table.c.job_id == job_id, table.c.transaction_id == transaction_id
            )
        ).mappings().first()
        if not row:
            raise KeyError(
                f"Transaction {transaction_id} was not found in {job_id}."
            )
        current = TransactionState(row["state"])
        if not validate_transaction_transition(current, target_state):
            return False
        now = _utc_now()
        entering_attempt = (
            target_state is TransactionState.RESOLVING_CUSTOMER
        )
        completed_at = (
            now if target_state in TERMINAL_TRANSACTION_STATES else None
        )
        values: dict[str, Any] = {
            "state": target_state.value,
            "retry_eligible": (
                int(retry_eligible)
                if retry_eligible is not None
                else int(row["retry_eligible"])
            ),
            "error_json": _json(error) if error is not None else None,
            "updated_at": now,
            "completed_at": completed_at,
        }
        if entering_attempt:
            values["attempt_count"] = table.c.attempt_count + 1
            values["started_at"] = now
        if result is not None:
            values["result_json"] = _json(result)
        connection.execute(
            table.update()
            .where(table.c.job_id == job_id, table.c.transaction_id == transaction_id)
            .values(**values)
        )
        self._insert_event(
            connection,
            job_id=job_id,
            transaction_id=transaction_id,
            event_type=event_type,
            from_state=current.value,
            to_state=target_state.value,
            payload={
                "result": dataclass_payload(result)
                if result is not None
                else None,
                "error": dataclass_payload(error)
                if error is not None
                else None,
                "retry_eligible": retry_eligible,
            },
            occurred_at=now,
        )
        return True

    def transition_transaction(
        self,
        job_id: str,
        transaction_id: str,
        target: TransactionState | str,
        *,
        result: Any = None,
        error: Any = None,
        retry_eligible: bool | None = None,
        event_type: str = "transaction_state_changed",
    ) -> bool:
        with self._write_lock, self._engine.begin() as connection:
            changed = self._transition_transaction_in_connection(
                connection,
                job_id,
                transaction_id,
                target,
                result=result,
                error=error,
                retry_eligible=retry_eligible,
                event_type=event_type,
            )
            self._refresh_counts(connection, job_id)
            return changed

    def complete_preparation_transaction(
        self,
        job_id: str,
        transaction_id: str,
        terminal_state: TransactionState | str,
        *,
        result: Any,
        error: Any = None,
        retry_eligible: bool = False,
        terminal_event_type: str,
    ) -> None:
        """Persist one completed preparation with one durable commit.

        ERP/customer/open-AR reads happen before this call. The preparation
        worker has already been atomically claimed in RESOLVING_CUSTOMER by
        begin_run(). Recording the remaining analytical states and terminal
        checkpoint together preserves the append-only state/event history
        while avoiding three connection/transaction cycles per check.
        """

        target_state = TransactionState(terminal_state)
        if target_state not in {
            TransactionState.PREPARED_BALANCED,
            TransactionState.PREPARED_EXCEPTION,
        }:
            raise ValueError(
                "A completed preparation must end in a prepared terminal state."
            )

        with self._write_lock, self._engine.begin() as connection:
            self._transition_transaction_in_connection(
                connection,
                job_id,
                transaction_id,
                TransactionState.LOADING_OPEN_AR,
                event_type="open_ar_load_completed",
            )
            self._transition_transaction_in_connection(
                connection,
                job_id,
                transaction_id,
                TransactionState.EVALUATING_ALLOCATION,
                event_type="allocation_evaluation_completed",
            )
            self._transition_transaction_in_connection(
                connection,
                job_id,
                transaction_id,
                target_state,
                result=result,
                error=error,
                retry_eligible=retry_eligible,
                event_type=terminal_event_type,
            )
            self._refresh_counts(connection, job_id)

    def _refresh_counts(
        self,
        connection: Any,
        job_id: str,
    ) -> None:
        table = lockbox_preparation_transactions_table
        counts = connection.execute(
            select(
                func.count().label("expected_count"),
                func.sum(
                    case(
                        (
                            table.c.state.in_(
                                (
                                    TransactionState.PREPARED_BALANCED.value,
                                    TransactionState.PREPARED_EXCEPTION.value,
                                    TransactionState.PREEXISTING_HUMAN_DISPOSITION.value,
                                )
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("terminal_count"),
                func.sum(
                    case(
                        (table.c.state == TransactionState.PREPARED_BALANCED.value, 1),
                        else_=0,
                    )
                ).label("balanced_count"),
                func.sum(
                    case(
                        (table.c.state == TransactionState.PREPARED_EXCEPTION.value, 1),
                        else_=0,
                    )
                ).label("exception_count"),
                func.sum(
                    case(
                        (
                            table.c.state
                            == TransactionState.PREEXISTING_HUMAN_DISPOSITION.value,
                            1,
                        ),
                        else_=0,
                    )
                ).label("preserved_count"),
            ).where(table.c.job_id == job_id)
        ).mappings().first()
        jobs = lockbox_preparation_jobs_table
        connection.execute(
            jobs.update()
            .where(jobs.c.job_id == job_id)
            .values(
                terminal_count=int(counts["terminal_count"] or 0),
                balanced_count=int(counts["balanced_count"] or 0),
                exception_count=int(counts["exception_count"] or 0),
                preserved_count=int(counts["preserved_count"] or 0),
                updated_at=_utc_now(),
            )
        )

    def begin_run(
        self,
        job_id: str,
        *,
        retry_exceptions: bool = False,
    ) -> list[SourceTransaction]:
        jobs = lockbox_preparation_jobs_table
        transactions = lockbox_preparation_transactions_table
        with self._write_lock, self._engine.begin() as connection:
            job = connection.execute(
                select(jobs.c.state).where(jobs.c.job_id == job_id)
            ).mappings().first()
            if not job:
                raise KeyError(f"Preparation job {job_id} was not found.")

            file_state = FileState(job["state"])
            if file_state is FileState.REGISTERED:
                validate_file_transition(file_state, FileState.QUEUED)
                connection.execute(
                    jobs.update()
                    .where(jobs.c.job_id == job_id)
                    .values(state=FileState.QUEUED.value)
                )
                file_state = FileState.QUEUED
            elif file_state is FileState.COMPLETE and retry_exceptions:
                validate_file_transition(file_state, FileState.QUEUED)
                connection.execute(
                    jobs.update()
                    .where(jobs.c.job_id == job_id)
                    .values(state=FileState.QUEUED.value, completed_at=None)
                )
                file_state = FileState.QUEUED

            if retry_exceptions:
                rows = connection.execute(
                    select(transactions.c.transaction_id)
                    .where(
                        transactions.c.job_id == job_id,
                        transactions.c.state == TransactionState.PREPARED_EXCEPTION.value,
                        transactions.c.retry_eligible == 1,
                    )
                    .order_by(transactions.c.ordinal)
                ).all()
                for (transaction_id,) in rows:
                    self._transition_transaction_in_connection(
                        connection,
                        job_id,
                        transaction_id,
                        TransactionState.RETRY_PENDING,
                        event_type="exception_retry_requested",
                    )

            retry_rows = connection.execute(
                select(transactions.c.transaction_id)
                .where(
                    transactions.c.job_id == job_id,
                    transactions.c.state == TransactionState.RETRY_PENDING.value,
                )
                .order_by(transactions.c.ordinal)
            ).all()
            for (transaction_id,) in retry_rows:
                self._transition_transaction_in_connection(
                    connection,
                    job_id,
                    transaction_id,
                    TransactionState.QUEUED,
                    event_type="retry_queued",
                )

            if file_state in {FileState.QUEUED, FileState.RECOVERING}:
                validate_file_transition(file_state, FileState.RUNNING)
                now = _utc_now()
                current_started_at = connection.execute(
                    select(jobs.c.started_at).where(jobs.c.job_id == job_id)
                ).scalar()
                connection.execute(
                    jobs.update()
                    .where(jobs.c.job_id == job_id)
                    .values(
                        state=FileState.RUNNING.value,
                        started_at=current_started_at or now,
                        updated_at=now,
                    )
                )
                self._insert_event(
                    connection,
                    job_id=job_id,
                    event_type="job_started",
                    from_state=file_state.value,
                    to_state=FileState.RUNNING.value,
                    payload={"retry_exceptions": retry_exceptions},
                    occurred_at=now,
                )

            rows = connection.execute(
                select(transactions.c.transaction_id, transactions.c.source_json)
                .where(
                    transactions.c.job_id == job_id,
                    transactions.c.state == TransactionState.QUEUED.value,
                )
                .order_by(transactions.c.ordinal)
            ).all()
            for transaction_id, _source_json in rows:
                self._transition_transaction_in_connection(
                    connection,
                    job_id,
                    transaction_id,
                    TransactionState.RESOLVING_CUSTOMER,
                    event_type="transaction_claimed",
                )
        return [
            self._source_transaction(_loads(source_json, {}))
            for _transaction_id, source_json in rows
        ]

    def finalize(self, job_id: str) -> dict[str, Any]:
        jobs = lockbox_preparation_jobs_table
        with self._write_lock, self._engine.begin() as connection:
            self._refresh_counts(connection, job_id)
            job = connection.execute(
                select(jobs).where(jobs.c.job_id == job_id)
            ).mappings().first()
            if not job:
                raise KeyError(f"Preparation job {job_id} was not found.")
            if int(job["terminal_count"]) != int(job["expected_count"]):
                raise FullCoverageError(
                    "A Lockbox preparation job cannot complete before every "
                    "source transaction has a terminal state."
                )
            current = FileState(job["state"])
            if current is not FileState.COMPLETE:
                validate_file_transition(current, FileState.COMPLETE)
                now = _utc_now()
                connection.execute(
                    jobs.update()
                    .where(jobs.c.job_id == job_id)
                    .values(state=FileState.COMPLETE.value, completed_at=now, updated_at=now)
                )
                self._insert_event(
                    connection,
                    job_id=job_id,
                    event_type="job_completed",
                    from_state=current.value,
                    to_state=FileState.COMPLETE.value,
                    payload={
                        "expected_count": int(job["expected_count"]),
                        "balanced_count": int(job["balanced_count"]),
                        "exception_count": int(job["exception_count"]),
                        "preserved_count": int(job["preserved_count"]),
                    },
                    occurred_at=now,
                )
            return self._get_job(connection, job_id)

    def recover_incomplete(self) -> list[str]:
        recovered: list[str] = []
        jobs = lockbox_preparation_jobs_table
        transactions = lockbox_preparation_transactions_table
        with self._write_lock, self._engine.begin() as connection:
            job_rows = connection.execute(
                select(jobs.c.job_id, jobs.c.state).where(
                    jobs.c.state.in_(
                        (
                            FileState.REGISTERED.value,
                            FileState.QUEUED.value,
                            FileState.RUNNING.value,
                            FileState.RECOVERING.value,
                        )
                    )
                )
            ).mappings().all()
            now = _utc_now()
            for job in job_rows:
                job_id = str(job["job_id"])
                current = FileState(job["state"])
                if current is FileState.REGISTERED:
                    validate_file_transition(current, FileState.QUEUED)
                    connection.execute(
                        jobs.update()
                        .where(jobs.c.job_id == job_id)
                        .values(state=FileState.QUEUED.value, updated_at=now)
                    )
                    self._insert_event(
                        connection,
                        job_id=job_id,
                        event_type="registered_job_recovery_queued",
                        from_state=current.value,
                        to_state=FileState.QUEUED.value,
                        payload={},
                        occurred_at=now,
                    )
                    current = FileState.QUEUED
                if current in {FileState.QUEUED, FileState.RUNNING}:
                    validate_file_transition(current, FileState.RECOVERING)
                    connection.execute(
                        jobs.update()
                        .where(jobs.c.job_id == job_id)
                        .values(state=FileState.RECOVERING.value, updated_at=now)
                    )
                    self._insert_event(
                        connection,
                        job_id=job_id,
                        event_type="job_recovered",
                        from_state=current.value,
                        to_state=FileState.RECOVERING.value,
                        payload={},
                        occurred_at=now,
                    )
                rows = connection.execute(
                    select(transactions.c.transaction_id, transactions.c.state)
                    .where(transactions.c.job_id == job_id)
                    .order_by(transactions.c.ordinal)
                ).all()
                for transaction_id, state_value in rows:
                    state = TransactionState(state_value)
                    if state in ACTIVE_TRANSACTION_STATES:
                        self._transition_transaction_in_connection(
                            connection,
                            job_id,
                            transaction_id,
                            TransactionState.RETRY_PENDING,
                            error={
                                "type": "process_restart",
                                "message": (
                                    "Preparation was interrupted by a local "
                                    "backend restart."
                                ),
                            },
                            retry_eligible=True,
                            event_type="transaction_recovered",
                        )
                self._refresh_counts(connection, job_id)
                recovered.append(job_id)
        return recovered

    def _get_job(self, connection: Any, job_id: str) -> dict[str, Any]:
        jobs = lockbox_preparation_jobs_table
        transactions = lockbox_preparation_transactions_table
        job = connection.execute(
            select(jobs).where(jobs.c.job_id == job_id)
        ).mappings().first()
        if not job:
            raise KeyError(f"Preparation job {job_id} was not found.")
        transaction_rows = connection.execute(
            select(transactions)
            .where(transactions.c.job_id == job_id)
            .order_by(transactions.c.ordinal)
        ).mappings().all()
        complete = (
            job["state"] == FileState.COMPLETE.value
            and int(job["terminal_count"]) == int(job["expected_count"])
        )
        transaction_payloads = [
            decorate_transaction(
                {
                    **dict(row),
                    "source": _loads(row["source_json"], {}),
                    "result": _loads(row["result_json"], None),
                    "error": _loads(row["error_json"], None),
                }
            )
            for row in transaction_rows
        ]
        return {
            **dict(job),
            "complete": complete,
            "counts_final": complete,
            "final_exception_count": (
                int(job["exception_count"]) if complete else None
            ),
            "exception_reason_summary": build_exception_summary(
                transaction_payloads
            ),
            "transactions": transaction_payloads,
        }

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._engine.connect() as connection:
            return self._get_job(connection, job_id)

    def get_current_job(
        self,
        source_job_id: str,
        source_file_hash: str,
    ) -> dict[str, Any]:
        """Return the current-rule generation without creating work."""

        jobs = lockbox_preparation_jobs_table
        with self._engine.connect() as connection:
            row = connection.execute(
                select(jobs.c.job_id)
                .where(
                    jobs.c.source_job_id == source_job_id,
                    jobs.c.source_file_hash == source_file_hash.strip().lower(),
                    jobs.c.rule_version == self.rule_version,
                )
                .order_by(jobs.c.preparation_generation.desc(), jobs.c.created_at.desc())
                .limit(1)
            ).first()
            if not row:
                raise KeyError(
                    "No governed preparation exists for the current source "
                    "hash and rule version."
                )
            return self._get_job(connection, str(row[0]))

    def get_job_for_rule(
        self,
        source_job_id: str,
        source_file_hash: str,
        rule_version: str,
        *,
        service_version: str | None = None,
    ) -> dict[str, Any]:
        """Read one exact historical governed generation.

        Increment 3I uses this read-only lookup to bind its supplemental
        candidate generation to the accepted Increment 3F R1 control.  It
        never updates, retries, or relabels the historical row.
        """

        jobs = lockbox_preparation_jobs_table
        query = select(jobs.c.job_id).where(
            jobs.c.source_job_id == source_job_id,
            jobs.c.source_file_hash == source_file_hash.strip().lower(),
            jobs.c.rule_version == rule_version.strip(),
        )
        if service_version is not None:
            query = query.where(jobs.c.service_version == service_version.strip())
        query = query.order_by(
            jobs.c.preparation_generation.desc(), jobs.c.created_at.desc()
        ).limit(1)
        with self._engine.connect() as connection:
            row = connection.execute(query).first()
            if not row:
                raise KeyError(
                    "No preparation exists for the exact source, rule, and "
                    "service identity."
                )
            return self._get_job(connection, str(row[0]))

    def get_transaction(
        self,
        job_id: str,
        transaction_id: str,
    ) -> dict[str, Any]:
        table = lockbox_preparation_transactions_table
        with self._engine.connect() as connection:
            row = connection.execute(
                select(table).where(
                    table.c.job_id == job_id, table.c.transaction_id == transaction_id
                )
            ).mappings().first()
        if not row:
            raise KeyError(
                f"Transaction {transaction_id} was not found in {job_id}."
            )
        return decorate_transaction(
            {
                **dict(row),
                "source": _loads(row["source_json"], {}),
                "result": _loads(row["result_json"], None),
                "error": _loads(row["error_json"], None),
            }
        )

    def list_events(self, job_id: str) -> list[dict[str, Any]]:
        jobs = lockbox_preparation_jobs_table
        events = lockbox_preparation_events_table
        with self._engine.connect() as connection:
            exists = connection.execute(
                select(jobs.c.job_id).where(jobs.c.job_id == job_id)
            ).first()
            if not exists:
                raise KeyError(f"Preparation job {job_id} was not found.")
            rows = connection.execute(
                select(events)
                .where(events.c.job_id == job_id)
                .order_by(events.c.event_id)
            ).mappings().all()
        return [
            {
                **dict(row),
                "payload": _loads(row["payload_json"], {}),
            }
            for row in rows
        ]

    def list_incomplete_jobs(self) -> list[str]:
        jobs = lockbox_preparation_jobs_table
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(jobs.c.job_id)
                .where(jobs.c.state != FileState.COMPLETE.value)
                .order_by(jobs.c.created_at)
            ).all()
        return [str(row[0]) for row in rows]

    @staticmethod
    def _source_transaction(payload: dict[str, Any]) -> SourceTransaction:
        payment_date = payload.get("payment_date")
        return SourceTransaction(
            transaction_id=str(payload["transaction_id"]),
            ordinal=int(payload["ordinal"]),
            check_amount=Decimal(str(payload["check_amount"])),
            extracted_invoice_numbers=tuple(
                str(value)
                for value in payload.get("extracted_invoice_numbers", [])
            ),
            original_source=payload.get("original_source", {}),
            extraction_version=str(
                payload.get("extraction_version") or "unknown"
            ),
            source_reference=str(payload.get("source_reference") or ""),
            source_hash=str(payload.get("source_hash") or ""),
            payment_date=(
                date.fromisoformat(str(payment_date))
                if payment_date
                else None
            ),
            remittance_evidence_complete=bool(
                payload.get("remittance_evidence_complete")
            ),
            projection_evidence=payload.get("projection_evidence", {}),
            preexisting_human_disposition=payload.get(
                "preexisting_human_disposition"
            ),
        )

    def assert_terminal_coverage(self, job_id: str) -> None:
        job = self.get_job(job_id)
        terminal = sum(
            1
            for transaction in job["transactions"]
            if is_terminal_transaction(transaction["state"])
        )
        if terminal != int(job["expected_count"]):
            raise FullCoverageError(
                f"Terminal coverage is {terminal}/{job['expected_count']}."
            )

    def count_states(self, job_id: str) -> dict[str, int]:
        table = lockbox_preparation_transactions_table
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(table.c.state, func.count().label("count"))
                .where(table.c.job_id == job_id)
                .group_by(table.c.state)
            ).all()
        return {str(state): int(count) for state, count in rows}

    def mark_transactions_for_test(
        self,
        job_id: str,
        transaction_ids: Iterable[str],
        state: TransactionState,
    ) -> None:
        """Test-only helper is intentionally explicit and state-validated."""

        for transaction_id in transaction_ids:
            self.transition_transaction(
                job_id,
                transaction_id,
                state,
                result={"test_fixture": True},
                retry_eligible=False,
                event_type="test_fixture_transition",
            )
