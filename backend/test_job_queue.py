from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from modules.job_queue.repository import JobQueueRepository
from modules.job_queue.service import JobQueueService


class JobQueueRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.database_path = str(
            Path(self.temp_directory.name) / "job_queue.db"
        )
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        self.addCleanup(self.engine.dispose)
        self.repository = JobQueueRepository(engine=self.engine)

    def test_enqueue_starts_a_job_as_queued(self) -> None:
        self.repository.enqueue("job-1", "lockbox_preparation", "Lockbox batch A")

        jobs = self.repository.list_jobs()

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_id"], "job-1")
        self.assertEqual(jobs[0]["status"], "queued")
        self.assertIsNone(jobs[0]["started_at"])
        self.assertIsNone(jobs[0]["completed_at"])

    def test_mark_running_then_completed_moves_through_lifecycle(self) -> None:
        self.repository.enqueue("job-1", "lockbox_preparation", "Lockbox batch A")

        self.repository.mark_running("job-1")
        running = self.repository.list_jobs()[0]
        self.assertEqual(running["status"], "running")
        self.assertIsNotNone(running["started_at"])

        self.repository.mark_completed(
            "job-1",
            message="39 balanced, 19 need review",
            result_module="Document Intelligence",
            result_reference="job-1",
        )
        completed = self.repository.list_jobs()[0]
        self.assertEqual(completed["status"], "completed")
        self.assertIsNotNone(completed["completed_at"])
        self.assertEqual(completed["message"], "39 balanced, 19 need review")
        self.assertEqual(completed["result_module"], "Document Intelligence")

    def test_mark_failed_records_message(self) -> None:
        self.repository.enqueue("job-1", "lockbox_preparation", "Lockbox batch A")
        self.repository.mark_running("job-1")

        self.repository.mark_failed("job-1", message="boom")

        job = self.repository.list_jobs()[0]
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["message"], "boom")

    def test_reenqueue_an_existing_job_id_resets_it_to_queued(self) -> None:
        self.repository.enqueue("job-1", "lockbox_preparation", "Lockbox batch A")
        self.repository.mark_running("job-1")
        self.repository.mark_completed("job-1", message="done")

        self.repository.enqueue("job-1", "lockbox_preparation", "Lockbox batch A retry")

        job = self.repository.list_jobs()[0]
        self.assertEqual(job["status"], "queued")
        self.assertIsNone(job["completed_at"])
        self.assertIsNone(job["message"])
        self.assertEqual(job["title"], "Lockbox batch A retry")

    def test_acknowledge_is_idempotent_and_only_applies_once(self) -> None:
        self.repository.enqueue("job-1", "lockbox_preparation", "Lockbox batch A")
        self.repository.mark_completed("job-1", message="done")

        self.repository.acknowledge("job-1")
        first_ack = self.repository.list_jobs()[0]["acknowledged_at"]
        self.assertIsNotNone(first_ack)

        self.repository.acknowledge("job-1")
        second_ack = self.repository.list_jobs()[0]["acknowledged_at"]
        self.assertEqual(first_ack, second_ack)

    def test_unacknowledged_terminal_jobs_excludes_active_and_acknowledged(
        self,
    ) -> None:
        self.repository.enqueue("job-active", "lockbox_preparation", "Active")
        self.repository.enqueue("job-done", "lockbox_preparation", "Done")
        self.repository.mark_completed("job-done", message="done")
        self.repository.enqueue("job-acked", "lockbox_preparation", "Acked")
        self.repository.mark_completed("job-acked", message="done")
        self.repository.acknowledge("job-acked")

        unacknowledged = self.repository.unacknowledged_terminal_jobs()

        self.assertEqual(
            {job["job_id"] for job in unacknowledged},
            {"job-done"},
        )
        self.assertEqual(self.repository.unacknowledged_count(), 1)

    def test_counts_by_status_only_reflects_active_jobs(self) -> None:
        self.repository.enqueue("job-queued", "lockbox_preparation", "Queued")
        self.repository.enqueue("job-running", "lockbox_preparation", "Running")
        self.repository.mark_running("job-running")
        self.repository.enqueue("job-done", "lockbox_preparation", "Done")
        self.repository.mark_completed("job-done", message="done")

        counts = self.repository.counts_by_status()

        self.assertEqual(counts, {"queued": 1, "running": 1})

    def test_recover_interrupted_fails_closed_without_replay(self) -> None:
        self.repository.enqueue("job-stuck-queued", "lockbox_preparation", "Stuck")
        self.repository.enqueue("job-stuck-running", "lockbox_preparation", "Stuck2")
        self.repository.mark_running("job-stuck-running")
        self.repository.enqueue("job-done", "lockbox_preparation", "Done")
        self.repository.mark_completed("job-done", message="done")

        recovered_ids = self.repository.recover_interrupted()

        self.assertEqual(
            set(recovered_ids),
            {"job-stuck-queued", "job-stuck-running"},
        )
        jobs_by_id = {job["job_id"]: job for job in self.repository.list_jobs()}
        self.assertEqual(jobs_by_id["job-stuck-queued"]["status"], "failed")
        self.assertEqual(jobs_by_id["job-stuck-running"]["status"], "failed")
        self.assertIn(
            "Interrupted by backend restart.",
            jobs_by_id["job-stuck-queued"]["message"],
        )
        self.assertEqual(jobs_by_id["job-done"]["status"], "completed")

    def test_list_jobs_filters_by_status(self) -> None:
        self.repository.enqueue("job-queued", "lockbox_preparation", "Queued")
        self.repository.enqueue("job-done", "lockbox_preparation", "Done")
        self.repository.mark_completed("job-done", message="done")

        queued_only = self.repository.list_jobs(statuses=("queued",))

        self.assertEqual([job["job_id"] for job in queued_only], ["job-queued"])


class JobQueueServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.database_path = str(
            Path(self.temp_directory.name) / "job_queue.db"
        )
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        self.addCleanup(self.engine.dispose)
        repository = JobQueueRepository(engine=self.engine)
        self.service = JobQueueService(repository)

    def test_summary_reports_active_counts_and_recent_unacknowledged(self) -> None:
        self.service.enqueue("job-running", "lockbox_preparation", "Running")
        self.service.mark_running("job-running")
        self.service.enqueue("job-done", "lockbox_preparation", "Done")
        self.service.mark_completed(
            "job-done",
            message="39 balanced, 19 need review",
            result_module="Document Intelligence",
            result_reference="job-done",
        )

        summary = self.service.summary()

        self.assertEqual(summary["running_count"], 1)
        self.assertEqual(summary["queued_count"], 0)
        self.assertEqual(summary["unacknowledged_count"], 1)
        self.assertEqual(len(summary["recent"]), 1)
        self.assertEqual(summary["recent"][0]["job_id"], "job-done")

    def test_acknowledge_removes_job_from_summary(self) -> None:
        self.service.enqueue("job-done", "lockbox_preparation", "Done")
        self.service.mark_completed("job-done", message="done")

        self.service.acknowledge("job-done")

        summary = self.service.summary()
        self.assertEqual(summary["unacknowledged_count"], 0)
        self.assertEqual(summary["recent"], [])


if __name__ == "__main__":
    unittest.main()
