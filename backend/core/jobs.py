"""Platform-Core job-queue contract.

Business modules that report background-job progress depend on this
module, not on `modules.job_queue` directly - `job_queue` owns the actual
tracking implementation, but other modules should couple to Platform
Core, not to a sibling module's internals (Module Rule 2, see
`core/auth.py`).
"""

from __future__ import annotations

from modules.job_queue.service import job_queue_service

__all__ = [
    "enqueue",
    "mark_running",
    "mark_completed",
    "mark_failed",
]


def enqueue(
    job_id: str,
    job_type: str,
    title: str,
    *,
    created_by: str | None = None,
) -> None:
    job_queue_service.enqueue(
        job_id,
        job_type,
        title,
        created_by=created_by,
    )


def mark_running(job_id: str) -> None:
    job_queue_service.mark_running(job_id)


def mark_completed(
    job_id: str,
    *,
    message: str | None = None,
    result_module: str | None = None,
    result_reference: str | None = None,
) -> None:
    job_queue_service.mark_completed(
        job_id,
        message=message,
        result_module=result_module,
        result_reference=result_reference,
    )


def mark_failed(job_id: str, *, message: str | None = None) -> None:
    job_queue_service.mark_failed(job_id, message=message)
