from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from data.database import get_connection


ACTIVE_STATUSES = ("queued", "running")
TERMINAL_STATUSES = ("completed", "failed")
ALL_STATUSES = ACTIVE_STATUSES + TERMINAL_STATUSES

INTERRUPTED_MESSAGE = "Interrupted by backend restart."


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobQueueRepository:
    """Local ETOP-owned tracking for background jobs started by any module.

    Not append-only: a job's row is mutated in place as it moves through
    queued -> running -> completed/failed, the same way
    `cash_flow_ap_due_date_cache` is a plain mutable cache rather than an
    evidence ledger. `job_id` is always caller-supplied (the producing
    module's own job id), so `enqueue` is an upsert rather than a strict
    insert - resuming an already-known job resets its row instead of
    failing on a duplicate key.
    """

    def __init__(
        self,
        connection_factory: Callable[[], sqlite3.Connection] = get_connection,
    ) -> None:
        self._connection_factory = connection_factory
        self._initialization_lock = threading.Lock()

    def _connection(self) -> sqlite3.Connection:
        connection = self._connection_factory()
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._initialization_lock:
            connection = self._connection()
            try:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS job_queue_jobs (
                        job_id TEXT PRIMARY KEY,
                        job_type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        status TEXT NOT NULL
                            CHECK (status IN ('queued', 'running', 'completed', 'failed')),
                        created_by TEXT,
                        created_at TEXT NOT NULL,
                        started_at TEXT,
                        completed_at TEXT,
                        message TEXT,
                        result_module TEXT,
                        result_reference TEXT,
                        acknowledged_at TEXT
                    );

                    CREATE INDEX IF NOT EXISTS idx_job_queue_jobs_status
                    ON job_queue_jobs(status, created_at DESC);

                    CREATE INDEX IF NOT EXISTS idx_job_queue_jobs_created_at
                    ON job_queue_jobs(created_at DESC);
                    """
                )
                connection.commit()
            finally:
                connection.close()

    def enqueue(
        self,
        job_id: str,
        job_type: str,
        title: str,
        *,
        created_by: str | None = None,
    ) -> None:
        self.initialize()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                INSERT INTO job_queue_jobs (
                    job_id, job_type, title, status, created_by,
                    created_at, started_at, completed_at, message,
                    result_module, result_reference, acknowledged_at
                ) VALUES (?, ?, ?, 'queued', ?, ?, NULL, NULL, NULL, NULL, NULL, NULL)
                ON CONFLICT(job_id) DO UPDATE SET
                    job_type = excluded.job_type,
                    title = excluded.title,
                    status = 'queued',
                    created_by = excluded.created_by,
                    started_at = NULL,
                    completed_at = NULL,
                    message = NULL,
                    result_module = NULL,
                    result_reference = NULL,
                    acknowledged_at = NULL;
                """,
                (job_id, job_type, title, created_by, _now()),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def mark_running(self, job_id: str) -> None:
        self.initialize()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                UPDATE job_queue_jobs
                SET status = 'running', started_at = ?
                WHERE job_id = ? AND status = 'queued';
                """,
                (_now(), job_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def mark_completed(
        self,
        job_id: str,
        *,
        message: str | None = None,
        result_module: str | None = None,
        result_reference: str | None = None,
    ) -> None:
        self._mark_terminal(
            job_id,
            status="completed",
            message=message,
            result_module=result_module,
            result_reference=result_reference,
        )

    def mark_failed(
        self,
        job_id: str,
        *,
        message: str | None = None,
    ) -> None:
        self._mark_terminal(job_id, status="failed", message=message)

    def _mark_terminal(
        self,
        job_id: str,
        *,
        status: str,
        message: str | None,
        result_module: str | None = None,
        result_reference: str | None = None,
    ) -> None:
        self.initialize()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                UPDATE job_queue_jobs
                SET status = ?, completed_at = ?, message = ?,
                    result_module = ?, result_reference = ?
                WHERE job_id = ? AND status IN ('queued', 'running');
                """,
                (
                    status,
                    _now(),
                    message,
                    result_module,
                    result_reference,
                    job_id,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def acknowledge(self, job_id: str) -> None:
        self.initialize()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                UPDATE job_queue_jobs
                SET acknowledged_at = ?
                WHERE job_id = ? AND acknowledged_at IS NULL;
                """,
                (_now(), job_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_jobs(
        self,
        *,
        limit: int = 50,
        statuses: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            if statuses:
                placeholders = ", ".join("?" for _ in statuses)
                rows = connection.execute(
                    f"""
                    SELECT * FROM job_queue_jobs
                    WHERE status IN ({placeholders})
                    ORDER BY created_at DESC
                    LIMIT ?;
                    """,
                    (*statuses, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM job_queue_jobs
                    ORDER BY created_at DESC
                    LIMIT ?;
                    """,
                    (limit,),
                ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def counts_by_status(self) -> dict[str, int]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM job_queue_jobs
                WHERE status IN ('queued', 'running')
                GROUP BY status;
                """
            ).fetchall()
        finally:
            connection.close()
        return {row["status"]: row["count"] for row in rows}

    def unacknowledged_terminal_jobs(
        self,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT * FROM job_queue_jobs
                WHERE status IN ('completed', 'failed')
                    AND acknowledged_at IS NULL
                ORDER BY completed_at DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def unacknowledged_count(self) -> int:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count FROM job_queue_jobs
                WHERE status IN ('completed', 'failed')
                    AND acknowledged_at IS NULL;
                """
            ).fetchone()
        finally:
            connection.close()
        return int(row["count"]) if row is not None else 0

    def recover_interrupted(self) -> list[str]:
        """Fail-closed startup recovery: a row still queued/running when the
        process starts could not have survived the restart (no in-memory
        executor from a prior process can still be running it), so it is
        marked failed rather than silently left queued forever or
        auto-replayed - matching `automations`' restart recovery."""

        self.initialize()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            rows = connection.execute(
                """
                SELECT job_id FROM job_queue_jobs
                WHERE status IN ('queued', 'running');
                """
            ).fetchall()
            job_ids = [row["job_id"] for row in rows]
            if job_ids:
                placeholders = ", ".join("?" for _ in job_ids)
                connection.execute(
                    f"""
                    UPDATE job_queue_jobs
                    SET status = 'failed', completed_at = ?, message = ?
                    WHERE job_id IN ({placeholders});
                    """,
                    (_now(), INTERRUPTED_MESSAGE, *job_ids),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return job_ids


job_queue_repository = JobQueueRepository()


def initialize_job_queue_database() -> None:
    """Startup migration hook for the shared SQLite initialization boundary."""

    job_queue_repository.initialize()
