from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from data.mysql import get_engine, job_queue_jobs_table, metadata


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

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialization_lock = threading.Lock()

    def initialize(self) -> None:
        with self._initialization_lock:
            metadata.create_all(self._engine, checkfirst=True, tables=[job_queue_jobs_table])

    def enqueue(
        self,
        job_id: str,
        job_type: str,
        title: str,
        *,
        created_by: str | None = None,
    ) -> None:
        self.initialize()
        now = _now()
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(job_queue_jobs_table.c.job_id).where(
                    job_queue_jobs_table.c.job_id == job_id
                )
            ).first()
            values = {
                "job_type": job_type,
                "title": title,
                "status": "queued",
                "created_by": created_by,
                "started_at": None,
                "completed_at": None,
                "message": None,
                "result_module": None,
                "result_reference": None,
                "acknowledged_at": None,
            }
            if existing is None:
                connection.execute(
                    job_queue_jobs_table.insert().values(
                        job_id=job_id, created_at=now, **values
                    )
                )
            else:
                connection.execute(
                    job_queue_jobs_table.update()
                    .where(job_queue_jobs_table.c.job_id == job_id)
                    .values(**values)
                )

    def mark_running(self, job_id: str) -> None:
        self.initialize()
        with self._engine.begin() as connection:
            connection.execute(
                job_queue_jobs_table.update()
                .where(
                    job_queue_jobs_table.c.job_id == job_id,
                    job_queue_jobs_table.c.status == "queued",
                )
                .values(status="running", started_at=_now())
            )

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
        with self._engine.begin() as connection:
            connection.execute(
                job_queue_jobs_table.update()
                .where(
                    job_queue_jobs_table.c.job_id == job_id,
                    job_queue_jobs_table.c.status.in_(("queued", "running")),
                )
                .values(
                    status=status,
                    completed_at=_now(),
                    message=message,
                    result_module=result_module,
                    result_reference=result_reference,
                )
            )

    def acknowledge(self, job_id: str) -> None:
        self.initialize()
        with self._engine.begin() as connection:
            connection.execute(
                job_queue_jobs_table.update()
                .where(
                    job_queue_jobs_table.c.job_id == job_id,
                    job_queue_jobs_table.c.acknowledged_at.is_(None),
                )
                .values(acknowledged_at=_now())
            )

    def list_jobs(
        self,
        *,
        limit: int = 50,
        statuses: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        self.initialize()
        with self._engine.connect() as connection:
            query = select(job_queue_jobs_table)
            if statuses:
                query = query.where(job_queue_jobs_table.c.status.in_(statuses))
            rows = connection.execute(
                query.order_by(job_queue_jobs_table.c.created_at.desc()).limit(limit)
            ).mappings().all()
        return [dict(row) for row in rows]

    def counts_by_status(self) -> dict[str, int]:
        self.initialize()
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    job_queue_jobs_table.c.status, func.count().label("count")
                )
                .where(job_queue_jobs_table.c.status.in_(("queued", "running")))
                .group_by(job_queue_jobs_table.c.status)
            ).all()
        return {row.status: row.count for row in rows}

    def unacknowledged_terminal_jobs(
        self,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        self.initialize()
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(job_queue_jobs_table)
                .where(
                    job_queue_jobs_table.c.status.in_(("completed", "failed")),
                    job_queue_jobs_table.c.acknowledged_at.is_(None),
                )
                .order_by(job_queue_jobs_table.c.completed_at.desc())
                .limit(limit)
            ).mappings().all()
        return [dict(row) for row in rows]

    def unacknowledged_count(self) -> int:
        self.initialize()
        with self._engine.connect() as connection:
            count = connection.execute(
                select(func.count())
                .select_from(job_queue_jobs_table)
                .where(
                    job_queue_jobs_table.c.status.in_(("completed", "failed")),
                    job_queue_jobs_table.c.acknowledged_at.is_(None),
                )
            ).scalar_one()
        return int(count)

    def recover_interrupted(self) -> list[str]:
        """Fail-closed startup recovery: a row still queued/running when the
        process starts could not have survived the restart (no in-memory
        executor from a prior process can still be running it), so it is
        marked failed rather than silently left queued forever or
        auto-replayed - matching `automations`' restart recovery."""

        self.initialize()
        with self._engine.begin() as connection:
            rows = connection.execute(
                select(job_queue_jobs_table.c.job_id).where(
                    job_queue_jobs_table.c.status.in_(("queued", "running"))
                )
            ).all()
            job_ids = [row.job_id for row in rows]
            if job_ids:
                connection.execute(
                    job_queue_jobs_table.update()
                    .where(job_queue_jobs_table.c.job_id.in_(job_ids))
                    .values(
                        status="failed",
                        completed_at=_now(),
                        message=INTERRUPTED_MESSAGE,
                    )
                )
        return job_ids


job_queue_repository = JobQueueRepository()


def initialize_job_queue_database() -> None:
    """Startup migration hook for the shared SQLite initialization boundary."""

    job_queue_repository.initialize()
