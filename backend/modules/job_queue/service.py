from __future__ import annotations

from typing import Any

from .repository import JobQueueRepository, job_queue_repository


class JobQueueService:
    """Thin seam any module can report background-job progress through."""

    def __init__(
        self,
        repository: JobQueueRepository = job_queue_repository,
    ) -> None:
        self._repository = repository

    def recover_interrupted(self) -> list[str]:
        return self._repository.recover_interrupted()

    def enqueue(
        self,
        job_id: str,
        job_type: str,
        title: str,
        *,
        created_by: str | None = None,
    ) -> None:
        self._repository.enqueue(
            job_id,
            job_type,
            title,
            created_by=created_by,
        )

    def mark_running(self, job_id: str) -> None:
        self._repository.mark_running(job_id)

    def mark_completed(
        self,
        job_id: str,
        *,
        message: str | None = None,
        result_module: str | None = None,
        result_reference: str | None = None,
    ) -> None:
        self._repository.mark_completed(
            job_id,
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
        self._repository.mark_failed(job_id, message=message)

    def acknowledge(self, job_id: str) -> None:
        self._repository.acknowledge(job_id)

    def list_jobs(
        self,
        *,
        limit: int = 50,
        statuses: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        return self._repository.list_jobs(limit=limit, statuses=statuses)

    def summary(self, *, recent_limit: int = 10) -> dict[str, Any]:
        counts = self._repository.counts_by_status()
        return {
            "queued_count": counts.get("queued", 0),
            "running_count": counts.get("running", 0),
            "unacknowledged_count": self._repository.unacknowledged_count(),
            "recent": self._repository.unacknowledged_terminal_jobs(
                limit=recent_limit,
            ),
        }


job_queue_service = JobQueueService()
