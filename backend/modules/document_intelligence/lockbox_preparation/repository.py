"""SQLite persistence for restart-safe Lockbox preparation."""

from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import threading
import uuid
from contextlib import closing
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

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


SCHEMA_VERSION = 3
SERVICE_VERSION = "lockbox-preparation@0.7.0-wave2-increment4a"


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


def default_database_path() -> Path:
    configured = os.getenv("ETOP_LOCKBOX_PREPARATION_DB", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    project_root = Path(__file__).resolve().parents[4]
    return project_root / "data" / "etop_state" / "lockbox_preparation.db"


class LockboxPreparationRepository:
    """Own durable preparation state without owning operational approval."""

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        rule_version: str = RULE_VERSION,
        service_version: str = SERVICE_VERSION,
    ) -> None:
        self.database_path = Path(
            database_path or default_database_path()
        ).resolve()
        self.rule_version = rule_version.strip()
        self.service_version = service_version.strip()
        if not self.rule_version:
            raise ValueError("rule_version is required.")
        if not self.service_version:
            raise ValueError("service_version is required.")
        self._write_lock = threading.RLock()
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.database_path,
            timeout=30,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def initialize(self) -> None:
        with self._write_lock, closing(self._connect()) as connection:
            # Journal mode is persistent database configuration. Reapplying it
            # on every short-lived connection is unnecessary and can acquire a
            # file lock, which is especially costly on Windows.
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS preparation_schema (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS preparation_jobs (
                    job_id TEXT PRIMARY KEY,
                    source_job_id TEXT NOT NULL,
                    source_file_hash TEXT NOT NULL,
                    source_reference TEXT NOT NULL DEFAULT '',
                    correlation_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    request_fingerprint TEXT NOT NULL DEFAULT '',
                    preparation_generation INTEGER NOT NULL DEFAULT 1,
                    state TEXT NOT NULL,
                    expected_count INTEGER NOT NULL,
                    terminal_count INTEGER NOT NULL DEFAULT 0,
                    balanced_count INTEGER NOT NULL DEFAULT 0,
                    exception_count INTEGER NOT NULL DEFAULT 0,
                    preserved_count INTEGER NOT NULL DEFAULT 0,
                    rule_version TEXT NOT NULL,
                    service_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    UNIQUE(source_job_id, source_file_hash, rule_version)
                );
                CREATE TABLE IF NOT EXISTS preparation_transactions (
                    job_id TEXT NOT NULL,
                    transaction_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    retry_eligible INTEGER NOT NULL DEFAULT 0,
                    source_json TEXT NOT NULL,
                    source_hash TEXT NOT NULL DEFAULT '',
                    extraction_version TEXT NOT NULL DEFAULT 'unknown',
                    result_json TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    PRIMARY KEY(job_id, transaction_id),
                    UNIQUE(job_id, ordinal),
                    FOREIGN KEY(job_id) REFERENCES preparation_jobs(job_id)
                        ON DELETE RESTRICT
                );
                CREATE TABLE IF NOT EXISTS preparation_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    transaction_id TEXT,
                    event_type TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT,
                    payload_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES preparation_jobs(job_id)
                        ON DELETE RESTRICT
                );
                CREATE INDEX IF NOT EXISTS idx_preparation_transactions_state
                    ON preparation_transactions(job_id, state, ordinal);
                CREATE INDEX IF NOT EXISTS idx_preparation_events_job
                    ON preparation_events(job_id, event_id);
                INSERT OR IGNORE INTO preparation_schema (
                    singleton, schema_version, updated_at
                ) VALUES (1, 3, CURRENT_TIMESTAMP);
                COMMIT;
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(preparation_jobs)"
                ).fetchall()
            }
            if "request_fingerprint" not in columns:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    ALTER TABLE preparation_jobs
                    ADD COLUMN request_fingerprint TEXT NOT NULL DEFAULT ''
                    """
                )
                connection.execute(
                    """
                    UPDATE preparation_schema
                    SET schema_version = ?, updated_at = ?
                    WHERE singleton = 1
                    """,
                    (SCHEMA_VERSION, _utc_now()),
                )
                connection.commit()

            job_columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(preparation_jobs)"
                ).fetchall()
            }
            legacy_source_identity = self._has_unique_index(
                connection,
                "preparation_jobs",
                ("source_job_id", "source_file_hash"),
            )
            if (
                "preparation_generation" not in job_columns
                or legacy_source_identity
            ):
                self._migrate_preparation_jobs_v3(connection)

            connection.execute(
                """
                UPDATE preparation_schema
                SET schema_version = ?, updated_at = ?
                WHERE singleton = 1
                """,
                (SCHEMA_VERSION, _utc_now()),
            )

    @staticmethod
    def _has_unique_index(
        connection: sqlite3.Connection,
        table_name: str,
        columns: tuple[str, ...],
    ) -> bool:
        for index in connection.execute(
            f"PRAGMA index_list({table_name})"
        ).fetchall():
            if not int(index["unique"]):
                continue
            index_columns = tuple(
                str(row["name"])
                for row in connection.execute(
                    f"PRAGMA index_info({index['name']})"
                ).fetchall()
            )
            if index_columns == columns:
                return True
        return False

    def _migrate_preparation_jobs_v3(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """Permit a new governed rule generation without rewriting history."""

        connection.execute("PRAGMA foreign_keys=OFF")
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                CREATE TABLE preparation_jobs_v3 (
                    job_id TEXT PRIMARY KEY,
                    source_job_id TEXT NOT NULL,
                    source_file_hash TEXT NOT NULL,
                    source_reference TEXT NOT NULL DEFAULT '',
                    correlation_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    request_fingerprint TEXT NOT NULL DEFAULT '',
                    preparation_generation INTEGER NOT NULL DEFAULT 1,
                    state TEXT NOT NULL,
                    expected_count INTEGER NOT NULL,
                    terminal_count INTEGER NOT NULL DEFAULT 0,
                    balanced_count INTEGER NOT NULL DEFAULT 0,
                    exception_count INTEGER NOT NULL DEFAULT 0,
                    preserved_count INTEGER NOT NULL DEFAULT 0,
                    rule_version TEXT NOT NULL,
                    service_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    UNIQUE(source_job_id, source_file_hash, rule_version)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO preparation_jobs_v3 (
                    job_id, source_job_id, source_file_hash,
                    source_reference, correlation_id, idempotency_key,
                    request_fingerprint, preparation_generation, state,
                    expected_count, terminal_count, balanced_count,
                    exception_count, preserved_count, rule_version,
                    service_version, created_at, updated_at, started_at,
                    completed_at
                )
                SELECT
                    job_id, source_job_id, source_file_hash,
                    source_reference, correlation_id, idempotency_key,
                    request_fingerprint, 1, state, expected_count,
                    terminal_count, balanced_count, exception_count,
                    preserved_count, rule_version, service_version,
                    created_at, updated_at, started_at, completed_at
                FROM preparation_jobs
                """
            )
            connection.execute("DROP TABLE preparation_jobs")
            connection.execute(
                "ALTER TABLE preparation_jobs_v3 RENAME TO preparation_jobs"
            )
            connection.execute(
                """
                UPDATE preparation_schema
                SET schema_version = ?, updated_at = ?
                WHERE singleton = 1
                """,
                (SCHEMA_VERSION, _utc_now()),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.execute("PRAGMA foreign_keys=ON")

        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(
                "Lockbox preparation schema migration failed foreign-key "
                "integrity validation."
            )

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
        connection: sqlite3.Connection,
        job_id: str,
    ) -> str:
        rows = connection.execute(
            """
            SELECT source_json
            FROM preparation_transactions
            WHERE job_id = ?
            ORDER BY ordinal, transaction_id
            """,
            (job_id,),
        ).fetchall()
        return hashlib.sha256(
            _json(
                [
                    _loads(row["source_json"], {})
                    for row in rows
                ]
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
        with self._write_lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT * FROM preparation_jobs
                WHERE idempotency_key = ?
                   OR job_id = ?
                   OR (
                        source_job_id = ?
                    AND source_file_hash = ?
                    AND rule_version = ?
                   )
                """,
                (
                    idempotency_key,
                    job_id,
                    request.source_job_id,
                    request.source_file_hash,
                    self.rule_version,
                ),
            ).fetchone()
            if existing:
                if (
                    existing["source_job_id"] != request.source_job_id
                    or existing["source_file_hash"] != request.source_file_hash
                    or existing["rule_version"] != self.rule_version
                    or int(existing["expected_count"]) != len(request.transactions)
                ):
                    connection.rollback()
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
                        """
                        UPDATE preparation_jobs
                        SET request_fingerprint = ?, updated_at = ?
                        WHERE job_id = ?
                        """,
                        (
                            existing_fingerprint,
                            now,
                            existing["job_id"],
                        ),
                    )
                if existing_fingerprint != request_fingerprint:
                    connection.rollback()
                    raise IdempotencyConflictError(
                        "The source identity is already bound to a different "
                        "transaction/source fingerprint."
                    )
                connection.commit()
                return self.get_job(str(existing["job_id"]))

            prior_jobs = connection.execute(
                """
                SELECT job_id, preparation_generation, rule_version
                FROM preparation_jobs
                WHERE source_job_id = ? AND source_file_hash = ?
                ORDER BY preparation_generation, created_at, job_id
                """,
                (request.source_job_id, request.source_file_hash),
            ).fetchall()
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
                """
                INSERT INTO preparation_jobs (
                    job_id, source_job_id, source_file_hash, source_reference,
                    correlation_id, idempotency_key, state, expected_count,
                    request_fingerprint, preparation_generation, rule_version,
                    service_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    request.source_job_id,
                    request.source_file_hash,
                    request.source_reference,
                    correlation_id,
                    idempotency_key,
                    FileState.REGISTERED.value,
                    len(request.transactions),
                    request_fingerprint,
                    preparation_generation,
                    self.rule_version,
                    self.service_version,
                    now,
                    now,
                ),
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
                    """
                    INSERT INTO preparation_transactions (
                        job_id, transaction_id, ordinal, state, source_json,
                        source_hash, extraction_version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        transaction.transaction_id,
                        transaction.ordinal,
                        initial_state.value,
                        _json(transaction),
                        transaction.source_hash,
                        transaction.extraction_version,
                        now,
                        now,
                    ),
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
            connection.commit()
        return self.get_job(job_id)

    def _insert_event(
        self,
        connection: sqlite3.Connection,
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
            """
            INSERT INTO preparation_events (
                job_id, transaction_id, event_type, from_state, to_state,
                payload_json, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                transaction_id,
                event_type,
                from_state,
                to_state,
                _json(payload),
                occurred_at,
            ),
        )

    def append_event(
        self,
        job_id: str,
        event_type: str,
        payload: Any,
        transaction_id: str | None = None,
    ) -> None:
        with self._write_lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._insert_event(
                connection,
                job_id=job_id,
                transaction_id=transaction_id,
                event_type=event_type,
                payload=payload,
                occurred_at=_utc_now(),
            )
            connection.commit()

    def transition_file(
        self,
        job_id: str,
        target: FileState | str,
        *,
        event_type: str = "file_state_changed",
        payload: Any = None,
    ) -> bool:
        target_state = FileState(target)
        with self._write_lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state FROM preparation_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if not row:
                connection.rollback()
                raise KeyError(f"Preparation job {job_id} was not found.")
            current = FileState(row["state"])
            if not validate_file_transition(current, target_state):
                connection.commit()
                return False
            now = _utc_now()
            connection.execute(
                """
                UPDATE preparation_jobs
                SET state = ?, updated_at = ?,
                    started_at = CASE
                        WHEN ? = 'running' THEN COALESCE(started_at, ?)
                        ELSE started_at
                    END,
                    completed_at = CASE
                        WHEN ? = 'complete' THEN ?
                        ELSE completed_at
                    END
                WHERE job_id = ?
                """,
                (
                    target_state.value,
                    now,
                    target_state.value,
                    now,
                    target_state.value,
                    now,
                    job_id,
                ),
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
            connection.commit()
            return True

    def _transition_transaction_in_connection(
        self,
        connection: sqlite3.Connection,
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
        row = connection.execute(
            """
            SELECT state, attempt_count, retry_eligible
            FROM preparation_transactions
            WHERE job_id = ? AND transaction_id = ?
            """,
            (job_id, transaction_id),
        ).fetchone()
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
        connection.execute(
            """
            UPDATE preparation_transactions
            SET state = ?,
                attempt_count = attempt_count + ?,
                retry_eligible = ?,
                result_json = COALESCE(?, result_json),
                error_json = ?,
                updated_at = ?,
                started_at = CASE
                    WHEN ? = 1 THEN ?
                    ELSE started_at
                END,
                completed_at = ?
            WHERE job_id = ? AND transaction_id = ?
            """,
            (
                target_state.value,
                1 if entering_attempt else 0,
                (
                    int(retry_eligible)
                    if retry_eligible is not None
                    else int(row["retry_eligible"])
                ),
                _json(result) if result is not None else None,
                _json(error) if error is not None else None,
                now,
                1 if entering_attempt else 0,
                now,
                completed_at,
                job_id,
                transaction_id,
            ),
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
        with self._write_lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
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
            connection.commit()
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
        """Persist one completed preparation with one durable SQLite commit.

        ERP/customer/open-AR reads happen before this call. The preparation
        worker has already been atomically claimed in RESOLVING_CUSTOMER by
        begin_run(). Recording the remaining analytical states and terminal
        checkpoint together preserves the append-only state/event history
        while avoiding three connection/transaction cycles per check on
        Windows.
        """

        target_state = TransactionState(terminal_state)
        if target_state not in {
            TransactionState.PREPARED_BALANCED,
            TransactionState.PREPARED_EXCEPTION,
        }:
            raise ValueError(
                "A completed preparation must end in a prepared terminal state."
            )

        with self._write_lock, closing(self._connect()) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
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
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def _refresh_counts(
        self,
        connection: sqlite3.Connection,
        job_id: str,
    ) -> None:
        counts = connection.execute(
            """
            SELECT
                COUNT(*) AS expected_count,
                SUM(CASE WHEN state IN (?, ?, ?) THEN 1 ELSE 0 END)
                    AS terminal_count,
                SUM(CASE WHEN state = ? THEN 1 ELSE 0 END)
                    AS balanced_count,
                SUM(CASE WHEN state = ? THEN 1 ELSE 0 END)
                    AS exception_count,
                SUM(CASE WHEN state = ? THEN 1 ELSE 0 END)
                    AS preserved_count
            FROM preparation_transactions
            WHERE job_id = ?
            """,
            (
                TransactionState.PREPARED_BALANCED.value,
                TransactionState.PREPARED_EXCEPTION.value,
                TransactionState.PREEXISTING_HUMAN_DISPOSITION.value,
                TransactionState.PREPARED_BALANCED.value,
                TransactionState.PREPARED_EXCEPTION.value,
                TransactionState.PREEXISTING_HUMAN_DISPOSITION.value,
                job_id,
            ),
        ).fetchone()
        connection.execute(
            """
            UPDATE preparation_jobs
            SET terminal_count = ?, balanced_count = ?,
                exception_count = ?, preserved_count = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (
                int(counts["terminal_count"] or 0),
                int(counts["balanced_count"] or 0),
                int(counts["exception_count"] or 0),
                int(counts["preserved_count"] or 0),
                _utc_now(),
                job_id,
            ),
        )

    def begin_run(
        self,
        job_id: str,
        *,
        retry_exceptions: bool = False,
    ) -> list[SourceTransaction]:
        with self._write_lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute(
                "SELECT state FROM preparation_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if not job:
                connection.rollback()
                raise KeyError(f"Preparation job {job_id} was not found.")

            file_state = FileState(job["state"])
            if file_state is FileState.REGISTERED:
                validate_file_transition(file_state, FileState.QUEUED)
                connection.execute(
                    "UPDATE preparation_jobs SET state = ? WHERE job_id = ?",
                    (FileState.QUEUED.value, job_id),
                )
                file_state = FileState.QUEUED
            elif file_state is FileState.COMPLETE and retry_exceptions:
                validate_file_transition(file_state, FileState.QUEUED)
                connection.execute(
                    """
                    UPDATE preparation_jobs
                    SET state = ?, completed_at = NULL
                    WHERE job_id = ?
                    """,
                    (FileState.QUEUED.value, job_id),
                )
                file_state = FileState.QUEUED

            if retry_exceptions:
                rows = connection.execute(
                    """
                    SELECT transaction_id FROM preparation_transactions
                    WHERE job_id = ? AND state = ? AND retry_eligible = 1
                    ORDER BY ordinal
                    """,
                    (
                        job_id,
                        TransactionState.PREPARED_EXCEPTION.value,
                    ),
                ).fetchall()
                for row in rows:
                    self._transition_transaction_in_connection(
                        connection,
                        job_id,
                        row["transaction_id"],
                        TransactionState.RETRY_PENDING,
                        event_type="exception_retry_requested",
                    )

            retry_rows = connection.execute(
                """
                SELECT transaction_id FROM preparation_transactions
                WHERE job_id = ? AND state = ?
                ORDER BY ordinal
                """,
                (job_id, TransactionState.RETRY_PENDING.value),
            ).fetchall()
            for row in retry_rows:
                self._transition_transaction_in_connection(
                    connection,
                    job_id,
                    row["transaction_id"],
                    TransactionState.QUEUED,
                    event_type="retry_queued",
                )

            if file_state in {FileState.QUEUED, FileState.RECOVERING}:
                validate_file_transition(file_state, FileState.RUNNING)
                now = _utc_now()
                connection.execute(
                    """
                    UPDATE preparation_jobs
                    SET state = ?, started_at = COALESCE(started_at, ?),
                        updated_at = ?
                    WHERE job_id = ?
                    """,
                    (FileState.RUNNING.value, now, now, job_id),
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
                """
                SELECT transaction_id, source_json
                FROM preparation_transactions
                WHERE job_id = ? AND state = ?
                ORDER BY ordinal
                """,
                (job_id, TransactionState.QUEUED.value),
            ).fetchall()
            for row in rows:
                self._transition_transaction_in_connection(
                    connection,
                    job_id,
                    row["transaction_id"],
                    TransactionState.RESOLVING_CUSTOMER,
                    event_type="transaction_claimed",
                )
            connection.commit()
        return [
            self._source_transaction(_loads(row["source_json"], {}))
            for row in rows
        ]

    def finalize(self, job_id: str) -> dict[str, Any]:
        with self._write_lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._refresh_counts(connection, job_id)
            job = connection.execute(
                "SELECT * FROM preparation_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if not job:
                connection.rollback()
                raise KeyError(f"Preparation job {job_id} was not found.")
            if int(job["terminal_count"]) != int(job["expected_count"]):
                connection.rollback()
                raise FullCoverageError(
                    "A Lockbox preparation job cannot complete before every "
                    "source transaction has a terminal state."
                )
            current = FileState(job["state"])
            if current is not FileState.COMPLETE:
                validate_file_transition(current, FileState.COMPLETE)
                now = _utc_now()
                connection.execute(
                    """
                    UPDATE preparation_jobs
                    SET state = ?, completed_at = ?, updated_at = ?
                    WHERE job_id = ?
                    """,
                    (FileState.COMPLETE.value, now, now, job_id),
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
            connection.commit()
        return self.get_job(job_id)

    def recover_incomplete(self) -> list[str]:
        recovered: list[str] = []
        with self._write_lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            jobs = connection.execute(
                """
                SELECT job_id, state FROM preparation_jobs
                WHERE state IN (?, ?, ?, ?)
                """,
                (
                    FileState.REGISTERED.value,
                    FileState.QUEUED.value,
                    FileState.RUNNING.value,
                    FileState.RECOVERING.value,
                ),
            ).fetchall()
            now = _utc_now()
            for job in jobs:
                job_id = str(job["job_id"])
                current = FileState(job["state"])
                if current is FileState.REGISTERED:
                    validate_file_transition(current, FileState.QUEUED)
                    connection.execute(
                        """
                        UPDATE preparation_jobs
                        SET state = ?, updated_at = ?
                        WHERE job_id = ?
                        """,
                        (FileState.QUEUED.value, now, job_id),
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
                        """
                        UPDATE preparation_jobs
                        SET state = ?, updated_at = ?
                        WHERE job_id = ?
                        """,
                        (FileState.RECOVERING.value, now, job_id),
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
                    """
                    SELECT transaction_id, state
                    FROM preparation_transactions
                    WHERE job_id = ?
                    ORDER BY ordinal
                    """,
                    (job_id,),
                ).fetchall()
                for row in rows:
                    state = TransactionState(row["state"])
                    if state in ACTIVE_TRANSACTION_STATES:
                        self._transition_transaction_in_connection(
                            connection,
                            job_id,
                            row["transaction_id"],
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
            connection.commit()
        return recovered

    def get_job(self, job_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            job = connection.execute(
                "SELECT * FROM preparation_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if not job:
                raise KeyError(f"Preparation job {job_id} was not found.")
            transactions = connection.execute(
                """
                SELECT * FROM preparation_transactions
                WHERE job_id = ? ORDER BY ordinal
                """,
                (job_id,),
            ).fetchall()
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
            for row in transactions
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

    def get_current_job(
        self,
        source_job_id: str,
        source_file_hash: str,
    ) -> dict[str, Any]:
        """Return the current-rule generation without creating work."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT job_id FROM preparation_jobs
                WHERE source_job_id = ?
                  AND source_file_hash = ?
                  AND rule_version = ?
                ORDER BY preparation_generation DESC, created_at DESC
                LIMIT 1
                """,
                (
                    source_job_id,
                    source_file_hash.strip().lower(),
                    self.rule_version,
                ),
            ).fetchone()
        if not row:
            raise KeyError(
                "No governed preparation exists for the current source "
                "hash and rule version."
            )
        return self.get_job(str(row["job_id"]))

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

        parameters: list[Any] = [
            source_job_id,
            source_file_hash.strip().lower(),
            rule_version.strip(),
        ]
        service_clause = ""
        if service_version is not None:
            service_clause = " AND service_version = ?"
            parameters.append(service_version.strip())
        with closing(self._connect()) as connection:
            row = connection.execute(
                f"""
                SELECT job_id FROM preparation_jobs
                WHERE source_job_id = ?
                  AND source_file_hash = ?
                  AND rule_version = ?
                  {service_clause}
                ORDER BY preparation_generation DESC, created_at DESC
                LIMIT 1
                """,
                parameters,
            ).fetchone()
        if not row:
            raise KeyError(
                "No preparation exists for the exact source, rule, and "
                "service identity."
            )
        return self.get_job(str(row["job_id"]))

    def get_transaction(
        self,
        job_id: str,
        transaction_id: str,
    ) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT * FROM preparation_transactions
                WHERE job_id = ? AND transaction_id = ?
                """,
                (job_id, transaction_id),
            ).fetchone()
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
        with closing(self._connect()) as connection:
            exists = connection.execute(
                "SELECT 1 FROM preparation_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if not exists:
                raise KeyError(f"Preparation job {job_id} was not found.")
            rows = connection.execute(
                """
                SELECT * FROM preparation_events
                WHERE job_id = ? ORDER BY event_id
                """,
                (job_id,),
            ).fetchall()
        return [
            {
                **dict(row),
                "payload": _loads(row["payload_json"], {}),
            }
            for row in rows
        ]

    def list_incomplete_jobs(self) -> list[str]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT job_id FROM preparation_jobs
                WHERE state <> ? ORDER BY created_at
                """,
                (FileState.COMPLETE.value,),
            ).fetchall()
        return [str(row["job_id"]) for row in rows]

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
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT state, COUNT(*) AS count
                FROM preparation_transactions
                WHERE job_id = ?
                GROUP BY state
                """,
                (job_id,),
            ).fetchall()
        return {str(row["state"]): int(row["count"]) for row in rows}

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
